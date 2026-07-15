"""Contract tests for validators that reported PASS without actually verifying.

Purpose: Lock down the "validator reports success on empty/zero" cluster from the
         P19 contract audit — a gate must never report a clean pass when it
         validated nothing.
Spec:    TODO.md#p19-contract-audit-findings (A5, A9, A10, A11)
Tests:   this file

  A5  — header-validation never counted PASS/WARN/FAIL, so a real FAIL rode
        through as success (and the model's `**STATUS:**` drift hid it).
  A9  — coverage validators used `all(item.covered for item in required_items)`,
        and `all([]) == True`, so an empty required checklist reported PASS.
  A10 — a transient purpose-extraction failure (no API key / timeout) returned the
        same sentinel as a genuine absence, silently demoting the required purpose
        check to optional and flipping FAIL→PASS (P1).
  A11 — an item whose keyword list is empty was auto-marked covered='high',
        satisfying required coverage without any grounding.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import abstract_pipeline  # noqa: E402
import abstract_validation  # noqa: E402
import config  # noqa: E402
import summary_validation  # noqa: E402


# ---------------------------------------------------------------------------
# A11 — empty keyword list must NOT auto-satisfy coverage
# ---------------------------------------------------------------------------

def test_a11_summary_empty_keywords_not_auto_covered():
    item = summary_validation.CoverageItem(
        category="topic", label="ungroundable", required=True,
        keywords=[], source_text="Us vs Them", expected_words=50,
    )
    covered, confidence = summary_validation.check_keyword_coverage(
        "A summary that never mentions the topic at all.", item
    )
    assert covered is False, "empty-keyword item must not be auto-covered (A11)"
    # 'low' (not 'high', not 'none') so it stays eligible for the LLM rescue pass.
    assert confidence == "low"


def test_a11_abstract_empty_keywords_not_auto_covered():
    item = abstract_validation.CoverageItem(
        category="topic", label="ungroundable", required=True,
        keywords=[], source_text="Us vs Them",
    )
    covered, confidence = abstract_validation.check_keyword_coverage(
        "An abstract that never mentions the topic at all.", item
    )
    assert covered is False, "empty-keyword item must not be auto-covered (A11)"
    assert confidence == "low"


def test_a11_empty_keyword_item_is_rescuable_via_llm(monkeypatch):
    """F1 regression guard: a short-name required topic (no extractable keywords)
    that IS covered must be rescuable by the LLM pass — not hard-failed."""
    ai = SimpleNamespace(
        metadata={},
        topics=[SimpleNamespace(name="AI vs ML", percentage=40, sections="1-2")],
        themes=[],
        opening_purpose="Not explicitly stated",
        closing_conclusion="No explicit conclusion stated",
        qa_percentage=0, qa_topics=[], target_word_count=250,
    )
    items = abstract_validation.generate_coverage_items(ai)
    topic_items = [i for i in items if i.category == "topic"]
    assert topic_items and topic_items[0].required and topic_items[0].keywords == [], (
        "precondition: a required topic with zero extractable keywords"
    )

    # LLM confirms coverage -> the item is rescued and validation passes.
    monkeypatch.setattr(abstract_validation, "verify_with_llm", lambda *a, **k: [True])
    result = abstract_validation.validate_abstract_coverage(
        "This abstract thoroughly covers the AI vs ML debate.",
        ai, use_llm_verification=True, api_client=object(),
    )
    assert result["passed"] is True, "empty-keyword item must be LLM-rescuable (F1)"


# ---------------------------------------------------------------------------
# A9 — an empty required checklist must NOT report a clean pass
# ---------------------------------------------------------------------------

def _empty_abstract_input():
    return SimpleNamespace(
        metadata={},                       # no speaker
        topics=[],                         # no topic items
        themes=[],                         # no theme items (theme[0] would be required)
        opening_purpose="Not explicitly stated",   # no purpose item
        closing_conclusion="No explicit conclusion stated",  # no conclusion item
        qa_percentage=0,
        qa_topics=[],
        target_word_count=250,
    )


def test_a9_abstract_empty_required_checklist_does_not_pass():
    ai = _empty_abstract_input()
    items = abstract_validation.generate_coverage_items(ai)
    assert not [i for i in items if i.required], "precondition: no required items"

    result = abstract_validation.validate_abstract_coverage(
        "Some non-empty abstract prose that covers nothing in particular.",
        ai, use_llm_verification=False,
    )
    assert result["passed"] is False, (
        "empty required checklist must not report PASS (A9 — all([]) guard)"
    )


def _empty_summary_input():
    return SimpleNamespace(
        metadata={},
        opening=SimpleNamespace(stated_purpose="Not explicitly stated", word_allocation=0),
        body=SimpleNamespace(topics=[], word_allocation=0),
        qa=SimpleNamespace(include=False, percentage=0, question_types=[], word_allocation=0),
        closing=SimpleNamespace(conclusion="No explicit conclusion", word_allocation=0),
        target_word_count=250,
    )


def test_a9_summary_empty_required_checklist_does_not_pass():
    si = _empty_summary_input()
    items = summary_validation.generate_coverage_items(si)
    assert not [i for i in items if i.required], "precondition: no required items"

    result = summary_validation.validate_summary_coverage(
        "Some non-empty summary prose that covers nothing in particular.",
        si, use_llm_verification=False,
    )
    assert result["passed"] is False, (
        "empty required checklist must not report PASS (A9 — all([]) guard)"
    )


# ---------------------------------------------------------------------------
# A10 — transient purpose-extraction failure must not silently pass
# ---------------------------------------------------------------------------

def test_a10_extract_purpose_distinguishes_transient_failure(monkeypatch):
    """No API key is a transient/config failure — it must NOT look identical to a
    genuine 'speaker did not state a purpose'."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    transcript = (
        "## Section 1\nGood evening, my purpose tonight is to walk through two "
        "family cases and what they reveal.\n## Section 2\nLet's begin.\n"
    )
    result = abstract_pipeline.extract_opening_purpose(transcript, section_count=2)
    assert result == config.PURPOSE_EXTRACTION_FAILED, (
        "a transient/config failure must return a distinct 'undetermined' sentinel, "
        "not the genuine-absent 'manually insert' value (A10/P1)"
    )
    assert "manually insert" not in result


