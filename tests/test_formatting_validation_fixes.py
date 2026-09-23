"""
Regression tests for formatting validation fixes:
  1. truncated formatted output must fail (each missing word counted)
  2. words inserted by the formatter must be counted
  3. [sic] stripping must never merge a heading into the previous paragraph
  4. deterministic section-heading contract check
  plus: substitutions counted once, largest contiguous difference reported,
  procedural words stripped symmetrically.
"""

import logging
from pathlib import Path

import pytest

import config
import formatting_pipeline as fp
from transcript_utils import strip_yaml_frontmatter

FIXTURE_DIR = (
    Path(__file__).parent
    / "fixtures"
    / "where_roots"
    / "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"
)
STEM = FIXTURE_DIR.name
RAW_FIXTURE = FIXTURE_DIR / f"{STEM}.txt"
FORMATTED_FIXTURE = FIXTURE_DIR / f"{STEM} - formatted.md"


def _compare(raw: str, formatted: str) -> dict:
    return fp._compare_transcripts(raw, formatted, set(), 10, 1.0, None)


def _words(n: int, start: int = 0) -> str:
    return " ".join(f"w{i}" for i in range(start, start + n))


# ---------------------------------------------------------------- comparison


def test_truncated_output_counts_every_missing_word():
    result = _compare(_words(1000), _words(600))
    assert result["mismatch_count"] == 400
    assert result["stopped_reason"] == "B_exhausted"
    assert result["mismatch_ratio"] == pytest.approx(0.4)
    assert {m["reason"] for m in result["mismatches"]} == {"B exhausted"}


def test_inserted_words_are_counted():
    raw = _words(100)
    formatted = _words(50) + " invented words appear here " + _words(50, start=50)
    result = _compare(raw, formatted)
    inserted = [m["b_word"] for m in result["mismatches"] if m["reason"] == "Inserted in B"]
    assert inserted == ["invented", "words", "appear", "here"]
    assert result["mismatch_count"] == 4


def test_trailing_inserted_words_are_counted():
    result = _compare(_words(20), _words(20) + " extra tail")
    assert result["mismatch_count"] == 2
    assert all(m["reason"] == "Inserted in B" for m in result["mismatches"])


def test_substitution_counted_once():
    result = _compare("alpha beta gamma delta", "alpha zzz gamma delta")
    assert result["mismatch_count"] == 1
    assert result["mismatches"][0]["reason"] == "Mismatch"
    assert result["mismatches"][0]["a_word"] == "beta"
    assert result["mismatches"][0]["b_word"] == "zzz"


def test_large_deletion_located_exactly():
    raw = _words(300)
    formatted = _words(100) + " " + _words(150, start=150)  # drop w100..w149
    result = _compare(raw, formatted)
    assert result["mismatch_count"] == 50
    assert result["max_contiguous_run"] == 50
    assert result["max_run_a_index"] == 100


def test_skip_words_ignored_on_both_sides():
    result = fp._compare_transcripts(
        "a b um c", "a b c um", {"um"}, 10, 1.0, None
    )
    assert result["mismatch_count"] == 0
    assert result["checked_words"] == 3


def test_procedural_words_are_compared_not_stripped():
    """Procedural speech is no longer stripped (stripping only the raw side hid
    deletions and created false insertions). Kept words match; a deleted
    'next slide, please' is now visible as deletions."""
    raw = "Speaker 1  0:01\nThe triangle, please. Next slide, please. More content."
    formatted = "## Section 1 – T ([00:00:01]).\n\nThe triangle, please. Next slide, please. More content."
    raw_clean, formatted_clean = fp._prepare_texts_for_comparison(raw, formatted)
    assert _compare(raw_clean, formatted_clean)["mismatch_count"] == 0
    dropped = "## Section 1 – T ([00:00:01]).\n\nThe triangle, please. More content."
    raw_clean, dropped_clean = fp._prepare_texts_for_comparison(raw, dropped)
    assert _compare(raw_clean, dropped_clean)["mismatch_count"] == 3


def test_near_match_accepted_only_for_words_absent_from_formatted():
    # 'homostasis' never appears in the formatted text -> accepted correction
    r = _compare("the homostasis of cells", "the homeostasis of cells")
    assert r["mismatch_count"] == 0
    assert r["corrections"][0]["a_word"] == "homostasis"
    # 'their' is used elsewhere in the formatted text -> real edit, counted
    r = _compare("their house and their car", "there house and their car")
    assert r["mismatch_count"] == 1
    assert r["corrections"] == []


# ---------------------------------------------------------------- [sic]


def test_sic_strip_keeps_following_heading_on_its_own_line():
    text = "end of para Cobra [sic] (Brahe)\n\n## Section 2 – Next Topic ([00:05:00]).\n\nText"
    cleaned, count = fp.strip_sic_annotations(text)
    assert count == 1
    assert "\n\n## Section 2 – Next Topic ([00:05:00])." in cleaned
    assert cleaned.startswith("end of para Cobra\n")


def test_sic_strip_inline_spacing():
    cleaned, count = fp.strip_sic_annotations("Cobra [sic] (Tycho Brahe) moved, pliocentric [sic], then.")
    assert cleaned == "Cobra moved, pliocentric, then."
    assert count == 2


# ---------------------------------------------------------------- headings

GOOD = """## Section 1 – Welcome and Two Mini Lectures ([00:00:04]).

Okay, welcome.

## Section 2 – Exploring the Roots of Theory ([00:01:11]).

More text here.
"""
RAW = "[00:00:04] Okay, welcome.\n[00:01:11] More text here.\n"


