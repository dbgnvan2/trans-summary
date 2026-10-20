"""JS (docs/plan_judge_severity_2026-10-19.md): a faithfulness flag fails the run only
when the claim is WRONG; a claim that is only NOT QUITE RIGHT passes with a warning.
Review of the 2026-10-18 flags: docs/judge_flag_review_2026-10-18.md (9 WRONG, 34 NOT
QUITE RIGHT). JS5 stops the summary prompt asking for speaker credentials the transcript
does not give."""
import config


def _summary_prompt():
    return (config.PROMPTS_DIR / config.PROMPT_STRUCTURED_SUMMARY_FILENAME).read_text(
        encoding="utf-8")


def _opening_instruction(text):
    """The text under the Opening Paragraph heading, up to the next heading."""
    after = text.split("### Opening Paragraph", 1)[1]
    return after.split("###", 1)[0]


# One phrase per point of JS5.a.
JS5_OPENING_PHRASES = (
    "by the name the transcript or recording title gives",          # who the speaker is
    "only if the transcript states them",                           # credentials
    "do not add them from other knowledge",                         # no outside facts
    "say the speaker previews or outlines it only if the speaker does",  # preview
)


# --- JS5: the opening asks only for what the transcript gives -----------------------

def test_js5a_opening_asks_only_for_what_the_transcript_gives():
    """Review flags R16, R24, R32, R36 (credentials not in the source) and R17 (a
    preview the speaker never gave) came from "Identify speaker with credentials, …
    and preview of content areas"."""
    text = _summary_prompt()
    assert "Identify speaker with credentials" not in text
    opening = " ".join(_opening_instruction(text).split())
    for phrase in JS5_OPENING_PHRASES:
        assert phrase in opening, phrase


def test_js5a_opening_instruction_is_in_the_prompt_sent(monkeypatch):
    import pytest

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
    with pytest.raises(RuntimeError, match="stop"):  # str.format raised nothing first
        sp.generate_summary(si, api_client=object(), model="m")
    prompt = " ".join(seen["messages"][0]["content"].split())
    for phrase in JS5_OPENING_PHRASES:
        assert phrase in prompt, phrase


# ===================================================================================
# JS1–JS4: the severity step
# ===================================================================================
import importlib.util
import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import faithfulness_judge as fj
import release_gate

ROOT = Path(__file__).resolve().parent.parent
SRC = ("Section 1. The speaker opens by thanking the hosts for the invitation today. "
       "Section 9. The speaker said the roof leaked after the storm last year. "
       "Section 12. A visitor asked whether the garden would reopen in spring.")
A = "The speaker thanks the hosts."
B = "The speaker closes by thanking the hosts."
C = "The speaker says the garden will reopen in spring."
GOOD = "the speaker opens by thanking the hosts"          # in SRC (case folded)
BAD = "the speaker closes by thanking the hosts warmly"   # not in SRC


@pytest.fixture
def severity_on(monkeypatch):
    monkeypatch.setattr(config, "FAITHFULNESS_SEVERITY_MODE", "majority3")


def _vote(sev, typ, ev=""):
    return fj.SeverityVote(sev, typ, ev)


def _scripted(votes_by_claim):
    """A fake judge_severity: each claim's votes are taken in order, one per call that
    includes it. Records the claims and contexts sent in each call."""
    calls = []
    state = {k: list(v) for k, v in votes_by_claim.items()}

    def fake(claims, contexts, source, client, *, model=None, logger=None):
        calls.append((list(claims), list(contexts)))
        out = []
        for c in claims:
            v = state[c].pop(0)
            if isinstance(v, Exception):
                raise v
            out.append(v)
        return out
    return fake, calls


def _classify(votes, contexts=None):
    fake, calls = _scripted(votes)
    with patch.object(fj, "judge_severity", fake):
        out = fj.classify_severity(list(votes), SRC, client=None, contexts=contexts)
    return out, calls


NQR_GOOD = _vote(fj.NOT_QUITE_RIGHT, "N3", GOOD)
NQR_BAD = _vote(fj.NOT_QUITE_RIGHT, "N3", BAD)
WRONG_W4 = _vote(fj.WRONG, "W4", "absent")


