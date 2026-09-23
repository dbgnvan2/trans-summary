"""
Review of differences between a raw transcript and its formatted version.

Every difference that is not a stutter or a transcription-artifact tag must be
decided by a person before the transcript passes validation:

  accept  keep the formatted wording (recorded as an approval)
  reject  restore the raw wording in the formatted transcript
  edit    replace the formatted wording with text the reviewer types
          (recorded as an approved human edit)

Optionally, an accepted or edited change can be saved as a fix in the
project's pattern set, so it is applied to the raw text of future transcripts
in that group before formatting.

Decisions are stored in the project's `` - format-review.json``: the approved
difference keys (valid only for the raw text they were made against) and a
dated log of every decision.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Optional

import config
import formatting_pipeline as fp
import pattern_sets
from transcript_utils import strip_yaml_frontmatter

ACTIONS = ("accept", "reject", "edit")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def review_path(stem: str) -> Path:
    return config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_FORMAT_REVIEW}"


def formatted_path(stem: str) -> Path:
    return config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_FORMATTED}"


def _load_review(stem: str) -> dict:
    try:
        return json.loads(review_path(stem).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_approvals(stem: str, raw_text: str) -> set:
    """Approved difference keys, only if they were made against this raw text
    (keys encode raw word positions, so they mean nothing for another raw)."""
    data = _load_review(stem)
    if data.get("raw_sha256") != _sha(raw_text):
        return set()
    return set(data.get("approvals", []))


def review_counts(stem: str) -> dict:
    """Counts of accepted / edited / rejected decisions (for the YAML note)."""
    counts = {"accept": 0, "edit": 0, "reject": 0}
    for entry in _load_review(stem).get("log", []):
        if entry.get("action") in counts:
            counts[entry["action"]] += 1
    return counts


def project_raw(stem: str) -> Optional[str]:
    """The raw text the project's formatted transcript is compared with: the
    raw-source copy saved at format validation (the text the formatter saw)."""
    path = fp.raw_source_copy_path(stem)
    return path.read_text(encoding="utf-8") if path.exists() else None


def pending_items(stem: str, raw_text: Optional[str] = None) -> list:
    """Differences that still need a decision."""
    raw_text = raw_text if raw_text is not None else project_raw(stem)
    if raw_text is None:
        raise FileNotFoundError(f"no raw source for {stem}; run format validation first")
    formatted = strip_yaml_frontmatter(formatted_path(stem).read_text(encoding="utf-8"))
    outcome = fp.verify_source_fidelity(raw_text, formatted, approvals=load_approvals(stem, raw_text))
    return outcome["unresolved"]


def apply_decisions(stem: str, decisions: list, raw_text: Optional[str] = None,
                    reviewer: str = "") -> dict:
    """Apply review decisions to a project.

    ``decisions``: list of dicts with ``key`` (from the item), ``action``
    (accept / reject / edit), optional ``edit_text`` (for edit) and optional
    ``save_pattern`` (bool; accept or edit only).

    Returns {"changed_text": bool, "errors": [...], "patterns_saved": [...]}.
    Reject/edit rewrite the formatted transcript (any YAML transcript must then
    be regenerated). Items whose span covers a heading or speaker label are
    refused and reported, so the file structure is never damaged.
    """
    raw_text = raw_text if raw_text is not None else project_raw(stem)
    if raw_text is None:
        raise FileNotFoundError(f"no raw source for {stem}; run format validation first")
    path = formatted_path(stem)
    original = path.read_text(encoding="utf-8")
    if strip_yaml_frontmatter(original) != original:
        raise ValueError("formatted transcript unexpectedly contains YAML front matter")

    _, items = fp.difference_items(raw_text, original)
    by_key = {item["key"]: item for item in items}
    data = _load_review(stem)
    approvals = set(data.get("approvals", [])) if data.get("raw_sha256") == _sha(raw_text) else set()
    log = data.get("log", [])
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    errors, edits, patterns_saved = [], [], []

    pattern_record = pattern_sets.load_project_record(stem) or {}
    pattern_name = pattern_record.get("name")

    for decision in decisions:
        key, action = decision.get("key"), decision.get("action")
        item = by_key.get(key)
        if item is None:
            errors.append(f"unknown or already-resolved difference: {key}")
            continue
        if action not in ACTIONS:
            errors.append(f"invalid action {action!r} for {key}")
            continue
        start, end = item["span"]
        if action == "accept":
            approvals.add(key)
            final_text = item["formatted_text"]
        else:
            new_text = item["raw_text"] if action == "reject" else (decision.get("edit_text") or "").strip()
            if start != end and not fp.span_is_plain_text(original, start, end):
                errors.append(f"cannot {action} {key}: it spans a heading or speaker label; edit the file by hand")
                continue
            edits.append((start, end, new_text, action))
            final_text = new_text
        if decision.get("save_pattern") and action in ("accept", "edit"):
            if not pattern_name:
                errors.append("no pattern set assigned to this project; pattern not saved")
            elif not item["raw_text"] or not final_text:
                errors.append(f"cannot save a pattern for a deletion or insertion ({key})")
            else:
                try:
                    if pattern_sets.add_fix(pattern_name, item["raw_text"], final_text, source=stem):
                        patterns_saved.append(f"{item['raw_text']} = {final_text}")
                except ValueError as exc:
                    errors.append(f"pattern not saved for {key}: {exc}")
        log.append({"at": now, "reviewer": reviewer, "key": key, "action": action,
                    "section": item["section"], "raw_text": item["raw_text"],
                    "formatted_text": item["formatted_text"],
                    "edit_text": decision.get("edit_text") if action == "edit" else None})

    # Build the new text left to right so the final position of every edit is
    # known (needed to approve human edits afterwards).
    pieces, cursor, edited_ranges = [], 0, []
    for start, end, new_text, action in sorted(edits, key=lambda e: e[0]):
        if start < cursor:
            errors.append("overlapping decisions skipped")
            continue
        if start == end:  # restore deleted words at an insertion point
            if not new_text:
                continue
            pieces.append(original[cursor:start])
            lead = " " if start > 0 and not original[start - 1].isspace() else ""
            trail = " " if start < len(original) and not original[start].isspace() else ""
            out_start = sum(len(p) for p in pieces) + len(lead)
            pieces.append(lead + new_text + trail)
            cursor = start
        elif new_text:
            pieces.append(original[cursor:start])
            out_start = sum(len(p) for p in pieces)
            pieces.append(new_text)
            cursor = end
        else:  # remove inserted words and one adjacent space
            if end < len(original) and original[end] == " ":
                end += 1
            elif start > cursor and original[start - 1] == " ":
                start -= 1
            pieces.append(original[cursor:start])
            cursor = end
            continue
        if action == "edit":
            edited_ranges.append((out_start, out_start + len(new_text)))
    pieces.append(original[cursor:])
    text = "".join(pieces)

    changed = text != original
    if changed:
        path.write_text(text, encoding="utf-8")
        # Human edits are approved: find the differences now covering them.
        _, new_items = fp.difference_items(raw_text, text)
        for item in new_items:
            s, e = item["span"]
            if any(lo <= s and e <= hi for lo, hi in edited_ranges):
                approvals.add(item["key"])
        # Approvals of untouched items keep their keys (raw positions unchanged).

    record = {
        "raw_sha256": _sha(raw_text),
        "formatted_sha256": _sha(text),
        "approvals": sorted(approvals),
        "log": log,
        "updated_at": now,
    }
    review_path(stem).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"changed_text": changed, "errors": errors, "patterns_saved": patterns_saved}
