"""WO (docs/plan_warn_only_2026-10-19.md): faithfulness flags warn and never block.

User decision 2026-10-19: "Warn only, never block. Add the no-outside-facts rule to all
prose prompts, show the % score with the flagged claims as warnings." The entity check
(a name not in the source) still blocks."""
from unittest.mock import MagicMock, patch

import pytest

import config
import extraction_pipeline as ep
import faithfulness_judge as fj
import release_gate as rg

SRC = ("Section 1. The speaker opens by thanking the hosts for the invitation today. "
       "Section 9. The speaker said the roof leaked after the storm last year.")
WRONG_CLAIM = "The speaker says the garden will reopen in spring."
NQR_CLAIM = "The speaker closes by thanking the hosts."

# --- WO1: no outside facts in any prose prompt ---------------------------------------

PROSE_PROMPTS = ("PROMPT_STRUCTURED_SUMMARY_FILENAME", "PROMPT_STRUCTURED_ABSTRACT_FILENAME",
                 "PROMPT_OVERVIEW_FILENAME", "PROMPT_BLOG_FILENAME")
# One phrase per part of the rule.
WO1_PHRASES = ("No outside facts",
               "Do not spell out an abbreviation",
               "first name, age, place, occupation, affiliation or family fact",
               "even if you know it")


@pytest.mark.parametrize("name", PROSE_PROMPTS)
def test_wo1_prose_prompts_forbid_outside_facts(name):
    """JS6: 6 of the 12 summary drafts that failed had an outside fact in them
    ("KCFC" spelled out, an age, a first name, "late grandmother")."""
    text = " ".join((config.PROMPTS_DIR / getattr(config, name)).read_text(
        encoding="utf-8").split())
    for phrase in WO1_PHRASES:
        assert phrase in text, (name, phrase)


def test_wo1_rule_is_in_the_summary_prompt_sent(monkeypatch):
    import summary_pipeline as sp
    seen = {}

    def fake_call(**kw):
        seen.update(kw)
        raise RuntimeError("stop")
    monkeypatch.setattr(sp, "call_claude_with_retry", fake_call)
    si = sp.prepare_summary_input(
        metadata={"title": "T", "presenter": "P", "date": "2021-01-01"}, topics_markdown=
        "## Topics\n\n### A\nD.\n*_(~50% of transcript; Sections 1-2)_*\n",
        themes_markdown="", transcript="## Section 1\nKerr said things.\n")
    with pytest.raises(RuntimeError, match="stop"):
        sp.generate_summary(si, api_client=object(), model="m")
    prompt = " ".join(seen["messages"][0]["content"].split())
    for phrase in WO1_PHRASES:
        assert phrase in prompt, phrase


# --- WO2/WO3: the gate warns, with a score -------------------------------------------

def _result(n_ok, wrong=(), nqr=()):
    claims = [fj.ClaimVerdict(f"Fine claim {i}.", fj.ENTAILED) for i in range(n_ok)]
    claims += [fj.ClaimVerdict(c, fj.UNSUPPORTED, "r", severity=fj.WRONG, severity_type="W1")
               for c in wrong]
    claims += [fj.ClaimVerdict(c, fj.UNSUPPORTED, "r", severity=fj.NOT_QUITE_RIGHT,
                               severity_type="N3", evidence="the speaker opens by thanking")
               for c in nqr]
    return fj.FaithfulnessResult(fj.FAIL if wrong else fj.PASS, "d", claims=claims,
                                 judged=len(claims))


def _setup(tmp_path, monkeypatch, suffixes):
    base = "T - P - 2026-01-01"
    proj = tmp_path / base
    proj.mkdir()
    for s in suffixes:
        (proj / f"{base}{s}").write_text(f"text of {s}", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(rg, "_FAITHFULNESS_CACHE", {})
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True)
    return base


def _check(base, suffixes, results):
    """check_faithfulness with the judge stubbed: one result per artifact, in order."""
    queue = list(results)
    with patch.object(rg, "_source_with_metadata", return_value=SRC), \
            patch("transcript_utils.resolve_anthropic_key", return_value="k"), \
            patch("transcript_utils.get_anthropic_client", return_value=object()), \
            patch.object(rg, "_judge_cached", side_effect=lambda *a, **k: queue.pop(0)):
        return rg.check_faithfulness(base, None, suffixes=suffixes)


