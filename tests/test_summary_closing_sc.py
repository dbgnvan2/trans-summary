"""SC1–SC3 (docs/plan_summary_closing_2026-10-18.md): the 2026-10-18 Holt run stopped at
Structured Summary. The prompt asked every talk for a conclusion, open questions and
future directions; the recording had none, so the closing was invented and flagged on
every try (SC1). Tries 2 and 3 tied on one claim and the earlier, worse draft was kept
(SC2). The last try's warning said it was "revising" though no try followed (SC3)."""
from unittest.mock import MagicMock

import config
import extraction_pipeline as ep


def _loop(monkeypatch, verdicts, drafts, advisory=False):
    """Run ``_generate_until_faithful`` with three tries. ``drafts`` are the texts of
    tries 1..3 (try 1 generated, later ones revised); ``verdicts`` are the precheck
    results of the drafts that get judged, in order."""
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 3)
    texts, seq, written, judged = iter(drafts), iter(verdicts), [], []
    logger = MagicMock()

    def precheck(*a):
        judged.append(written[-1])
        return next(seq)
    ok = ep._generate_until_faithful(
        "summary", "B", " - x.md", logger, lambda feedback: next(texts), written.append,
        precheck=precheck, revise=lambda draft, claims: next(texts), advisory=advisory)
    return ok, written, judged, logger


def _warnings(logger):
    return [c.args[0] % c.args[1:] for c in logger.warning.call_args_list]


# --- SC2: on a tie in flagged claims, keep the later draft --------------------------

def test_sc2a_tie_keeps_the_later_draft(monkeypatch):
    """Holt run: tries 2 and 3 each had one flagged claim; try 3 had had more revision."""
    ok, written, judged, _ = _loop(
        monkeypatch, [("fail", ["Claim A."]), ("fail", ["Claim B."]), ("fail", ["Claim C."])],
        ["draft one", "draft two", "draft three"])
    assert ok is False
    assert judged == ["draft one", "draft two", "draft three"]
    assert written[-1] == "draft three"


def test_sc2b_fewer_claims_beat_a_later_draft(monkeypatch):
    """Adversarial: a later draft is kept only on a tie, never with more claims."""
    ok, written, _, _ = _loop(
        monkeypatch, [("fail", ["Claim A."]), ("fail", ["Claim B.", "Claim C."]),
                      ("fail", ["Claim D.", "Claim E."])],
        ["draft one", "draft two", "draft three"])
    assert ok is False
    assert written[-1] == "draft one"


def test_sc2c_unjudged_draft_never_kept_on_a_tie(monkeypatch):
    """Try 3 repeats a flagged claim, so it is rejected without a judge call; its count
    (one echoed claim) ties the judged drafts but it must not be kept."""
    ok, written, judged, _ = _loop(
        monkeypatch, [("fail", ["Claim A."]), ("fail", ["Claim B."])],
        ["draft one", "draft two", "It still says Claim B."])
    assert ok is False
    assert judged == ["draft one", "draft two"]
    assert written[-1] == "draft two"


def test_sc2e_judge_error_with_names_is_partial(tmp_path, monkeypatch):
    """SC2 review: when the judge errors but the name check finds a name, the draft
    fails as "partial", not "fail": its count holds only the names."""
    import release_gate as rg
    base = "Talk - A Person - 2021-01-01"
    (tmp_path / base).mkdir()
    (tmp_path / base / f"{base}{config.SUFFIX_SUMMARY_GEN}").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True, raising=False)
    names = rg.Verdict("entity_grounding", rg.Status.FAIL, "", [{"names": ["Luciano Malorni"]}])
    monkeypatch.setattr(rg, "check_entity_grounding", lambda *a, **k: names)
    monkeypatch.setattr(rg, "check_faithfulness",
                        lambda *a, **k: rg.Verdict("faithfulness", rg.Status.ERROR, "timeout"))
    status, issues = ep._faithfulness_precheck(base, config.SUFFIX_SUMMARY_GEN)
    assert status == "partial" and any("Luciano Malorni" in i for i in issues)
    # Both checks ran: still "fail".
    monkeypatch.setattr(rg, "check_faithfulness", lambda *a, **k: rg.Verdict(
        "faithfulness", rg.Status.FAIL, "", [{"unfaithful": ["Claim A."]}]))
    assert ep._faithfulness_precheck(base, config.SUFFIX_SUMMARY_GEN)[0] == "fail"
    # The blog precheck, the same way.
    monkeypatch.setattr(rg, "blog_ungrounded_claims",
                        lambda *a, **k: ("error", ["the name 'X Y' is not in the source"], ""))
    assert ep._blog_precheck(base, config.SUFFIX_BLOG)[0] == "partial"


