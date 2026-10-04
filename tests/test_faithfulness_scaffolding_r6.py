"""R6 (review F2): a fabricated name in a heading, bold-only line, dash/period
bold label, or between two `---` rules is checked by both hard blockers.

Spec: docs/plan_review_fixes_2026-10-04.md#R6
"""
import glob
import os
import re

import pytest

import abstract_validation as av
import faithfulness_judge as fj

FAKE = "Luciano Malorni"
SOURCE = (
    "Today I want to talk about differentiation of self and the family emotional "
    "system. Bowen described the nuclear family emotional process and chronic "
    "anxiety. Michael Kerr spoke about cancer, biology, and systems thinking."
)

SHAPES = {
    "heading": f"Intro paragraph about the family system.\n\n## {FAKE}'s 1975 Study\n\nMore text.",
    "bold_only": f"Intro paragraph.\n\n**{FAKE} pioneered niche theory**\n\nMore text.",
    "dash_label": f"- **{FAKE}** — pioneered the cancer niche model.\n",
    "period_label": f"**{FAKE}.** Pioneered the cancer niche model.\n",
    "en_dash_label": f"**{FAKE}** – pioneered the cancer niche model.\n",
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_r6a_extract_claims_sees_name_in_scaffolding(shape):
    claims = fj.extract_claims(SHAPES[shape], source=SOURCE)
    assert any(FAKE in c for c in claims), f"{shape}: {claims}"


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_r6b_entity_grounding_flags_name_in_scaffolding(shape):
    assert FAKE in av.find_ungrounded_names(SHAPES[shape], SOURCE)


def test_r6c_hr_delimited_prose_is_judged():
    text = (f"---\n\nThe talk opens with {FAKE}, who pioneered the cancer niche model in "
            "1975 and changed the field.\n\n---\n\nThe rest of the overview.")
    assert any(FAKE in c for c in fj.extract_claims(text))
    assert FAKE in av.find_ungrounded_names(text, SOURCE)


def test_r6c_real_front_matter_still_stripped():
    text = ("---\ntitle: Some Talk\nslug: some-talk\ntags:\n  - bowen\n  - kerr\n---\n\n"
            "The talk covers differentiation of self in the family emotional system.")
    claims = fj.extract_claims(text)
    assert not any("slug" in c or "title:" in c for c in claims)
    assert av._strip_scaffolding(text).startswith("The talk covers")


def test_r6d_scaffolding_headings_not_claims_or_names():
    text = ("## Key Takeaways\n\n## Frequently Asked Questions\n\n"
            "**Differentiation Of Self**\n\nThe family emotional system shapes anxiety "
            "and differentiation of self across generations.")
    claims = fj.extract_claims(text, source=SOURCE)
    assert not any("Takeaways" in c or "Frequently" in c for c in claims)
    assert av.find_ungrounded_names(text, SOURCE) == []


def test_r6d_grounded_heading_name_not_reemitted():
    """A heading naming something the source contains is not sent to the judge."""
    text = "## Michael Kerr\n\nHe described the family emotional system and anxiety."
    claims = fj.extract_claims(text, source=SOURCE)
    assert "Michael Kerr" not in claims


# --- R6.e: real artifacts -------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, "tests", "fixtures", "prose_real")

# Observed on the real fixtures when R6 landed (2026-10-04). Where Roots' blog/overview
# are clean here; its known fabrication (Luciano Malorni) is in the abstract.
EXPECTED_UNGROUNDED: dict = {}


def _real_prose():
    for d in sorted(glob.glob(os.path.join(REAL, "*", ""))):
        src = glob.glob(os.path.join(d, "* - formatted.md"))
        assert src, d
        transcript = open(src[0], encoding="utf-8").read()
        for f in sorted(glob.glob(os.path.join(d, "*.md"))):
            if re.search(r" - (summary-generated|overview|blog)\.md$", f):
                yield os.path.basename(f), open(f, encoding="utf-8").read(), transcript


def test_r6e_real_prose_artifacts_no_new_ungrounded():
    seen = 0
    for name, text, transcript in _real_prose():
        seen += 1
        got = av.find_ungrounded_names(text, transcript, known_names=["Michael Kerr"])
        assert got == EXPECTED_UNGROUNDED.get(name, []), (name, got)
    assert seen == 7, f"expected 7 real prose artifacts, found {seen}"


def test_r6e_real_prose_reemits_no_scaffolding_claims():
    """No heading/label from real artifacts is added to the judge's claims, so R6
    cannot introduce a false BLOCK on them."""
    for name, text, transcript in _real_prose():
        assert fj.extract_claims(text, source=transcript) == fj.extract_claims(text), name