# --- JS1.a: prompt and parse ---------------------------------------------------------

def test_js1a_severity_prompt_and_parse():
    content = fj.build_severity_prompt([B, C], [A, None], SRC)
    prefix, tail = content[0]["text"], content[1]["text"]
    assert content[0]["cache_control"] == {"type": "ephemeral"}  # source cached
    assert fj.severity_instructions() in prefix and SRC in prefix
    assert f"1. {B}\n   (sentence before it: {A})" in tail
    assert f"2. {C}\n" in tail and tail.count("sentence before it") == 1
    reply = ('```json\n[{"index": 1, "severity": "not_quite_right", "type": "N3", '
             f'"evidence": "{GOOD}"}}, {{"index": 2, "severity": "wrong", "type": "W4", '
             '"evidence": "absent"}]\n```')
    got = fj._parse_severity_response(reply, [B, C])
    assert [(v.severity, v.type) for v in got] == [("not_quite_right", "N3"), ("wrong", "W4")]
    assert got[0].evidence == GOOD


def test_js1a_parse_reads_unescaped_quotes_and_bare_object():
    reply = ('[{"index": 1, "severity": "not_quite_right", "type": "N2", '
             '"evidence": "he said "the roof leaked" after"}]')
    assert fj._parse_severity_response(reply, [B])[0].evidence == 'he said "the roof leaked" after'
    bare = '{"index": 1, "severity": "wrong", "type": "W1", "evidence": "absent"}'
    assert fj._parse_severity_response(bare, [B])[0].type == "W1"


@pytest.mark.parametrize("reply", [
    '[{"index": 1, "severity": "wrong", "type": "N2", "evidence": "x"}]',        # type/severity
    '[{"index": 1, "severity": "minor", "type": "N2", "evidence": "x"}]',        # unknown
    '[{"index": 2, "severity": "wrong", "type": "W1", "evidence": "x"}]',        # missing 1
    '[{"index": 1, "severity": "wrong", "type": "W1", "evidence": "x"}, '
    '{"index": 1, "severity": "not_quite_right", "type": "N1", "evidence": "x"}]',  # repeat
    'no json here',
])
def test_js1a_parse_rejects_bad_replies(reply):
    with pytest.raises(ValueError):
        fj._parse_severity_response(reply, [B])


# --- JS1.b: votes --------------------------------------------------------------------

def test_js1b_wrong_first_vote_is_final(severity_on):
    out, calls = _classify({B: [WRONG_W4]})
    assert out[0].severity == fj.WRONG and out[0].type == "W4"
    assert len(calls) == 1


def test_js1b_two_nqr_votes_downgrade(severity_on):
    out, calls = _classify({B: [NQR_GOOD, NQR_GOOD], C: [WRONG_W4]})
    assert [o.severity for o in out] == [fj.NOT_QUITE_RIGHT, fj.WRONG]
    assert out[0].type == "N3" and out[0].evidence == GOOD
    assert [c[0] for c in calls] == [[B, C], [B]]  # only the NQR vote goes to round 2


def test_js1b_split_goes_to_third_vote(severity_on):
    out, calls = _classify({B: [NQR_GOOD, WRONG_W4, NQR_GOOD],
                            C: [NQR_GOOD, WRONG_W4, WRONG_W4]})
    assert [o.severity for o in out] == [fj.NOT_QUITE_RIGHT, fj.WRONG]
    assert len(calls) == 3 and len(out[1].votes) == 3


def test_js1b_contexts_are_sent(severity_on):
    _, calls = _classify({B: [WRONG_W4]}, contexts=[A])
    assert calls[0][1] == [A]


# --- JS1.c: evidence must be in the source ---------------------------------------------

def test_js1c_invented_evidence_counts_as_wrong(severity_on):
    """Adversarial: a vote says NOT QUITE RIGHT and quotes plausible words that are not
    in the source. It counts as WRONG, so one good vote is not enough."""
    out, calls = _classify({B: [NQR_BAD]})
    assert out[0].severity == fj.WRONG and len(calls) == 1
    assert "not found in the source" in out[0].note
    out, _ = _classify({B: [NQR_GOOD, NQR_BAD, NQR_GOOD]})
    assert out[0].severity == fj.NOT_QUITE_RIGHT  # two good votes of three


