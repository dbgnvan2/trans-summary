"""Regression tests that pin the validator decision logic exposed as unprotected
by the mutation-testing pass (2026-07-15 test-validity audit).

These target concrete surviving mutants: the `required=` integrity of coverage
items, the topic/QA required-vs-optional thresholds, the keyword-coverage
count/ratio decision, and the lexical grounding ratio. Each assertion is written
so the specific mutation that survived (a flipped comparison, a moved threshold,
an `and`/`or` swap, a `True`->`False`) would make it fail.

Bug-class context: the validators are the layer meant to catch bad LLM output;
the audit found they detected only 9-36% of injected faults. See
TEST_VALIDITY_REPORT.md / LEARNINGS.md.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import abstract_validation  # noqa: E402
import config  # noqa: E402
import summary_validation  # noqa: E402
import validation_pipeline  # noqa: E402


# ---------------------------------------------------------------------------
# helpers to build the minimal input shapes the generators read
# ---------------------------------------------------------------------------

def _summary_topic(name, percentage):
    return SimpleNamespace(name=name, percentage=percentage, key_points=[], word_allocation=100)


def _summary_input(topics=(), speaker="Dr. Kerr", purpose="Walk through two cases",
                   conclusion="The pattern repeats across generations",
                   qa_include=False, qa_pct=0, qa_types=()):
    return SimpleNamespace(
        metadata={"speaker": speaker} if speaker else {},
        opening=SimpleNamespace(stated_purpose=purpose, word_allocation=50),
        body=SimpleNamespace(topics=list(topics), word_allocation=300),
        qa=SimpleNamespace(include=qa_include, percentage=qa_pct,
                           question_types=list(qa_types), word_allocation=40),
        closing=SimpleNamespace(conclusion=conclusion, word_allocation=50),
        target_word_count=250,
    )


def _abstract_input(topics=(), themes=(), speaker="Dr. Kerr",
                    purpose="Walk through two cases",
                    conclusion="The pattern repeats across generations",
                    qa_pct=0, qa_topics=()):
    return SimpleNamespace(
        metadata={"speaker": speaker} if speaker else {},
        topics=[SimpleNamespace(name=n, percentage=p) for n, p in topics],
        themes=[SimpleNamespace(name=n, description=d) for n, d in themes],
        opening_purpose=purpose,
        closing_conclusion=conclusion,
        qa_percentage=qa_pct,
        qa_topics=list(qa_topics),
    )


def _item_by_cat(items, category):
    return [i for i in items if i.category == category]


# ---------------------------------------------------------------------------
# summary_validation.generate_coverage_items — required flags & thresholds
# ---------------------------------------------------------------------------

def test_summary_speaker_opening_closing_qa_items_are_required():
    si = _summary_input(topics=[_summary_topic("Family systems", 40)],
                        qa_include=True, qa_pct=40, qa_types=["clinical case questions"])
    items = summary_validation.generate_coverage_items(si)
    assert _item_by_cat(items, "metadata")[0].required is True, "speaker item must be required"
    assert _item_by_cat(items, "opening")[0].required is True, "opening purpose must be required"
    assert _item_by_cat(items, "closing")[0].required is True, "closing conclusion must be required"
    assert _item_by_cat(items, "qa")[0].required is True, "Q&A item must be required"


def test_summary_topic_required_threshold_at_10pct():
    """A topic at exactly 10% is required; below 10% it is not (pins `>= 10`)."""
    si = _summary_input(topics=[_summary_topic("Big topic", 10),
                                 _summary_topic("Minor topic", 9)])
    topics = _item_by_cat(summary_validation.generate_coverage_items(si), "topic")
    by_label = {t.label: t.required for t in topics}
    big = next(v for k, v in by_label.items() if "Big topic" in k)
    minor = next(v for k, v in by_label.items() if "Minor topic" in k)
    assert big is True, "10% topic must be required (boundary)"
    assert minor is False, "9% topic must not be required"


# ---------------------------------------------------------------------------
# summary_validation.check_keyword_coverage — count/ratio decision
# ---------------------------------------------------------------------------

def _sv_item(keywords):
    return summary_validation.CoverageItem(
        category="topic", label="x", required=True,
        keywords=list(keywords), source_text="x", expected_words=10,
    )


def test_summary_keyword_two_matches_is_high():
    covered, conf = summary_validation.check_keyword_coverage(
        "alpha and beta appear here", _sv_item(["alpha", "beta"]))
    assert covered is True and conf == "high", "2 keyword matches must be high-confidence covered"


def test_summary_keyword_ratio_or_path_is_high():
    """1 of 2 keywords = 0.5 ratio >= 0.4 -> high via the OR branch (pins `or`, 0.4)."""
    covered, conf = summary_validation.check_keyword_coverage(
        "alpha appears but not the other", _sv_item(["alpha", "zzznotpresent"]))
    assert covered is True and conf == "high"


def test_summary_keyword_none_is_low():
    covered, conf = summary_validation.check_keyword_coverage(
        "nothing relevant here", _sv_item(["alpha", "beta"]))
    assert covered is False and conf == "low"


def test_summary_keyword_empty_is_low_not_autocovered():
    covered, conf = summary_validation.check_keyword_coverage("anything", _sv_item([]))
    assert covered is False and conf == "low", "empty keywords must not auto-cover (A11)"


def test_summary_keyword_one_of_many_is_medium():
    """Exactly 1 match of 10 keywords: count 1 (< threshold 2), ratio 0.1 (< 0.4 and
    < 0.2) -> the MEDIUM tier via `match_count >= 1`. Pins the previously-untested
    medium branch AND the count>=2 high boundary (2->high, 1->medium)."""
    item = _sv_item(["alpha"] + [f"kw{i}" for i in range(9)])  # 10 keywords
    covered, conf = summary_validation.check_keyword_coverage("only alpha here", item)
    assert covered is True and conf == "medium"


def test_summary_keyword_count_at_threshold_with_low_ratio_is_high():
    """2 matches of 10 keywords: ratio 0.2 (< 0.4) so the ratio path can't rescue it —
    only the `match_count >= threshold(2)` path yields high. Pins the threshold value
    and the `>=` boundary (which the ratio OR-branch otherwise masks)."""
    item = _sv_item(["alpha", "beta"] + [f"kw{i}" for i in range(8)])  # 10 keywords
    covered, conf = summary_validation.check_keyword_coverage("alpha and beta here", item)
    assert covered is True and conf == "high"


# ---------------------------------------------------------------------------
# summary_validation.check_proportionality — section vs total tolerance logic
# ---------------------------------------------------------------------------

def _prop_input(target, op, body, cl):
    return SimpleNamespace(
        target_word_count=target,
        opening=SimpleNamespace(word_allocation=op),
        body=SimpleNamespace(word_allocation=body),
        closing=SimpleNamespace(word_allocation=cl),
    )


def _summary(op, body, cl):
    para = lambda n: " ".join(["w"] * n)  # noqa: E731
    return f"{para(op)}\n\n{para(body)}\n\n{para(cl)}"


def test_proportionality_ok_when_sections_match_allocations():
    r = summary_validation.check_proportionality(
        _summary(50, 300, 50), _prop_input(400, 50, 300, 50))
    assert all(s["within_tolerance"] for s in r["sections"])
    assert r["proportionality_ok"] is True


def test_proportionality_fails_when_a_section_is_far_over():
    """Body 600 vs allocation 300 = 100% deviation > 30% tol -> section fails ->
    proportionality_ok False (pins the per-section `all(within_tolerance)` term)."""
    r = summary_validation.check_proportionality(
        _summary(50, 600, 50), _prop_input(700, 50, 300, 50))
    body = next(s for s in r["sections"] if s["name"] == "Body (total)")
    assert body["within_tolerance"] is False
    assert r["proportionality_ok"] is False


def test_proportionality_fails_on_total_deviation_even_if_sections_ok():
    """Sections match their allocations (within tol) but the total (400) is far from
    the target (250) -> total_deviation 0.6 > 0.3 -> not ok. Pins the
    `total_deviation <= tolerance` term of the AND (distinct from the section term)."""
    r = summary_validation.check_proportionality(
        _summary(50, 300, 50), _prop_input(250, 50, 300, 50))
    assert all(s["within_tolerance"] for s in r["sections"])
    assert r["total_deviation"] > 0.3
    assert r["proportionality_ok"] is False


def test_proportionality_closing_under_50_gets_generous_tolerance():
    """A Closing section allocated < 50 words gets a 250% tolerance: alloc 30, actual
    90 = 200% deviation is still within. Pins the Closing-<50 special-case tier
    (any other <100 section would only get 50% and would FAIL at that deviation)."""
    r = summary_validation.check_proportionality(
        _summary(50, 300, 90), _prop_input(440, 50, 300, 30))
    closing = next(s for s in r["sections"] if s["name"] == "Closing")
    assert closing["expected"] == 30 and closing["actual"] == 90
    assert closing["within_tolerance"] is True


def test_proportionality_midsize_section_uses_040_tolerance():
    """A 100–200-word section gets 40% tolerance: body alloc 150, actual 220 =
    46.7% deviation FAILS (a <100 section would get 50% and pass). Pins the
    mid-size tier (0.4) and its 200 upper bound."""
    r = summary_validation.check_proportionality(
        _summary(50, 220, 50), _prop_input(320, 50, 150, 50))
    body = next(s for s in r["sections"] if s["name"] == "Body (total)")
    assert abs(body["deviation"] - (70 / 150)) < 0.001
    assert body["within_tolerance"] is False


def test_proportionality_small_section_uses_050_tolerance():
    """A <100-word (non-Closing) section gets 50% tolerance: opening alloc 60, actual
    89 = 48.3% deviation is within (would FAIL under the 40% mid-size tier). Pins the
    <100 tier (0.5) distinct from the 0.4 tier."""
    r = summary_validation.check_proportionality(
        _summary(89, 300, 50), _prop_input(439, 60, 300, 50))
    opening = next(s for s in r["sections"] if s["name"] == "Opening")
    assert opening["expected"] == 60 and opening["actual"] == 89
    assert opening["within_tolerance"] is True  # 0.483 <= 0.5, but > 0.4


def test_proportionality_zero_allocation_does_not_divide_by_zero():
    """A section with a 0-word allocation must NOT crash: deviation is 0 (guarded),
    the section is within tolerance. Pins the `expected > 0 else 0` divide-by-zero
    guard on every section."""
    r = summary_validation.check_proportionality(
        _summary(40, 300, 50), _prop_input(390, 0, 300, 50))  # opening alloc 0
    opening = next(s for s in r["sections"] if s["name"] == "Opening")
    assert opening["expected"] == 0
    assert opening["deviation"] == 0
    assert opening["within_tolerance"] is True


# ---------------------------------------------------------------------------
# abstract_validation.generate_coverage_items — thresholds & first-theme rule
# ---------------------------------------------------------------------------

def test_abstract_topic_required_threshold_at_15pct():
    ai = _abstract_input(topics=[("Major", 15), ("Minor", 14)])
    topics = _item_by_cat(abstract_validation.generate_coverage_items(ai), "topic")
    by = {t.label: t.required for t in topics}
    assert next(v for k, v in by.items() if "Major" in k) is True, "15% topic required (boundary)"
    assert next(v for k, v in by.items() if "Minor" in k) is False, "14% topic not required"


def test_abstract_first_theme_required_second_not():
    ai = _abstract_input(themes=[("Theme A", "first desc"), ("Theme B", "second desc")])
    themes = _item_by_cat(abstract_validation.generate_coverage_items(ai), "theme")
    assert themes[0].required is True, "first theme must be required (i == 0)"
    assert themes[1].required is False, "second theme must not be required"


def test_abstract_speaker_and_closing_required():
    ai = _abstract_input()
    items = abstract_validation.generate_coverage_items(ai)
    assert _item_by_cat(items, "metadata")[0].required is True
    assert _item_by_cat(items, "conclusion")[0].required is True


def test_abstract_qa_required_only_at_or_above_required_threshold():
    """qa_pct>=30 -> required; 15<=qa_pct<30 -> present but optional; <15 -> absent."""
    topics = ["family boundaries", "emotional cutoff patterns"]
    req = _item_by_cat(abstract_validation.generate_coverage_items(
        _abstract_input(qa_pct=30, qa_topics=topics)), "qa")
    assert req and req[0].required is True, "qa_pct 30 (>= REQUIRED) must be required"

    opt = _item_by_cat(abstract_validation.generate_coverage_items(
        _abstract_input(qa_pct=20, qa_topics=topics)), "qa")
    assert opt and opt[0].required is False, "qa_pct 20 (optional band) present but not required"

    absent = _item_by_cat(abstract_validation.generate_coverage_items(
        _abstract_input(qa_pct=10, qa_topics=topics)), "qa")
    assert absent == [], "qa_pct 10 (< OPTIONAL) must produce no qa item"


def _av_item(keywords):
    return abstract_validation.CoverageItem(
        category="topic", label="x", required=True,
        keywords=list(keywords), source_text="x",
    )


def test_abstract_keyword_two_matches_high_and_ratio_path():
    covered, conf = abstract_validation.check_keyword_coverage(
        "alpha and beta are both here", _av_item(["alpha", "beta"]))
    assert covered is True and conf == "high", "2 matches -> high"
    # 1 of 2 = 0.5 ratio >= 0.5 -> high via OR (pins `or`, 0.5)
    covered2, conf2 = abstract_validation.check_keyword_coverage(
        "alpha only", _av_item(["alpha", "zzzabsent"]))
    assert covered2 is True and conf2 == "high"


# ---------------------------------------------------------------------------
# validation_pipeline._keyword_grounding_ratio — overlap math
# ---------------------------------------------------------------------------

def test_grounding_ratio_no_keywords_is_zero():
    assert validation_pipeline._keyword_grounding_ratio("the a of it is", "anything") == 0.0


def test_grounding_ratio_partial_overlap():
    r = validation_pipeline._keyword_grounding_ratio(
        "differentiation triangles anxiety", "differentiation and triangles")
    assert round(r, 2) == 0.67, "2 of 3 probe keywords grounded"


def test_grounding_ratio_full_overlap():
    r = validation_pipeline._keyword_grounding_ratio(
        "differentiation triangles", "differentiation triangles anxiety")
    assert r == 1.0


# ---------------------------------------------------------------------------
# validation_pipeline.validate_key_terms_fidelity — fail-closed on no terms
# ---------------------------------------------------------------------------

def test_key_terms_validation_no_terms_returns_false(tmp_path, monkeypatch):
    """No key-terms artifact -> nothing validated -> must return False, not True."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path, raising=False)
    base = "sample_project"
    (tmp_path / base).mkdir(parents=True)
    formatted = tmp_path / "formatted.md"
    formatted.write_text("## Section 1\nSome transcript text.\n", encoding="utf-8")
    import logging
    logger = logging.getLogger("test_kt")
    result = validation_pipeline.validate_key_terms_fidelity(formatted, base, logger)
    assert result is False, "validation with zero terms must fail closed (not report success)"
