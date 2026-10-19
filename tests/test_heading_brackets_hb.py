"""HB: heading timestamps written without brackets (docs/plan_heading_brackets_2026-10-19.md)."""
import logging

import pytest

import config
import formatting_pipeline as fp


def _heading(n, title, suffix):
    return f"## Section {n} – {title} {suffix}"


def test_hb1a_bare_paren_timestamp_gets_brackets():
    """Holt panel run, 2026-10-19: every heading was written (00:00:19). and Format
    stopped on the heading contract."""
    line = _heading(3, "Family Triangles and the Kaczynski Story", "(00:00:19).")
    text = f"{line}\n\nSome words.\n"
    assert any("does not match contract" in e
               for e in fp.validate_section_headings(text)[0])  # the defect
    fixed, rewrites = fp.normalize_heading_brackets(text)
    assert fixed == ("## Section 3 – Family Triangles and the Kaczynski Story ([00:00:19]).\n"
                     "\nSome words.\n")
    assert rewrites == [(3, "(00:00:19).", "([00:00:19]).")]


@pytest.mark.parametrize("suffix", [
    "(00:05:20).", "(00:05:20)",
    "[00:05:20].", "[00:05:20]",
    "([00:05:20])",
    "(00:05:20).  ",
])
def test_hb1b_each_loose_form_is_rewritten(suffix):
    text = _heading(1, "Opening Words Here Now", suffix) + "\n\nSome words.\n"
    fixed, rewrites = fp.normalize_heading_brackets(text)
    assert fixed.splitlines()[0] == "## Section 1 – Opening Words Here Now ([00:05:20])."
    assert [r[0] for r in rewrites] == [1]
    assert fp.validate_section_headings(fixed)[0] == []


def test_hb1c_canonical_heading_unchanged():
    text = (_heading(1, "Opening Words Here Now", "([00:00:00]).") + "\n\nSome words.\n\n"
            + _heading(2, "Later Words (Part 2) Here", "([00:05:20]).") + "\n\nMore words.\n\n"
            # Trailing spaces are allowed by the contract; not counted as a fix.
            + _heading(3, "Last Words Here Now", "([00:09:10]).  ") + "\n\nLast words.\n")
    fixed, rewrites = fp.normalize_heading_brackets(text)
    assert fixed == text and rewrites == []


@pytest.mark.parametrize("line", [
    "He said it at the start (00:05:20).",        # body text
    "### Section 2 – Not a Section Heading (00:05:20).",
    "## Section 2 - Hyphen Not Dash (00:05:20).",  # not the contract's en dash
    "## Section 2 – Two Groups Only (05:20).",     # m:ss or h:mm: ambiguous
    "## Section 2 – Four Groups (00:01:02:04).",   # RS.4's case, not this one
    "## Section 2 – Four Groups ([00:01:02:04]).",
    "## Section 2 – No Timestamp At All.",
    "## Section 2 – Unpaired Brackets (00:05:20].",
    "## Section 2 – Unpaired Brackets [00:05:20).",
    "## Section 2 – Unpaired Brackets ([00:05:20).",
    # A stray time in the title: rewriting the last one would let it pass the contract.
    "## Section 2 – Title ([00:05:20]) (00:06:00).",
])
def test_hb1d_non_heading_lines_untouched(line):
    text = f"{line}\n\nSome words.\n"
    fixed, rewrites = fp.normalize_heading_brackets(text)
    assert fixed == text and rewrites == []


# Headings from the failed run (first five sections) and the raw timestamps they use.
_RUN_HEADINGS = [
    '## Section 1 – Trying and Finding "I\'m No Different Than Anybody Else" (00:00:19).',
    "## Section 2 – Question: Thought Disorder Symptoms at 18 to 20 Years Old (00:00:19).",
    "## Section 3 – Family Triangles and the Kaczynski Story (00:00:19).",
    "## Section 6 – Revolving Door of Schizophrenia and Generational Attachment (00:05:20).",
    "## Section 7 – Schizophrenia as a Developmental Disorder: Diabetes and Parkinson's (00:05:20).",
]
_RUN_RAW = "[00:00:19]\n\nfirst words\n\n[00:05:20]\n\nlater words\n"