@pytest.mark.parametrize("evidence,found", [
    (GOOD, True),
    ("The Speaker opens, by thanking: the HOSTS", True),           # case and punctuation
    ("the speaker opens by … the roof leaked after the storm", True),  # both parts present
    ("the speaker opens by … the roof fell in after the storm", False),  # one part absent
    ("the speaker opens by … the hosts warmly", False),   # real 4-word run, invented tail
    ("the hosts", False),                                           # under 4 words
    ("absent", False),
    ("", False),
])
def test_js1c_evidence_check(evidence, found):
    assert fj._evidence_in_source(evidence, SRC) is found


def test_js1c_evidence_with_invented_short_part(severity_on):
    """learning-qa F4: a misattribution quoting a real 4-word run plus a short invented
    part ("... in Vienna") is not evidence; every part of 2+ words must be in the source."""
    assert not fj._evidence_in_source("the roof leaked after ... in Vienna", SRC)
    assert not fj._evidence_in_source("the roof leaked after ... Kerr said", SRC)
    out, _ = _classify({B: [_vote(fj.NOT_QUITE_RIGHT, "N3", "the speaker opens by ... in Vienna"),
                           NQR_GOOD]})
    assert out[0].severity == fj.WRONG


def test_js1c_unrelated_real_quote_does_not_count(severity_on):
    """learning-qa F4: real source words that share no significant word with the claim
    do not support it (adversarial, P7)."""
    assert fj._evidence_in_source("the roof leaked after the storm", SRC)
    assert not fj._evidence_in_source("the roof leaked after the storm", SRC, claim=B)
    assert fj._evidence_in_source(GOOD, SRC, claim=B)
    unrelated = _vote(fj.NOT_QUITE_RIGHT, "N2", "the roof leaked after the storm")
    out, _ = _classify({B: [unrelated, NQR_GOOD, NQR_GOOD]})
    assert out[0].severity == fj.WRONG


# --- JS1.d: fail closed ----------------------------------------------------------------

def test_js1d_api_error_keeps_wrong(severity_on):
    out, _ = _classify({B: [RuntimeError("api down")]})
    assert out[0].severity == fj.WRONG and "api down" in out[0].note
    out, _ = _classify({B: [NQR_GOOD, RuntimeError("timeout")]})  # error in round 2
    assert out[0].severity == fj.WRONG and "vote 2 failed" in out[0].note


def test_js1d_error_marks_claim_undecided(severity_on):
    """learning-qa F1: a claim kept WRONG because a vote failed is marked undecided; a
    WRONG decision is not."""
    out, _ = _classify({B: [NQR_GOOD, RuntimeError("timeout")]})
    assert out[0].severity == fj.WRONG and out[0].undecided
    out, _ = _classify({B: [WRONG_W4]})
    assert out[0].severity == fj.WRONG and not out[0].undecided


def test_js1d_parse_error_keeps_wrong(severity_on, monkeypatch):
    replies = []
    monkeypatch.setattr("transcript_utils.call_claude_with_retry",
                        lambda **kw: replies.append(1) or "not json")
    monkeypatch.setattr("transcript_utils.response_text", lambda r: r)
    out = fj.classify_severity([B], SRC, client=None)
    assert out[0].severity == fj.WRONG and "ValueError" in out[0].note
    assert len(replies) == config.JUDGE_PARSE_ATTEMPTS  # asked again, then gave up


# --- JS1.e: mode -----------------------------------------------------------------------

