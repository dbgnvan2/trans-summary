"""R12 (review G6): the required "Speaker identified" item is built from the
metadata production actually provides (parse_filename_metadata -> "presenter").

Spec: docs/plan_review_fixes_2026-10-04.md#R12
"""
from types import SimpleNamespace

import abstract_validation
import summary_validation
from transcript_utils import parse_filename_metadata

META = parse_filename_metadata("Roots of Bowen Theory - Michael Kerr - 2019-03-01")


def _speaker_items(items):
    return [i for i in items if i.category == "metadata"]


def test_r12a_metadata_has_presenter_not_speaker():
    assert "speaker" not in META and META["presenter"] == "Michael Kerr"


def test_r12a_abstract_speaker_item_from_presenter():
    ai = SimpleNamespace(metadata=META, topics=[], themes=[], opening_purpose="",
                         closing_conclusion="", qa_percentage=0, qa_topics=[])
    items = _speaker_items(abstract_validation.generate_coverage_items(ai))
    assert len(items) == 1 and items[0].required
    assert "kerr" in items[0].keywords


def test_r12a_summary_speaker_item_from_presenter():
    si = SimpleNamespace(
        metadata=META,
        opening=SimpleNamespace(stated_purpose="", word_allocation=0),
        body=SimpleNamespace(topics=[], word_allocation=0),
        themes=[], qa=SimpleNamespace(include=False, topics=[], word_allocation=0),
        closing=SimpleNamespace(conclusion="", word_allocation=0),
    )
    items = _speaker_items(summary_validation.generate_coverage_items(si))
    assert len(items) == 1 and items[0].required
    assert "kerr" in items[0].keywords