def test_hb1e_run_headings_pass_contract():
    lines = []
    for n, heading in enumerate(_RUN_HEADINGS, 1):
        # Renumber 1..5 so the sequence check does not fail on the excerpt.
        heading = heading.replace(heading.split(" – ")[0], f"## Section {n}", 1)
        lines += [heading, "", f"Words of section {n}.", ""]
    text = "\n".join(lines)
    errors, _ = fp.validate_section_headings(text, _RUN_RAW)
    assert sum("does not match contract" in e for e in errors) == 5
    fixed, rewrites = fp.normalize_heading_brackets(text)
    assert len(rewrites) == 5
    assert fp.validate_section_headings(fixed, _RUN_RAW)[0] == []


def test_hb1f_format_stage_saves_brackets_and_logs(tmp_path, monkeypatch, caplog):
    name = "Talk - A Person - 2021-01-01.txt"
    stem = "Talk - A Person - 2021-01-01"
    src = tmp_path / "source"
    src.mkdir()
    (src / name).write_text("[00:00:19]\n\nOpening words here.\n\n[00:05:20]\n\n"
                            "Later words here.\n", encoding="utf-8")
    monkeypatch.setattr(config, "SOURCE_DIR", src)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "PATTERNS_DIR", tmp_path / "patterns", raising=False)
    reply = ("## Section 1 – Opening Words Here Now (00:00:19).\n\nOpening words here.\n\n"
             "## Section 2 – Later Words Here Now (00:05:20).\n\nLater words here.\n")
    monkeypatch.setattr(fp, "format_transcript_with_claude", lambda *a, **k: reply)
    monkeypatch.setattr(fp, "load_prompt", lambda: "PROMPT")
    logger = logging.getLogger("hb_test")
    with caplog.at_level(logging.INFO, logger="hb_test"):
        assert fp.format_transcript(name, model="claude-haiku-5-5", logger=logger)
    saved = (tmp_path / "projects" / stem / f"{stem}{config.SUFFIX_FORMATTED}").read_text(
        encoding="utf-8")
    assert "## Section 1 – Opening Words Here Now ([00:00:19])." in saved
    assert "## Section 2 – Later Words Here Now ([00:05:20])." in saved
    assert any("Added the brackets to 2 of 2 heading timestamp(s)" in r.getMessage()
               for r in caplog.records)
    assert fp.validate_format(name, logger=logger) is True


def test_hb1g_brackets_added_before_timestamp_correction(tmp_path, monkeypatch, caplog):
    """The m:ss fix (RF.A.1) matches only bracketed headings, so the brackets must be
    added first: (00:33:00). against a raw 0:33 must be saved as ([00:00:33])."""
    name = "Talk - A Person - 2021-01-01.txt"
    stem = "Talk - A Person - 2021-01-01"
    src = tmp_path / "source"
    src.mkdir()
    (src / name).write_text("0:00\nOpening words here.\n0:33\nLater words here.\n",
                            encoding="utf-8")
    monkeypatch.setattr(config, "SOURCE_DIR", src)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "PATTERNS_DIR", tmp_path / "patterns", raising=False)
    reply = ("## Section 1 – Opening Words Here Now (00:00:00).\n\nOpening words here.\n\n"
             "## Section 2 – Later Words Here Now (00:33:00).\n\nLater words here.\n")
    monkeypatch.setattr(fp, "format_transcript_with_claude", lambda *a, **k: reply)
    monkeypatch.setattr(fp, "load_prompt", lambda: "PROMPT")
    logger = logging.getLogger("hb_test")
    with caplog.at_level(logging.INFO, logger="hb_test"):
        assert fp.format_transcript(name, model="claude-haiku-5-5", logger=logger)
    saved = (tmp_path / "projects" / stem / f"{stem}{config.SUFFIX_FORMATTED}").read_text(
        encoding="utf-8")
    assert "## Section 2 – Later Words Here Now ([00:00:33])." in saved
    messages = [r.getMessage() for r in caplog.records]
    assert any("Added the brackets to 2 of 2" in m for m in messages)
    assert any("Corrected 1 of 2 heading timestamp(s)" in m for m in messages)
    assert fp.validate_format(name, logger=logger) is True
