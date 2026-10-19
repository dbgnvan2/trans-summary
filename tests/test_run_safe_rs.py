"""RS: runs finish on output a person would accept (docs/plan_run_safe_2026-10-14.md)."""
import logging
from types import SimpleNamespace

import pytest

import config
import transcript_utils as tu


# --- helpers ---------------------------------------------------------------------------

def _reply(n_words):
    return SimpleNamespace(
        type="message", role="assistant", stop_reason="end_turn", stop_details=None,
        model="m", content=[SimpleNamespace(type="text", text=" ".join(["word"] * n_words))],
        usage=SimpleNamespace(input_tokens=1, output_tokens=n_words,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0))


def _client(word_counts):
    """A fake client that answers with replies of the given word counts, in order."""
    replies = iter([_reply(n) for n in word_counts])
    calls = []

    class _Stream:
        def __init__(self, msg):
            self.msg = msg

        def __enter__(self):
            return SimpleNamespace(get_final_message=lambda: self.msg)

        def __exit__(self, *a):
            return False

    class _Client:
        class messages:
            @staticmethod
            def create(**kw):
                calls.append(kw)
                return next(replies)

            @staticmethod
            def stream(**kw):
                calls.append(kw)
                return _Stream(next(replies))
    return _Client(), calls


@pytest.fixture
def quiet(monkeypatch):
    """No effort setting, no sleeping; token-usage rows captured, not written."""
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: None))
    monkeypatch.setattr("time.sleep", lambda s: None)
    rows = []
    monkeypatch.setattr(tu, "log_token_usage",
                        lambda script, model, usage, stop: rows.append((usage.output_tokens, stop)))
    return rows


def _call(client, logger=None, **kw):
    lo, hi = config.summary_word_bounds(650)  # 553-780
    args = dict(model="claude-sonnet-5-5", messages=[{"role": "user", "content": "x"}],
                max_tokens=4096, min_words=lo, max_words=hi, max_retries=3,
                logger=logger or logging.getLogger("rs_test"))
    args.update(kw)
    return tu.call_claude_with_retry(client, **args)


# --- RS.1: a word-count miss never fails summary, abstract or overview -----------------

def test_rs1a_soft_keeps_closest_after_last_try(quiet, caplog):
    """Run 7: 580 and 562 words on every try failed the summary stage. Soft limits keep
    the reply closest to the range after the last try, with a warning."""
    client, calls = _client([516, 540, 530])
    with caplog.at_level(logging.WARNING, logger="rs_test"):
        msg = _call(client, word_limits="soft")
    assert len(tu.response_text(msg).split()) == 540
    assert len(calls) == 3
    kept = [r for r in caplog.records if "closest" in r.getMessage()]
    assert kept and kept[0].levelno == logging.WARNING
    assert "540" in kept[0].getMessage() and "553" in kept[0].getMessage()


def test_rs1a_soft_keeps_closest_over_the_top(quiet):
    """Run 8: abstract drafts of 274 and 266 words against a 249 limit."""
    client, _ = _client([274, 266, 270])
    msg = _call(client, word_limits="soft", min_words=0, max_words=249)
    assert len(tu.response_text(msg).split()) == 266


def test_rs1b_soft_returns_first_reply_in_range(quiet):
    client, calls = _client([600, 700])
    msg = _call(client, word_limits="soft")
    assert len(tu.response_text(msg).split()) == 600
    assert len(calls) == 1


def test_rs1c_hard_still_raises(quiet):
    client, calls = _client([516, 540, 530])
    with pytest.raises(ValueError, match="too short"):
        _call(client)
    assert len(calls) == 3


def test_rs1c_unknown_mode_is_refused(quiet):
    client, calls = _client([600])
    with pytest.raises(ValueError, match="word_limits"):
        _call(client, word_limits="loose")
    assert calls == []


def test_rs1d_soft_does_not_soften_other_checks(quiet):
    """A reply that misses the range AND fails check_reply is never kept."""
    def reject(text):
        raise ValueError("bad reply")
    client, calls = _client([516, 540, 530])
    with pytest.raises(ValueError, match="bad reply"):
        _call(client, word_limits="soft", check_reply=reject)
    assert len(calls) == 3


def test_rs1d_soft_does_not_keep_too_few_characters(quiet):
    client, _ = _client([3, 3, 3])
    with pytest.raises(ValueError, match="chars"):
        _call(client, word_limits="soft", min_length=50)


