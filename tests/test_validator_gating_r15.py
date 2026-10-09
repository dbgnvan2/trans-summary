"""R13 / R14 / R15 validator fixes and gating (plan decisions 1a, 2a, 3a).

Spec: docs/plan_review_fixes_2026-10-04.md#R13 #R14 #R15
"""
import glob
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import abstract_validation as av
import config
import summary_validation as sv
import validation_pipeline as vp


def _item(category, required=True, covered=False, confidence="low"):
    return SimpleNamespace(category=category, required=required, covered=covered,
                           confidence=confidence, label=category, source_text="x")


def _reply(text):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


# --- R13 (review F13): summary LLM rescue works ---------------------------------

def test_r13a_short_yes_no_reply_accepted(monkeypatch):
    seen = {}

    def fake_call(**kw):
        seen.update(kw)
        return _reply("YES\nNO")

    monkeypatch.setattr(av, "call_claude_with_retry", fake_call)
    items = [_item("topic"), _item("closing")]
    assert sv.verify_with_llm("summary text", items, api_client=object()) == [True, False]
    assert seen["min_length"] <= len("YES\nNO")


def test_r13b_api_error_marks_unverified(monkeypatch):
    def boom(**_kw):
        raise RuntimeError("timeout")

    monkeypatch.setattr(av, "call_claude_with_retry", boom)
    items = [_item("topic"), _item("closing")]
    assert sv.verify_with_llm("summary", items, api_client=object()) == [None, None]
    av.apply_llm_results(items, [None, None])
    assert all(i.confidence == "llm_unavailable" and not i.covered for i in items)


# --- R14 (review C-07): "could not verify" is distinct from "missing" ----------

def test_r14b_unavailable_is_error():
    assert av.coverage_status([_item("topic", confidence="llm_unavailable")]) == "ERROR"


def test_r14b_verified_miss_is_fail_even_with_unavailable_sibling():
    items = [_item("topic", confidence="llm_unavailable"),
             _item("topic", confidence="llm_verified")]
    assert av.coverage_status(items) == "FAIL"


def test_r14b_no_required_items_is_none_and_all_covered_is_pass():
    assert av.coverage_status([_item("topic", required=False)]) == "NONE"
    assert av.coverage_status([_item("topic", covered=True)]) == "PASS"


# --- decision 3a: summary gate ignores speaker and stated purpose ---------------

def test_r15_summary_status_ignores_speaker_and_purpose():
    items = [_item("metadata"), _item("opening"),
             _item("topic", covered=True), _item("closing", covered=True)]
    assert av.coverage_status(items, config.SUMMARY_COVERAGE_GATING_CATEGORIES) == "PASS"
    items.append(_item("topic", confidence="llm_verified"))
    assert av.coverage_status(items, config.SUMMARY_COVERAGE_GATING_CATEGORIES) == "FAIL"


def test_r15_gating_categories_are_topic_and_closing():
    assert config.SUMMARY_COVERAGE_GATING_CATEGORIES == {"topic", "closing"}


# --- decision 1a: emphasis matching ignores disfluencies ------------------------

def test_r15_emphasis_ignores_disfluencies():
    source = ("He said that's what my uh my my degrees are in and where my love is. "
              "It was, it was light. It was, um, it was freedom.")
    assert vp._emphasis_quote_found_ratio(
        "that's what my degrees are in and where my love is.", source) == 1.0
    assert vp._emphasis_quote_found_ratio("It was light. It was freedom.", source) == 1.0


def test_r15_emphasis_still_fails_absent_wording():
    """Disfluency handling never creates a match for words the source lacks."""
    source = "It was, um, it was freedom to me."
    assert vp._emphasis_quote_found_ratio(
        "Instead of targeting the proliferation of cancer cells we target niches.",
        source) < config.EMPHASIS_QUOTE_PARTIAL_RATIO


# --- decision 2a: key-term alternatives -----------------------------------------

@pytest.mark.parametrize("term, expected", [
    ("OCD (Obsessive-Compulsive Disorder)", {"OCD", "Obsessive-Compulsive Disorder"}),
    ("Wanting versus Liking", {"Wanting versus Liking", "Wanting and Liking"}),
    ("Symbiosis / Symbiotic Relationship", {"Symbiosis", "Symbiotic Relationship"}),
])
def test_r15_key_term_alternatives(term, expected):
    assert expected <= set(vp._key_term_alternatives(term))


def test_r15_key_term_alternatives_never_single_generic_words():
    alts = vp._key_term_alternatives("Verbal and Physical Abuse")
    assert alts == ["Verbal and Physical Abuse"]


# --- R15.c: gate checks ---------------------------------------------------------

import json  # noqa: E402
import logging  # noqa: E402
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

