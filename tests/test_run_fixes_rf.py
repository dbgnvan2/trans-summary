"""RF.A-RF.E: fixes from the 2026-10-09 Kerr run (docs/plan_run_fixes_2026-10-09.md).

That run was blocked by wrong heading timestamps (m:ss read as h:mm) and by a
verbatim quote that only changed the inner quotation marks; the blog stage stopped
without a recorded reason, and the GUI offered no Simple Web stage.
"""
from pathlib import Path
from unittest.mock import MagicMock

import config
import validation_pipeline as vp

FIX = Path(__file__).resolve().parent / "fixtures" / "prose_real" / \
    "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13"
BASE = FIX.name

# The emphasis quote from the 2026-10-09 run, verbatim: the speaker's inner
# "He's smiling..." became 'He's smiling...'.
KERR_QUOTE = (
    "Then I looked up at him, and he hadn't said much of anything, and I said, "
    "'He's smiling. What's he smiling about?' But then I realized he hadn't got "
    "tangled up with it, with me. And that was a big step to help me start doing "
    "something differently. It was the first time I had seen that he could stay "
    "outside the system with my utterings and utterings and utterings."
)


def _formatted():
    return (FIX / f"{BASE} - formatted.md").read_text(encoding="utf-8")


# --- RF.B: quote-within-a-quote --------------------------------------------------

def test_rfb1_nested_single_quotes_are_verbatim():
    source = _formatted()
    assert vp._emphasis_quote_found_ratio(KERR_QUOTE, source) >= config.EMPHASIS_QUOTE_FOUND_RATIO
    assert vp._quote_word_coverage(KERR_QUOTE, source) >= config.QUOTE_MIN_WORD_COVERAGE


def test_rfb1_curly_inner_quotes_are_verbatim():
    curly = KERR_QUOTE.replace("'He's", "‘He's").replace("about?'", "about?’")
    assert vp._emphasis_quote_found_ratio(curly, _formatted()) >= config.EMPHASIS_QUOTE_FOUND_RATIO


def test_rfb1_changed_word_inside_nested_quote_still_fails():
    # P7: a quote that looks right but changes a word inside the inner quotation.
    altered = KERR_QUOTE.replace("'He's smiling.", "'He's laughing.")
    assert vp._quote_word_coverage(altered, _formatted()) < config.QUOTE_MIN_WORD_COVERAGE


def test_rfb1_contractions_kept():
    assert vp._without_disfluencies("'He's here,' I said. Don't go.") == "he's here i said don't go"
    assert vp._without_disfluencies("he's") != vp._without_disfluencies("hes")


def test_rfb1_quote_ending_inside_a_repeat_is_verbatim():
    # The quote stops at "utterings and utterings and utterings"; the source goes
    # on "... and that was very helpful". Both must collapse the same way.
    assert vp._collapse_disfluencies("my utterings and utterings and utterings".split()) == \
        ["my", "utterings", "and"]
    assert vp._collapse_disfluencies("my utterings and utterings and utterings and that".split()) == \
        ["my", "utterings", "and", "that"]


def test_rfb1_trailing_word_kept_when_no_repeat_was_collapsed():
    # P7: "the dog the" is not a repeat; the final word must not be dropped.
    assert vp._collapse_disfluencies("i saw the dog the".split()) == ["i", "saw", "the", "dog", "the"]


# --- RF.A: heading timestamps match the raw transcript ---------------------------

import re  # noqa: E402

import formatting_pipeline as fp  # noqa: E402


def _raw():
    return (FIX / f"{BASE}.txt").read_text(encoding="utf-8-sig")


def _timestamp_errors(formatted, raw):
    errors, _ = fp.validate_section_headings(formatted, raw)
    return [e for e in errors if "does not occur in the raw" in e]


def test_rfa1_mss_read_as_hmm_is_rewritten():
    # Real Kerr output: raw "0:33" (33 s) was written as [00:33:00] (33 min).
    formatted, raw = _formatted(), _raw()
    assert _timestamp_errors(formatted, raw)  # the defect is present in the fixture
    fixed, rewrites = fp.normalize_heading_timestamps(formatted, raw)
    assert _timestamp_errors(fixed, raw) == []
    assert ("00:33:00", "00:00:33") in [(old, new) for _n, old, new in rewrites]
    assert "## Section 2 – Introduction to Michael Kerr and Bowen Theory ([00:00:33])." in fixed
    # Only the heading timestamps changed.
    strip = lambda t: re.sub(r"\(\[\d\d:\d\d:\d\d\]\)", "", t)  # noqa: E731
    assert strip(fixed) == strip(formatted)


def test_rfa1_heading_present_in_raw_is_not_rewritten():
    # P7: an h:mm:ss raw where 0:33:00 really is 33 minutes keeps its heading.
    raw = "0:00\nHello there.\n0:33:00\nLater words here.\n"
    formatted = ("## Section 1 – Opening Words Here Now ([00:00:00]).\n\nHello there.\n\n"
                 "## Section 2 – Later Words Here Now ([00:33:00]).\n\nLater words here.\n")
    fixed, rewrites = fp.normalize_heading_timestamps(formatted, raw)
    assert fixed == formatted and rewrites == []


