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
    assert config.JUDGE_LOGIC_VERSION == "2026-10-12d"


# Words of the gold set's and fixtures' subject matter (ported from the archived
# judge-framing branch, test_tf1_framing_examples_avoid_gold_subject). Every quoted
# example in the prompt must come from an unrelated subject (FX, 2026-10-12).
_GOLD_DOMAIN = {"bowen", "theory", "theory's", "family", "families", "anxiety",
                "differentiation", "science", "scientific", "research", "researcher",
                "researchers", "clinician", "clinicians", "therapist", "therapists",
                "cancer", "brain", "kerr", "symptom", "symptoms", "reckoning", "dos",
                "equation", "history", "environment", "discoveries", "pattern", "parts",
                "explanation", "heliocentrism", "astronomy"}


def test_fx_examples_avoid_gold_subject():
    for ex in _examples():
        assert not (set(re.findall(r"[a-z']+", ex.lower())) & _GOLD_DOMAIN), ex


def test_fx_no_example_is_copied_from_a_fixture():
    """Adversarial: an example taken word for word from a measured artifact (the
    Systems Biology blog in prose_real) makes that artifact's check measure the
    example. No quoted example of 20+ characters may occur in any fixture file."""
    fixtures = Path(__file__).parent / "fixtures"
    texts = [p.read_text(encoding="utf-8", errors="ignore").lower()
             for p in fixtures.rglob("*") if p.suffix in (".md", ".json", ".txt")]
    for ex in _examples():
        if len(ex) >= 20:
            needle = ex.lower().rstrip(".")
            assert not any(needle in t for t in texts), ex


def test_fx_framing_section_keeps_four_entailed_examples():
    """The rule is unchanged: the framing paragraph still gives four entailed examples."""
    p = fj._JUDGE_INSTRUCTIONS
    section = p.split("EDITORIAL / RHETORICAL FRAMING", 1)[1].split("Reserve ", 1)[0]
    assert len([e for e in re.findall(r'"([^"]{8,})"', section) if " " in e]) == 4



def _prose_real_sentences():
    root = Path(__file__).parent / "fixtures" / "prose_real"
    out = []
    for f in root.rglob("*.md"):
        if "formatted" in f.name:
            continue
        out += [s for s in re.split(r"(?<=[.!?])\s+", f.read_text(encoding="utf-8", errors="ignore"))
                if len(s.split()) >= 4]
    return out


def test_fx_no_example_paraphrases_a_measured_sentence():
    """FX review: an example rewritten slot-for-slot from a measured blog sentence
    ("looking at the parts when the explanation lives in the pattern" -> "counting the
    bricks when the answer lies in the design") still points at it. No example may
    share half its content words with any sentence of a prose_real artifact, and the
    framing examples may not reuse a measured sentence's opening frame."""
    sentences = _prose_real_sentences()
    assert len(sentences) > 200
    for ex in _examples():
        ew = _words(ex)
        if len(ew) < 3:
            continue
        for s in sentences:
            assert len(ew & _words(s)) / len(ew) < 0.5, (ex, s[:80])
    frames = ("it was a", "they are", "that kind of", "the environment is", "is not incidental")
    p = fj._JUDGE_INSTRUCTIONS
    section = p.split("EDITORIAL / RHETORICAL FRAMING", 1)[1].split("Reserve ", 1)[0]
    for ex in [e for e in re.findall(r'"([^"]{8,})"', section) if " " in e]:
        assert not ex.lower().startswith(frames), ex
        assert "not a side detail" not in ex.lower() and "lies in the design" not in ex.lower(), ex
        # FX re-check: the old "rare in science" example followed a passage about a
        # field openly admitting error; the rarity example must not be about that.
        assert not any(w in ex.lower() for w in ("admit", "mistake", "error", "misjudg")), ex