def test_a10_failed_purpose_extraction_does_not_silently_pass():
    """When purpose extraction failed, validation must not report a clean pass even
    if the abstract happens to mention purpose-like words."""
    ai = SimpleNamespace(
        metadata={"speaker": "Dr. Kerr"},
        topics=[SimpleNamespace(name="Family systems", percentage=40, sections="1-3")],
        themes=[],
        opening_purpose=config.PURPOSE_EXTRACTION_FAILED,
        closing_conclusion="No explicit conclusion stated",
        qa_percentage=0,
        qa_topics=[],
        target_word_count=250,
    )
    items = abstract_validation.generate_coverage_items(ai)
    purpose_items = [i for i in items if i.category == "purpose"]
    assert purpose_items, "a failed purpose extraction must still produce a purpose item"
    assert purpose_items[0].required is True, (
        "failed purpose extraction must stay REQUIRED, not be demoted to optional (A10)"
    )

    abstract = (
        "Dr. Kerr discusses family systems. His purpose and intent and goal and aim "
        "are described in detail across the presentation."
    )
    result = abstract_validation.validate_abstract_coverage(
        abstract, ai, use_llm_verification=False
    )
    assert result["passed"] is False, (
        "unverified (failed-extraction) purpose must not ride through as PASS (A10)"
    )


def test_a10_failed_purpose_item_is_not_rescued_by_llm(monkeypatch):
    """F2: the failed-purpose sentinel must NOT be sent to the LLM rescue pass, and
    even an all-confirming LLM cannot flip it to covered — it's genuinely unverified."""
    ai = SimpleNamespace(
        metadata={"speaker": "Dr. Kerr"},
        topics=[SimpleNamespace(name="Family systems theory", percentage=40, sections="1-3")],
        themes=[],
        opening_purpose=config.PURPOSE_EXTRACTION_FAILED,
        closing_conclusion="No explicit conclusion stated",
        qa_percentage=0, qa_topics=[], target_word_count=250,
    )

    sent_to_llm = []

    def spy_verify(abstract, items, api_client, **kwargs):
        sent_to_llm.extend(items)
        return [True] * len(items)

    monkeypatch.setattr(abstract_validation, "verify_with_llm", spy_verify)
    result = abstract_validation.validate_abstract_coverage(
        "An abstract mentioning purpose, intent, aim, and goal repeatedly.",
        ai, use_llm_verification=True, api_client=object(),
    )
    purpose_item = next(i for i in result["items"] if i["category"] == "purpose")
    assert purpose_item["confidence"] == "extraction_failed"
    assert not any(
        i.source_text == config.PURPOSE_EXTRACTION_FAILED for i in sent_to_llm
    ), "failed-purpose sentinel must not be sent to the LLM (F2)"
    assert result["passed"] is False, (
        "an all-confirming LLM must not rescue a genuinely-unverified purpose (F2)"
    )


# ---------------------------------------------------------------------------
# A5 — header-validation verdict counting, tolerant of the model's format drift
# ---------------------------------------------------------------------------

def test_a5_count_header_verdicts_tolerates_drift():
    from transcript_utils import count_header_verdicts

    report = (
        "### Batch 1\n"
        "SECTION 1:\nSTATUS: PASS\n"
        "SECTION 2:\nSTATUS: WARN\n"
        "### Batch 3\n"
        "## SECTION 15:\n**STATUS:** FAIL\n"       # markdown-bold drift
        "## SECTION 16:\n**STATUS:** WARN\n"
    )
    counts = count_header_verdicts(report)
    assert counts["PASS"] == 1
    assert counts["WARN"] == 2, "must count both plain and **bold** WARN lines"
    assert counts["FAIL"] == 1, "the real bolded FAIL must be counted, not hidden"
    assert counts["total"] == 4


def test_a5_prompt_template_line_is_not_counted():
    from transcript_utils import count_header_verdicts

    # The prompt's own `STATUS: [PASS / WARN / FAIL]` scaffold must not be a verdict.
    counts = count_header_verdicts("STATUS: [PASS / WARN / FAIL]\n")
    assert counts["total"] == 0


def test_a5_zero_verdicts_from_nonempty_is_detectable():
    from transcript_utils import count_header_verdicts

    counts = count_header_verdicts("Lots of prose about headings but no verdict lines.\n")
    assert counts["total"] == 0  # caller must treat 0-from-non-empty as drift, not clean