def test_wo2_wrong_claim_warns_and_gate_allows(tmp_path, monkeypatch):
    s = config.SUFFIX_SUMMARY_GEN
    base = _setup(tmp_path, monkeypatch, [s])
    v = _check(base, [s], [_result(9, wrong=[WRONG_CLAIM])])
    assert v.status is rg.Status.WARN
    assert "1 wrong claim(s) flagged in" in v.detail
    assert "publication goes on" in v.detail
    # The flagged claim stays in items, where generation reads it to revise.
    assert v.items[0]["unfaithful"] == [WRONG_CLAIM]
    assert "faithfulness" not in config.GATE_BLOCKING_CHECKS
    decision = rg.decide([v])
    assert decision.decision is rg.Decision.ALLOW_WITH_WARNINGS and decision.allowed


def test_wo2_judge_error_does_not_block():
    """A judge that could not run is reported as unverified, and does not block."""
    v = rg.Verdict("faithfulness", rg.Status.ERROR, "judge error: TimeoutError")
    assert rg.decide([v]).decision is rg.Decision.ALLOW_WITH_WARNINGS


def test_wo2_error_detail_does_not_state_the_policy(tmp_path, monkeypatch):
    """Whether a check blocks is config (GATE_BLOCKING_CHECKS); the detail must not
    say "not blocking", which would be false if faithfulness were put back in the
    set. The log tag says it, from the decision (verdict_warning_lines)."""
    s1, s2 = config.SUFFIX_SUMMARY_GEN, config.SUFFIX_ABSTRACT_GEN
    base = _setup(tmp_path, monkeypatch, [s1, s2])
    v = _check(base, [s1, s2], [_result(9, wrong=[WRONG_CLAIM]),
                                fj.FaithfulnessResult(fj.ERROR, "judge error")])
    assert v.status is rg.Status.ERROR
    assert "1 of 2 artifact(s) could not be verified" in v.detail
    assert "blocking" not in v.detail
    monkeypatch.setattr(config, "GATE_BLOCKING_CHECKS",
                        config.GATE_BLOCKING_CHECKS | {"faithfulness"})
    assert rg.decide([v]).decision is rg.Decision.BLOCK


def test_wo2_entity_check_still_blocks():
    """Adversarial: dropping faithfulness from the blocking set must not loosen the
    entity check (a name not in the source)."""
    names = rg.Verdict("entity_grounding", rg.Status.FAIL, "1 name not in source")
    faith = rg.Verdict("faithfulness", rg.Status.WARN, "flagged")
    assert rg.decide([faith, names]).decision is rg.Decision.BLOCK


def test_wo3_score_in_detail_and_items(tmp_path, monkeypatch):
    s1, s2 = config.SUFFIX_SUMMARY_GEN, config.SUFFIX_ABSTRACT_GEN
    base = _setup(tmp_path, monkeypatch, [s1, s2])
    v = _check(base, [s1, s2], [_result(8, wrong=[WRONG_CLAIM], nqr=[NQR_CLAIM]),
                                _result(4)])
    assert v.status is rg.Status.WARN
    assert "1 wrong and 1 not quite right claim(s) flagged" in v.detail
    summary, abstract = s1.strip(" -").removesuffix(".md"), s2.strip(" -").removesuffix(".md")
    assert f"{summary} 80% (8 of 10 claims supported)" in v.detail
    assert f"{abstract} 100% (4 of 4 claims supported)" in v.detail
    scores = [i for i in v.items if "score_pct" in i]
    assert [(i["claims_judged"], i["flagged"], i["supported"], i["score_pct"])
            for i in scores] == [(10, 2, 8, 80), (4, 0, 4, 100)]


def test_wo3_pass_shows_score(tmp_path, monkeypatch):
    s = config.SUFFIX_SUMMARY_GEN
    base = _setup(tmp_path, monkeypatch, [s])
    v = _check(base, [s], [_result(12)])
    assert v.status is rg.Status.PASS
    assert "100% (12 of 12 claims supported)" in v.detail