def test_rs1d_soft_keeps_earlier_miss_when_last_try_fails_otherwise(quiet):
    """The kept reply passed every other check; a later broken reply does not discard it."""
    client, _ = _client([540, 3])
    msg = _call(client, word_limits="soft", min_length=50, max_retries=2)
    assert len(tu.response_text(msg).split()) == 540


def _raising_client(word_counts, error):
    """Replies of the given word counts, then ``error`` (an exception or a reply object)
    on every later call."""
    replies = [_reply(n) for n in word_counts]
    calls = []

    class _Stream:
        def __enter__(self):
            calls.append(1)
            if len(calls) <= len(replies):
                msg = replies[len(calls) - 1]
            elif isinstance(error, Exception):
                raise error
            else:
                msg = error
            return SimpleNamespace(get_final_message=lambda: msg)

        def __exit__(self, *a):
            return False

    class _Client:
        class messages:
            @staticmethod
            def stream(**kw):
                return _Stream()
    return _Client(), calls


def test_rs1d_held_reply_kept_when_later_try_times_out(quiet):
    """Review: a near-miss reply held under soft limits was lost (and its tokens never
    logged) when a later try raised an API error."""
    import anthropic
    import httpx
    rows = quiet
    timeout = anthropic.APITimeoutError(request=httpx.Request("POST", "https://x"))
    client, calls = _raising_client([540], timeout)
    msg = _call(client, word_limits="soft", stream=True)
    assert len(tu.response_text(msg).split()) == 540 and len(calls) == 3
    assert rows == [(540, "end_turn")]


def test_rs1d_held_reply_kept_when_later_reply_is_cut_off(quiet):
    rows = quiet
    cut = _reply(900)
    cut.stop_reason = "max_tokens"
    client, calls = _raising_client([540], cut)
    msg = _call(client, word_limits="soft", stream=True)
    assert len(tu.response_text(msg).split()) == 540 and len(calls) == 2
    assert sorted(rows) == [(540, "end_turn"), (900, "rejected:max_tokens")]