def test_headings_valid():
    errors, warnings = fp.validate_section_headings(GOOD, RAW)
    assert errors == []
    assert warnings == []


def test_headings_merged_into_text_is_error():
    merged = GOOD.replace("Okay, welcome.\n\n## Section 2", "Okay, welcome. ## Section 2")
    errors, _ = fp.validate_section_headings(merged, RAW)
    assert any("not at the start of a line" in e for e in errors)


def test_headings_number_gap_is_error():
    errors, _ = fp.validate_section_headings(GOOD.replace("Section 2", "Section 3"), RAW)
    assert any("not sequential" in e for e in errors)


def test_headings_decreasing_timestamp_is_error():
    bad = GOOD.replace("[00:01:11]", "[00:00:02]")
    errors, _ = fp.validate_section_headings(bad, RAW + "[00:00:02] x\n")
    assert any("earlier than the previous" in e for e in errors)


def test_headings_timestamp_absent_from_raw_is_error():
    errors, _ = fp.validate_section_headings(GOOD.replace("[00:01:11]", "[00:05:00]"), RAW)
    assert any("does not occur in the raw transcript" in e for e in errors)


def test_headings_raw_mss_timestamps_are_recognised():
    raw_otter = "Speaker 1  0:04\nOkay, welcome.\n\nSpeaker 1  1:11\nMore text here.\n"
    errors, _ = fp.validate_section_headings(GOOD, raw_otter)
    assert errors == []


def test_headings_malformed_is_error():
    bad = GOOD.replace("([00:01:11]).", "[00:01:11]")
    errors, _ = fp.validate_section_headings(bad, RAW)
    assert any("does not match contract" in e for e in errors)


def test_headings_empty_section_is_error():
    bad = GOOD.replace("More text here.\n", "")
    errors, _ = fp.validate_section_headings(bad, RAW)
    assert any("Section 2: no transcript text" in e for e in errors)


def test_headings_preamble_is_warning_not_error():
    errors, warnings = fp.validate_section_headings("# Title\n\n" + GOOD, RAW)
    assert errors == []
    assert any("Content before the first" in w for w in warnings)


def test_headings_none_found_is_error():
    errors, _ = fp.validate_section_headings("just text\n", RAW)
    assert errors == ["No '## Section' headings found"]


# ---------------------------------------------------------------- real fixture


@pytest.fixture
def fixture_texts():
    raw = RAW_FIXTURE.read_text(encoding="utf-8-sig")
    formatted = strip_yaml_frontmatter(FORMATTED_FIXTURE.read_text(encoding="utf-8-sig"))
    return raw, formatted


def _fixture_result(raw: str, formatted: str) -> dict:
    raw_clean, formatted_clean = fp._prepare_texts_for_comparison(raw, formatted)
    return fp._compare_transcripts(raw_clean, formatted_clean, set(), 10, 0.05, None)


def test_real_fixture_passes(fixture_texts):
    raw, formatted = fixture_texts
    result = _fixture_result(raw, formatted)
    assert result["mismatch_ratio"] <= config.VALIDATION_MISMATCH_RATIO
    assert result["max_contiguous_run"] <= config.VALIDATION_MAX_CONTIGUOUS_RUN
    errors, _ = fp.validate_section_headings(formatted, raw)
    assert errors == []


def test_real_fixture_truncated_fails(fixture_texts):
    raw, formatted = fixture_texts
    result = _fixture_result(raw, formatted[: int(len(formatted) * 0.97)])
    assert result["stopped_reason"] == "B_exhausted"
    assert result["mismatch_ratio"] > config.VALIDATION_MISMATCH_RATIO


def test_real_fixture_dropped_paragraph_exceeds_run_limit(fixture_texts):
    raw, formatted = fixture_texts
    paras = formatted.split("\n\n")
    mid = len(paras) // 2
    assert len(paras[mid].split()) > config.VALIDATION_MAX_CONTIGUOUS_RUN
    result = _fixture_result(raw, "\n\n".join(paras[:mid] + paras[mid + 1:]))
    assert result["max_contiguous_run"] > config.VALIDATION_MAX_CONTIGUOUS_RUN


def test_validate_format_end_to_end(monkeypatch, tmp_path, fixture_texts):
    raw, formatted = fixture_texts
    src = tmp_path / "src"
    proj = tmp_path / "proj" / STEM
    src.mkdir()
    proj.mkdir(parents=True)
    (src / f"{STEM}.txt").write_text(raw, encoding="utf-8")
    formatted_path = proj / f"{STEM}{config.SUFFIX_FORMATTED}"
    monkeypatch.setattr(config, "SOURCE_DIR", src)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "proj")
    logger = logging.getLogger("test_validate_format_end_to_end")

    formatted_path.write_text(formatted, encoding="utf-8")
    # Unreviewed differences fail validation ...
    assert fp.validate_format(f"{STEM}.txt", logger=logger) is False
    # ... and pass once they are approved (fixture review file).
    review = FIXTURE_DIR / f"{STEM}{config.SUFFIX_FORMAT_REVIEW}"
    (proj / review.name).write_text(review.read_text(encoding="utf-8"), encoding="utf-8")
    assert fp.validate_format(f"{STEM}.txt", logger=logger) is True

    formatted_path.write_text(formatted[: int(len(formatted) * 0.6)], encoding="utf-8")
    assert fp.validate_format(f"{STEM}.txt", logger=logger) is False