NAME = "the name 'Luciano Malorni' does not appear in the source"


def test_sc2f_partial_draft_never_beats_a_judged_draft(monkeypatch):
    # A judged draft with one claim beats a partial draft with one name.
    ok, written, _, _ = _loop(
        monkeypatch, [("fail", ["Claim A."]), ("partial", [NAME]), ("fail", ["B.", "C."])],
        ["draft one", "draft two", "draft three"])
    assert ok is False and written[-1] == "draft one"
    # A judged draft beats an earlier partial one, even with more claims.
    ok, written, _, _ = _loop(
        monkeypatch, [("partial", [NAME]), ("fail", ["Claim A.", "Claim B."]),
                      ("partial", [NAME])],
        ["draft one", "draft two", "draft three"])
    assert written[-1] == "draft two"
    # Among partial drafts only, a tie keeps the later one.
    ok, written, _, _ = _loop(
        monkeypatch, [("partial", [NAME]), ("partial", [NAME]), ("partial", [NAME])],
        ["draft one", "draft two", "draft three"])
    assert ok is False and written[-1] == "draft three"


# --- SC3: the last try's warning does not promise another try -----------------------

def test_sc3a_last_try_does_not_say_it_will_revise(monkeypatch):
    ok, _, _, logger = _loop(
        monkeypatch, [("fail", ["Claim A."]), ("fail", ["Claim B."]), ("fail", ["Claim C."])],
        ["draft one", "draft two", "draft three"])
    assert ok is False
    tries = [w for w in _warnings(logger) if "not faithful" in w]
    assert len(tries) == 3
    assert all("revising the flagged sentences" in w for w in tries[:2])
    assert "attempt 3/3" in tries[2]
    assert "no attempts left" in tries[2]
    assert "revising" not in tries[2] and "regenerating" not in tries[2]


# --- SC1: the closing asks only for what the speaker says ---------------------------

def _summary_prompt():
    return (config.PROMPTS_DIR / config.PROMPT_STRUCTURED_SUMMARY_FILENAME).read_text(
        encoding="utf-8")


def _closing_instruction(text):
    """The text under the Closing Paragraph heading, up to the next heading."""
    after = text.split("### Closing Paragraph", 1)[1]
    return after.split("**Constraints:**", 1)[0]


# One phrase per point of the guard (plan SC1.a, points 1-5).
SC1_GUARD_PHRASES = (
    "if the speaker gives them near the end of the talk",          # 1: speaker's own only
    "close by restating the main point the speaker makes",         # 2: fallback
    "without saying that it comes at the end",                     # 2: no position claim
    "add no conclusion, open question or future direction of your own",  # 3
    "do not say that the talk has no conclusion",                  # 4
    "come from a phrase search and are often empty or wrong",      # 5: JSON fields
)


def test_sc1a_closing_asks_only_for_what_the_speaker_says():
    text = _summary_prompt()
    assert "State the conclusion, open questions, and future directions." not in text
    closing = " ".join(_closing_instruction(text).split())
    for phrase in SC1_GUARD_PHRASES:
        assert phrase in closing, phrase


def test_sc1b_guard_is_in_the_prompt_sent(monkeypatch):
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
    for phrase in SC1_GUARD_PHRASES:
        assert phrase in prompt, phrase
    assert "{" not in _closing_instruction(seen["messages"][0]["content"])


def test_sc1c_review_checklist_closing_line():
    import summary_pipeline as sp
    import summary_validation as sv
    si = sp.prepare_summary_input(
        metadata={"title": "T", "presenter": "P", "date": "2021-01-01"}, topics_markdown=
        "## Topics\n\n### A\nD.\n*_(~50% of transcript; Sections 1-2)_*\n",
        themes_markdown="", transcript="## Section 1\nKerr said things.\n")
    checklist = sv.generate_review_checklist(si)
    assert "- [ ] Closes with conclusion\n" not in checklist + "\n"
    assert ("- [ ] Closes with the speaker's conclusion, or the main point if the talk "
            "states none") in checklist