import release_gate as rg  # noqa: E402
from release_gate import Status  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
SB = "Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25_20260718_155038"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)

    def make(base=SB):
        shutil.copytree(FIX / "prose_real" / base, tmp_path / base)
        return base, tmp_path / base
    return make


def test_r15c_topics_fail_blocks(project):
    base, proj = project()
    topics = proj / f"{base}{config.SUFFIX_TOPICS}"
    topics.write_text(topics.read_text(encoding="utf-8") + (
        "\n### Byzantine Numismatics and Viking Longship Rigging\n"
        "Gilded solidus hoards alongside walrus-ivory chess pieces from Lewis.\n"
        "*_(~5% of transcript; Sections 2-3)_*\n"), encoding="utf-8")
    v = rg.check_topics_grounding(base)
    assert v.status is Status.FAIL
    assert any("Numismatics" in i["topic"] for i in v.items)
    assert rg.decide([v]).decision is rg.Decision.BLOCK


def test_r15c_topics_real_project_passes(project):
    base, _ = project()
    assert rg.check_topics_grounding(base).status is Status.PASS


def test_r15c_summary_no_summary_is_pass(project):
    base, proj = project("Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid")
    assert rg.check_summary_coverage(base).status is Status.PASS


def test_r15c_summary_uses_matching_stored_verdict(project, monkeypatch):
    base, proj = project()
    calls = []
    monkeypatch.setattr(vp, "validate_summary_coverage", lambda *a, **k: calls.append(1))
    vp._write_summary_coverage_verdict(base, "FAIL", "Validation: FAILED - missing: Topic X")
    v = rg.check_summary_coverage(base)
    assert v.status is Status.FAIL and "Topic X" in v.detail
    assert calls == []


def test_r15c_summary_stale_verdict_revalidated(project, monkeypatch):
    base, proj = project()
    vp._write_summary_coverage_verdict(base, "FAIL", "old")
    summary = proj / f"{base}{config.SUFFIX_SUMMARY_GEN}"
    summary.write_text(summary.read_text(encoding="utf-8") + "\nEdited.", encoding="utf-8")
    calls = []

    def fake_validate(b, logger=None, **_k):
        calls.append(b)
        vp._write_summary_coverage_verdict(b, "PASS", "Validation: PASSED")
    monkeypatch.setattr(vp, "validate_summary_coverage", fake_validate)
    assert rg.check_summary_coverage(base).status is Status.PASS
    assert calls == [base]


def test_r15c_summary_unverifiable_is_error_and_not_stored(project, monkeypatch):
    base, proj = project()
    monkeypatch.setattr(vp, "validate_summary_coverage",
                        lambda b, logger=None, **_k: vp._write_summary_coverage_verdict(b, "ERROR", "x"))
    v = rg.check_summary_coverage(base)
    assert v.status is Status.ERROR
    assert not (proj / f"{base}{config.SUFFIX_SUMMARY_COVERAGE_VERDICT}").exists()


# --- R15.d: shipped gate policy is pinned (also closes review G14) ---------------