def test_rfa1_unmatched_timestamp_left_for_validator():
    raw = "0:00\nHello there.\n0:33\nLater words here.\n"
    formatted = ("## Section 1 – Opening Words Here Now ([00:00:00]).\n\nHello there.\n\n"
                 "## Section 2 – Later Words Here Now ([00:47:00]).\n\nLater words here.\n")
    fixed, rewrites = fp.normalize_heading_timestamps(formatted, raw)
    assert fixed == formatted and rewrites == []
    assert _timestamp_errors(fixed, raw)  # still reported


def test_rfa2_format_transcript_saves_corrected_headings(tmp_path, monkeypatch):
    src = tmp_path / "source"
    src.mkdir()
    name = f"{BASE}.txt"
    (src / name).write_text(_raw(), encoding="utf-8")
    monkeypatch.setattr(config, "SOURCE_DIR", src)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "PATTERNS_DIR", tmp_path / "patterns", raising=False)
    monkeypatch.setattr(fp, "format_transcript_with_claude",
                        lambda raw, prompt, model=None, logger=None: _formatted())
    monkeypatch.setattr(fp, "load_prompt", lambda: "PROMPT")
    logger = MagicMock()
    assert fp.format_transcript(name, model="claude-sonnet-4-6", logger=logger)
    saved = (tmp_path / "projects" / BASE / f"{BASE}{config.SUFFIX_FORMATTED}").read_text(encoding="utf-8")
    assert _timestamp_errors(saved, _raw()) == []
    logged = " ".join(str(c.args) for c in logger.info.call_args_list)
    assert "heading timestamp(s)" in logged


def test_rfa3_prompt_states_mss_rule():
    prompt = (Path(config.PROMPTS_DIR) / "Transcript Formatting Prompt v12-Lite.md").read_text(encoding="utf-8")
    assert "`0:33` becomes `[00:00:33]`" in prompt


# --- RF.C: Blog-only stage retries lens validation and checks the lens -----------

import extraction_pipeline as ep  # noqa: E402

GOOD_LENS = {"title": "Lens A", "description": "d", "rationale": "r",
             "evidence": "Section 1", "hooks": ["h"]}


def _blog_project(tmp_path, monkeypatch, validations):
    """A project with Core artifacts on disk; ``validations`` is the sequence the
    theme/lens validator returns. Returns (project_dir, stem, calls, logger)."""
    stem = "Blog-Lens-Test"
    proj = tmp_path / "projects" / stem
    proj.mkdir(parents=True)
    for suffix, text in (
        (config.SUFFIX_STRUCTURAL_THEMES, "## Structural Themes\n\n1. **Structure A**: x.\n"),
        (config.SUFFIX_INTERPRETIVE_THEMES, "## Interpretive Themes\n\n1. **Interp A**: y.\n"),
        (config.SUFFIX_TOPICS, "## Topics\n\n### Topic A\nD.\n*_(~20% of transcript; Sections 1)_*\n"),
        (config.SUFFIX_KEY_TERMS, "## Key Terms\n\n### Term A\nDef.\n"),
        (config.SUFFIX_LENSES, "## Lenses (Ranked)\n\n1. **Lens A**\nRationale.\n"),
    ):
        (proj / f"{stem}{suffix}").write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "SOURCE_DIR", tmp_path / "source")
    monkeypatch.setattr(ep, "_load_formatted_transcript", lambda _f: "## Section 1\nText.\n")
    monkeypatch.setattr(ep, "parse_filename_metadata", lambda f: {
        "stem": stem, "title": stem, "presenter": "P", "author": "P",
        "date": "1980-00-00", "filename": f})
    monkeypatch.setattr(ep, "create_system_message_with_cache", lambda _t: [{"type": "text", "text": "c"}])
    monkeypatch.setattr(ep, "_load_summary_prompt", lambda _n: "Blog for {{top_lens_title}}")
    monkeypatch.setattr(ep, "_generate_summary_with_claude", lambda *a, **k: "Generated blog post.")
    calls = []
    seq = list(validations)

    def _validate(*_a, **_k):
        calls.append(1)
        return seq.pop(0) if seq else validations[-1]

    monkeypatch.setattr(ep, "_validate_themes_and_lenses", _validate)
    return proj, stem, calls, MagicMock()


def _run_blog(stem, logger):
    return ep.summarize_transcript(
        f"{stem}{config.SUFFIX_YAML}", config.DEFAULT_MODEL, "Family Systems",
        "General public", True, True, True, False, logger=logger)


