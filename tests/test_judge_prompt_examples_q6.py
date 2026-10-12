"""Q6 — the faithfulness judge prompt's examples must not paraphrase gold cases, or
the calibration measures recall of the examples rather than of the rule (LEARNINGS
2026-10-11, framing-rule entry). "attributes recovery to medication" mirrored us6 and
"definitively proven" mirrored us7.

Spec: docs/plan_todo_triage_2026-10-11.md#Q6
"""
import json
import re
from pathlib import Path

import config
import faithfulness_judge as fj

GOLD = Path(__file__).parent / "fixtures" / "faithfulness_gold" / "gold.json"
_STOP = {"the", "a", "an", "of", "to", "in", "is", "was", "and", "that", "this", "it",
         "for", "on", "as", "with", "be", "not", "he", "she", "they", "his", "her",
         "has", "have", "been", "now", "by", "or", "when", "its"}


def _words(text):
    return set(re.findall(r"[a-z']+", text.lower())) - _STOP


def _examples():
    return re.findall(r'"([^"]{6,})"', fj._JUDGE_INSTRUCTIONS)


def _gold():
    return json.loads(GOLD.read_text(encoding="utf-8"))["cases"]


def test_q6_prompt_does_not_quote_gold_claims():
    p = fj._JUDGE_INSTRUCTIONS.lower()
    for c in _gold():
        assert c["claim"].lower().rstrip(".") not in p, c["id"]


def test_q6_no_example_covers_half_a_gold_claim():
    for c in _gold():
        cw = _words(c["claim"])
        for ex in _examples():
            ew = _words(ex)
            if cw and ew:
                assert len(cw & ew) / len(cw) < 0.5, (c["id"], ex)


def test_q6_named_paraphrases_removed():
    p = fj._JUDGE_INSTRUCTIONS.lower()
    assert "medication" not in p  # us6
    assert "definitively proven" not in p  # us7


def test_q6_unsupported_examples_share_no_rare_word_with_their_gold_twins():
    """Adversarial: an example that shares the distinctive word of a gold claim
    (e.g. "medication", "proven") lets the judge recognise the case, not apply the rule."""
    distinctive = {"us6": {"medication", "psychiatric", "recovery"},
                   "us7": {"definitively", "proven", "neuroscience"}}
    ex_words = set().union(*(_words(e) for e in _examples()))
    for cid, words in distinctive.items():
        assert not (words & ex_words), cid


def test_q6_logic_version_bumped():
    assert config.JUDGE_LOGIC_VERSION == "2026-10-12"