def test_js1e_off_is_todays_behaviour(monkeypatch):
    monkeypatch.setattr(config, "FAITHFULNESS_SEVERITY_MODE", "off")
    called = []
    monkeypatch.setattr(fj, "judge_severity", lambda *a, **k: called.append(1))
    monkeypatch.setattr(fj, "extract_claims", lambda text, source=None: [A, B])
    monkeypatch.setattr(fj, "judge_claims_confirmed", lambda *a, **k: (
        [fj.ClaimVerdict(A, "entailed"), fj.ClaimVerdict(B, "unsupported")], []))
    r = fj.judge_artifact("text", SRC, client=None)
    assert r.status == fj.FAIL and [c.claim for c in r.unfaithful] == [B]
    assert called == [] and r.not_quite_right == []
    assert r.detail.startswith("1 of 2 claim(s) not entailed by source; first: [unsupported]")


def test_js1e_unknown_mode_fails_closed(monkeypatch):
    monkeypatch.setattr(config, "FAITHFULNESS_SEVERITY_MODE", "lenient")
    with pytest.raises(ValueError):
        fj.classify_severity([B], SRC, client=None)
    monkeypatch.setattr(fj, "extract_claims", lambda text, source=None: [B])
    monkeypatch.setattr(fj, "judge_claims_confirmed",
                        lambda *a, **k: ([fj.ClaimVerdict(B, "unsupported")], []))
    assert fj.judge_artifact("text", SRC, client=None).status == fj.ERROR


# --- JS2.a: judge_artifact -------------------------------------------------------------

def _artifact(monkeypatch, verdicts, votes):
    monkeypatch.setattr(fj, "extract_claims", lambda text, source=None: [v.claim for v in verdicts])
    monkeypatch.setattr(fj, "judge_claims_confirmed", lambda *a, **k: (list(verdicts), []))
    fake, calls = _scripted(votes)
    monkeypatch.setattr(fj, "judge_severity", fake)
    return fj.judge_artifact("text", SRC, client=None), calls


def test_js2a_only_nqr_flags_pass_with_record(severity_on, monkeypatch):
    r, calls = _artifact(monkeypatch, [fj.ClaimVerdict(A, "entailed"),
                                       fj.ClaimVerdict(B, "unsupported", "not at the end")],
                         {B: [NQR_GOOD, NQR_GOOD]})
    assert r.status == fj.PASS and r.unfaithful == []
    assert [c.claim for c in r.not_quite_right] == [B]
    nqr = r.not_quite_right[0]
    assert (nqr.label, nqr.severity_type, nqr.evidence) == ("unsupported", "N3", GOOD)
    assert "1 claim(s) not quite right" in r.detail and "[N3]" in r.detail
    assert calls[0][1] == [A]  # the claim before the flag is sent as context
    d = r.to_dict()
    assert d["unfaithful"] == [] and d["not_quite_right"][0]["severity_type"] == "N3"


def test_js2a_one_wrong_fails(severity_on, monkeypatch):
    r, _ = _artifact(monkeypatch, [fj.ClaimVerdict(B, "unsupported"),
                                   fj.ClaimVerdict(C, "contradicted")],
                     {B: [NQR_GOOD, NQR_GOOD], C: [_vote(fj.WRONG, "W3", "A visitor asked")]})
    assert r.status == fj.FAIL
    assert [c.claim for c in r.unfaithful] == [C]
    assert [c.claim for c in r.not_quite_right] == [B]
    assert "[contradicted/W3]" in r.detail and "not quite right" in r.detail


def test_js2a_contradicted_flag_can_be_downgraded(severity_on, monkeypatch):
    """Decision JS0.e: a "contradicted" first-pass label goes through the same rule."""
    r, _ = _artifact(monkeypatch, [fj.ClaimVerdict(B, "contradicted")],
                     {B: [NQR_GOOD, NQR_GOOD]})
    assert r.status == fj.PASS and r.not_quite_right[0].label == "contradicted"


# --- JS2.b: the gate --------------------------------------------------------------------

def _gate(tmp_path, monkeypatch, result, suffix=None):
    suffix = suffix or config.SUFFIX_ABSTRACT_GEN
    base = "T - P - 2026-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base}{suffix}").write_text(B, encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(release_gate, "_FAITHFULNESS_CACHE", {})
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True)
    with patch.object(release_gate, "_source_with_metadata", return_value=SRC), \
            patch("transcript_utils.resolve_anthropic_key", return_value="k"), \
            patch("transcript_utils.get_anthropic_client", return_value=object()), \
            patch.object(release_gate, "_judge_cached", return_value=result):
        return base, release_gate.check_faithfulness(base, None, suffixes=[suffix])


