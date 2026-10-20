"""The removed-sentences record, and the list of this run's removals.

One JSON file per project (``config.SUFFIX_REMOVED_SENTENCES``) with one entry per
artifact: what the last generation of that artifact removed, the draft before the
removal, and the saved file's hash. The GUI and the CLI print the list at the end of
a run, so every removed sentence is seen and can be put back by hand.

Spec: docs/plan_remove_flagged_2026-10-19.md#RM3, #RM4
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import config
import flagged_removal as fr


def record_path(base_name: str) -> Path:
    return config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_REMOVED_SENTENCES}"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load(path: Path, logger=None) -> dict:
    """The record, or {} when there is none. An unreadable record is reported and
    replaced by the next write, so it cannot stop later removals from being recorded."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        (logger or logging.getLogger(__name__)).warning(
            "The removed-sentences record %s could not be read (%s); it will be replaced.",
            path, e)
        return {}
    return data if isinstance(data, dict) and isinstance(data.get("artifacts"), dict) else {}


def _save(path: Path, data: dict) -> None:
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def write_entry(base_name: str, artifact: str, suffix: str, *, draft_before: str,
                final_text: str, removed: list, kept: list, logger=None) -> Path:
    """Replace ``artifact``'s entry with this removal (``removed`` may be empty: the
    flags left in are still recorded). Raises OSError when the file cannot be
    written: the caller then removes nothing (RM3.b).

    Purpose: Keep every removed sentence with its context, so it can be put back.
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM3.a, #RM3.b
    Tests:   tests/test_remove_flagged_rm.py::test_rm3a_record_fields,
             tests/test_remove_flagged_rm.py::test_rm3b_record_write_fails_nothing_removed
    """
    path = record_path(base_name)
    data = _load(path, logger) or {"artifacts": {}}
    data["artifacts"][artifact] = {
        "file": f"{base_name}{suffix}",
        "removed_at": datetime.now().isoformat(),
        "sha256": _sha(final_text),
        "draft_before": draft_before,
        "removed": [{"sentence": r.sentence, "before": r.before, "after": r.after,
                     "reason": r.reason, "label": r.record.get("label", ""),
                     "rationale": r.record.get("rationale", ""),
                     "evidence": r.record.get("evidence", ""),
                     "in_front_matter": r.in_front_matter} for r in removed],
        "kept": [{"claim": str(k.claim), "reason": k.reason} for k in kept],
    }
    _save(path, data)
    return path


def clear_entry(base_name: str, artifact: str, logger=None) -> None:
    """Remove ``artifact``'s entry when the artifact is generated again, so an old
    removal is not listed for the new file (P8). A failure is logged, not raised: a
    stale entry's hash no longer matches the file, so it is not listed anyway.

    Spec:  docs/plan_remove_flagged_2026-10-19.md#RM3.c
    Tests: tests/test_remove_flagged_rm.py::test_rm3c_dirty_state_clean_regeneration_clears_entry
    """
    path = record_path(base_name)
    try:
        data = _load(path, logger)
        if artifact not in data.get("artifacts", {}):
            return
        del data["artifacts"][artifact]
        if data["artifacts"]:
            _save(path, data)
        else:
            path.unlink()
    except OSError as e:
        (logger or logging.getLogger(__name__)).warning(
            "Could not clear the %s entry of %s (%s).", artifact, path, e)


def _why(r: dict) -> str:
    if r.get("reason") != fr.FAITHFULNESS:
        return r.get("reason", "")
    detail = " — ".join(x for x in (r.get("label"), r.get("rationale")) if x)
    return f"judge: {detail}" if detail else "flagged by the faithfulness judge"


def format_run_removals(base_name: str, since: datetime, logger=None) -> str:
    """The list of sentences removed during the run that started at ``since``: per
    artifact each sentence, why, and the sentence now after it (where a "This …" may
    have lost its referent); then the flags not removed, also for an artifact where
    removal was refused; then the record's path. An entry whose file has changed since
    is not shown as current.

    Purpose: Show every removal at the end of the run (RM4).
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM4.a
    Tests:   tests/test_remove_flagged_rm.py::test_rm4a_lists_this_run_only,
             tests/test_remove_flagged_rm.py::test_rm4a_changed_file_not_shown,
             tests/test_remove_flagged_rm.py::test_rm4a_none_says_so
    """
    path = record_path(base_name)
    entries = []
    for artifact, e in _load(path, logger).get("artifacts", {}).items():
        try:
            if datetime.fromisoformat(e["removed_at"]) >= since:
                entries.append((artifact, e))
        except (KeyError, TypeError, ValueError):
            continue
    if not entries:
        return "Removed sentences: none this run."
    order = list(config.FAITHFULNESS_REMOVE_ARTIFACTS)
    entries.sort(key=lambda a: order.index(a[0]) if a[0] in order else len(order))
    total = sum(len(e.get("removed", [])) for _, e in entries)
    out = [f"--- Sentences removed this run ({total}) ---"]
    for artifact, e in entries:
        file = path.parent / e.get("file", "")
        try:
            current = file.is_file() and _sha(file.read_text(encoding="utf-8")) == e.get("sha256")
        except OSError:
            current = False
        if not current:
            out.append(f"{artifact.capitalize()}: the file has changed since the removal; "
                       "see the record.")
            continue
        n_removed = len(e.get("removed", []))
        out.append(f"{artifact.capitalize()} ({n_removed}):" if n_removed else
                   f"{artifact.capitalize()}: nothing removed.")
        for n, r in enumerate(e.get("removed", []), 1):
            out.append(f'  {n}. "{r.get("sentence", "")}"')
            out.append(f"     Why: {_why(r)}")
            if r.get("in_front_matter"):
                out.append("     Also removed from the front matter's FAQ answers.")
            if r.get("after"):
                out.append(f'     Now followed by: "{r["after"]}"')
        for k in e.get("kept", []):
            out.append(f'  Still flagged, not removed: "{k.get("claim", "")}" '
                       f'({k.get("reason", "")})')
    out.append(f"Record, with the sentence before each one and the draft before removal: {path}")
    out.append("To put a sentence back, edit the artifact by hand.")
    return "\n".join(out)


def print_run_removals(base_name: str, since: datetime, logger=None) -> None:
    """Print the run's list (``format_run_removals``) for a command-line script. The
    list is a report: a failure to read the record is printed, never raised.

    Purpose: One end-of-run list for every script that can remove sentences (P25).
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM4.c
    Tests:   tests/test_remove_flagged_rm.py::test_rm4c_cli_prints_list,
             tests/test_remove_flagged_rm.py::test_rm4c_overview_cli_prints_list
    """
    try:
        text = format_run_removals(base_name, since, logger)
    except Exception as e:  # noqa: BLE001
        text = f"⚠️ Could not read the removed-sentences record: {e}"
    print("\n" + text)