def test_rs1d_no_held_reply_still_raises_on_api_error(quiet):
    import anthropic
    import httpx
    timeout = anthropic.APITimeoutError(request=httpx.Request("POST", "https://x"))
    client, _ = _raising_client([], timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        _call(client, word_limits="soft", stream=True)


def test_rs1g_far_miss_is_not_kept(quiet):
    """Review: a 56-word non-answer was kept against the overview's 800 floor. Soft limits
    keep only a reply within SOFT_WORD_LIMIT_TOLERANCE of the range."""
    client, _ = _client([60, 60, 60])
    with pytest.raises(ValueError, match="too short"):
        _call(client, word_limits="soft")
    floor = config.summary_word_bounds(650)[0] * (1 - config.SOFT_WORD_LIMIT_TOLERANCE)
    client, _ = _client([int(floor) - 1, int(floor) + 1, 60])
    msg = _call(client, word_limits="soft")
    assert len(tu.response_text(msg).split()) == int(floor) + 1
    client, _ = _client([400, 320, 330])  # over the top: 249 * 1.25 = 311
    with pytest.raises(ValueError, match="too long"):
        _call(client, word_limits="soft", min_words=0, max_words=249)


def test_rs1e_summary_and_abstract_use_soft_limits(monkeypatch):
    import abstract_pipeline as ap
    import summary_pipeline as sp
    seen = []

    def fake_call(**kw):
        seen.append(kw)
        raise RuntimeError("stop")
    monkeypatch.setattr(sp, "call_claude_with_retry", fake_call)
    monkeypatch.setattr(ap, "call_claude_with_retry", fake_call)
    si = sp.prepare_summary_input(
        metadata={"title": "T", "presenter": "P", "date": "2021-01-01"}, topics_markdown=
        "## Topics\n\n### A\nD.\n*_(~50% of transcript; Sections 1-2)_*\n",
        themes_markdown="", transcript="## Section 1\nKerr said things.\n")
    with pytest.raises(RuntimeError):
        sp.generate_summary(si, api_client=object(), model="claude-sonnet-5-5")
    ai = ap.prepare_abstract_input(
        metadata={"title": "T", "presenter": "P", "date": "2021-01-01"},
        topics_markdown="## Topics\n\n### A\nD.\n*_(~50% of transcript; Sections 1-2)_*\n",
        themes_markdown="", transcript="## Section 1\nKerr said things.\n")
    with pytest.raises(RuntimeError):
        ap.generate_abstract(ai, api_client=object(), model="claude-sonnet-5-5")
    assert [kw.get("word_limits") for kw in seen] == ["soft", "soft"]


def test_rs1e_formatting_keeps_hard_limits(monkeypatch):
    """Formatting's floor (half the raw words) guards against a cut-off reply."""
    import formatting_pipeline as fp
    seen = {}

    def fake_call(**kw):
        seen.update(kw)
        raise RuntimeError("stop")
    monkeypatch.setattr(fp, "call_claude_with_retry", fake_call)
    monkeypatch.setattr(fp, "get_anthropic_client", lambda *a, **k: object())
    with pytest.raises(RuntimeError):
        fp.format_transcript_with_claude("one two three four", "Format this.",
                                         model="claude-sonnet-5-5",
                                         logger=logging.getLogger("rs_test"))
    assert seen["min_words"] == 2
    assert seen.get("word_limits", "hard") == "hard"


def test_rs1f_kept_reply_logged_as_call_not_rejected(quiet):
    rows = quiet
    client, _ = _client([516, 540, 530])
    _call(client, word_limits="soft")
    assert sorted(rows) == sorted([(516, "rejected:end_turn"), (530, "rejected:end_turn"),
                                   (540, "end_turn")])


# --- RS.2: a retried check logs a warning, not an error --------------------------------

def test_rs2a_retried_miss_logs_warning(quiet, caplog):
    """Run 8: a stage that passed showed "2 error(s)" from two retried length misses."""
    client, _ = _client([516, 600])
    with caplog.at_level(logging.DEBUG, logger="rs_test"):
        _call(client)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("516" in r.getMessage() and r.levelno == logging.WARNING
               for r in caplog.records)


def test_rs2b_final_miss_logs_error(quiet, caplog):
    client, _ = _client([516, 516, 516])
    with caplog.at_level(logging.DEBUG, logger="rs_test"), pytest.raises(ValueError):
        _call(client)
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1 and "516" in errors[0].getMessage()


def test_rs2c_soft_keep_logs_no_error(quiet, caplog):
    client, _ = _client([516, 540, 530])
    with caplog.at_level(logging.DEBUG, logger="rs_test"):
        _call(client, word_limits="soft")
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


# --- RS.5: a correct Q&A note is not sent to human review ------------------------------

def _qa_coverage_item(pct=config.ABSTRACT_QA_REQUIRED_PCT):
    import abstract_pipeline as ap
    import abstract_validation as av
    ai = ap.AbstractInput(
        metadata={"title": "Talk", "presenter": "A Person", "date": "2021-01-01"},
        topics=[ap.Topic(name="Cancer as a niche problem", percentage=37, sections="6-7")],
        themes=[], opening_purpose="o", closing_conclusion=config.NO_CONCLUSION_TEXT,
        qa_percentage=pct, qa_topics=[], target_word_count=200)
    return [i for i in av.generate_coverage_items(ai) if i.category == "qa"][0]


def test_rs5a_one_qa_marker_is_high_confidence():
    """Run 8: both abstracts had "The question period addressed …", yet the check listed
    "UNCERTAIN Q&A note" for review: 1 of 12 alternative phrases scored as medium."""
    import abstract_validation as av
    item = _qa_coverage_item()
    assert item.match_any is True
    note = ("The question period addressed whether David's distancing reflects true "
            "differentiation or self-preservation.")
    assert av.check_keyword_coverage(note, item) == (True, "high")


def test_rs5b_no_qa_marker_is_low():
    import abstract_validation as av
    item = _qa_coverage_item()
    prose = "The central question is how anxiety moves; the discussion then turns to cancer."
    assert av.check_keyword_coverage(prose, item) == (False, "low")


def test_rs5b_correct_note_leaves_no_review_item():
    """End to end through validate_abstract_coverage: no Q&A line in the review list."""
    import abstract_pipeline as ap
    import abstract_validation as av
    ai = ap.AbstractInput(
        metadata={"title": "Talk", "presenter": "A Person", "date": "2021-01-01"},
        topics=[], themes=[], opening_purpose="o",
        closing_conclusion=config.NO_CONCLUSION_TEXT,
        qa_percentage=config.ABSTRACT_QA_REQUIRED_PCT, qa_topics=[], target_word_count=200)
    result = av.validate_abstract_coverage(
        "A Person describes the talk. The question period addressed how families change.", ai)
    qa = [i for i in result["items"] if i["category"] == "qa"]
    assert qa and qa[0]["covered"] is True and qa[0]["confidence"] == "high"
    assert "Q&A" not in (result["human_review_checklist"] or "")


def test_rs5c_topic_items_unchanged():
    """Pinned decision (test_summary_keyword_one_of_many_is_medium): one keyword of many
    on a topic item stays medium."""
    import abstract_validation as av
    item = av.CoverageItem(category="topic", label="t", required=True,
                           keywords=["alpha"] + [f"kw{i}" for i in range(9)], source_text="t")
    assert item.match_any is False
    assert av.check_keyword_coverage("only alpha here", item) == (True, "medium")


# --- RS.4: a heading timestamp with an extra 00: group is corrected ---------------------

_RS4_RAW = "0:00\nOpening words here.\n1:02:04\nLater words here.\n"


def _rs4_formatted(ts):
    return ("## Section 1 – Opening Words Here Now ([00:00:00]).\n\nOpening words here.\n\n"
            f"## Section 2 – Later Words Here Now ([{ts}]).\n\nLater words here.\n")


def test_rs4a_extra_zero_group_rewritten():
    """Run 6, Systems Biology: a heading written ([00:01:02:04]). for 1:02:04 failed the
    heading contract and stopped Format."""
    import formatting_pipeline as fp
    formatted = _rs4_formatted("00:01:02:04")
    errors, _ = fp.validate_section_headings(formatted, _RS4_RAW)
    assert any("does not match contract" in e for e in errors)  # the defect
    fixed, rewrites = fp.normalize_heading_timestamps(formatted, _RS4_RAW)
    assert fixed == _rs4_formatted("01:02:04")
    assert rewrites == [(2, "00:01:02:04", "01:02:04")]
    assert fp.validate_section_headings(fixed, _RS4_RAW)[0] == []


def test_rs4b_not_rewritten_when_raw_lacks_the_time():
    import formatting_pipeline as fp
    raw = "0:00\nOpening words here.\n1:05:00\nLater words here.\n"
    formatted = _rs4_formatted("00:01:02:04")
    fixed, rewrites = fp.normalize_heading_timestamps(formatted, raw)
    assert fixed == formatted and rewrites == []


# --- RS.3: Format puts the source's words back by itself --------------------------------

_RS3_NAME = "Talk - A Person - 2021-01-01.txt"
_RS3_STEM = "Talk - A Person - 2021-01-01"


@pytest.fixture
def rs3_project(tmp_path, monkeypatch):
    src, projects = tmp_path / "source", tmp_path / "projects"
    src.mkdir()
    (projects / _RS3_STEM).mkdir(parents=True)
    monkeypatch.setattr(config, "SOURCE_DIR", src)
    monkeypatch.setattr(config, "PROJECTS_DIR", projects)
    monkeypatch.setattr(config, "PATTERNS_DIR", tmp_path / "patterns", raising=False)
    monkeypatch.setattr(config, "VALIDATION_APPROVED_TERMS_PATH", tmp_path / "none.txt",
                        raising=False)

    def write(raw, fmt):
        (src / _RS3_NAME).write_text(raw, encoding="utf-8")
        path = projects / _RS3_STEM / f"{_RS3_STEM}{config.SUFFIX_FORMATTED}"
        path.write_text(fmt, encoding="utf-8")
        return path
    return write


def _rs3_gui(monkeypatch):
    from pathlib import Path
    from unittest.mock import MagicMock

    import ts_gui
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.logger = logging.getLogger("rs3_test")
    gui.lines = []
    gui.log = lambda msg, *a: gui.lines.append(msg % a if a else msg)
    gui.root = MagicMock()
    gui.selected_file = Path(_RS3_NAME)
    gui.base_name = _RS3_STEM
    gui.pattern_set_var = MagicMock(get=MagicMock(return_value=ts_gui.PATTERN_SET_NONE))
    gui._open_review_if_needed = MagicMock(return_value=True)
    monkeypatch.setattr(ts_gui.pipeline, "format_transcript", lambda *a, **k: True)
    return gui


# Long enough that one dropped word stays under the gross limit (1.5%).
_RS3_BODY = " ".join(["The family meets each week to talk about the past year."] * 10)
_RS3_RAW = f"Speaker 1  0:01\nWe do not accept that idea here, and we say so. {_RS3_BODY}\n"
_RS3_FMT = ("## Section 1 – Accepting That Idea Here ([00:00:01]).\n\n"
            f"We do accept that idea here, and we say so. {_RS3_BODY}\n")


def test_rs3a_dropped_word_restored_and_format_passes(rs3_project, monkeypatch, caplog):
    """Runs 4, 6, 7: one or two dropped words ("that,", "the,") stopped Format for a
    person's review and blocked all four publish stages. A stage that passes after the
    restore logs no error (review: the first check logged "Validation FAILED")."""
    import formatting_pipeline as fp
    path = rs3_project(_RS3_RAW, _RS3_FMT)
    gui = _rs3_gui(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger="rs3_test"):
        assert gui._run_format_and_validate() is True
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not [r for r in caplog.records if "FAILED" in r.getMessage()]
    assert not [line for line in gui.lines if "❌" in line]
    assert "We do not accept that idea here, and we say so." in path.read_text(encoding="utf-8")
    assert fp.load_format_validation_record(_RS3_STEM)["passed"] is True
    gui._open_review_if_needed.assert_not_called()


def test_rs3b_restore_is_logged_and_recorded(rs3_project, monkeypatch):
    import format_review as fr
    rs3_project(_RS3_RAW, _RS3_FMT)
    gui = _rs3_gui(monkeypatch)
    gui._run_format_and_validate()
    restored = [line for line in gui.lines if "Restored the source's words" in line]
    assert len(restored) == 1 and restored[0].startswith("⚠️")
    assert "section 1" in restored[0] and "'not'" in restored[0]
    log = fr._load_review(_RS3_STEM)["log"]
    assert [(e["reviewer"], e["action"], e["raw_text"]) for e in log] == [
        (fr.AUTO_REVIEWER, "reject", "not")]
    # Counted apart from a person's decisions.
    assert fr.review_counts(_RS3_STEM) == {"accept": 0, "edit": 0, "reject": 0,
                                           "auto_restored": 1}


def test_rs3c_heading_boundary_difference_still_needs_review(rs3_project, monkeypatch, caplog):
    raw = (f"Speaker 1  0:01\n{_RS3_BODY} First part ends here. Dropped words. "
           f"Second part starts. {_RS3_BODY}\n")
    fmt = ("## Section 1 – The First Part Ends Here ([00:00:01]).\n\n"
           f"{_RS3_BODY} First part ends here.\n\n"
           "## Section 2 – The Second Part Starts Now ([00:00:01]).\n\n"
           f"Second part starts. {_RS3_BODY}\n")
    path = rs3_project(raw, fmt)
    gui = _rs3_gui(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger="rs3_test"):
        assert gui._run_format_and_validate() is False
    assert path.read_text(encoding="utf-8") == fmt
    gui._open_review_if_needed.assert_called_once()
    # Nothing could be restored: the final check reports the failure in full.
    assert any("Validation FAILED" in r.getMessage() and r.levelno == logging.ERROR
               for r in caplog.records)


def test_rs3c_restores_plain_ones_and_leaves_boundary_one(rs3_project, monkeypatch):
    raw = (f"Speaker 1  0:01\nWe do not accept that idea. {_RS3_BODY} First part ends here. "
           f"Dropped words. Second part starts. {_RS3_BODY}\n")
    fmt = ("## Section 1 – The First Part Ends Here ([00:00:01]).\n\n"
           f"We do accept that idea. {_RS3_BODY} First part ends here.\n\n"
           "## Section 2 – The Second Part Starts Now ([00:00:01]).\n\n"
           f"Second part starts. {_RS3_BODY}\n")
    path = rs3_project(raw, fmt)
    gui = _rs3_gui(monkeypatch)
    assert gui._run_format_and_validate() is False
    text = path.read_text(encoding="utf-8")
    assert "We do not accept that idea." in text and "Dropped words." not in text
    gui._open_review_if_needed.assert_called_once()


def test_rs3d_gross_limits_still_fail(rs3_project, monkeypatch):
    words = " ".join(f"word{i}" for i in range(40))
    other = " ".join(f"other{i}" for i in range(40))
    raw = f"Speaker 1  0:01\nThe start. {words} The end.\n"
    fmt = f"## Section 1 – The Start And The End ([00:00:01]).\n\nThe start. {other} The end.\n"
    path = rs3_project(raw, fmt)
    gui = _rs3_gui(monkeypatch)
    assert gui._run_format_and_validate() is False
    assert path.read_text(encoding="utf-8") == fmt
    assert not [line for line in gui.lines if "Restored" in line]


def test_rs3e_release_gate_source_fidelity_passes_after_restore(rs3_project, monkeypatch):
    import release_gate as rg
    rs3_project(_RS3_RAW, _RS3_FMT)
    assert rg.check_source_fidelity(_RS3_STEM).status == rg.Status.FAIL
    _rs3_gui(monkeypatch)._run_format_and_validate()
    assert rg.check_source_fidelity(_RS3_STEM).status == rg.Status.PASS


def test_rs3f_validate_format_stays_read_only(rs3_project):
    """The CLI and the after-review re-check do not restore anything."""
    import formatting_pipeline as fp
    path = rs3_project(_RS3_RAW, _RS3_FMT)
    assert fp.validate_format(_RS3_NAME, logger=logging.getLogger("rs3_test")) is False
    assert path.read_text(encoding="utf-8") == _RS3_FMT


# --- RS.6: after a failed faithfulness check, fix the flagged sentences ------------------

def _loop(monkeypatch, verdicts, generate, revise, advisory=False):
    from unittest.mock import MagicMock

    import extraction_pipeline as ep
    # WO4: a kept draft fails its stage only on a name the gate's entity check
    # rejects. There is no source here, so that check is stubbed.
    import release_gate as rg
    monkeypatch.setattr(rg, "check_entity_grounding", lambda *a, **k: rg.Verdict(
        "entity_grounding", rg.Status.PASS, "stub"))
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 3)
    seq, written, judged = iter(verdicts), [], []

    def precheck(*a):
        judged.append(written[-1])
        return next(seq)
    ok = ep._generate_until_faithful("overview", "B", " - x.md", MagicMock(), generate,
                                     written.append, precheck=precheck, revise=revise,
                                     advisory=advisory)
    return ok, written, judged