def _nqr_result():
    return fj.FaithfulnessResult(fj.PASS, "no wrong claims in 1", claims=[
        fj.ClaimVerdict(B, "unsupported", "r", severity=fj.NOT_QUITE_RIGHT,
                        severity_type="N3", evidence=GOOD)])


def test_js2b_gate_warns_on_nqr_only(tmp_path, monkeypatch):
    _, v = _gate(tmp_path, monkeypatch, _nqr_result())
    assert v.status is release_gate.Status.WARN
    assert "1 not quite right claim(s) flagged" in v.detail
    assert v.items[0]["not_quite_right"] == [
        {"claim": B, "type": "N3", "evidence": GOOD, "first_label": "unsupported"}]
    decision = release_gate.decide([v])
    assert decision.decision is release_gate.Decision.ALLOW_WITH_WARNINGS
    assert decision.allowed


def test_js2b_gate_fail_still_lists_nqr(tmp_path, monkeypatch):
    r = _nqr_result()
    r.status = fj.FAIL
    r.claims.append(fj.ClaimVerdict(C, "unsupported", severity=fj.WRONG, severity_type="W4"))
    _, v = _gate(tmp_path, monkeypatch, r)
    assert v.status is release_gate.Status.WARN  # WO2: a WRONG claim warns too
    assert v.items[0]["unfaithful"] == [C]
    assert v.items[0]["not_quite_right"][0]["claim"] == B
    assert release_gate.decide([v]).decision is release_gate.Decision.ALLOW_WITH_WARNINGS


def test_js2b_fail_items_record_why_each_claim_failed(tmp_path, monkeypatch):
    """learning-qa F2: a FAIL item names each failing claim's type, evidence, note and
    whether it was undecided, so a severity timeout is told apart from a W1 vote."""
    r = fj.FaithfulnessResult(fj.FAIL, "x", claims=[
        fj.ClaimVerdict(C, "unsupported", severity=fj.WRONG, severity_type="W4",
                        evidence="absent"),
        fj.ClaimVerdict(B, "unsupported", severity=fj.WRONG,
                        severity_note="severity vote 1 failed: TimeoutError: t",
                        severity_undecided=True)])
    _, v = _gate(tmp_path, monkeypatch, r)
    assert v.items[0]["unfaithful"] == [C, B]  # existing readers keep plain strings
    # "rationale" since RM2.h: a removed sentence's record says why it was flagged.
    assert v.items[0]["wrong"] == [
        {"claim": C, "label": "unsupported", "rationale": "", "type": "W4",
         "evidence": "absent", "note": "", "undecided": False},
        {"claim": B, "label": "unsupported", "rationale": "", "type": "", "evidence": "",
         "note": "severity vote 1 failed: TimeoutError: t", "undecided": True}]


def _undecided_fail():
    return fj.FaithfulnessResult(fj.FAIL, "x", claims=[
        fj.ClaimVerdict(B, "unsupported", severity=fj.WRONG,
                        severity_note="severity vote 1 failed: TimeoutError: t",
                        severity_undecided=True)])


