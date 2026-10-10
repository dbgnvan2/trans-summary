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
    # on "... and that was very helpful". Repeat collapsing differs at that
    # boundary, but the quote is literally in the source.
    source = "So he could stay outside with my utterings and utterings and utterings. And that was very helpful."
    quote = "he could stay outside with my utterings and utterings and utterings."
    assert vp._quote_word_coverage(quote, source) == 1.0
    assert vp._emphasis_quote_found_ratio(quote, source) == 1.0


def test_rfb1_changed_last_word_in_a_repeat_still_fails():
    # P7 (sweep finding): "do" where the speaker said "don't" reverses the meaning.
    source = "And he said do it, do it, don't. Then he left the room quietly."
    quote = "And he said do it, do it, do"
    assert vp._quote_word_coverage(quote, source) < config.QUOTE_MIN_WORD_COVERAGE


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
        result = seq.pop(0) if seq else validations[-1]
        return {"structural_themes_valid": True, "interpretive_themes_valid": True, **result}

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


def test_rfc2_blog_refuses_lens_when_themes_denied(tmp_path, monkeypatch):
    # Sweep finding: Core needs both theme sets valid; the Blog-only path must too.
    proj, stem, calls, logger = _blog_project(
        tmp_path, monkeypatch, [{"top_lens": GOOD_LENS, "interpretive_themes_valid": False}])
    assert _run_blog(stem, logger) is False
    assert not (proj / f"{stem}{config.SUFFIX_BLOG}").exists()
    message = logger.error.call_args.args[0] % logger.error.call_args.args[1:]
    assert "validator denied the interpretive themes on disk (re-run Core)" in message


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
         patch("ts_gui.pipeline.generate_simple_webpage", return_value=True) as simple, \
         patch("ts_gui.transcript_validate_webpage.validate_webpage", return_value=True) as check:
        assert gui._run_stage_simple_web() is True
    simple.assert_called_once_with("Sample")
    check.assert_called_once_with("Sample", simple_mode=True)


def test_rfe2_simple_web_validation_failure_fails_stage():
    logs = []
    gui = _gui(logs)
    allow = release_gate.GateDecision(release_gate.Decision.ALLOW, [], [])
    with patch("release_gate.run_gate", return_value=allow), \
         patch("ts_gui.pipeline.generate_simple_webpage", return_value=True), \
         patch("ts_gui.transcript_validate_webpage.validate_webpage", return_value=False):
        assert gui._run_stage_simple_web() is False
    assert any("Simple webpage validation FAILED" in line for line in logs)


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


# --- RF.D: the GUI log is saved to a file -----------------------------------------

def _logging_gui(tmp_path, monkeypatch, logs_dir):
    monkeypatch.setattr(config, "LOGS_DIR", logs_dir)
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui._log_file_enabled = True  # set by __init__ in the real GUI
    shown = []
    gui._append_log_text = shown.append
    return gui, shown