def test_rs6a_second_try_revises_previous_draft(monkeypatch):
    """Run 8, Why Families overview: each retry rewrote the overview from scratch and made
    a new unsupported claim; three tries never converged. Try 2 now revises try 1."""
    generated, revised = [], []
    ok, written, _ = _loop(
        monkeypatch, [("fail", ["claim X"]), ("pass", [])],
        lambda feedback: generated.append(feedback) or "draft one",
        lambda draft, claims: revised.append((draft, claims)) or "draft two")
    assert ok is True
    assert generated == [None]
    assert revised == [("draft one", ["claim X"])]
    assert written == ["draft one", "draft two"]


def test_rs6a_third_try_revises_the_second_draft(monkeypatch):
    revised = []
    drafts = iter(["draft two", "draft three"])
    ok, written, _ = _loop(
        monkeypatch, [("fail", ["claim X"]), ("fail", ["claim Y"]), ("pass", [])],
        lambda feedback: "draft one",
        lambda draft, claims: revised.append((draft, claims)) or next(drafts))
    assert ok is True
    assert revised == [("draft one", ["claim X"]), ("draft two", ["claim Y"])]


def test_rs6b_revise_prompt_has_draft_claims_and_keep_rule(monkeypatch):
    from unittest.mock import MagicMock

    import extraction_pipeline as ep
    seen = {}

    def fake(prompt, model, temperature, logger, **kw):
        seen.update(prompt=prompt, model=model, kw=kw)
        return "revised text"
    monkeypatch.setattr(ep, "_generate_summary_with_claude", fake)
    draft = "---\nslug: x {not a placeholder}\n---\nIntro stays.\n\nKerr says Bowen told him so."
    claims = ["Kerr says Bowen told him so.", "It is a talk. [in answer to: What is it?]"]
    system = [{"type": "text", "text": "TRANSCRIPT"}]
    out = ep._revise_flagged("overview post", draft, claims, model="m", system=system,
                             logger=MagicMock(), min_words=800, word_limits="soft")
    assert out == "revised text"
    prompt = seen["prompt"]
    assert draft in prompt and prompt.rstrip().endswith(draft.rstrip())
    assert "- Kerr says Bowen told him so." in prompt
    assert "- It is a talk. [in answer to: What is it?]" in prompt
    assert "overview post" in prompt and "{{" not in prompt
    assert "Leave every other sentence exactly as it is" in prompt
    assert seen["model"] == "m" and seen["kw"]["system"] == system
    assert seen["kw"]["min_words"] == 800 and seen["kw"]["word_limits"] == "soft"