def test_js1d_undecided_fail_is_not_cached_or_flagged(tmp_path, monkeypatch):
    """learning-qa F1 (P1, P8): a FAIL that rests only on failed severity votes is
    transient. The same process asks again, and no flagged marker is left on disk."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    _cold(monkeypatch)
    replies = [_undecided_fail(), _nqr_result()]
    calls = []  # one fake for both runs: the cache key hashes judge_artifact's source
    monkeypatch.setattr(fj, "judge_artifact",
                        lambda a, s, c, logger=None: calls.append(1) or replies.pop(0))
    first = release_gate._judge_cached(fj, "art", "src", object(), None)
    assert first.status == fj.FAIL and first.undecided
    second = release_gate._judge_cached(fj, "art", "src", object(), None)  # same process
    assert calls == [1, 1] and second.status == fj.PASS
    assert not any(release_gate._is_flagged(v)
                   for v in release_gate._load_judge_disk_cache().values())


def test_js1d_decided_fail_still_cached_and_flagged(tmp_path, monkeypatch):
    """The contrast: a FAIL with a WRONG decision keeps the D2 behaviour."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    _cold(monkeypatch)
    calls = []
    decided = fj.FaithfulnessResult(fj.FAIL, "x", claims=[
        fj.ClaimVerdict(C, "unsupported", severity=fj.WRONG, severity_type="W4")])
    monkeypatch.setattr(fj, "judge_artifact",
                        lambda a, s, c, logger=None: calls.append(1) or decided)
    release_gate._judge_cached(fj, "art", "src", object(), None)
    release_gate._judge_cached(fj, "art", "src", object(), None)
    assert calls == [1]
    assert any(release_gate._is_flagged(v)
               for v in release_gate._load_judge_disk_cache().values())


# --- JS2.c: generation prechecks ---------------------------------------------------------

def _warn_verdict():
    return release_gate.Verdict("faithfulness", release_gate.Status.WARN, "w", items=[
        {"artifact": "summary-generated.md",
         "not_quite_right": [{"claim": B, "type": "N3", "evidence": GOOD,
                              "first_label": "unsupported"}]}])


def test_js2c_precheck_ignores_nqr(tmp_path, monkeypatch):
    import extraction_pipeline as ep
    base, suffix = "T - P - 2026-01-01", config.SUFFIX_SUMMARY_GEN
    (tmp_path / base).mkdir()
    (tmp_path / base / f"{base}{suffix}").write_text(B, encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True)
    ok = release_gate.Verdict("entity_grounding", release_gate.Status.PASS, "ok")
    logger = MagicMock()
    with patch.object(release_gate, "check_entity_grounding", return_value=ok), \
            patch.object(release_gate, "check_faithfulness", return_value=_warn_verdict()):
        assert ep._faithfulness_precheck(base, suffix, logger) == ("pass", [])
    warned = [c.args[0] % c.args[1:] for c in logger.warning.call_args_list]
    assert any(B in w and "[N3]" in w and "not quite right" in w for w in warned)


def test_js2c_nqr_only_draft_passes_without_revision(monkeypatch):
    """Decision JS0.d: the loop sees no issues, so the first draft is kept as written."""
    import extraction_pipeline as ep
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 3)
    revised = []
    ok = ep._generate_until_faithful(
        "summary", "B", " - x.md", MagicMock(), lambda feedback: "draft one", lambda t: None,
        precheck=lambda *a: ("pass", []), revise=lambda d, c: revised.append(1) or "x")
    assert ok is True and revised == []


# --- JS2.d: the warning lists every claim ----------------------------------------------

def test_js2d_warning_lists_every_claim(monkeypatch):
    """2026-10-18: the log cut the claim list at 300 characters and lost a claim."""
    import extraction_pipeline as ep
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 1)
    claims = [f"Claim {i} " + "word " * 40 + "end." for i in range(3)]
    logger = MagicMock()
    ep._generate_until_faithful("summary", "B", " - x.md", logger, lambda f: "draft",
                                lambda t: None, precheck=lambda *a: ("fail", claims))
    warned = " ".join(c.args[0] % c.args[1:] for c in logger.warning.call_args_list)
    for c in claims:
        assert c in warned


# --- JS2.e: the blog's advisory check counts NQR claims --------------------------------