def test_rfc1_attempts_from_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "THEME_LENS_VALIDATION_ATTEMPTS", 2)
    proj, stem, calls, logger = _blog_project(tmp_path, monkeypatch, [{"top_lens": {}}])
    assert _run_blog(stem, logger) is False
    assert len(calls) == 2
    # Core reads the same setting (no second literal).
    import inspect
    assert "max_attempts = config.THEME_LENS_VALIDATION_ATTEMPTS" in inspect.getsource(ep.summarize_transcript)


def test_rfc2_blog_retries_until_grounded_lens(tmp_path, monkeypatch):
    proj, stem, calls, logger = _blog_project(
        tmp_path, monkeypatch, [{"top_lens": {}}, {"top_lens": GOOD_LENS}])
    assert _run_blog(stem, logger) is True
    assert len(calls) == 2
    assert "Generated blog post." in (proj / f"{stem}{config.SUFFIX_BLOG}").read_text(encoding="utf-8")


def test_rfc2_blog_rejects_ungrounded_lens(tmp_path, monkeypatch):
    # P7: a lens the validator names that was never generated must not be used.
    ghost = dict(GOOD_LENS, title="A Completely Different Invented Framing")
    proj, stem, calls, logger = _blog_project(tmp_path, monkeypatch, [{"top_lens": ghost}])
    assert _run_blog(stem, logger) is False
    assert not (proj / f"{stem}{config.SUFFIX_BLOG}").exists()
    assert len(calls) == config.THEME_LENS_VALIDATION_ATTEMPTS


def test_rfc3_blog_failure_reason_logged(tmp_path, monkeypatch):
    ghost = dict(GOOD_LENS, title="A Completely Different Invented Framing")
    proj, stem, calls, logger = _blog_project(tmp_path, monkeypatch, [
        {"top_lens": {}, "parse_error": True}, {"top_lens": {}}, {"top_lens": ghost}])
    assert _run_blog(stem, logger) is False
    message = logger.error.call_args.args[0] % logger.error.call_args.args[1:]
    assert "attempt 1/3: validator output was not JSON" in message
    assert "attempt 2/3: validator returned no top lens" in message
    assert "is not among the generated lenses" in message


# --- RF.E: "8b. Simple Web" stage -------------------------------------------------

from unittest.mock import patch  # noqa: E402

import release_gate  # noqa: E402
import ts_gui  # noqa: E402


def _gui(logs):
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = "Sample"
    gui.logger = None
    gui.log = lambda *a, **_k: logs.append(" ".join(str(x) for x in a))
    return gui


def test_rfe1_simple_web_before_package():
    keys = [k for k, _ in ts_gui.STAGE_DEFINITIONS]
    assert keys.index("webpdf") < keys.index("simple_web") < keys.index("package")
    assert ts_gui.STAGE_OUTPUTS["simple_web"] == ["SUFFIX_WEBPAGE_SIMPLE"]
    assert ts_gui.STAGE_DEPENDENCIES["simple_web"] == ts_gui.STAGE_DEPENDENCIES["webpdf"]
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    assert gui.stage_runners["simple_web"].__func__ is ts_gui.TranscriptProcessorGUI._run_stage_simple_web


def test_rfe2_simple_web_calls_generator_on_allow():
    gui = _gui([])
    allow = release_gate.GateDecision(release_gate.Decision.ALLOW, [], [])
    with patch("release_gate.run_gate", return_value=allow), \
         patch("ts_gui.pipeline.generate_simple_webpage", return_value=True) as simple:
        assert gui._run_stage_simple_web() is True
    simple.assert_called_once_with("Sample")


def test_rfe2_simple_web_block_writes_nothing_and_logs_blockers():
    logs = []
    gui = _gui(logs)
    verdict = release_gate.Verdict("source_fidelity", release_gate.Status.FAIL,
                                   "timestamp 00:33:00 does not occur in the raw transcript")
    block = release_gate.GateDecision(release_gate.Decision.BLOCK, [verdict], [verdict])
    with patch("release_gate.run_gate", return_value=block), \
         patch("release_gate.record_decision") as record, \
         patch("ts_gui.pipeline.generate_simple_webpage") as simple:
        assert gui._run_stage_simple_web() is False
    simple.assert_not_called()
    record.assert_called_once()
    assert any("BLOCKED" in line and "simple webpage" in line for line in logs)
    assert any("source_fidelity" in line for line in logs)


def test_rfe2_simple_web_generator_failure_reported():
    logs = []
    gui = _gui(logs)
    allow = release_gate.GateDecision(release_gate.Decision.ALLOW, [], [])
    with patch("release_gate.run_gate", return_value=allow), \
         patch("ts_gui.pipeline.generate_simple_webpage", return_value=False):
        assert gui._run_stage_simple_web() is False
    assert any("Simple webpage generation failed" in line for line in logs)


def test_rfe3_manifest_lists_simple_webpage():
    assert config.SUFFIX_WEBPAGE_SIMPLE in release_gate._MANIFEST_SUFFIXES