def test_rs6c_revision_repeating_a_claim_is_rejected(monkeypatch):
    """A revision that leaves the flagged sentence in is rejected without a judge call."""
    drafts = iter(["It is still true that claim X holds.", "clean draft"])
    ok, written, judged = _loop(
        monkeypatch, [("fail", ["claim X holds."]), ("pass", [])],
        lambda feedback: "draft one", lambda draft, claims: next(drafts))
    assert ok is True
    assert written[-1] == "clean draft"
    assert judged == ["draft one", "clean draft"]


def test_rs6e_all_tries_fail_still_blocks_or_warns(monkeypatch):
    """Since WO4 (2026-10-19) a kept draft with only flagged claims warns in both
    modes; it used to fail the stage when not advisory."""
    verdicts = [("fail", ["claim A.", "claim B."]), ("fail", ["claim A."]),
                ("fail", ["claim A.", "claim C."])]
    for advisory, expected in ((False, True), (True, True)):
        drafts = iter(["draft two", "draft three"])
        ok, written, _ = _loop(monkeypatch, verdicts, lambda feedback: "draft one",
                               lambda draft, claims: next(drafts), advisory=advisory)
        assert ok is expected
        assert written[-1] == "draft two"  # fewest claims kept


def test_rs6d_summary_passes_revise(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    import extraction_pipeline as ep
    base = "Talk - A Person - 2021-01-01"
    (tmp_path / base).mkdir()
    (tmp_path / base / f"{base}{config.SUFFIX_TOPICS}").write_text(
        "## Topics\n\n### Topic A\nD.\n*_(~20% of transcript; Sections 1)_*\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(ep, "load_project_transcript", lambda *a, **k: "## Section 1\nText.\n")
    monkeypatch.setattr(ep, "create_system_message_with_cache",
                        lambda _t: [{"type": "text", "text": "c"}])
    monkeypatch.setattr(ep, "get_anthropic_client", lambda: object())
    seen = {}

    def fake_loop(what, *a, revise=None, **k):
        seen[what] = revise
        return True
    monkeypatch.setattr(ep, "_generate_until_faithful", fake_loop)
    revised = {}
    monkeypatch.setattr(ep, "_revise_flagged",
                        lambda what, draft, claims, **k: revised.update(what=what, **k) or "r")
    assert ep.generate_structured_summary(base, logger=MagicMock(), model="m") is True
    assert seen["summary"]("draft", ["claim"]) == "r"
    lo, hi = config.summary_word_bounds(config.DEFAULT_SUMMARY_WORD_COUNT)
    assert revised["what"] == "summary"
    assert (revised["min_words"], revised["max_words"], revised["word_limits"]) == (lo, hi, "soft")


def test_rs3g_stale_check_record_restores_nothing(rs3_project, monkeypatch):
    """Review: restore trusted the latest check record without checking it was for the
    current files; a stale record could write an older raw version's words."""
    import format_review as fr
    import formatting_pipeline as fp
    path = rs3_project(_RS3_RAW, _RS3_FMT)
    assert fp.validate_format(_RS3_NAME, logger=logging.getLogger("rs3_test")) is False
    changed = _RS3_FMT.replace("the past year.", "the past years.", 1)
    path.write_text(changed, encoding="utf-8")  # the file moved on after the check
    result = fr.restore_source_words(_RS3_STEM)
    assert result["restored"] == [] and "not for the current transcript" in result["errors"][0]
    assert path.read_text(encoding="utf-8") == changed


def test_rs5d_qa_markers_match_whole_words():
    """Review (P7): substring matching made "question periodically" a high-confidence
    Q&A note, which skips human review."""
    import abstract_validation as av
    item = _qa_coverage_item()
    assert av.check_keyword_coverage("The question periodically returns.", item) == (False, "low")
    assert av.check_keyword_coverage("A short Q&A followed.", item) == (True, "high")
    assert av.check_keyword_coverage("In the question period, the audience asked about it.",
                                     item) == (True, "high")


def test_rs6g_unjudged_echo_draft_is_never_kept(monkeypatch):
    """Review: a revision rejected for repeating a flagged claim was never judged but
    competed for "best draft" with a count of only its echoed claims."""
    drafts = iter(["The revision keeps claim a.", "draft three"])
    ok, written, judged = _loop(
        monkeypatch, [("fail", ["claim a.", "claim b.", "claim c."]), ("fail", ["claim x.", "claim y."])],
        lambda feedback: "draft one", lambda draft, claims: next(drafts))
    assert ok is True  # WO4
    assert judged == ["draft one", "draft three"]
    assert written[-1] == "draft three"  # judged, 2 claims; not the unjudged echo


def test_rs6f_revision_reply_check():
    """Review: a revision got no check for a comment before the text, the instructions
    echoed back, or lost front matter. Run 9: a revised overview's metadata was judged
    as claims because the block no longer counted as front matter."""
    import extraction_pipeline as ep
    draft = "---\ntitle: x\nslug: y\n---\n# Heading\n\nBody text here."
    check = ep._revise_reply_check(draft)
    check("---\ntitle: x\nslug: y\n---\n# Heading\n\nBetter body text.")
    check("```yaml\ntitle: x\nslug: y\n```\n# Heading\n\nBody.")  # other form: fine
    for bad in ("Here is the revised overview post:\n\n" + draft,
                "# Heading\n\nBody text here.",                       # front matter dropped
                "---\ntitle: x\nThis line is prose now.\n---\n# Heading\n\nBody.",
                draft + "\n\nLeave every other sentence exactly as it is, word for word, "
                        "with its headings, front matter, lists and formatting."):
        with pytest.raises(ValueError):
            check(bad)
    fenced = '```yaml\nslug: "x"\ntarget_audience: "General public"\n```\n\nBody text.'
    fenced_check = ep._revise_reply_check(fenced)
    fenced_check(fenced.replace("Body text.", "Better body text."))
    with pytest.raises(ValueError):  # the fenced block no longer leads the text
        fenced_check("Overview\n\n" + fenced)
    # A flagged title must be fixable: changing a first-line heading is allowed.
    titled = ep._revise_reply_check("# Swapping One Culprit\n\nBody text.")
    titled("# Replacing the Culprit Story\n\nBody text.")
    plain = "Michael Kerr presents a talk. The question period covered X."
    plain_check = ep._revise_reply_check(plain)
    plain_check("Michael Kerr presents a lecture. The question period covered X.")
    with pytest.raises(ValueError):
        plain_check("Here is the revised abstract: Michael Kerr presents a lecture.")


def test_rs6f_revise_passes_the_reply_check(monkeypatch):
    from unittest.mock import MagicMock

    import extraction_pipeline as ep
    seen = {}
    monkeypatch.setattr(ep, "_generate_summary_with_claude",
                        lambda prompt, model, t, logger, **kw: seen.update(kw) or "x")
    ep._revise_flagged("summary", "---\nslug: a\n---\nText.", ["c"], model="m", system=None,
                       logger=MagicMock())
    with pytest.raises(ValueError):
        seen["check_reply"]("Text.")  # front matter dropped


def test_rs1h_stage_log_names_a_kept_length_miss(tmp_path, monkeypatch):
    """Review: the "kept the closest" warning went to the summary module's logger, which
    the GUI does not show; the stage log now says it."""
    from unittest.mock import MagicMock

    import extraction_pipeline as ep
    base = "Talk - A Person - 2021-01-01"
    (tmp_path / base).mkdir()
    (tmp_path / base / f"{base}{config.SUFFIX_TOPICS}").write_text(
        "## Topics\n\n### Topic A\nD.\n*_(~20% of transcript; Sections 1)_*\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(ep, "load_project_transcript", lambda *a, **k: "## Section 1\nText.\n")
    monkeypatch.setattr(ep, "create_system_message_with_cache",
                        lambda _t: [{"type": "text", "text": "c"}])
    monkeypatch.setattr(ep, "get_anthropic_client", lambda: object())
    monkeypatch.setattr(ep.summary_pipeline, "generate_summary",
                        lambda *a, **k: " ".join(["word"] * 516))
    monkeypatch.setattr(ep, "_faithfulness_precheck", lambda b, s, logger=None: ("pass", []))
    logger = MagicMock()
    assert ep.generate_structured_summary(base, logger=logger, model="m") is True
    said = [c.args[0] % c.args[1:] for c in logger.warning.call_args_list]
    assert any("516 words" in line for line in said), said


def test_rs5e_qa_note_checked_only_when_asked_for():
    """Run 9, Systems Biology: Q&A was 16% of the talk. The abstract is asked for a Q&A
    note only above ABSTRACT_QA_NOTE_MIN_PCT (20), so it had none, yet the check looked
    for one from 15% and logged "❌ MISSING [optional] Q&A note"."""
    import abstract_pipeline as ap
    import abstract_validation as av
    edge = config.ABSTRACT_QA_NOTE_MIN_PCT
    for pct in (16, edge):
        ai = ap.AbstractInput(
            metadata={"title": "T", "presenter": "P", "date": "2021-01-01"}, topics=[],
            themes=[], opening_purpose="o", closing_conclusion=config.NO_CONCLUSION_TEXT,
            qa_percentage=pct, qa_topics=[], target_word_count=200)
        assert '"include_qa_note": false' in ai.to_json()
        assert not [i for i in av.generate_coverage_items(ai) if i.category == "qa"], pct
    asked = ap.AbstractInput(
        metadata={"title": "T", "presenter": "P", "date": "2021-01-01"}, topics=[],
        themes=[], opening_purpose="o", closing_conclusion=config.NO_CONCLUSION_TEXT,
        qa_percentage=edge + 1, qa_topics=[], target_word_count=200)
    assert '"include_qa_note": true' in asked.to_json()
    assert [i for i in av.generate_coverage_items(asked) if i.category == "qa"]