def test_js2e_blog_nqr_named_and_warned(tmp_path, monkeypatch, caplog):
    """JS2.e / learning-qa F3: NOT QUITE RIGHT blog claims are not fed back as
    ungrounded, but each is logged by name and the blog verdict is WARN listing them."""
    import logging
    base = "T - P - 2026-01-01"
    (tmp_path / base).mkdir()
    (tmp_path / base / f"{base}{config.SUFFIX_BLOG}").write_text("A blog text.", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True)
    log = logging.getLogger("t_js2e")
    with patch.object(release_gate, "_load_source_transcript", return_value=SRC), \
            patch.object(release_gate, "check_faithfulness", return_value=_warn_verdict()), \
            caplog.at_level(logging.WARNING, logger="t_js2e"):
        minor = []
        status, ungrounded, detail = release_gate.blog_ungrounded_claims(base, log, minor=minor)
        v = release_gate.check_blog_faithfulness(base, log)
    assert (status, ungrounded) == ("pass", [])
    assert detail.startswith("no wrong blog claims; 1 claim(s) not quite right")
    assert [m["claim"] for m in minor] == [B]
    assert f"[N3] {B}" in caplog.text
    assert v.status is release_gate.Status.WARN
    assert v.items == [{"artifact": "blog", "not_quite_right": minor}]


# --- JS3: cache key and dirty state ------------------------------------------------------

def test_js3a_logic_version_bumped():
    assert config.JUDGE_LOGIC_VERSION >= "2026-10-19"


def test_js3a_severity_prompt_change_rekeys_cache(monkeypatch):
    key = release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS)
    with patch.object(fj, "severity_instructions", return_value="other policy"):
        assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != key
    monkeypatch.setattr(config, "FAITHFULNESS_SEVERITY_MODE", "majority3")
    on = release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS)
    monkeypatch.setattr(config, "FAITHFULNESS_SEVERITY_MODE", "off")
    assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != on
    monkeypatch.setattr(config, "FAITHFULNESS_SEVERITY_EVIDENCE_MIN_WORDS", 9)
    assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != key
    assert fj.classify_severity in release_gate._judge_input_functions()
    assert fj._evidence_in_source in release_gate._judge_input_functions()


def test_js3a_failing_rule_and_types_rekey_cache():
    """learning-qa F5: which claims fail (FaithfulnessResult) and the valid severity
    types are code and a constant; changing either re-keys the cache."""
    key = release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS)
    with patch.object(fj, "_SEVERITY_TYPES", {fj.WRONG: {"W1", "W2", "W3", "W4", "N3"},
                                              fj.NOT_QUITE_RIGHT: {"N1", "N2"}}):
        assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != key

    class FaithfulnessResult(fj.FaithfulnessResult):
        @property
        def unfaithful(self):  # a different failing rule
            return [c for c in self.claims if not c.faithful]
    with patch.object(fj, "FaithfulnessResult", FaithfulnessResult):
        assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != key
    assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) == key  # restored
    for name in ("FAITHFULNESS_SEVERITY_EVIDENCE_PART_MIN_WORDS",
                 "FAITHFULNESS_SEVERITY_EVIDENCE_MIN_SHARED_WORDS"):
        with patch.object(config, name, 3):
            assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != key


def test_js3a_missing_prompt_file_still_keys(monkeypatch):
    with patch.object(fj, "severity_instructions", side_effect=OSError("gone")):
        assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS)


def _cold(monkeypatch):
    monkeypatch.setattr(release_gate, "_FAITHFULNESS_CACHE", {})


