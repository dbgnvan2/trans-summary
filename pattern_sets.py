"""
Named pattern files ("pattern sets") for groups of similar transcripts.

A pattern set is a plain-text file in the patterns folder, e.g.
``patterns/kerr_lectures.txt``:

    # approved terms
    Bowen
    differentiation of self
    # fixes (wrong = correct)
    # added 2026-09-23 from Where Roots Bowen Theory ...
    homostasis = homeostasis

Lines with ``=`` are fixes, other non-comment lines are approved terms (the same
format as the existing approved-terms file). Fixes are applied to the RAW
transcript before formatting, so the formatter's job stays verbatim; every
application is recorded in the project's `` - pattern-set.json``.

Each project records which set it used, the file's SHA-256 at that time and
the fixes actually applied, so a later edit to the set does not change what an
earlier project claims.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import config
from validation_learning import replace_alias_occurrences

DEFAULTS_FILENAME = "_presenter_defaults.json"
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,60}$")


@dataclass
class PatternSet:
    name: str
    terms: list = field(default_factory=list)
    fixes: list = field(default_factory=list)  # [(wrong, correct)]
    sha256: str = ""


def patterns_dir() -> Path:
    """Folder holding pattern-set files (config.PATTERNS_DIR if set, otherwise
    <transcripts base>/patterns)."""
    override = getattr(config, "PATTERNS_DIR", None)
    if override:
        return Path(override)
    return Path(config.settings.TRANSCRIPTS_BASE) / "patterns"


def _set_path(name: str) -> Path:
    if not _NAME_RE.match(name or ""):
        raise ValueError(f"invalid pattern set name: {name!r}")
    return patterns_dir() / f"{name}.txt"


def _migrate_approved_terms() -> None:
    """First use: copy the existing global approved-terms file in as a named
    set so nothing already in it is lost."""
    folder = patterns_dir()
    if any(folder.glob("*.txt")):
        return
    old = Path(getattr(config, "VALIDATION_APPROVED_TERMS_PATH", "") or "")
    if old.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{re.sub(r'[^A-Za-z0-9 _.-]', '_', old.stem)[:60] or 'approved_terms'}.txt"
        if not target.exists():
            shutil.copyfile(old, target)


def list_sets() -> list:
    """Names of available pattern sets, sorted."""
    _migrate_approved_terms()
    folder = patterns_dir()
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.txt"))


def create_set(name: str) -> Path:
    path = _set_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# approved terms\n\n# fixes (wrong = correct)\n", encoding="utf-8")
    return path


def parse_set(name: str, text: str) -> PatternSet:
    terms, fixes = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            wrong, correct = (" ".join(part.split()) for part in stripped.split("=", 1))
            if wrong and correct:
                fixes.append((wrong, correct))
        else:
            terms.append(" ".join(stripped.split()))
    return PatternSet(name=name, terms=terms, fixes=fixes,
                      sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())


def load_set(name: str) -> PatternSet:
    return parse_set(name, _set_path(name).read_text(encoding="utf-8"))


def add_fix(name: str, wrong: str, correct: str, source: str = "") -> bool:
    """Append ``wrong = correct`` to the set (with a dated comment). Returns
    False if an identical fix already exists."""
    wrong, correct = " ".join(wrong.split()), " ".join(correct.split())
    if not wrong or not correct or "=" in wrong or "=" in correct or wrong == correct:
        raise ValueError("a fix needs different, non-empty wrong and correct text without '='")
    path = create_set(name)
    existing = parse_set(name, path.read_text(encoding="utf-8"))
    if any(w.lower() == wrong.lower() and c == correct for w, c in existing.fixes):
        return False
    stamp = datetime.date.today().isoformat()
    note = f"# added {stamp}" + (f" from {source}" if source else "")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{note}\n{wrong} = {correct}\n")
    return True


def is_single_word(text: str) -> bool:
    return len(text.split()) == 1


def apply_fixes(text: str, fixes: list) -> tuple:
    """Apply whole-word, case-insensitive fixes (longest first, so phrases win
    over single words). Returns (new_text, [{"wrong", "correct", "count"}])."""
    applied = []
    for wrong, correct in sorted(fixes, key=lambda f: len(f[0]), reverse=True):
        text, count = replace_alias_occurrences(text, wrong, correct)
        if count:
            applied.append({"wrong": wrong, "correct": correct, "count": count})
    return text, applied


# ----------------------------------------------------------------- per project
def _canonical_raw(text: str) -> str:
    """Raw text as the formatter receives it (BOM and appended validation
    report removed), so hashes match whichever way the file was read."""
    from formatting_pipeline import strip_transcript_validation_footer
    return strip_transcript_validation_footer(text.lstrip("\ufeff"))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def project_record_path(stem: str) -> Path:
    return config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_PATTERN_SET}"


class CorruptRecordError(ValueError):
    """A project/review JSON file exists but cannot be read. Raised instead of
    treating it as absent, which would silently drop the pattern-set assignment
    or approvals (P2/P8)."""


def load_project_record(stem: str) -> Optional[dict]:
    path = project_record_path(stem)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CorruptRecordError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CorruptRecordError(f"{path} does not contain a JSON object")
    return data


def assign_to_project(stem: str, name: Optional[str]) -> None:
    """Choose the pattern set for a project (None clears it). Takes effect the
    next time the project is formatted."""
    path = project_record_path(stem)
    if name is None:
        if path.exists():
            path.unlink()
        return
    _set_path(name)  # validates the name
    path.parent.mkdir(parents=True, exist_ok=True)
    record = load_project_record(stem) or {}
    record.update({"name": name})
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


def apply_to_raw_for_project(stem: str, raw_text: str) -> tuple:
    """Apply the project's assigned set to the raw transcript before formatting
    and record what was applied. Returns (text, record or None)."""
    record = load_project_record(stem)
    if not record or not record.get("name"):
        return raw_text, None
    pattern_set = load_set(record["name"])
    raw_text = _canonical_raw(raw_text)
    fixed, applied = apply_fixes(raw_text, pattern_set.fixes)
    record.update({
        "name": pattern_set.name,
        "set_sha256": pattern_set.sha256,
        "original_raw_sha256": _sha(raw_text),
        "applied": applied,
        "applied_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    project_record_path(stem).write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return fixed, record


def effective_raw(stem: str, raw_text: str) -> str:
    """The raw text the formatter actually received: the original raw with the
    fixes recorded for this project re-applied in the recorded order. If the
    original raw no longer matches the recorded hash, it is returned unchanged
    (the comparison will then show the fix differences for review)."""
    record = load_project_record(stem)
    if not record or not record.get("applied"):
        return raw_text
    canonical = _canonical_raw(raw_text)
    if record.get("original_raw_sha256") != _sha(canonical):
        return raw_text
    text = canonical
    for fix in record["applied"]:
        text, _ = replace_alias_occurrences(text, fix["wrong"], fix["correct"])
    return text


# ----------------------------------------------------------------- defaults
def _defaults_path() -> Path:
    return patterns_dir() / DEFAULTS_FILENAME


def default_for_presenter(presenter: str) -> Optional[str]:
    try:
        data = json.loads(_defaults_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get(presenter)
    return name if name in list_sets() else None


def remember_for_presenter(presenter: str, name: str) -> None:
    if not presenter:
        return
    path = _defaults_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data[presenter] = name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