def test_rfd1_log_lines_written_to_session_file(tmp_path, monkeypatch):
    gui, shown = _logging_gui(tmp_path, monkeypatch, tmp_path / "logs")
    gui.log("STEP 7: Generating Blog Post from Lens #1...")
    gui.log("Blog lens not validated (%s).", "attempt 1/3: validator returned no top lens")
    files = list((tmp_path / "logs").glob("gui_*.log"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert lines[0].endswith("STEP 7: Generating Blog Post from Lens #1...")
    assert lines[1].endswith("Blog lens not validated (attempt 1/3: validator returned no top lens).")
    assert re.match(r"^\d\d:\d\d:\d\d ", lines[0])
    assert shown[:2] == ["STEP 7: Generating Blog Post from Lens #1...",
                         "Blog lens not validated (attempt 1/3: validator returned no top lens)."]


def test_rfd1_log_file_error_does_not_raise(tmp_path, monkeypatch):
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")  # LOGS_DIR is a file -> cannot create the log
    gui, shown = _logging_gui(tmp_path, monkeypatch, blocker)
    gui.log("first")
    gui.log("second")
    assert "first" in shown and "second" in shown
    warnings = [s for s in shown if "not being saved" in s]
    assert len(warnings) == 1  # reported once, not on every line


def test_rfd1_headless_instances_do_not_write(tmp_path, monkeypatch):
    # Tests build the GUI with __new__; only the real __init__ turns file logging on.
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui._append_log_text = lambda _t: None
    gui.log("hello")
    assert not (tmp_path / "logs").exists()


def test_rfe4_package_skips_stale_simple_webpage(tmp_path, monkeypatch):
    # Sweep finding: Package must not ship a simple page older than the full page.
    import os
    import zipfile

    import packaging_pipeline

    base = "Sample Talk - A Person - 2021-01-01"
    proj = tmp_path / base
    proj.mkdir()
    simple = proj / f"{base}{config.SUFFIX_WEBPAGE_SIMPLE}"
    simple.write_text("<html>old</html>", encoding="utf-8")
    os.utime(simple, (1_000_000, 1_000_000))
    (proj / f"{base}{config.SUFFIX_WEBPAGE}").write_text("<html>new</html>", encoding="utf-8")
    (proj / f"{base}{config.SUFFIX_FORMATTED}").write_text("## Section 1\ntext\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(release_gate, "publish_allowed", lambda *_a, **_k: True)
    logger = MagicMock()
    assert packaging_pipeline.package_transcript(base, logger)
    names = zipfile.ZipFile(next(tmp_path.rglob("*.zip"))).namelist()
    assert not any(n.endswith(config.SUFFIX_WEBPAGE_SIMPLE) for n in names)
    assert any("Simple webpage not packaged" in str(c.args[0]) for c in logger.warning.call_args_list)

    # A fresh simple page is packaged.
    simple.write_text("<html>fresh</html>", encoding="utf-8")
    assert packaging_pipeline.package_transcript(base, logger)
    names = zipfile.ZipFile(next(tmp_path.rglob("*.zip"))).namelist()
    assert any(n.endswith(config.SUFFIX_WEBPAGE_SIMPLE) for n in names)


def test_rfd1_unencodable_text_does_not_raise(tmp_path, monkeypatch):
    # Sweep finding: a lone surrogate must not escape log() and crash a stage.
    gui, shown = _logging_gui(tmp_path, monkeypatch, tmp_path / "logs")
    gui.log("bad \ud800 text")
    assert shown == ["bad \ud800 text"]
    assert list((tmp_path / "logs").glob("gui_*.log"))


# --- RF.F: interview turns are not audience Q&A -----------------------------------

import abstract_pipeline as ap  # noqa: E402
import summary_pipeline as sp  # noqa: E402
import transcript_utils as tu  # noqa: E402


def _section(n, body, heading="Heading Words For Section"):
    return f"## Section {n} – {heading} ([00:00:{n:02d}]).\n\n{body}\n\n"


def _pct(text, presenter="Michael Kerr"):
    return ap.calculate_qa_percentage(text, presenter=presenter)[0]


def test_rff1_interview_is_not_qa():
    # Real Kerr interview: **Interviewer:** / **Michael Kerr:** turns. Was 26%.
    assert ap.calculate_qa_percentage(_formatted(), presenter="Michael Kerr") == (0, [])
    assert sp.analyze_qa_content(_formatted(), presenter="Michael Kerr")["percentage"] == 0


def test_rff1_audience_section_still_detected():
    text = (_section(1, "**Interviewer:** Tell us about it.\n\n**Kerr:** It began early.")
            + _section(2, "**Audience Member:** What about cutoff?\n\n**Kerr:** Distance."))
    assert _pct(text) == 50


def test_rff1_one_named_questioner_is_qa():
    # Sweep finding: one questioner turn plus the presenter's answer, no keyword.
    text = (_section(1, "**Kerr:** Lecture text here.")
            + _section(2, "**Mary:** What about cutoff in families?\n\n**Kerr:** Distance."))
    assert _pct(text) == 50
    assert _pct(text.replace("**Mary:**", "**MARY:**")) == 50  # any case


def test_rff1_dr_label_is_presenter():
    # Sweep finding: an interview formatted with "**Dr. Kerr:**" is still not Q&A.
    body = "**Interviewer:** Tell me more.\n\n**Dr. Kerr:** Gladly.\n\n**Dr. Kerr:** And more."
    assert _pct(_section(1, body) + _section(2, body), presenter="Dr. Michael Kerr") == 0


def test_rff1_presenter_first_name_alone_is_audience():
    # Sweep finding: an audience member who shares the presenter's first name counts.
    text = _section(1, "**Michael:** Can I ask something?\n\n**Kerr:** Yes.")
    assert _pct(text) == 100


def test_rff1_presenter_label_not_qa():
    text = _section(1, "**Kerr:** First point.\n\n**Kerr:** Second point.")
    assert _pct(text) == 0
    assert _pct(text, presenter=None) == 100  # unknown speaker: counted, as before


def test_rff1_qa_heading_counts():
    text = _section(1, "Lecture.") + _section(2, "Thank you all.", heading="Q&A: Amy Post on Cutoff")
    assert tu.find_qa_sections(text)[0][0][0].startswith("## Section 2")


def test_rff1_numbered_and_accented_labels():
    # Sweep 2: generic numbered labels and non-ASCII names are audience speakers.
    assert _pct(_section(1, "**Audience Member 2:** Why?\n\n**Kerr:** Because.")) == 100
    assert _pct(_section(1, "**José García:** Why?\n\n**Kerr:** Because.")) == 100


def test_rff1_question_words_alone_are_not_qa():
    # P7 (sweep 2): a lecture section that says "question" is not audience Q&A.
    body = ("**Kerr:** That is the question of differentiation, unquestionably. "
            "Another question follows, and a comment on commentary.")
    assert _pct(_section(1, body)) == 0


def test_rff1_lecture_heading_with_question_is_not_qa():
    # P7 (sweep 2): only Q&A-style headings count.
    assert _pct(_section(1, "**Kerr:** Text.", heading="The Question of Differentiation")) == 0
    assert _pct(_section(1, "**Kerr:** Text.", heading="Questions and Answers")) == 100
    assert _pct(_section(1, "Text.", heading="Question About Faith and Belief")) == 100


def test_rff1_presenter_label_variants():
    # Sweep 2: initials and co-presenters are still the presenter; another Kerr is not.
    body = "**Interviewer:** Go on.\n\n**Dr. Michael E. Kerr:** Yes.\n\n**Smith:** Indeed."
    assert _pct(_section(1, body), presenter="Michael Kerr and John Smith") == 0
    assert _pct(_section(1, "**Kathy Kerr:** A question.\n\n**Kerr:** Yes.")) == 100


def test_rff2_inputs_use_presenter_from_filename_metadata(monkeypatch):
    # Production metadata (parse_filename_metadata) has "presenter", not "speaker".
    seen = []
    real = tu.find_qa_sections

    def _spy(transcript, presenter=None):
        seen.append(presenter)
        return real(transcript, presenter)

    monkeypatch.setattr(tu, "find_qa_sections", _spy)
    monkeypatch.setattr(ap, "find_qa_sections", _spy)
    meta = {"presenter": "Michael Kerr", "title": "T", "event_type": "webinar", "domain": "d"}
    for call in (lambda: ap.prepare_abstract_input(meta, "## Topics\n", "## Themes\n", _formatted(), 250),
                 lambda: sp.prepare_summary_input(meta, "## Topics\n", "## Themes\n", _formatted(), 500)):
        try:
            call()
        except Exception:
            pass  # only the Q&A call is under test here
    assert seen[:2] == ["Michael Kerr", "Michael Kerr"]


# --- RF.G: curly and straight quotes are the same word ---------------------------

def _unresolved(raw, formatted):
    return fp.verify_source_fidelity(raw, formatted)["unresolved"]


HEAD = "## Section 1 – Opening Words Here Now ([00:00:00]).\n\n"


def test_rfg1_curly_quotes_are_not_differences():
    raw = "Bowen’s idea isn’t new, “he said” today.\n"
    assert _unresolved(raw, HEAD + "Bowen's idea isn't new, \"he said\" today.\n") == []


def test_rfg1_changed_word_still_reported():
    # P7: the real formatter edit from the 20:16 run must still need review.
    raw = "neither one was the victim or contributor to that, it’s true.\n"
    items = _unresolved(raw, HEAD + "neither one was the victim or perpetrator to that, it's true.\n")
    assert [(i["raw_text"], i["formatted_text"]) for i in items] == [("contributor", "perpetrator")]


def test_rfg1_real_kerr_no_quote_only_differences():
    curly = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
    items = _unresolved(_raw(), _formatted())
    assert not [i for i in items if i["raw_text"].translate(curly) == i["formatted_text"]]


# --- RF.H: a deleted chapter-title line needs no review --------------------------

def test_rfh1_deleted_title_line_is_auto():
    raw = "the mother took a\nWho Was Murray Bowen?\n1:44\nstrong view of it.\n"
    o = fp.verify_source_fidelity(raw, HEAD + "the mother took a strong view of it.\n")
    assert o["unresolved"] == []
    assert [i["auto"] for i in o["items"]] == ["chapter title"]


def test_rfh1_title_plus_speech_word_needs_review():
    # P7: the deletion must be exactly the title line, nothing more.
    raw = "the mother took a\nWho Was Murray Bowen?\n1:44\nstrong view of it.\n"
    o = fp.verify_source_fidelity(raw, HEAD + "the mother took a view of it.\n")
    assert o["unresolved"]


def test_rfh1_deleted_speech_line_needs_review():
    raw = "we began the talk\nand then he said it was over\n1:44\nfor now.\n"
    o = fp.verify_source_fidelity(raw, HEAD + "we began the talk for now.\n")
    assert o["unresolved"]


def test_rfh1_changed_title_needs_review():
    raw = "the mother took a\nWho Was Murray Bowen?\n1:44\nstrong view of it.\n"
    o = fp.verify_source_fidelity(raw, HEAD + "the mother took a Who Is Murray Bowen strong view of it.\n")
    assert o["unresolved"]


def test_rfh1_real_kerr_titles_auto():
    titles = {"Who Was Murray Bowen?", "The Family as an Emotional System"}
    items = fp.verify_source_fidelity(_raw(), _formatted())["items"]
    auto = {i["raw_text"] for i in items if i["auto"] == "chapter title"}
    assert titles <= auto


def test_rfh1_name_on_caption_line_needs_review():
    # P7 (sweep): YouTube captions put a name or phrase on its own line after a
    # timestamp; dropping it is a real change.
    raw = "0:01\nthe theory was developed by\n0:05\nMurray Bowen\n0:07\nat the NIMH.\n"
    assert _unresolved(raw, HEAD + "the theory was developed by at the NIMH.\n")
    raw = "0:01\nshe was blamed but\n0:05\nNot the Mother\n0:07\nin the end.\n"
    assert _unresolved(raw, HEAD + "she was blamed but in the end.\n")


def test_rfh1_otter_answer_turn_needs_review():
    raw = "Interviewer 0:01\nWho did it?\nMichael Kerr 0:12\nMurray Bowen\nInterviewer 0:20\nRight.\n"
    assert _unresolved(raw, HEAD + "**Interviewer:** Who did it?\n\n**Interviewer:** Right.\n")


def test_rfh1_speech_fragment_is_not_a_title():
    # Sweep: one capitalised word plus minor words is speech ("But the", "It is").
    for words in (["But", "the"], ["It", "is"], ["Bowen", "and", "the"]):
        assert not fp._looks_like_chapter_title(words)
    assert fp._looks_like_chapter_title(["What", "Remains"])


def test_rfh1_titles_listed_in_warnings():
    raw = "the mother took a\nWho Was Murray Bowen?\n1:44\nstrong view of it.\n"
    o = fp.verify_source_fidelity(raw, HEAD + "the mother took a strong view of it.\n")
    assert any("chapter-title line(s) removed" in w and "Who Was Murray Bowen?" in w
               for w in o["warnings"])


# --- RF.K: extracted quotes pass the gate's verbatim test or are dropped ----------

SPLICED = ("I think I sent him a letter about six months into my time in the Navy. He sent me "
           "a letter saying, 'Mike, if this is how you deal with your family, no wonder you had "
           "so much trouble.' You have to heal in the system.")
NAVY_SOURCE = (
    "I spent two years in the Navy after finishing my psychiatric rotation. I think I sent him "
    "a letter about six months into my time in the Navy. I was out at Great Lakes Naval "
    "Hospital. He sent me a letter saying, \"Mike, if this is how you deal with your family, no "
    "wonder you had so much trouble.\"\n\n**Interviewer:** So he was judging you for running "
    "away?\n\n**Michael Kerr:** Yeah. Right, right, right. For leaving the system. That was not "
    "his idea, leaving the system. You have to heal in the system.\n")


def test_rfk1_gate_uses_shared_predicate():
    import inspect
    src = inspect.getsource(release_gate.check_verbatim_quotes)
    assert "quote_is_verbatim_for_gate" in src
    assert not vp.quote_is_verbatim_for_gate(SPLICED, NAVY_SOURCE)[0]


def test_rfk2_verbatim_quote_kept():
    ok, _ends, _cov = vp.quote_is_verbatim_for_gate(
        "I think I sent him a letter about six months into my time in the Navy.", NAVY_SOURCE)
    assert ok


def _emphasis_response(quotes):
    return "\n\n".join(
        f'[Explicit - Clinical - Rank: 92%] Concept: Item {n} about distance and family\n"{q}"'
        for n, q in enumerate(quotes, 1))


def test_rfk2_spliced_emphasis_quote_dropped(tmp_path, monkeypatch):
    good = "I think I sent him a letter about six months into my time in the Navy."
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(ep, "_load_summary_prompt", lambda _n: "PROMPT")
    monkeypatch.setattr(ep, "_generate_summary_with_claude",
                        lambda *a, **k: _emphasis_response([SPLICED, good]))
    logger = MagicMock()
    assert ep.extract_scored_emphasis("Talk - A Person - 2021-01-01 - yaml.md", logger=logger,
                                      transcript_text=NAVY_SOURCE)
    saved = next(tmp_path.rglob("* - emphasis-scored.md")).read_text(encoding="utf-8")
    assert good in saved and "heal in the system" not in saved
    logged = [c.args[0] % c.args[1:] for c in logger.info.call_args_list]
    assert "Emphasis verbatim check: kept 1 of 2." in logged


def test_rfk2_bowen_spliced_quote_dropped():
    refs = [("Bowen's letter", SPLICED),
            ("Bowen's letter", "He sent me a letter saying, \"Mike, if this is how you deal "
                               "with your family, no wonder you had so much trouble.\"")]
    kept = ep._ground_bowen_refs(refs, NAVY_SOURCE, MagicMock())
    assert [q for _c, q in kept] == [refs[1][1]]