def test_wo3_unknown_count_is_not_shown_as_a_score():
    """Adversarial: a result with flags but no claim count must not read as 0% or
    100%."""
    r = fj.FaithfulnessResult(fj.FAIL, "d", claims=[
        fj.ClaimVerdict(WRONG_CLAIM, fj.UNSUPPORTED, severity=fj.WRONG)], judged=0)
    rec = rg._score_record("summary.md", r)
    assert rec["score_pct"] is None and rec["supported"] is None
    assert "claim count not known" in rg._score_text([rec])


def test_wo3_cached_pass_keeps_its_claim_count(tmp_path, monkeypatch):
    """Dirty state (P8): a PASS stored in the disk cache by one process is replayed
    by the next (fresh memory cache) with its claim count, so the score survives."""
    s = config.SUFFIX_SUMMARY_GEN
    base = _setup(tmp_path, monkeypatch, [s])
    calls = []

    def judge(text, source, client, logger=None):
        calls.append(text)
        return _result(9, nqr=[NQR_CLAIM])

    with patch.object(rg, "_source_with_metadata", return_value=SRC), \
            patch("transcript_utils.resolve_anthropic_key", return_value="k"), \
            patch("transcript_utils.get_anthropic_client", return_value=object()), \
            patch.object(fj, "judge_artifact", new=judge):
        first = rg.check_faithfulness(base, None, suffixes=[s])
        monkeypatch.setattr(rg, "_FAITHFULNESS_CACHE", {})  # a new process
        second = rg.check_faithfulness(base, None, suffixes=[s])
    assert len(calls) == 1  # the second check was served from the disk cache
    assert "90% (9 of 10 claims supported)" in first.detail
    assert "90% (9 of 10 claims supported)" in second.detail


def test_wo3_logic_version_bumped():
    """Cache entries written before WO have no claim count; the bump keeps them from
    being served."""
    assert config.JUDGE_LOGIC_VERSION >= "2026-10-19b"


# --- WO4: generation keeps the best draft and goes on --------------------------------

def _entity(status):
    return lambda base, logger=None, suffixes=None: rg.Verdict(
        "entity_grounding", status, f"entity {status.value}",
        items=[{"names": ["Ann Example"]}] if status is rg.Status.FAIL else [])


def _run_all_fail(monkeypatch, entity_status):
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 2)
    monkeypatch.setattr(rg, "check_entity_grounding", _entity(entity_status))
    written, n = [], iter(range(10))
    logger = MagicMock()
    ok = ep._generate_until_faithful(
        "summary", "B", config.SUFFIX_SUMMARY_GEN, logger,
        generate=lambda feedback: f"draft {next(n)}", write=written.append,
        precheck=lambda base, suffix, logger=None: ("fail", [WRONG_CLAIM]))
    return ok, written, logger


def test_wo4_summary_kept_with_flags_stage_succeeds(monkeypatch):
    ok, written, logger = _run_all_fail(monkeypatch, rg.Status.PASS)
    assert ok is True
    assert written[-1] == "draft 1"  # the best draft (a tie keeps the later one)
    assert not logger.error.called
    msg = logger.warning.call_args_list[-1].args[0]
    assert "Faithfulness flags are warnings" in msg


def test_wo4_summary_kept_with_name_stage_fails(monkeypatch):
    ok, _, logger = _run_all_fail(monkeypatch, rg.Status.FAIL)
    assert ok is False
    assert "BLOCK" in logger.error.call_args.args[0]


def test_wo4_entity_check_error_still_fails_stage(monkeypatch):
    """Adversarial: an entity check that could not run blocks at the gate
    (GATE_ERROR_BLOCKS), so the stage must not report success."""
    ok, _, _ = _run_all_fail(monkeypatch, rg.Status.ERROR)
    assert ok is False


# --- WO5: the run log lists the flagged claims ---------------------------------------