def test_js3b_old_cached_pass_not_served(tmp_path, monkeypatch):
    """Dirty state (P8): a PASS cached with the step in another mode is not replayed."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    _cold(monkeypatch)
    calls = []
    monkeypatch.setattr(fj, "judge_artifact", lambda a, s, c, logger=None: calls.append(1)
                        or fj.FaithfulnessResult(fj.PASS, "ok"))
    monkeypatch.setattr(config, "FAITHFULNESS_SEVERITY_MODE", "off")
    release_gate._judge_cached(fj, "art", "src", object(), None)
    _cold(monkeypatch)
    monkeypatch.setattr(config, "FAITHFULNESS_SEVERITY_MODE", "majority3")
    release_gate._judge_cached(fj, "art", "src", object(), None)
    assert calls == [1, 1]  # judged again: the key changed with the mode


def test_js3b_warn_replayed_with_claims(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    _cold(monkeypatch)
    calls = []  # one fake for both runs: the cache key hashes judge_artifact's source
    monkeypatch.setattr(fj, "judge_artifact",
                        lambda a, s, c, logger=None: calls.append(1) or _nqr_result())
    first = release_gate._judge_cached(fj, "art", "src", object(), None)
    assert first.not_quite_right
    _cold(monkeypatch)  # a later process
    back = release_gate._judge_cached(fj, "art", "src", object(), None)
    assert calls == [1]  # replayed from disk, not judged again
    assert back.status == fj.PASS and back.unfaithful == []
    nqr = back.not_quite_right
    assert [(c.claim, c.severity_type, c.evidence) for c in nqr] == [(B, "N3", GOOD)]


# --- JS4: the policy text --------------------------------------------------------------

def test_js4a_prompt_file_loaded_and_registered():
    text = fj.severity_instructions()
    for phrase in ("WRONG", "NOT QUITE RIGHT", "If you are unsure, answer WRONG.",
                   "- W3. It credits words, a story, a question or a view to the wrong person.",
                   "- N3. It places real content at the wrong point in the talk"):
        assert phrase in text, phrase
    registry = (ROOT / "PROMPT_REGISTRY.md").read_text(encoding="utf-8")
    assert config.PROMPT_FAITHFULNESS_SEVERITY_FILENAME in registry
    assert "PROMPT_FAITHFULNESS_SEVERITY_FILENAME" in registry


def _q6():
    spec = importlib.util.spec_from_file_location(
        "q6", ROOT / "tests" / "test_judge_prompt_examples_q6.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _examples():
    section = fj.severity_instructions().split("EXAMPLES", 1)[1].split("END OF EXAMPLES", 1)[0]
    found = re.findall(r'"([^"]{6,})"', section)
    assert len(found) == 4
    return found


def _review_claims():
    """The 43 claims of docs/judge_flag_review_2026-10-18.md (the development set)."""
    text = (ROOT / "docs" / "judge_flag_review_2026-10-18.md").read_text(encoding="utf-8")
    rows = [r.split("|") for r in text.splitlines()
            if re.match(r"\| [RSL]\d+ \(", r)]
    return [r[2].strip() for r in rows]


def test_js4b_examples_not_fitted_to_measured_claims():
    q6 = _q6()
    review = _review_claims()
    assert len(review) == 43
    targets = [c["claim"] for c in q6._gold()] + review + q6._prose_real_sentences()
    for ex in _examples():
        assert not (set(re.findall(r"[a-z']+", ex.lower())) & q6._GOLD_DOMAIN), ex
        ew = q6._words(ex)
        for t in targets:
            assert len(ew & q6._words(t)) / len(ew) < 0.5, (ex, t[:80])


def test_js4b_prompt_shares_no_five_word_run_with_a_review_claim():
    """Adversarial: the policy must not carry wording from the claims it was built on
    (the 2026-10-11 lesson). The draft's "can contribute" was Kerr's phrase in R25."""
    def grams(text, n=5):
        w = re.findall(r"[a-z0-9']+", text.lower())
        return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}
    prompt = grams(fj.severity_instructions())
    for claim in _review_claims():
        assert not (grams(claim) & prompt), claim[:80]
    assert "can contribute" not in fj.severity_instructions().lower()


def test_js0c_gold_cases_carry_severity_labels():
    """JS0.c: every non-entailed gold case has a severity label and type; entailed
    cases have none; k4 is WRONG, k5 and k6 NOT QUITE RIGHT (user decision 2026-10-19).
    Spec: docs/plan_judge_severity_2026-10-19.md#JS0"""
    import json
    from pathlib import Path

    import faithfulness_judge as fj
    gold = json.loads((Path(__file__).parent / "fixtures" / "faithfulness_gold" / "gold.json")
                      .read_text(encoding="utf-8"))
    for c in gold["cases"]:
        if fj.is_unfaithful(c["label"]):
            assert c["severity_type"] in fj._SEVERITY_TYPES[c["severity"]], c["id"]
        else:
            assert "severity" not in c and "severity_type" not in c, c["id"]
    sev = {c["id"]: c.get("severity") for c in gold["cases"]}
    assert sev["k4"] == fj.WRONG
    assert {k for k, v in sev.items() if v == fj.NOT_QUITE_RIGHT} == {"k5", "k6"}