def test_r15d_blocking_checks_and_judges_armed():
    """conftest forces the judge flags off for the suite, so read config.py's
    SOURCE: the shipped values, not the patched ones."""
    import ast
    tree = ast.parse((Path(config.__file__)).read_text(encoding="utf-8"))
    shipped = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            try:
                shipped[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    assert shipped["FAITHFULNESS_JUDGE_ENABLED"] is True
    assert shipped["THEME_JUDGE_ENABLED"] is True
    assert {"entity_grounding", "artifact_contracts", "faithfulness", "theme_grounding",
            "consistency", "verbatim_quotes", "source_fidelity", "topics_grounding",
            "summary_coverage"} <= shipped["GATE_BLOCKING_CHECKS"]
    names = {n for n, _fn in rg.DEFAULT_CHECKS}
    assert shipped["GATE_BLOCKING_CHECKS"] <= names


# --- R15.e: observed verdicts on trusted real samples (2026-10-05) ---------------

REAL = {
    # One quote says "bird" where the transcript has the typo "birdd": allowed since
    # decision J8 (2026-10-09), so the whole-quote check passes.
    "Societal Emotional Process - Michael Kerr - 2021-12-12_v-valid": Status.PASS,
    SB: Status.FAIL,  # two quotes absent from the transcript (real catch)
    "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid": Status.PASS,
}


@pytest.mark.parametrize("base", sorted(REAL))
def test_r15e_quotes_on_trusted_samples(project, base):
    project(base)
    assert rg.check_verbatim_quotes(base).status is REAL[base]


@pytest.mark.parametrize("base", sorted(REAL))
def test_r15e_topics_pass_on_trusted_samples(project, base):
    project(base)
    assert rg.check_topics_grounding(base).status is Status.PASS


def test_r15e_key_terms_stay_advisory():
    """Decision 2a: key terms gate only if every trusted sample passes. dave_g
    still fails on paraphrased labels ("Verbal and Physical Abuse"), so there is
    no key-terms gate check."""
    assert "key_terms" not in {n for n, _fn in rg.DEFAULT_CHECKS}
    assert not any("key_term" in c for c in config.GATE_BLOCKING_CHECKS)


# --- R15.b: the GUI Structured Summary stage validates coverage -----------------

def test_r15b_structured_summary_stage_validates(monkeypatch):
    import ts_gui

    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name, gui.logger = "Sample", None
    logs = []
    gui.log = lambda *a, **k: logs.append(" ".join(str(x) for x in a))
    calls = []
    monkeypatch.setattr(ts_gui.pipeline, "generate_structured_summary", lambda *a, **k: True)
    monkeypatch.setattr(ts_gui.pipeline, "validate_summary_coverage",
                        lambda b, **k: calls.append(b) or False)
    assert gui._run_stage_structured_summary() is True  # a miss blocks publish, not the run
    assert calls == ["Sample"]
    assert any("publication will be blocked" in line for line in logs)


# --- learning-qa sweep findings (2026-10-05) -------------------------------------

def test_sweep1_no_api_key_is_error_not_a_stored_fail(project, monkeypatch):
    """No client: a required topic the keywords can't confirm is unverified ->
    ERROR, never stored, so it can't outlive a missing key."""
    base, proj = project()
    topics = proj / f"{base}{config.SUFFIX_TOPICS}"
    topics.write_text(topics.read_text(encoding="utf-8") + (
        "\n### Byzantine Numismatics and Viking Longship Rigging\n"
        "Gilded solidus hoards alongside walrus-ivory chess pieces from Lewis.\n"
        "*_(~30% of transcript; Sections 2-3)_*\n"), encoding="utf-8")
    monkeypatch.setattr(vp, "get_anthropic_client_or_none", lambda *a, **k: None)
    vp.validate_summary_coverage(base, logger=logging.getLogger("t"))
    assert not (proj / f"{base}{config.SUFFIX_SUMMARY_COVERAGE_VERDICT}").exists()
    report = (proj / f"{base}{config.SUFFIX_SUMMARY_VAL}").read_text(encoding="utf-8")
    assert "Gate status: ERROR" in report and "unverified" in report


@pytest.mark.parametrize("reply, expected", [
    ("1. YES\n2. NO", [True, False]),
    ("NOTE: answers follow\nYES", [None, None]),     # preamble 'NOTE' is not a NO
    ("YES", [None, None]),                            # short reply: unknown mapping
    ("YES\nNO\nYES", [None, None]),                   # too many answers
])
def test_sweep2_reply_parsing_never_pads_a_miss(monkeypatch, reply, expected):
    monkeypatch.setattr(av, "call_claude_with_retry", lambda **_k: _reply(reply))
    items = [_item("topic"), _item("closing")]
    assert av.verify_items_with_llm("text", items, object(), "summary") == expected


def test_sweep3_emphasis_parsed_to_nothing_is_error(project):
    base, proj = project()
    (proj / f"{base}{config.SUFFIX_EMPHASIS_SCORED}").write_text(
        "Some reformatted emphasis output the parser no longer reads.\n", encoding="utf-8")
    for legacy in proj.glob(f"*{config.SUFFIX_EMPHASIS}"):
        legacy.unlink()
    assert rg.check_verbatim_quotes(base).status is Status.ERROR


@pytest.mark.parametrize("term, generic", [
    ("Sibling Position (Bowen)", "Bowen"),
    ("Multigenerational Transmission (in families)", "in families"),
])
def test_sweep8_generic_parenthetical_is_not_an_alternative(term, generic):
    alts = vp._key_term_alternatives(term)
    assert generic not in alts
    assert term.split(" (")[0] in alts


def test_sweep_empty_or_filler_only_quote_grounds_nothing():
    assert vp._emphasis_quote_found_ratio("", "any text") == 0.0
    assert vp._emphasis_quote_found_ratio("Uh, um.", "uh um the family") == 0.0



# --- J8 (decision 2026-10-09): one-letter typo tolerance in whole-quote coverage ---

SRC = "and it was the cleft of the wing of a birdd that night and the family is an emotional unit"


def test_j8a_one_letter_typo_allowed():
    assert vp._quote_word_coverage("the cleft of the wing of a bird that night", SRC) == 1.0


def test_j8b_changed_word_still_fails():
    assert vp._quote_word_coverage("the family is an rational unit", SRC) < 1.0


def test_j8c_short_words_exact():
    assert not vp._one_letter_apart("is", "in")
    assert not vp._one_letter_apart("unit", "unit")
    assert vp._one_letter_apart("bird", "birdd")
    assert vp._one_letter_apart("their", "thier") is False  # transposition is 2 edits