def test_wo5_gui_lists_flagged_claims_on_allow():
    faith = rg.Verdict("faithfulness", rg.Status.WARN, "1 wrong and 1 not quite right", items=[
        {"artifact": "summary-generated.md", "unfaithful": [WRONG_CLAIM],
         "wrong": [{"claim": WRONG_CLAIM}],
         "not_quite_right": [{"claim": NQR_CLAIM, "type": "N3"}]}])
    topic = rg.Verdict("topic_term_faithfulness", rg.Status.FAIL, "2 topics ungrounded")
    unverified = rg.Verdict("faithfulness", rg.Status.ERROR, "judge error")
    decision = rg.decide([faith, topic, unverified,
                          rg.Verdict("source_fidelity", rg.Status.PASS, "ok")])
    assert decision.decision is rg.Decision.ALLOW_WITH_WARNINGS
    lines = rg.verdict_warning_lines(decision)
    assert lines == [
        "[WARN] faithfulness: 1 wrong and 1 not quite right",
        f"  - [summary-generated] wrong: {WRONG_CLAIM}",
        f"  - [summary-generated] not quite right: {NQR_CLAIM}",
        "[FAIL, not blocking] topic_term_faithfulness: 2 topics ungrounded",
        "[UNVERIFIED, not blocking] faithfulness: judge error",
    ]


def _faith_warn():
    return rg.Verdict("faithfulness", rg.Status.WARN, "1 wrong and 1 not quite right", items=[
        {"artifact": "summary-generated.md", "unfaithful": [WRONG_CLAIM],
         "wrong": [{"claim": WRONG_CLAIM}],
         "not_quite_right": [{"claim": NQR_CLAIM, "type": "N3"}]}])


def _stub_checks(*verdicts):
    return [(v.check, lambda base_name, logger=None, v=v: v) for v in verdicts]


def test_wo5_run_gate_logs_flagged_claims_for_every_caller(caplog):
    """publish_allowed (html_generator, packaging, bundle export, CLI) logs the
    faithfulness warning with each flagged claim, and an advisory ERROR as
    UNVERIFIED, not only the "N warn(s)" count."""
    import logging
    checks = _stub_checks(_faith_warn(), rg.Verdict("fake_advisory", rg.Status.ERROR, "judge error"),
                          rg.Verdict("source_fidelity", rg.Status.PASS, "ok"))
    with patch.object(rg, "DEFAULT_CHECKS", checks), patch.object(rg, "record_decision"), \
            caplog.at_level(logging.WARNING, logger="wo5"):
        assert rg.publish_allowed("Sample", logging.getLogger("wo5")) is True
    warned = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("[WARN] faithfulness: 1 wrong and 1 not quite right" in m for m in warned)
    assert any(f"[summary-generated] wrong: {WRONG_CLAIM}" in m for m in warned)
    assert any(f"[summary-generated] not quite right: {NQR_CLAIM}" in m for m in warned)
    assert any("[UNVERIFIED, not blocking] fake_advisory: judge error" in m for m in warned)
    assert not any("source_fidelity" in m for m in warned)


def test_wo5_gui_log_shows_flagged_claims_once():
    """The GUI's publish log gets the lines through its logger, from the real
    run_gate, once each (the GUI no longer prints its own copy)."""
    import ts_gui
    logs = []
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = "Sample"
    gui.log = lambda *a, **_k: logs.append(" ".join(str(x) for x in a))
    gui.logger = ts_gui.GuiLoggerAdapter(gui)
    checks = _stub_checks(_faith_warn(), rg.Verdict("fake_advisory", rg.Status.ERROR, "judge error"))
    with patch.object(rg, "DEFAULT_CHECKS", checks), patch.object(rg, "record_decision"):
        assert gui._publication_blocked("webpage/PDF") is False
    for text in (f"[summary-generated] wrong: {WRONG_CLAIM}",
                 f"[summary-generated] not quite right: {NQR_CLAIM}",
                 "[UNVERIFIED, not blocking] fake_advisory: judge error"):
        assert sum(text in line for line in logs) == 1, (text, logs)


def test_wo5_blockers_are_not_listed_as_warnings():
    names = rg.Verdict("entity_grounding", rg.Status.FAIL, "1 name not in source")
    faith = rg.Verdict("faithfulness", rg.Status.WARN, "flagged")
    lines = rg.verdict_warning_lines(rg.decide([names, faith]))
    assert lines == ["[WARN] faithfulness: flagged"]
