"""RM: remove sentences still flagged after revision (docs/plan_remove_flagged_2026-10-19.md)."""
import json
import logging
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import yaml

import config
import extraction_pipeline as ep
import faithfulness_judge as fj
import flagged_removal as fr
import release_gate as rg
import removal_record as rr

REPO = Path(__file__).resolve().parents[1]

SUMMARY = """### Opening Paragraph

Michael Kerr presents two lectures on Bowen theory. He says the choir will tour next spring. The first lecture traces the history of cosmology.

### Body Section

- **Family triangles:** Kerr describes how triangles form in families under stress.
- The mayor says the bridge will close next year.
- Kerr says distance is not differentiation and that you heal in the system.

### Closing

Kerr ends with a question about the future of the theory. Michael Kerr says distance is not differentiation.
"""


def _remove(text, flags, **kw):
    # The unit texts are short, so one sentence is a large share; the cap has its
    # own tests at the configured value (RM1.h, the replay).
    kw.setdefault("max_share", 0.9)
    return fr.remove_flagged_sentences(text, flags, **kw)


# --- RM1.g: the deletion-only check (written first) ----------------------------------

def test_rm1g_changed_text_rejected_draft_unchanged(monkeypatch):
    """A removal that changes one word must not be used: the input comes back and
    every flag is kept with the reason."""
    real_cut = fr._cut

    def cut_and_change(raw, spans):
        return real_cut(raw, spans).replace("traces", "explains")

    monkeypatch.setattr(fr, "_cut", cut_and_change)
    flag = "He says the choir will tour next spring."
    text, removed, kept = _remove(SUMMARY, [flag])
    assert text == SUMMARY
    assert removed == []
    assert [k.claim for k in kept] == [flag]
    assert kept[0].reason.startswith("deletion check failed")


def test_rm1g_check_names_each_problem():
    before = SUMMARY
    added = SUMMARY.replace("He says the choir will tour next spring. ", "He sings. ")
    problems = fr.deletion_problems(before, added, {"He says the choir will tour next spring."})
    assert any("not only deleted" in p for p in problems)
    lost = SUMMARY.replace("Kerr ends with a question about the future of the theory. ", "")
    problems = fr.deletion_problems(before, lost, set())
    assert any("not flagged" in p for p in problems)
    retitled = SUMMARY.replace("### Closing", "### End")
    assert any("heading" in p for p in fr.deletion_problems(before, retitled, set()))


def _replay_drafts():
    data = json.loads((REPO / "docs/calibration/2026-10-19_outside_facts/results.json")
                      .read_text(encoding="utf-8"))
    runs = next(v for v in data.values() if isinstance(v, list))
    out = []
    for r in runs:
        flagged = [c["claim"] for c in r.get("claims") or [] if c.get("label") != "entailed"]
        if flagged:
            out.append((r["draft"], flagged))
    return out


def test_rm1g_replay_drafts_pass_check():
    """The 5 flagged WO6 drafts (RM0): 8 of the 9 flagged sentences are removed and the
    deletion-only check holds. The ninth is the only sentence under 'Closing
    Paragraph', so RM1.f keeps it."""
    drafts = _replay_drafts()
    assert len(drafts) == 5
    n_removed, kept_all = 0, []
    for draft, flagged in drafts:
        text, removed, kept = _remove(draft, flagged, max_share=0.25)
        assert ({r.sentence for r in removed} | {fj._claim_body(k.claim) for k in kept}
                == {fj._claim_body(c) for c in flagged})
        assert fr.deletion_problems(draft, text, {r.sentence for r in removed}) == []
        assert (len(text.split()) < len(draft.split())) if removed else text == draft
        n_removed += len(removed)
        kept_all += kept
    assert n_removed == 8
    assert [k.reason for k in kept_all] == ["only text under heading 'Closing Paragraph'"]


# --- RM1.d: adversarial -------------------------------------------------------------

def test_rm1d_part_of_longer_sentence_not_removed():
    """'Kerr says distance is not differentiation.' is flagged; the closing's
    'Michael Kerr says distance is not differentiation.' is a different sentence."""
    flag = "Kerr says distance is not differentiation."
    text, removed, kept = _remove(SUMMARY, [flag])
    assert text == SUMMARY
    assert removed == []
    assert kept[0].reason == "not found as a whole sentence"


# --- RM1.a ---------------------------------------------------------------------------

def test_rm1a_flagged_sentence_removed_rest_unchanged():
    flag = "He says the choir will tour next spring."
    text, removed, kept = _remove(SUMMARY, [flag])
    assert text == SUMMARY.replace("He says the choir will tour next spring. ", "")
    assert kept == []
    (r,) = removed
    assert r.sentence == flag
    assert r.before == "Michael Kerr presents two lectures on Bowen theory."
    assert r.after == "The first lecture traces the history of cosmology."
    assert r.reason == "faithfulness"


def test_rm1a_last_sentence_of_line_takes_space_before():
    flag = "Michael Kerr says distance is not differentiation."
    text, removed, _ = _remove(SUMMARY, [flag])
    assert "Kerr ends with a question about the future of the theory.\n" in text
    assert len(removed) == 1


def test_rm1a_fq_tag_ignored():
    text = ("## Is moving away the same as differentiation?\n\n"
            "Michael Kerr says distance is never differentiation of self. "
            "Distance changes only the setting a person lives in.\n")
    claims = fj.extract_claims(text)
    assert "[in answer to:" in claims[0]  # the judge's form of the claim
    out, removed, kept = _remove(text, [claims[0]])
    assert "Michael Kerr says" not in out
    assert "Distance changes only the setting a person lives in." in out
    assert kept == [] and len(removed) == 1


def test_rm1a_every_occurrence_removed():
    flag = "The mayor says the bridge will close next year."
    text = SUMMARY + f"\n### Recap\n\nKerr repeats his point about triangles. {flag}\n"
    out, removed, _ = _remove(text, [flag])
    assert flag not in out
    assert len(removed) == 2


def test_rm1a_bold_inside_sentence_removed():
    text = "Kerr opens with a story. He says **the choir** will tour next spring. He ends.\n"
    out, removed, _ = _remove(text, ["He says the choir will tour next spring."])
    assert out == "Kerr opens with a story. He ends.\n"
    assert len(removed) == 1


# --- RM1.b ---------------------------------------------------------------------------

def test_rm1b_bullet_left_empty_is_removed():
    flag = "The mayor says the bridge will close next year."
    out, _, _ = _remove(SUMMARY, [flag])
    assert "- The mayor" not in out
    assert ("- **Family triangles:** Kerr describes how triangles form in families under "
            "stress.\n- Kerr says distance") in out
    flag2 = "Kerr describes how triangles form in families under stress."
    out2, removed2, _ = _remove(SUMMARY, [flag2])
    assert "Family triangles" not in out2  # the bold label alone is not kept
    assert len(removed2) == 1


def test_rm1b_paragraph_removed_without_double_blank():
    text = "### A\n\nFirst paragraph says one thing at length here.\n\nSecond paragraph with the flagged claim in it.\n\nThird paragraph says another thing here.\n"
    out, _, _ = _remove(text, ["Second paragraph with the flagged claim in it."])
    assert out == ("### A\n\nFirst paragraph says one thing at length here.\n\n"
                   "Third paragraph says another thing here.\n")


# --- RM1.c ---------------------------------------------------------------------------

def test_rm1c_heading_and_reemitted_name_kept_with_reason():
    text = "## Section 2 – Events of 1972\n\nKerr describes the events in some detail.\n\nMore text follows about the family here.\n"
    heading_claim = "Section 2 – Events of 1972"
    assert heading_claim in fj.extract_claims(text)
    out, removed, kept = _remove(text, [heading_claim, "Luciano Malorni", "Events of 1972"])
    assert out == text and removed == []
    reasons = {k.claim: k.reason for k in kept}
    assert reasons[heading_claim] == "a heading (headings are not edited)"
    assert reasons["Events of 1972"] == "only in a heading, a label or the front matter"
    assert reasons["Luciano Malorni"] == "not found as a whole sentence"


def test_rm1c_claim_not_found_kept():
    out, removed, kept = _remove(SUMMARY, ["Nothing like this is in the summary at all."])
    assert out == SUMMARY and removed == []
    assert kept[0].reason == "not found as a whole sentence"


# --- RM1.e ---------------------------------------------------------------------------

OVERVIEW = '''```yaml
slug: "why-families-repeat"
faq:
  - q: "Who is Michael Kerr?"
    a: "Michael Kerr is a long-time student of Murray Bowen. Bowen theory has been part of his life for more than 60 years."
  - q: "What does Kerr recommend?"
    a: "Kerr recommends reading the collected papers of Murray Bowen."
```

# Why Families Repeat

## Who is Michael Kerr?

Michael Kerr is a long-time student of Murray Bowen. Bowen theory has been part of his life for more than 60 years.

## What does Kerr recommend?

Kerr recommends reading the collected papers of Murray Bowen. He says watching the system can settle people.
'''


def _front_matter(text):
    return yaml.safe_load(text.split("```yaml\n", 1)[1].split("\n```", 1)[0])


def test_rm1e_faq_copy_removed_front_matter_parses():
    flag = "Bowen theory has been part of his life for more than 60 years."
    out, removed, kept = _remove(OVERVIEW, [flag], max_share=0.5)
    assert flag not in out
    fm = _front_matter(out)
    assert fm["faq"][0]["a"] == "Michael Kerr is a long-time student of Murray Bowen."
    assert removed[0].in_front_matter is True
    assert kept == []


def test_rm1e_empty_answer_drops_pair():
    flag = "Kerr recommends reading the collected papers of Murray Bowen."
    out, removed, _ = _remove(OVERVIEW, [flag], max_share=0.5)
    fm = _front_matter(out)
    assert [p["q"] for p in fm["faq"]] == ["Who is Michael Kerr?"]
    assert "He says watching the system can settle people." in out


# --- RM1.f ---------------------------------------------------------------------------

def test_rm1f_last_sentence_under_heading_kept():
    text = ("### Opening\n\nKerr opens with a long story about his family.\n\n"
            "### Closing\n\nKerr closes by announcing a new book next year.\n")
    out, removed, kept = _remove(text, ["Kerr closes by announcing a new book next year."],
                                 max_share=0.9)
    assert out == text and removed == []
    assert kept[0].reason == "only text under heading 'Closing'"


# --- RM1.h ---------------------------------------------------------------------------

def test_rm1h_cap_keeps_draft_and_announces():
    """A real-length draft (~800 words) whose flagged sentences are over 25% of its
    words: nothing is removed and the reason gives the share."""
    filler = " ".join(f"Kerr makes point number {i} about the family as a system." for i in range(60))
    flagged = [f"The speaker invents event number {i} that never happened in the talk." for i in range(22)]
    text = "### Body\n\n" + filler + " " + " ".join(flagged) + "\n"
    assert len(text.split()) > 800
    out, removed, kept = _remove(text, flagged, max_share=0.25)
    assert out == text and removed == []
    assert len(kept) == len(flagged)
    assert kept[0].reason == "would remove 29% of the words (cap 25%)"


# --- RM1.i ---------------------------------------------------------------------------

def test_rm1i_name_sentences_removed():
    text = ("### Body\n\nKerr describes the case of Ann Example in detail here. "
            "He says the family was anxious. Later Ann Example moved away from home.\n")
    flag = fr.Flag("the name 'Ann Example' does not appear in the source",
                   kind="name", name="Ann Example")
    out, removed, kept = _remove(text, [flag], max_share=0.9)
    assert "Ann Example" not in out
    assert "He says the family was anxious." in out
    assert [r.reason for r in removed] == ["name 'Ann Example'"] * 2
    assert kept == []


def test_rm1i_name_in_heading_kept():
    text = "## Ann Example's Story\n\nKerr describes the family in detail at length.\n"
    flag = fr.Flag("the name 'Ann Example' does not appear in the source",
                   kind="name", name="Ann Example")
    out, removed, kept = _remove(text, [flag])
    assert out == text and removed == []
    assert kept[0].reason == "only in a heading, a label or the front matter"


def test_rm1a_partly_removed_flag_listed_as_kept():
    """learning-qa F1: a flag removed in one place but kept in another (a section's
    only text) is listed as kept, so the stage does not say every flag was removed."""
    flag = "He says the choir will tour next spring."
    text = ("### A\n\nMichael Kerr presents two lectures on Bowen theory. " + flag +
            " The first lecture traces the history of cosmology.\n\n### B\n\n" + flag + "\n")
    out, removed, kept = _remove(text, [flag])
    assert [r.sentence for r in removed] == [flag]
    assert out.count(flag) == 1 and out.endswith("### B\n\n" + flag + "\n")
    assert kept == [fr.Kept(flag, "removed in part; one copy kept: only text under heading 'B'")]


def test_rm1i_name_left_in_label_listed_as_kept():
    """learning-qa F1: the name's sentence is removed, but the name is still in a bold
    label, so the flag is listed as kept."""
    text = ("### Body\n\n- **Ann Example:** Kerr describes the family in detail here.\n"
            "- Kerr mentions Ann Example again in a later part of the talk.\n"
            "- He says anxiety moves through the family over many years.\n")
    flag = fr.Flag("the name 'Ann Example' does not appear in the source",
                   kind="name", name="Ann Example")
    out, removed, kept = _remove(text, [flag])
    assert [r.sentence for r in removed] == [
        "Kerr mentions Ann Example again in a later part of the talk."]
    assert "**Ann Example:**" in out
    assert kept == [fr.Kept(flag, "removed in part; one copy kept: "
                                  "only in a heading, a label or the front matter")]


# --- Cold sweep 2026-10-19 (Mini1): removal text fixes --------------------------------

def test_rm1b_marker_run_line_does_not_backtrack():
    """Security review: a line left as a long run of list markers plus text made
    _EMPTY_LINE backtrack exponentially (22 dashes took 0.6 s; each one doubles it).
    The match runs in a child process with a timeout, so a regression fails, not hangs.
    The removal runs there too: since RM1.b.1 it also matches _MARKED_LABEL on the line."""
    import subprocess
    import sys
    probe = ("import flagged_removal as fr\n"
             "assert fr._EMPTY_LINE.match('-' * 60 + ' text') is None\n"
             "assert fr._EMPTY_LINE.match('*' * 60 + ' text') is None\n"
             "flag = 'The speaker said ten things in the opening part.'\n"
             "text = '### Body\\n\\n' + '-' * 40 + ' ' + flag + ' The speaker also said more.\\n'\n"
             "removed = fr.remove_flagged_sentences(text, [flag], max_share=0.9)[1]\n"
             "assert [r.sentence for r in removed] == [flag]\n")
    try:
        subprocess.run([sys.executable, "-c", probe], cwd=REPO, check=True, timeout=20)
    except subprocess.TimeoutExpired:
        pytest.fail("a removal regex backtracks on a run of list markers")
    assert fr._EMPTY_LINE.match("- **Label:**") is not None


def test_rm1i_claim_and_name_flag_same_sentence_cut_once():
    """Correctness review #1: a claim flag and a name flag on one sentence cut it twice,
    which deleted the unflagged short sentence after it or refused every removal."""
    claim = "Malorni studied the cells in 1975 at the institute."
    name = fr.Flag("the name 'Malorni' does not appear in the source",
                   kind="name", name="Malorni")
    for after in ("He was sure of it.", "Kerr describes the family system in detail here."):
        text = ("### Body\n\nKerr opens the talk with a story about his family. "
                f"{claim} {after}\n")
        out, removed, kept = _remove(text, [claim, name])
        assert [r.sentence for r in removed] == [claim]
        assert after in out and claim not in out
        assert kept == []


def test_rm1a_fq_tagged_and_plain_copy_section_not_emptied():
    """Correctness review #1, case B: the same sentence flagged with and without its FQ
    tag was cut twice and took the section's other sentence with it."""
    text = ("## Is moving away the same as differentiation?\n\n"
            "Michael Kerr says distance is never differentiation of self. "
            "Kerr adds a detail about his own family here.\n")
    tagged = fj.extract_claims(text)[0]
    plain = fj._claim_body(tagged)
    out, removed, kept = _remove(text, [tagged, plain])
    assert "Kerr adds a detail about his own family here." in out
    assert [r.sentence for r in removed] == [plain] and kept == []


def test_rm1g_short_unflagged_sentence_lost_rejected():
    """Correctness review #1: the check compared claims only, so losing a sentence too
    short to be a claim passed."""
    before = "### Body\n\nKerr tells a long story about the family. He was sure. It ends.\n"
    after = "### Body\n\nKerr tells a long story about the family. It ends.\n"
    problems = fr.deletion_problems(before, after, set())
    assert any("a sentence was lost that was not flagged: 'He was sure.'" in p
               for p in problems)


@pytest.mark.parametrize("line, flag", [
    ("He served with Sen. Smith on the research into family units.", "He served with Sen."),
    ("She earned her Ph.D. Then she studied families in the clinic.",
     "Then she studied families in the clinic."),
    ("The study by Bowen et al. The results showed a pattern in families.",
     "The results showed a pattern in families."),
    ("The meeting was held in Sept. That autumn he moved to the clinic.",
     "That autumn he moved to the clinic."),
    ("The family moved in 1959. 20 years later the pattern came back again.",
     "The family moved in 1959."),
])
def test_rm1a_unsure_boundary_more_abbreviations(line, flag):
    """Re-sweep (learning-qa #2, #7): Ph.D., titles, "et al.", months and a following
    number were not all treated as uncertain splits."""
    text = f"### Body\n\nKerr opens with a long story about the family. {line}\n"
    out, removed, kept = _remove(text, [flag])
    assert out == text and removed == []
    assert kept == [fr.Kept(flag, fr.UNSURE_BOUNDARY)]


def test_rm1a_unsure_copy_kept_other_copy_removed():
    """Re-sweep (learning-qa #7): a flag with one sure and one uncertain copy removes
    the sure one and is listed as kept in part."""
    flag = "Army for many years before that."
    text = ("### A\n\nKerr opens with a long story about the family. " + flag +
            " Kerr adds a long example about his own family.\n\n### B\n\n"
            "Kerr opens the second part with a story. He trained with the U.S. " + flag + "\n")
    out, removed, kept = _remove(text, [flag])
    assert [r.sentence for r in removed] == [flag] and out.count(flag) == 1
    assert kept == [fr.Kept(flag, "removed in part; one copy kept: " + fr.UNSURE_BOUNDARY)]


def test_rm1i_name_in_unsure_split_takes_whole_sentence():
    """Re-sweep (learning-qa #3): a name in an uncertain split was kept, so the entity
    check failed the stage. The whole sentence (both parts) is removed."""
    name = fr.Flag("the name 'Malorni' does not appear in the source",
                   kind="name", name="Malorni")
    text = ("### Body\n\nKerr opens with a long story about the family. "
            "Dr. Malorni worked in the U.S. Army lab for many years. "
            "Kerr adds a long example about his own family.\n")
    out, removed, kept = _remove(text, [name])
    assert "Malorni" not in out and "Army lab" not in out and "U.S." not in out
    assert "Kerr adds a long example about his own family." in out
    assert [r.sentence for r in removed] == ["Dr. Malorni worked in the U.S.",
                                             "Army lab for many years."]
    assert kept == []


def test_rm1i_claim_and_name_same_sentence_unplaced_item_not_kept():
    """Re-sweep (learning-qa #1): when the guard cannot place an item, a claim whose
    sentence a name flag removes anyway was listed as kept."""
    claim = "Malorni studied the cells in 1975 at the institute."
    name = fr.Flag("the name 'Malorni' does not appear in the source",
                   kind="name", name="Malorni")
    text = ("### Body\n\nKerr opens the talk with a story about his family. "
            f"{claim} Kerr describes the family system in detail here.\n")
    out, removed, kept = _remove(text, [claim, name], guard=lambda b, a: [("Item X", ["zzz"])])
    assert claim not in out and kept == []
    assert removed[0].reason == "faithfulness (also name 'Malorni')"


def test_rm4a_two_reasons_listed():
    """Re-sweep (learning-qa #9): a sentence two flags named listed only the first."""
    r = {"reason": "faithfulness (also name 'Malorni')", "label": "unsupported",
         "rationale": "Not in the source."}
    assert rr._why(r) == "judge: unsupported — Not in the source. (also name 'Malorni')"


def test_rm1b_bold_lead_sentence_not_dropped():
    """Re-sweep (learning-qa #5, older than the sweep): removing the sentence after a
    bold lead sentence dropped the line, and the bold sentence with it, unrecorded."""
    flag = "He says the choir will tour next spring."
    text = ("### Body\n\nKerr opens with a long story about the family.\n\n"
            "**Kerr says the family is one emotional unit.** " + flag + "\n")
    out, removed, kept = _remove(text, [flag])
    assert "**Kerr says the family is one emotional unit.**" in out and flag not in out
    assert fr._EMPTY_LINE.match("- **Family triangles:**")


def test_rm1a_unsure_sentence_boundary_kept():
    """Correctness review #2: "U.S." and "Jan." split a sentence in two; removing one
    half left a fragment. Such sentences are kept, with the reason."""
    cases = [("He trained with the U.S. Army for many years before that.",
              "Army for many years before that."),
             ("He trained with the U.S. Army for many years before that.",
              "He trained with the U.S."),
             ("The meeting was held in Jan. 1975 he moved to the clinic.",
              "The meeting was held in Jan.")]
    for line, flag in cases:
        text = f"### Body\n\nKerr opens with a long story about the family. {line}\n"
        out, removed, kept = _remove(text, [flag])
        assert out == text and removed == []
        assert kept == [fr.Kept(flag, fr.UNSURE_BOUNDARY)]


@pytest.mark.parametrize("answer", [
    "a: 'Michael Kerr is a long-time student of Murray Bowen. {flag}'",
    "a: Michael Kerr is a long-time student of Murray Bowen. {flag}",
    "a: >-\n      Michael Kerr is a long-time student of Murray Bowen. {flag}",
])
def test_rm1e_unreadable_faq_answer_listed_as_kept(answer):
    """learning-qa #1 / correctness review #4: an FAQ answer that is not one
    double-quoted line kept the removed sentence, and nothing said so."""
    flag = "Bowen theory has been part of his life for more than 60 years."
    old = ('a: "Michael Kerr is a long-time student of Murray Bowen. Bowen theory has been '
           'part of his life for more than 60 years."')
    assert OVERVIEW.count(old) == 1
    text = OVERVIEW.replace(old, answer.format(flag=flag))
    out, removed, kept = _remove(text, [flag], max_share=0.5)
    assert [r.sentence for r in removed] == [flag]
    assert kept == [fr.Kept(flag, "removed from the body; still in the front matter's "
                                  "FAQ answers")]


def test_rm1a_body_copy_not_located_reason():
    """Correctness review #5: a copy left because it could not be located in the body
    was reported as being in a heading, a label or the front matter."""
    flag = "Dr. Bowen says the family moves as one emotional unit."
    text = ("### A\n\n" + flag + " Kerr adds a long example about his own family.\n\n"
            "### B\n\nKerr opens the second part with a story. "
            "Dr.  Bowen says the family moves as one emotional unit.\n")
    out, removed, kept = _remove(text, [flag])
    assert [r.sentence for r in removed] == [flag]
    assert kept == [fr.Kept(flag, "removed in part; one copy kept: " + fr.NOT_FOUND)]


# --- Items C and B (2026-10-20): RM1.g.1, RM1.i.1, RM1.i.2 ----------------------------

ZED = fr.Flag("the name 'Zed Example' does not appear in the source",
              kind="name", name="Zed Example")
OPENING = "### Body\n\nKerr opens with a long story about the family.\n\n"
NOTE = "Note: the family was anxious about the move to the city."
REST = " Kerr adds a long example about his own family.\n"


def test_rm1g1_label_after_removed_claim_removed():
    """Item C: removing the first sentence of a line put "Note: ..." at the start of the
    line, where the label is stripped, so the deletion check refused the removal."""
    flag = "Kerr says the move happened in the spring of that year."
    text = f"{OPENING}{flag} {NOTE}{REST}"
    out, removed, kept = _remove(text, [flag])
    assert [r.sentence for r in removed] == [flag] and kept == []
    assert out == f"{OPENING}{NOTE}{REST}"  # the label stays in the text


def test_rm1g1_label_after_removed_name_removed():
    """Item C: the refusal also kept a name, so the entity check failed the stage. A
    short sentence that is a claim only with its label ("Note: Kerr agreed.") is not a
    claim at the start of a line; that is not a loss either."""
    for after in (NOTE, "Note: Kerr agreed."):
        text = f"{OPENING}Zed Example spoke at length about the move. {after}{REST}"
        out, removed, kept = _remove(text, [ZED])
        assert [r.sentence for r in removed] == ["Zed Example spoke at length about the move."]
        assert kept == [] and out == f"{OPENING}{after}{REST}"


def test_rm1g1_enumerator_after_removed_name_removed():
    """Item C, enumerator: "2) Then ..." starts the line once the name sentence before it
    goes (it no longer joins that sentence, RM1.i.1)."""
    second = "2) Then the family moved to the city."
    text = f"{OPENING}Zed Example spoke at length about the move. {second}{REST}"
    out, removed, kept = _remove(text, [ZED])
    assert [r.sentence for r in removed] == ["Zed Example spoke at length about the move."]
    assert kept == [] and out == f"{OPENING}{second}{REST}"


def test_rm1g1_unflagged_label_sentence_lost_still_caught():
    """RM1.g.1 adversarial (P7): reading "Note: X" as "X" must not hide a real loss. An
    unflagged "Note: ..." sentence deleted with the flagged one is still reported."""
    flag = "Kerr says the move happened in the spring of that year."
    before = f"{OPENING}{flag} {NOTE}{REST}"
    after = f"{OPENING}{REST.lstrip()}"
    problems = fr.deletion_problems(before, after, {flag})
    assert any("not flagged" in p and "the family was anxious" in p for p in problems)


def test_rm1g1_skip_label_moved_to_line_start_still_refused():
    """RM1.g.1 adversarial: a "Status:" line is skipped whole by extract_claims, so moving
    "Status: ..." to the start of its line would hide its claims from the judge. That
    removal is still refused, with the reason. The "Status:" sentence is the only
    other one on its line, so it is what the refusal names."""
    flag = "Kerr says the move happened in the spring of that year."
    status = "Status: the family was anxious about the move."
    text = f"{OPENING}{flag} {status}\n\n{REST.lstrip()}"
    out, removed, kept = _remove(text, [flag])
    assert out == text and removed == []
    assert kept[0].claim == flag and kept[0].reason.startswith("deletion check failed")
    assert status in kept[0].reason


def test_rm1g1_short_claim_on_skipped_line_still_refused():
    """learning-qa #2: "Note: Kerr agreed." is a claim, "Kerr agreed." is not. Once its
    line starts with "Status:", the judge skips the line, so it is lost, not only
    shorter: the removal is refused."""
    text = (f"{OPENING}Zed Example spoke at length about the move. Status: done. "
            f"Note: Kerr agreed.\n\n{REST.lstrip()}")
    out, removed, kept = _remove(text, [ZED])
    assert out == text and removed == []
    assert kept[0].reason.startswith("deletion check failed") and "Kerr agreed." in kept[0].reason


def test_rm1g1_long_claim_judge_no_longer_reads_is_lost(monkeypatch):
    """RM1.g.1: the exemption is for claims too short to count without their label. A
    long claim extract_claims no longer returns is lost, even with its sentence still
    on a line (here the second call, on ``after``, leaves it out)."""
    x = "Kerr says the move happened in the spring of that year."
    text = f"{OPENING}{x}{REST}"
    real, calls = fj.extract_claims, []

    def claims(t, *a, **k):
        calls.append(t)
        out = real(t, *a, **k)
        return out if len(calls) == 1 else [c for c in out if c != x]

    monkeypatch.setattr(fj, "extract_claims", claims)
    problems = fr.deletion_problems(text, text, set())
    assert any("claim was lost" in p and x[:30] in p for p in problems)


def test_rm1g1_label_copy_lost_is_counted():
    """learning-qa #3: with "Note: X" read as "X", removing one X must not let an
    unflagged "Note: X" copy go too. Copies are counted; two cut copies may both go."""
    x = "Kerr says the move happened in the spring of that year."
    before = f"{OPENING}{x} Kerr adds a long example about his own family. Note: {x}\n"
    after = f"{OPENING}Kerr adds a long example about his own family.\n"
    problems = fr.deletion_problems(before, after, {x})
    assert any("claim was lost" in p and x[:30] in p for p in problems)
    assert any("sentence was lost" in p and x[:30] in p for p in problems)
    from collections import Counter
    assert fr.deletion_problems(before, after, Counter({x: 2})) == []


@pytest.mark.parametrize("copy", ["Note: Kerr agreed.", "Kerr agreed."])
def test_rm1g1_short_claim_copy_on_other_line_does_not_excuse_loss(copy):
    """learning-qa re-check #1: "Kerr agreed." already on another line, read and not a
    claim, does not make up for the "Note: Kerr agreed." claim lost when its line came
    to start with "Status:". Only sentences that stopped being claims count."""
    text = (f"{OPENING}Zed Example spoke at length about the move. Status: done. "
            f"Note: Kerr agreed.\n\n{copy}\n\n{REST.lstrip()}")
    out, removed, kept = _remove(text, [ZED])
    assert out == text and removed == []
    assert kept[0].reason.startswith("deletion check failed") and "Kerr agreed." in kept[0].reason


def test_rm1g1_sentence_on_line_judge_skipped_does_not_excuse_loss():
    """RM1.g.1: "Kerr agreed." on a "Status:" line the judge skipped was never a claim.
    When the cut makes the judge read that line, it does not make up for the "Note: Kerr
    agreed." claim lost on the line that now starts with "Status:"."""
    text = (f"{OPENING}Zed Example spoke at length about the move. Status: done. "
            f"Note: Kerr agreed.\n\nStatus: Zed Example did it. Kerr agreed.\n\n"
            f"{REST.lstrip()}")
    out, removed, kept = _remove(text, [ZED])
    assert out == text and removed == []
    assert kept[0].reason.startswith("deletion check failed") and "Kerr agreed." in kept[0].reason


def test_rm1g1_dropped_line_text_does_not_excuse_loss():
    """learning-qa re-check #2: a line removed whole excused any lost sentence found in
    its text, without counting copies. "Kerr agreed." inside the removed sentence is not
    the "Kerr agreed." sentence on another line."""
    removed_line = "- Zed Example said that Kerr agreed."
    before = (f"{OPENING}{removed_line}\n\n"
              f"Kerr adds a long example about his own family. Kerr agreed.\n")
    after = f"{OPENING}Kerr adds a long example about his own family.\n"
    problems = fr.deletion_problems(before, after, {"Zed Example said that Kerr agreed."},
                                    [removed_line])
    assert any("sentence was lost" in p and "Kerr agreed." in p for p in problems)
    # The same for a claim: only claims read from the removed line itself may go with it.
    claim = "Kerr agreed to the move in the spring."
    removed_line = f"- Zed Example said that {claim}"
    before = f"{OPENING}{removed_line}\n\nKerr adds a long example about his own family. {claim}\n"
    problems = fr.deletion_problems(before, after, {f"Zed Example said that {claim}"},
                                    [removed_line])
    assert any("claim was lost" in p and claim[:20] in p for p in problems)


@pytest.mark.parametrize("label", ["**Kerr Agreed** —", "• **Kerr Agreed:**"])
def test_rm1g1_label_line_under_question_heading_goes(label):
    """learning-qa re-check 2 #1: under a question heading the judge reads the first
    line's label and sentence as one claim ("Kerr Agreed — Zed Example ..."). The
    line's claims are read in the document, so removing the line is not refused."""
    question = "### Why did they move?\n\n"
    text = (f"{question}{label} Zed Example spoke at length about the move.\n\n"
            f"Kerr adds a long example about his own family.\n")
    out, removed, kept = _remove(text, [ZED])
    assert kept == [] and len(removed) == 1
    assert out == f"{question}Kerr adds a long example about his own family.\n"


def test_rm1g1_question_tagged_short_sentence_is_a_claim():
    """learning-qa re-check 2 #2: a short first sentence under a question heading is a
    claim (the judge adds the question). Counting it as too short excused the "Note:
    Kerr agreed." claim lost on the line that now starts with "Status:"."""
    text = ("### Why did they move?\n\nZed Example moved them. Note: Kerr agreed.\n\n"
            "Kerr adds a long example about his own family.\n\n### Later\n\n"
            "Zed Example spoke at length. Status: ok. Note: Kerr agreed.\n\n"
            "Kerr ends with a long story about the family.\n")
    out, removed, kept = _remove(text, [ZED])
    assert out == text and removed == []
    assert kept[0].reason.startswith("deletion check failed") and "Kerr agreed." in kept[0].reason


def test_rm1g1_dropped_line_sentence_counted_once():
    """RM1.g: the sentence of a line removed whole is counted once, as cut. Its copy on a
    line that stays is not excused by the line too."""
    x = "Kerr says the move happened in the spring of that year."
    before = f"{OPENING}- {x}\n\nKerr adds a long example about his own family. {x}\n"
    after = f"{OPENING}Kerr adds a long example about his own family.\n"
    problems = fr.deletion_problems(before, after, {x}, [f"- {x}"])
    assert any("claim was lost" in p and x[:30] in p for p in problems)


@pytest.mark.parametrize("label", ["1. **Kerr Agreed:**", "**Kerr Agreed:**"])
def test_rm1g1_label_claim_goes_with_its_line(label):
    """RM1.g: extract_claims reads a capitalised bold label ("Kerr Agreed") as a claim of
    its own. Removing the line's only sentence removes the line and the label with it;
    that is not a loss. After "1. " the judge reads the label with the sentence; the cut
    leaves the label, and the line left with only it goes (RM1.b.1)."""
    text = f"{OPENING}{label} Zed Example spoke at length about the move.\n\n{REST.lstrip()}"
    out, removed, kept = _remove(text, [ZED])
    assert kept == [] and len(removed) == 1 and "Zed Example" not in out
    assert out == f"{OPENING}{REST.lstrip()}"


def test_rm1i1_name_before_number_split_takes_only_its_sentence():
    """Item B: a split before a number joined the two sentences, so a name also deleted
    the correct sentence after it. The name takes only its own sentence."""
    text = (f"{OPENING}Zed Example spoke at length about the move. "
            f"2020 was a hard year for the whole family.{REST}")
    out, removed, kept = _remove(text, [ZED])
    assert [r.sentence for r in removed] == ["Zed Example spoke at length about the move."]
    assert kept == [] and out == f"{OPENING}2020 was a hard year for the whole family.{REST}"


def test_rm1i1_claim_before_number_split_still_kept():
    """RM1.i.1: the split before a number is still uncertain for a claim, on either side."""
    line = "The family moved to the city in the spring. 2020 was a hard year for them all."
    for flag in ("The family moved to the city in the spring.",
                 "2020 was a hard year for them all."):
        text = f"{OPENING}{line}{REST}"
        out, removed, kept = _remove(text, [flag])
        assert out == text and removed == []
        assert kept == [fr.Kept(flag, fr.UNSURE_BOUNDARY)]


@pytest.mark.parametrize("line", [
    "Zed Example covered this in ch. 4 of the book.",
    "Kerr covers this in ch. 4 with Zed Example as the case.",
    "Zed Example ran the clinic, est. 1950 in the city.",
    "Zed Example wrote about it in sec. 3 of the report.",
    "Zed Example played op. 27 in the spring of that year.",
])
def test_rm1i1_name_after_abbreviation_before_number_takes_both_parts(line):
    """learning-qa #1: "ch. 4", "est. 1950", "op. 27" were joined only by the number rule,
    so after RM1.i.1 a name left a fragment ("4 of the book."). They are listed
    abbreviations."""
    text = f"{OPENING}{line}{REST}"
    out, removed, kept = _remove(text, [ZED])
    assert out == f"{OPENING}{REST.lstrip()}" and kept == []
    assert len(removed) == 2


def test_rm1i2_two_names_each_part_gives_its_own_name():
    """learning-qa #4: with a name in each part, each part is recorded under its own
    name, not as "same sentence as" the other."""
    smith = fr.Flag("the name 'Smith' does not appear in the source", kind="name",
                    name="Smith")
    text = f"{OPENING}Zed Example served with Sen. Smith on the committee for years.{REST}"
    for flags in ([ZED, smith], [smith, ZED]):
        out, removed, kept = _remove(text, flags)
        assert [(r.sentence, r.reason) for r in removed] == [
            ("Zed Example served with Sen.", "name 'Zed Example'"),
            ("Smith on the committee for years.", "name 'Smith'")]


def test_rm1i2_split_part_without_name_has_own_reason():
    """Item B: the part of an abbreviation split without the name was recorded under the
    name. It now says it is the same sentence, split where it may not end."""
    text = f"{OPENING}Zed Example served with Sen. Smith on the committee for years.{REST}"
    out, removed, kept = _remove(text, [ZED])
    assert [(r.sentence, r.reason) for r in removed] == [
        ("Zed Example served with Sen.", "name 'Zed Example'"),
        ("Smith on the committee for years.",
         "same sentence as name 'Zed Example' (uncertain split)")]
    assert kept == [] and "Smith" not in out
    assert rr._why({"reason": removed[1].reason}) == removed[1].reason  # the list's text


# --- Bold label after a list or quote marker (2026-10-20): RM1.b.1, RM1.b.2, RM1.g.2,
# --- RM1.g.3

LABEL = "**Kerr Agreed:**"
ZED_SENTENCE = "Zed Example spoke at length about the move."
SECONDS = ["Then the family moved to the city in the spring.",
           "2020 was a hard year for the whole family."]
QUESTION = "### What did Kerr say?\n\n"
AFTER = "\n\nKerr adds a long example about his own family.\n"


@pytest.mark.parametrize("second", SECONDS)
@pytest.mark.parametrize("lead", ["1. ", "1) ", "- 1. ", "> ", "> - ", "+ ", "• ", "- "])
def test_rm1b1_name_sentence_after_marked_label_takes_own_span(lead, second):
    """TODO 2026-10-20: after "1. " or "> " the sentence's span started inside the bold
    label, so the cut left "1. **" and the deletion check refused; after "+ " it took the
    marker and the label too. The span starts after the label, which stays with its
    markers. "• " and "- " lines were already right (guards)."""
    text = f"{OPENING}{lead}{LABEL} {ZED_SENTENCE} {second}{AFTER}"
    out, removed, kept = _remove(text, [ZED])
    assert kept == [] and [r.sentence for r in removed] == [ZED_SENTENCE]
    assert out == f"{OPENING}{lead}{LABEL} {second}{AFTER}"


@pytest.mark.parametrize("lead", ["1. ", "> ", "• ", "+ "])
def test_rm1b1_marked_label_under_question_heading(lead):
    """Under a question heading the judge reads the label with the first sentence on
    each of these lines ("• Kerr Agreed: Zed ..."), and after the cut with the next one,
    which is the same sentence, not a new claim (RM1.g.2)."""
    text = f"{QUESTION}{lead}{LABEL} {ZED_SENTENCE} {SECONDS[0]}{AFTER}"
    out, removed, kept = _remove(text, [ZED])
    assert kept == [] and [r.sentence for r in removed] == [ZED_SENTENCE]
    assert out == f"{QUESTION}{lead}{LABEL} {SECONDS[0]}{AFTER}"


@pytest.mark.parametrize("lead", ["1. ", "1) ", "- 1. ", "> ", "> - ", "+ "])
def test_rm1b1_last_sentence_after_marked_label_line_goes(lead):
    """The line's only sentence: the line goes with its markers and label. The record
    holds the words cut, without the label (it held "Kerr Agreed: Zed ...")."""
    text = f"{OPENING}{lead}{LABEL} {ZED_SENTENCE}{AFTER}"
    out, removed, kept = _remove(text, [ZED])
    assert kept == [] and [r.sentence for r in removed] == [ZED_SENTENCE]
    assert out == f"{OPENING}{REST.lstrip()}"


@pytest.mark.parametrize("lead", ["1. ", "> ", "+ "])
def test_rm1b1_claim_flag_after_marked_label(lead):
    """A claim flag is the judge's reading, label included ("Kerr Agreed: Zed ..."). It
    still finds the sentence, and the cut leaves the label. The flag is also listed as
    kept (learning-qa): the label stays and is now read with the next sentence, which no
    judge has seen with it. When the line goes, the label goes too and nothing is kept."""
    text = f"{OPENING}{lead}{LABEL} {ZED_SENTENCE} {SECONDS[0]}{AFTER}"
    claim = next(c for c in fj.extract_claims(text) if ZED_SENTENCE in c)
    assert claim != ZED_SENTENCE  # the judge reads the label with it
    out, removed, kept = _remove(text, [claim])
    assert [r.sentence for r in removed] == [ZED_SENTENCE]
    assert kept == [fr.Kept(claim, fr.LABEL_LEFT)]
    assert out == f"{OPENING}{lead}{LABEL} {SECONDS[0]}{AFTER}"
    text = f"{OPENING}{lead}{LABEL} {ZED_SENTENCE}{AFTER}"
    claim = next(c for c in fj.extract_claims(text) if ZED_SENTENCE in c)
    out, removed, kept = _remove(text, [claim])
    assert kept == [] and out == f"{OPENING}{REST.lstrip()}"


def test_rm1b1_faq_copy_of_sentence_after_marked_label_removed():
    """RM1.e: the FAQ answer holds the sentence without the label, so the copy is found
    by the words cut, not by the judge's reading with the label."""
    sentence = "Kerr recommends reading the collected papers of Murray Bowen."
    text = OVERVIEW.replace(f"\n{sentence} He says", f"\n1. {LABEL} {sentence} He says")
    claim = next(c for c in fj.extract_claims(text) if sentence in c)
    out, removed, kept = _remove(text, [fr.Flag(claim)], max_share=0.5)
    assert f"1. {LABEL} He says watching the system can settle people." in out
    assert [p["q"] for p in _front_matter(out)["faq"]] == ["Who is Michael Kerr?"]
    assert [(r.sentence, r.in_front_matter) for r in removed] == [(sentence, True)]
    assert kept == [fr.Kept(claim, fr.LABEL_LEFT)]


def test_rm1e_faq_copy_left_listed_for_each_flag():
    """learning-qa: two labelled copies of one sentence, each flagged with its own label.
    The FAQ answer is unquoted, so its copy stays; both flags say so, not only one, and
    say that their labels stay (re-check R4)."""
    sentence = "Kerr recommends reading the collected papers of Murray Bowen."
    text = OVERVIEW.replace(f'a: "{sentence}"', f"a: {sentence}").replace(
        f"\n{sentence} He says watching the system can settle people.",
        f"\n1. **Kerr Agreed:** {sentence} He says watching the system can settle people."
        f"\n2. **Kerr Denied:** {sentence} Then he left the room before the end.")
    flags = [c for c in fj.extract_claims(text) if sentence in c and c != sentence]
    assert len(flags) == 2
    out, removed, kept = _remove(text, flags, max_share=0.5)
    assert [r.sentence for r in removed] == [sentence, sentence]
    faq = f"{fr.IN_FAQ}; {fr.LABEL_STAYS}"
    assert kept == [fr.Kept(flags[0], faq), fr.Kept(flags[1], faq)]


@pytest.mark.parametrize("lead", ["1. ", "+ "])
def test_rm1b1_number_inside_bold_label(lead):
    """learning-qa re-check R1: the judge reads "**2) Key point:**" as "Key point:" (the
    number is part of the line's lead), so the deletion check reads it that way too. The
    first fix refused all four. 813dd3c removed the one-sentence lines, cut the label with
    the sentence on "+ " lines, and left a stray "**" on the "1. " line."""
    line = f"{lead}**2) Key point:** {ZED_SENTENCE}"
    out, removed, kept = _remove(f"{OPENING}{line} {SECONDS[0]}{AFTER}", [ZED])
    assert kept == [] and out == f"{OPENING}{lead}**2) Key point:** {SECONDS[0]}{AFTER}"
    out, removed, kept = _remove(f"{OPENING}{line}{AFTER}", [ZED])
    assert kept == [] and out == f"{OPENING}{REST.lstrip()}"


@pytest.mark.parametrize("lead", ["+ ", "1. ", "- ", ""])
def test_rm1g_dash_after_label_is_its_own_token(lead):
    """learning-qa re-check R2: "**Kerr Agreed**—Zed ..." with no space. The cut joins the
    dash to the next word ("**Kerr Agreed**—Then"); a dash is its own token, so that is
    still only a deletion. At 813dd3c "+ " lines lost the label instead, and the others
    were refused."""
    out, removed, kept = _remove(
        f"{OPENING}{lead}**Kerr Agreed**—{ZED_SENTENCE} {SECONDS[0]}{AFTER}", [ZED])
    assert kept == [] and out == f"{OPENING}{lead}**Kerr Agreed**—{SECONDS[0]}{AFTER}"


def test_rm1b1_abbreviation_in_bold_is_not_a_label():
    """learning-qa: the judge reads on past "**Dr.**", so it is part of the sentence, not
    a label. Cutting the sentence after it would leave "1. **Dr.** Then ..."; the
    removal is refused instead, as at 813dd3c (a bold run that opens a sentence)."""
    text = f"{OPENING}1. **Dr.** {ZED_SENTENCE} {SECONDS[0]}{AFTER}"
    out, removed, kept = _remove(text, [ZED])
    assert out == text and removed == []
    assert [k.reason.split(":")[0] for k in kept] == ["deletion check failed"]


def test_rm1b1_marked_label_regex_does_not_backtrack():
    """The markers before a label are matched one per repetition, as in _EMPTY_LINE
    (cold sweep): a long run of markers with no label must not hang. The match runs in
    a child process with a timeout, so a regression fails, not hangs."""
    import subprocess
    import sys
    probe = ("import flagged_removal as fr\n"
             "for run in ('1. ' * 60, '*' * 60, '> ' * 60, '1.' * 60, '- ' * 60):\n"
             "    assert fr._MARKED_LABEL.match(run + '**x text') is None\n")
    try:
        subprocess.run([sys.executable, "-c", probe], cwd=REPO, check=True, timeout=20)
    except subprocess.TimeoutExpired:
        pytest.fail("_MARKED_LABEL backtracks on a run of list markers")
    assert fr._MARKED_LABEL.match("> - 1. **Kerr Agreed:** text")["rest"] == "text"


def test_rm1b2_name_only_in_marked_label_kept():
    """A name only in the label of a line with more sentences: cutting the sentence after
    the label would not remove the name, so the line is left and the name kept with the
    label reason, as on a "- **Label:**" line (RM1.i). Before, the removal was refused,
    and with it every other removal in the text."""
    labelled = ("1. **Zed Example:** He spoke at length about the move. "
                "Then the family moved to the city in the spring.")
    other = "Kerr mentions Zed Example again in a later part of the talk."
    text = f"{OPENING}{labelled}\n\n{other}{REST}"
    out, removed, kept = _remove(text, [ZED])
    assert labelled in out and other not in out
    assert [r.sentence for r in removed] == [other]
    assert kept == [fr.Kept(ZED, "removed in part; one copy kept: " + fr.IN_SCAFFOLDING)]
    text = f"{OPENING}{labelled}{AFTER}"
    out, removed, kept = _remove(text, [ZED])
    assert out == text and removed == [] and kept == [fr.Kept(ZED, fr.IN_SCAFFOLDING)]


def test_rm1b2_name_in_label_of_one_sentence_line_goes():
    """With one sentence the line goes, label and name with it, as before. The record
    holds the sentence without the label (it held "Zed Example: He spoke ...")."""
    text = f"{OPENING}1. **Zed Example:** He spoke at length about the move.{AFTER}"
    out, removed, kept = _remove(text, [ZED])
    assert kept == [] and out == f"{OPENING}{REST.lstrip()}"
    assert [(r.sentence, r.reason) for r in removed] == [
        ("He spoke at length about the move.", "name 'Zed Example'")]


def test_rm1g2_label_read_with_next_sentence_passes():
    """After the cut the judge reads the label with the next sentence ("Kerr Agreed: Then
    ..."); without the label it is the same sentence. A sentence lost or a label changed
    next to it is still reported (P7)."""
    third = "Kerr adds a long example about his own family."
    before = f"{OPENING}1. {LABEL} {ZED_SENTENCE} {SECONDS[0]} {third}\n"
    cut = {f"Kerr Agreed: {ZED_SENTENCE}"}
    after = f"{OPENING}1. {LABEL} {SECONDS[0]} {third}\n"
    assert fr.deletion_problems(before, after, cut) == []
    lost = fr.deletion_problems(before, f"{OPENING}1. {LABEL} {third}\n", cut)
    assert any("not flagged" in p and SECONDS[0][:30] in p for p in lost)
    changed = fr.deletion_problems(
        before, f"{OPENING}1. **Kerr Denied:** {SECONDS[0]} {third}\n", cut)
    assert "text was added or changed, not only deleted" in changed


def test_rm1g2_label_only_sentence_compared_as_is():
    """P7: a label is taken off only the first sentence of its own line. A sentence that
    is only a label ("Key point.") is compared as it is, so a lost label-only line does
    not cancel against a line the cut left with only its label."""
    before = f"{OPENING}1. **Key point.**\n2. **Other point:** Then he left.\n{REST.lstrip()}"
    after = f"{OPENING}2. **Other point:**\n{REST.lstrip()}"
    problems = fr.deletion_problems(before, after, {"Other point: Then he left."})
    assert problems == ["a sentence was lost that was not flagged: 'Key point.'"]


@pytest.mark.parametrize("lead,label,problem", [
    ("1. ", "**Key point:**", "a bold label was lost: 'Key point:'"),
    ("1. ", "**Not true:**", "a bold label was lost: 'Not true:'"),
    ("&gt; ", "**Key point:**", "a claim was added or changed"),
])
def test_rm1g2_deleted_label_still_caught(lead, label, problem):
    """learning-qa (P7): a bold label deleted while its sentence stays is a change ("Not
    true:" turns the meaning round). The label is read off only its own line's first
    sentence, and a bold label goes only with its line."""
    sentence = "the family moved to the city in the spring of that year."
    before = f"{OPENING}{lead}{label} {sentence}\n"
    after = f"{OPENING}{lead}{sentence}\n"
    assert problem in fr.deletion_problems(before, after, set())


def test_rm1g2_label_prefix_lost_on_other_line_caught():
    """learning-qa (P7): a bold "Kerr Agreed:" on one line does not let a plain "Kerr
    Agreed: " go from another line's sentence, even one with the same words."""
    labelled = f"1. {LABEL} {ZED_SENTENCE} {SECONDS[0]}"
    plain = "the family moved to the city in 2020."
    before = f"{OPENING}{labelled}\n\nKerr Agreed: {plain}\n"
    after = f"{OPENING}{labelled}\n\n{plain}\n"
    assert "a claim was added or changed" in fr.deletion_problems(before, after, set())
    # One claim per labelled line: a plain copy of that line's reading is not its own.
    before = f"{OPENING}{labelled}\n\nKerr Agreed: {ZED_SENTENCE}\n"
    after = f"{OPENING}{labelled}\n\n{ZED_SENTENCE}\n"
    assert "a claim was added or changed" in fr.deletion_problems(before, after, set())


@pytest.mark.parametrize("lead", ["+ ", "1. ", "1. - "])
def test_rm1g3_label_makes_short_sentence_a_claim(lead):
    """D2: "Then he left." is too short to be a claim. Read with the label after the cut
    ("Key point: Then he left.") it is one, but it was a sentence before, so it is not an
    added claim. Before RM1.b.1, "+ " and "1. - " lines lost the marker and label here."""
    text = f"{OPENING}{lead}**Key point:** {ZED_SENTENCE} Then he left.{AFTER}"
    out, removed, kept = _remove(text, [ZED])
    assert kept == [] and out == f"{OPENING}{lead}**Key point:** Then he left.{AFTER}"


def test_rm1g3_question_tag_moves_to_next_sentence():
    """F6: removing the first sentence under a question heading moves the question tag
    onto the next sentence, which then reads as a claim. It was a sentence before."""
    text = f"{QUESTION}{ZED_SENTENCE} Then he left.{AFTER}"
    out, removed, kept = _remove(text, [ZED])
    assert kept == [] and out == f"{QUESTION}Then he left.{AFTER}"


def test_rm1g3_name_sentence_on_skip_label_line_removed():
    """The judge skips a line that starts with "Status:". The plain label is part of the
    first sentence, so it goes with it, and the judge then reads "2020 was a hard year."
    as a claim. It was a sentence before, so it is not added. Before D2 the removal was
    refused and the name kept (TODO.md, "stricter since RM1.i.1")."""
    line = f"Status: {ZED_SENTENCE} 2020 was a hard year."
    out, removed, kept = _remove(f"{OPENING}{line}{AFTER}", [ZED])
    assert kept == [] and out == f"{OPENING}2020 was a hard year.{AFTER}"
    assert [r.sentence for r in removed] == [f"Status: {ZED_SENTENCE}"]


def test_rm1g3_new_claim_that_was_no_sentence_still_refused():
    """P7: a claim that was not a sentence before is still an added claim. Deleting
    "May." joins two sentences into one the judge never read."""
    before = f"{OPENING}Kerr met the family in May. Then he left.\n"
    after = f"{OPENING}Kerr met the family in Then he left.\n"
    assert "a claim was added or changed" in fr.deletion_problems(before, after, set())


# --- RM2: wiring into generation ----------------------------------------------------

FLAG = "He says the choir will tour next spring."
FLAG_RECORD = {"claim": FLAG, "label": "unsupported", "rationale": "No tour is mentioned.",
               "evidence": "absent"}


def _entity_pass(monkeypatch):
    monkeypatch.setattr(rg, "check_entity_grounding", lambda *a, **k: rg.Verdict(
        "entity_grounding", rg.Status.PASS, "all proper names grounded"))


def _loop(monkeypatch, tmp_path, what="summary", drafts=None, issues=None, **kw):
    """Run _generate_until_faithful for ``what`` with fake drafts and a fake precheck
    that always fails with ``issues``. Returns (ok, saved file, logger, precheck calls)."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 2)
    (tmp_path / "B").mkdir(exist_ok=True)
    suffix = {"summary": config.SUFFIX_SUMMARY_GEN, "overview": config.SUFFIX_OVERVIEW,
              "blog": config.SUFFIX_BLOG}[what]
    path = tmp_path / "B" / f"B{suffix}"
    drafts = iter(drafts or [SUMMARY, SUMMARY])
    calls = []

    def precheck(base, sfx, logger=None):
        calls.append(path.read_text(encoding="utf-8"))
        return "fail", list(issues if issues is not None
                            else [fr.Flag(FLAG, record=FLAG_RECORD)])

    logger = MagicMock()
    ok = ep._generate_until_faithful(
        what, "B", suffix, logger, generate=lambda feedback: next(drafts),
        write=lambda t: path.write_text(t, encoding="utf-8"), precheck=precheck, **kw)
    return ok, path, logger, calls


def _warnings(logger):
    return [str(c.args[0]) % c.args[1:] for c in logger.warning.call_args_list]


def test_rm2a_summary_last_attempt_sentence_removed_and_saved(monkeypatch, tmp_path):
    _entity_pass(monkeypatch)
    ok, path, logger, _ = _loop(monkeypatch, tmp_path)
    assert ok is True
    assert path.read_text(encoding="utf-8") == SUMMARY.replace(FLAG + " ", "")
    msgs = _warnings(logger)
    assert any("removed 1 sentence(s) still flagged" in m and FLAG in m for m in msgs)
    assert "every sentence still flagged after 2 attempt(s) was removed" in msgs[-1]
    assert not logger.error.called


def test_rm2a_overview_sentence_removed_and_saved(monkeypatch, tmp_path):
    _entity_pass(monkeypatch)
    flag = "Bowen theory has been part of his life for more than 60 years."
    ok, path, _, _ = _loop(monkeypatch, tmp_path, what="overview",
                           drafts=[OVERVIEW, OVERVIEW], issues=[fr.Flag(flag)])
    assert ok is True
    saved = path.read_text(encoding="utf-8")
    assert flag not in saved
    assert _front_matter(saved)["faq"][0]["a"] == "Michael Kerr is a long-time student of Murray Bowen."


def test_rm2b_abstract_sentence_removed_and_saved(monkeypatch, tmp_path):
    from test_abstract_faithful_retry import _setup as abstract_setup
    base, proj = abstract_setup(monkeypatch, tmp_path)
    abstract = ("Michael Kerr presents two lectures on Bowen theory and its roots. "
                "The first traces the long history of cosmology from Aristotle onward. "
                "The second turns to the neuroscience of differentiation of self. "
                "He says the choir will tour next spring. "
                "Kerr links the brain's functioning to the family emotional system. "
                "He closes by describing how anxiety moves through relationships. "
                "The talk ends with questions from the audience about practice.")
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract", lambda *a, **k: abstract)
    monkeypatch.setattr(ep, "_abstract_gate_precheck",
                        lambda b, logger=None: ("fail", [fr.Flag(FLAG, record=FLAG_RECORD)]))
    assert ep.generate_structured_abstract(base, logging.getLogger("rm2b")) is True
    saved = (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").read_text(encoding="utf-8")
    assert saved == abstract.replace(FLAG + " ", "")
    record = json.loads(rr.record_path(base).read_text(encoding="utf-8"))
    assert record["artifacts"]["abstract"]["removed"][0]["sentence"] == FLAG


def test_rm2c_blog_not_changed(monkeypatch, tmp_path):
    _entity_pass(monkeypatch)
    ok, path, _, _ = _loop(monkeypatch, tmp_path, what="blog", advisory=True)
    assert ok is True
    assert path.read_text(encoding="utf-8") == SUMMARY
    assert not rr.record_path("B").exists()


def test_rm2c_switch_off_keeps_flagged_draft(monkeypatch, tmp_path):
    _entity_pass(monkeypatch)
    monkeypatch.setattr(config, "FAITHFULNESS_REMOVE_FLAGGED", False)
    ok, path, logger, _ = _loop(monkeypatch, tmp_path)
    assert ok is True
    assert path.read_text(encoding="utf-8") == SUMMARY
    assert "Faithfulness flags are warnings" in _warnings(logger)[-1]
    assert not rr.record_path("B").exists()


NAME_TEXT = ("### Body\n\nKerr describes the case of Ann Example in detail here. "
             "He says the family was anxious about the move. Kerr adds a long note about "
             "anxiety in families across generations and how it is passed on. He ends with a "
             "description of how a calm parent can lower the anxiety of the whole family.\n")
NAME_FLAG = fr.Flag("the name 'Ann Example' does not appear in the source",
                    kind="name", name="Ann Example")


def _entity_reads_file(monkeypatch, tmp_path, suffix):
    """An entity check that rejects 'Ann Example' while it is in the saved file."""
    def check(base, logger=None, suffixes=None):
        text = (tmp_path / base / f"{base}{suffix}").read_text(encoding="utf-8")
        if "Ann Example" in text:
            return rg.Verdict("entity_grounding", rg.Status.FAIL, "Ann Example",
                              items=[{"names": ["Ann Example"]}])
        return rg.Verdict("entity_grounding", rg.Status.PASS, "all proper names grounded")
    monkeypatch.setattr(rg, "check_entity_grounding", check)


def test_rm2d_entity_check_rerun_on_saved_file(monkeypatch, tmp_path):
    """D4: the sentence with the rejected name is removed and the entity check, run
    again on the saved file, passes, so the stage succeeds."""
    _entity_reads_file(monkeypatch, tmp_path, config.SUFFIX_SUMMARY_GEN)
    ok, path, _, _ = _loop(monkeypatch, tmp_path, drafts=[NAME_TEXT, NAME_TEXT],
                           issues=[NAME_FLAG])
    assert ok is True
    assert "Ann Example" not in path.read_text(encoding="utf-8")


def test_rm2d_name_in_heading_stage_still_fails(monkeypatch, tmp_path):
    _entity_reads_file(monkeypatch, tmp_path, config.SUFFIX_SUMMARY_GEN)
    text = "### Ann Example's Story\n\n" + NAME_TEXT.split("\n\n", 1)[1]
    ok, path, logger, _ = _loop(monkeypatch, tmp_path, drafts=[text, text], issues=[NAME_FLAG])
    assert ok is False
    assert "BLOCK" in logger.error.call_args.args[0]


def test_rm2e_only_mention_of_required_item_kept(monkeypatch):
    """summary_coverage blocks publication: a removal must not leave a required item
    with no keyword in the summary."""
    import summary_validation as sv
    item = sv.CoverageItem(category="topic", label="Choir tours", required=True,
                           keywords=["choir"], source_text="", expected_words=0)
    monkeypatch.setattr(sv, "generate_coverage_items", lambda summary_input: [item])
    guard = ep._coverage_guard(object())
    out, removed, kept = _remove(SUMMARY, [FLAG, "The mayor says the bridge will close next year."],
                                 guard=guard)
    assert FLAG in out
    assert [r.sentence for r in removed] == ["The mayor says the bridge will close next year."]
    assert kept == [fr.Kept(FLAG, "only mention of required item 'Choir tours'")]


def _keyword_guard(label, keyword):
    def guard(before, after):
        return ([(label, [keyword])]
                if keyword in before.lower() and keyword not in after.lower() else [])
    return guard


def test_rm2e_keyword_in_bold_label_kept():
    """learning-qa F4: the item's only keyword is in the bullet's bold label, which goes
    with the line when its sentence is removed. The sentence is kept."""
    text = SUMMARY.replace("- The mayor says the bridge will close next year.",
                           "- **Choir tours:** " + FLAG)
    out, removed, kept = _remove(text, [FLAG], guard=_keyword_guard("Choir tours", "tours"))
    assert "- **Choir tours:** " + FLAG in out
    assert [r.sentence for r in removed] == [FLAG]  # the copy with no label still goes
    assert kept == [fr.Kept(FLAG, "removed in part; one copy kept: "
                                  "only mention of required item 'Choir tours'")]


def test_rm2e_unplaced_item_keeps_every_sentence():
    """learning-qa F4: when the guard names an item no removed sentence mentions, every
    removal is kept, since the code cannot tell which one drops it."""
    out, removed, kept = _remove(SUMMARY, [FLAG], guard=lambda b, a: [("Item X", ["zzz"])])
    assert out == SUMMARY and removed == []
    assert kept == [fr.Kept(FLAG, "could not place required item 'Item X'")]


def test_rm2e_item_already_low_keeps_claims_not_names(monkeypatch):
    """Cold sweep (correctness #3 / learning-qa #2): a required item with no keyword in
    the summary is decided by the gate's LLM check, which may rest on any sentence, so
    claim sentences are kept. A rejected name still goes (the entity check blocks it)."""
    import summary_validation as sv
    item = sv.CoverageItem(category="topic", label="Sibling position", required=True,
                           keywords=["sibling"], source_text="", expected_words=0)
    monkeypatch.setattr(sv, "generate_coverage_items", lambda summary_input: [item])
    guard = ep._coverage_guard(object())
    assert guard(NAME_TEXT, NAME_TEXT) == [("Sibling position", ["sibling"])]
    claim = "He says the family was anxious about the move."
    out, removed, kept = _remove(NAME_TEXT, [claim, NAME_FLAG], guard=guard)
    assert claim in out and "Ann Example" not in out
    assert [r.sentence for r in removed] == [
        "Kerr describes the case of Ann Example in detail here."]
    assert kept == [fr.Kept(claim, "could not place required item 'Sibling position'")]


def test_rm2f_no_judge_call_after_removal(monkeypatch, tmp_path):
    _entity_pass(monkeypatch)
    second = SUMMARY.replace(FLAG + " ", "")
    other = "The mayor says the bridge will close next year."
    issues = iter([[fr.Flag(FLAG)], [fr.Flag(other)]])
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 2)
    (tmp_path / "B").mkdir()
    path = tmp_path / "B" / f"B{config.SUFFIX_SUMMARY_GEN}"
    drafts, calls = iter([SUMMARY, second]), []

    def precheck(base, sfx, logger=None):
        calls.append(1)
        return "fail", next(issues)

    ok = ep._generate_until_faithful(
        "summary", "B", config.SUFFIX_SUMMARY_GEN, MagicMock(),
        generate=lambda feedback: next(drafts),
        write=lambda t: path.write_text(t, encoding="utf-8"), precheck=precheck)
    assert ok is True
    assert len(calls) == 2  # one per attempt; none after the removal
    assert other not in path.read_text(encoding="utf-8")


def test_rm2g_passing_draft_untouched_no_record(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    (tmp_path / "B").mkdir()
    path = tmp_path / "B" / f"B{config.SUFFIX_SUMMARY_GEN}"
    ok = ep._generate_until_faithful(
        "summary", "B", config.SUFFIX_SUMMARY_GEN, MagicMock(),
        generate=lambda feedback: SUMMARY, write=lambda t: path.write_text(t, encoding="utf-8"),
        precheck=lambda base, sfx, logger=None: ("pass", []))
    assert ok is True
    assert path.read_text(encoding="utf-8") == SUMMARY
    assert not rr.record_path("B").exists()


def test_rm2h_record_has_judge_rationale():
    faith = rg.Verdict("faithfulness", rg.Status.WARN, "1 wrong", items=[
        {"artifact": "summary-generated.md", "unfaithful": [FLAG], "wrong": [FLAG_RECORD]}])
    (flag,) = ep._claim_flags(faith)
    assert flag == FLAG and flag.kind == "claim"
    assert flag.record["rationale"] == "No tour is mentioned."
    entity = rg.Verdict("entity_grounding", rg.Status.FAIL, "x", items=[{"names": ["Ann Example"]}])
    (name,) = ep._name_flags(entity)
    assert name == "the name 'Ann Example' does not appear in the source"
    assert (name.kind, name.name) == ("name", "Ann Example")
    fv = fj.ClaimVerdict(FLAG, "unsupported", "No tour is mentioned.")
    result = fj.FaithfulnessResult(fj.FAIL, "", claims=[fv], judged=1)
    assert rg._wrong_records(result)[0]["rationale"] == "No tour is mentioned."


# --- RM3: the record ------------------------------------------------------------------

def test_rm3a_record_fields(monkeypatch, tmp_path):
    _entity_pass(monkeypatch)
    _, path, _, _ = _loop(monkeypatch, tmp_path)
    record = json.loads(rr.record_path("B").read_text(encoding="utf-8"))
    entry = record["artifacts"]["summary"]
    assert entry["file"] == f"B{config.SUFFIX_SUMMARY_GEN}"
    assert entry["draft_before"] == SUMMARY
    assert entry["sha256"] == rr._sha(path.read_text(encoding="utf-8"))
    assert entry["removed"] == [{
        "sentence": FLAG, "before": "Michael Kerr presents two lectures on Bowen theory.",
        "after": "The first lecture traces the history of cosmology.", "reason": "faithfulness",
        "label": "unsupported", "rationale": "No tour is mentioned.", "evidence": "absent",
        "in_front_matter": False}]
    assert entry["kept"] == []
    assert entry["removed_at"]


def test_rm3b_record_write_fails_nothing_removed(monkeypatch, tmp_path):
    _entity_pass(monkeypatch)

    def fail(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(rr, "write_entry", fail)
    ok, path, logger, _ = _loop(monkeypatch, tmp_path)
    assert ok is True
    assert path.read_text(encoding="utf-8") == SUMMARY
    assert any("record could not be written" in m and "nothing was removed" in m
               for m in _warnings(logger))


def test_rm3c_dirty_state_clean_regeneration_clears_entry(monkeypatch, tmp_path):
    """P8: run 1 removes a sentence; run 2 passes clean. The summary entry is gone, the
    overview's entry stays, and run 2's list shows nothing for the summary."""
    from datetime import datetime
    _entity_pass(monkeypatch)
    _loop(monkeypatch, tmp_path)
    data = json.loads(rr.record_path("B").read_text(encoding="utf-8"))
    data["artifacts"]["overview"] = dict(data["artifacts"]["summary"], file="B - overview.md")
    rr.record_path("B").write_text(json.dumps(data), encoding="utf-8")
    run2 = datetime.now()
    path = tmp_path / "B" / f"B{config.SUFFIX_SUMMARY_GEN}"
    ep._generate_until_faithful(
        "summary", "B", config.SUFFIX_SUMMARY_GEN, MagicMock(),
        generate=lambda feedback: SUMMARY, write=lambda t: path.write_text(t, encoding="utf-8"),
        precheck=lambda base, sfx, logger=None: ("pass", []))
    data = json.loads(rr.record_path("B").read_text(encoding="utf-8"))
    assert list(data["artifacts"]) == ["overview"]
    assert rr.format_run_removals("B", run2) == "Removed sentences: none this run."


def test_rm3c_refused_removal_recorded_and_listed(monkeypatch, tmp_path):
    """learning-qa F3: when removal is refused (here by the share cap), the record keeps
    the flags left in, so the list does not say "none this run"."""
    from datetime import datetime, timedelta
    start = datetime.now() - timedelta(seconds=1)
    _entity_pass(monkeypatch)
    monkeypatch.setattr(config, "FAITHFULNESS_REMOVE_MAX_SHARE", 0.01)
    ok, path, _, _ = _loop(monkeypatch, tmp_path)
    assert ok is True and path.read_text(encoding="utf-8") == SUMMARY
    entry = json.loads(rr.record_path("B").read_text(encoding="utf-8"))["artifacts"]["summary"]
    assert entry["removed"] == [] and entry["sha256"] == rr._sha(SUMMARY)
    text = rr.format_run_removals("B", start)
    assert "Summary: nothing removed." in text
    assert f'Still flagged, not removed: "{FLAG}" (would remove' in text


def test_rm3b_artifact_save_fails_stage_goes_on(monkeypatch, tmp_path):
    """learning-qa F5: the record is written, then saving the cleaned draft fails. The
    stage goes on with the draft as it was, and the record entry is cleared."""
    _entity_pass(monkeypatch)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 1)
    (tmp_path / "B").mkdir()
    path = tmp_path / "B" / f"B{config.SUFFIX_SUMMARY_GEN}"

    def write(t):
        if FLAG not in t:
            raise OSError("disk full")
        path.write_text(t, encoding="utf-8")

    logger = MagicMock()
    ok = ep._generate_until_faithful(
        "summary", "B", config.SUFFIX_SUMMARY_GEN, logger, generate=lambda feedback: SUMMARY,
        write=write, precheck=lambda base, sfx, logger=None: ("fail", [fr.Flag(FLAG)]))
    assert ok is True
    assert path.read_text(encoding="utf-8") == SUMMARY
    assert any("the removal was not applied" in m for m in _warnings(logger))
    # Cold sweep (learning-qa #3): the list names the flag left in, not "none".
    from datetime import datetime, timedelta
    listed = rr.format_run_removals("B", datetime.now() - timedelta(minutes=1))
    assert "Still flagged, not removed" in listed and "saving the cleaned draft failed" in listed


def _save_fails(monkeypatch, tmp_path, fail_resave):
    """_generate_until_faithful whose writer saves the cleaned draft and then raises;
    with ``fail_resave`` every later save raises too."""
    _entity_pass(monkeypatch)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 1)
    (tmp_path / "B").mkdir()
    path = tmp_path / "B" / f"B{config.SUFFIX_SUMMARY_GEN}"
    failed = []

    def write(t):
        if failed and fail_resave:
            raise OSError("disk gone")
        if FLAG not in t:
            path.write_text(t[: len(t) // 2], encoding="utf-8")  # a partial write
            failed.append(t)
            raise OSError("disk full")
        path.write_text(t, encoding="utf-8")

    logger = MagicMock()
    run = lambda: ep._generate_until_faithful(  # noqa: E731
        "summary", "B", config.SUFFIX_SUMMARY_GEN, logger, generate=lambda feedback: SUMMARY,
        write=write, precheck=lambda base, sfx, logger=None: ("fail", [fr.Flag(FLAG)]))
    return run, path, logger


def test_rm3b_partial_save_restores_kept_draft(monkeypatch, tmp_path):
    """Cold sweep (learning-qa #4): the re-save of the kept draft was never exercised,
    because the fake writer failed before writing anything."""
    run, path, _ = _save_fails(monkeypatch, tmp_path, fail_resave=False)
    assert run() is True
    assert path.read_text(encoding="utf-8") == SUMMARY


def test_rm3b_both_saves_fail_stage_fails(monkeypatch, tmp_path):
    """Cold sweep (learning-qa #3): when the kept draft cannot be saved again either,
    the file may be truncated, so the error goes up and the stage fails."""
    run, _, logger = _save_fails(monkeypatch, tmp_path, fail_resave=True)
    with pytest.raises(OSError, match="disk gone"):
        run()
    assert "could not be saved again" in logger.error.call_args.args[0]


def test_rm2_removal_error_stage_goes_on(monkeypatch, tmp_path):
    """Cold sweep (learning-qa #4): a bug in removal must not fail the stage; the draft
    is kept as it is and the record lists the flags with the error."""
    _entity_pass(monkeypatch)

    def broken(*a, **kw):
        raise ValueError("bug in removal")
    monkeypatch.setattr(fr, "remove_flagged_sentences", broken)
    ok, path, logger, _ = _loop(monkeypatch, tmp_path)
    assert ok is True
    assert path.read_text(encoding="utf-8") == SUMMARY
    entry = json.loads(rr.record_path("B").read_text())["artifacts"]["summary"]
    assert entry["kept"][0]["reason"] == "removal failed: bug in removal"


def test_rm2_names_only_message():
    """Re-sweep (learning-qa #6): the "all removed" message says what was removed."""
    claim, name = fr.Flag(FLAG), NAME_FLAG
    msg = ep._all_removed_message
    assert "every sentence still flagged" in msg("Summary", 3, [claim, name], False)
    assert "no claim was flagged" in msg("Summary", 3, [name], False)
    assert "could not run" in msg("Summary", 3, [name], True)
    assert "every sentence still flagged" in msg("Summary", 3, [claim], True)
    assert msg("Abstract", 3, [name], False, cause="no fully faithful abstract").startswith(
        "⚠️ Abstract: no fully faithful abstract; the sentences with the flagged names")


def test_rm2_partial_check_message_says_not_checked(monkeypatch, tmp_path):
    """Cold sweep (correctness #6): when the judge errored and only names were flagged,
    removing them must not be reported as every flagged sentence removed."""
    _entity_reads_file(monkeypatch, tmp_path, config.SUFFIX_SUMMARY_GEN)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 1)
    (tmp_path / "B").mkdir()
    path = tmp_path / "B" / f"B{config.SUFFIX_SUMMARY_GEN}"
    logger = MagicMock()
    ok = ep._generate_until_faithful(
        "summary", "B", config.SUFFIX_SUMMARY_GEN, logger, generate=lambda feedback: NAME_TEXT,
        write=lambda t: path.write_text(t, encoding="utf-8"),
        precheck=lambda base, sfx, logger=None: ("partial", [NAME_FLAG]))
    assert ok is True and "Ann Example" not in path.read_text(encoding="utf-8")
    msgs = _warnings(logger)
    assert any("faithfulness check could not run" in m for m in msgs)
    assert not any("every sentence still flagged" in m for m in msgs)


# --- RM2.b.1–RM2.b.5: the abstract check on a judge error -------------------------------

ABSTRACT_NAME_SENTENCE = "He describes the case of Ann Example in some detail."
ABSTRACT_NAME = ("Michael Kerr presents two lectures on Bowen theory and its roots. "
                 "The first traces the long history of cosmology from Aristotle onward. "
                 f"{ABSTRACT_NAME_SENTENCE} "
                 "The second turns to the neuroscience of differentiation of self. "
                 "Kerr links the brain's functioning to the family emotional system. "
                 "He closes by describing how anxiety moves through relationships. "
                 "The talk ends with questions from the audience about practice.")


def _judge(monkeypatch, status, detail="", claims=()):
    """Turn the judge on and give it one fixed verdict on the abstract."""
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True, raising=False)
    items = ([{"artifact": "abstract-generated.md", "unfaithful": list(claims),
               "wrong": [FLAG_RECORD]}] if claims else [])
    monkeypatch.setattr(rg, "check_faithfulness", lambda *a, **k: rg.Verdict(
        "faithfulness", status, detail, items=items))


def _abstract_run(monkeypatch, tmp_path, text=ABSTRACT_NAME, setup=None):
    """generate_structured_abstract with fake drafts (always ``text``), the real
    precheck, and an entity check that reads the saved abstract. Returns (ok, saved
    text, logger, the feedback each draft was made with, base)."""
    from test_abstract_faithful_retry import _setup as abstract_setup
    base, proj = setup or abstract_setup(monkeypatch, tmp_path)
    feedback = []
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract",
                        lambda *a, feedback_claims=None, **k: (feedback.append(feedback_claims)
                                                               or text))
    _entity_reads_file(monkeypatch, tmp_path, config.SUFFIX_ABSTRACT_GEN)
    logger = MagicMock()
    ok = ep.generate_structured_abstract(base, logger)
    saved = (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").read_text(encoding="utf-8")
    return ok, saved, logger, feedback, base


def test_rm2b1_judge_error_with_name_is_partial(monkeypatch):
    """The abstract precheck returned "unavailable" on a judge error even when the entity
    check rejected a name, so the name was kept and the gate blocked at publish."""
    _judge(monkeypatch, rg.Status.ERROR, "timeout")
    monkeypatch.setattr(rg, "check_entity_grounding", lambda *a, **k: rg.Verdict(
        "entity_grounding", rg.Status.FAIL, "1 name", items=[{"names": ["Ann Example"]}]))
    status, issues = ep._abstract_gate_precheck("B")
    assert status == "partial"
    assert [(f.kind, f.name) for f in issues] == [("name", "Ann Example")]


def test_rm2b1_entity_error_with_claim_is_partial(monkeypatch):
    _judge(monkeypatch, rg.Status.WARN, "1 wrong", claims=[FLAG])
    monkeypatch.setattr(rg, "check_entity_grounding", lambda *a, **k: rg.Verdict(
        "entity_grounding", rg.Status.ERROR, "source transcript missing"))
    status, issues = ep._abstract_gate_precheck("B")
    assert status == "partial" and issues == [FLAG]
    assert issues[0].record["rationale"] == FLAG_RECORD["rationale"]


def test_rm2b2_judge_error_name_sentence_removed_stage_passes(monkeypatch, tmp_path):
    """Judge ERROR and a rejected name: the name is fed back, its sentence is removed
    after the last attempt, the stage succeeds, and the message says the faithfulness
    check could not run (RM2.b.3)."""
    _judge(monkeypatch, rg.Status.ERROR, "timeout")
    ok, saved, logger, feedback, base = _abstract_run(monkeypatch, tmp_path)
    assert ok is True
    assert saved == ABSTRACT_NAME.replace(ABSTRACT_NAME_SENTENCE + " ", "")
    assert len(feedback) == 3 and all("Ann Example" in str(f) for f in feedback[1])
    record = json.loads(rr.record_path(base).read_text(encoding="utf-8"))
    assert [r["sentence"] for r in record["artifacts"]["abstract"]["removed"]] == [
        ABSTRACT_NAME_SENTENCE]
    msgs = _warnings(logger)
    assert "faithfulness check could not run" in msgs[-1]
    assert not any("every sentence still flagged" in m or "no claim was flagged" in m
                   for m in msgs)
    assert not logger.error.called


def test_rm2b2_partial_draft_never_beats_judged_draft(monkeypatch, tmp_path):
    """A partial draft's count holds only what the working check found, so it ranks
    after every fully judged draft, as in _generate_until_faithful (SC2 review)."""
    from test_abstract_faithful_retry import _setup as abstract_setup
    base, proj = abstract_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "FAITHFULNESS_REMOVE_FLAGGED", False)
    texts = iter(["draft-1", "draft-2", "draft-3"])
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract", lambda *a, **k: next(texts))
    seq = iter([("fail", ["claim a", "claim b"]), ("partial", ["name x"]),
                ("partial", ["name y"])])
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: next(seq))
    assert ep.generate_structured_abstract(base, MagicMock()) is True
    assert (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").read_text(encoding="utf-8") == "draft-1"


def test_rm2b3_judged_names_only_says_no_claim_flagged(monkeypatch, tmp_path):
    """Adversarial guard: when the judge ran and found nothing, removing the name's
    sentence still says no claim was flagged, not that the check could not run."""
    _judge(monkeypatch, rg.Status.PASS, "all narrative claims entailed by source")
    ok, saved, logger, _, _ = _abstract_run(monkeypatch, tmp_path)
    assert ok is True and "Ann Example" not in saved
    msgs = _warnings(logger)
    assert "no claim was flagged" in msgs[-1]
    assert not any("could not run" in m for m in msgs)


JUDGE_TIMEOUT = "judge error: APITimeoutError: Request timed out."


def _real_judge_error(monkeypatch, proj):
    """The gate's real check_faithfulness, with the judge call failing. The gate keeps
    the judge's own cause in the verdict's items; its detail says only "1 of 1
    artifact(s) could not be verified" (learning-qa #1)."""
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True, raising=False)
    (proj / f"{proj.name}{config.SUFFIX_FORMATTED}").write_text(
        "Spoken words about family systems.", encoding="utf-8")
    monkeypatch.setattr(rg, "_judge_cached", lambda *a, **k: fj.FaithfulnessResult(
        status=fj.ERROR, detail=JUDGE_TIMEOUT))
    monkeypatch.setattr("transcript_utils.resolve_anthropic_key", lambda: "k")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda **_k: object())


def test_rm2b4_unavailable_warning_names_the_error(monkeypatch, tmp_path):
    """The warning said "judge off or no key" on any error; a disabled judge never gets
    there. It now gives the cause the judge reported."""
    from test_abstract_faithful_retry import _setup as abstract_setup
    base, proj = abstract_setup(monkeypatch, tmp_path)
    _real_judge_error(monkeypatch, proj)
    ok, saved, logger, feedback, _ = _abstract_run(
        monkeypatch, tmp_path, text=ABSTRACT_NAME.replace(ABSTRACT_NAME_SENTENCE + " ", ""),
        setup=(base, proj))
    assert ok is True and len(feedback) == 1
    msgs = _warnings(logger)
    assert any("faithfulness check could not run" in m and JUDGE_TIMEOUT in m for m in msgs)
    assert not any("judge off" in m for m in msgs)


def test_rm2b4_summary_precheck_names_the_error(monkeypatch, tmp_path):
    """P5 (learning-qa #4): the summary and overview precheck logged nothing about why
    the judge did not run; it now logs the same line as the abstract's."""
    (tmp_path / "B").mkdir()
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    (tmp_path / "B" / f"B{config.SUFFIX_SUMMARY_GEN}").write_text(SUMMARY, encoding="utf-8")
    _real_judge_error(monkeypatch, tmp_path / "B")
    _entity_pass(monkeypatch)
    logger = MagicMock()
    assert ep._faithfulness_precheck("B", config.SUFFIX_SUMMARY_GEN, logger) == (
        "unavailable", [])
    assert any("faithfulness check could not run" in m and JUDGE_TIMEOUT in m
               for m in _warnings(logger))


def test_rm2b4_blog_precheck_names_the_error(monkeypatch):
    """P5 (learning-qa re-check): the blog also goes through _generate_until_faithful,
    whose "unavailable" warning no longer names the cause; the blog precheck dropped the
    cause blog_ungrounded_claims returns. It now logs it, unavailable or partial."""
    cause = "claims not verified: no Anthropic API key"
    for hits, expected in (([], ("unavailable", [])),
                           (["the name 'X Y' is not in the source"],
                            ("partial", ["the name 'X Y' is not in the source"]))):
        monkeypatch.setattr(rg, "blog_ungrounded_claims",
                            lambda *a, hits=hits, **k: ("error", list(hits), cause))
        logger = MagicMock()
        assert ep._blog_precheck("B", config.SUFFIX_BLOG, logger) == expected
        assert any(cause in m and "at publish" in m for m in _warnings(logger)), hits


def test_rm2b4_judge_off_entity_error_cause_logged(monkeypatch, tmp_path):
    """learning-qa #2: with the judge off, an entity check that could not run was not
    logged; the user saw its cause only when the gate blocked at publish. Both
    prechecks (abstract; summary and overview)."""
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    (tmp_path / "B").mkdir()
    (tmp_path / "B" / f"B{config.SUFFIX_SUMMARY_GEN}").write_text(SUMMARY, encoding="utf-8")
    monkeypatch.setattr(rg, "check_entity_grounding", lambda *a, **k: rg.Verdict(
        "entity_grounding", rg.Status.ERROR, "source transcript missing or empty"))
    for precheck in (lambda lg: ep._abstract_gate_precheck("B", lg),
                     lambda lg: ep._faithfulness_precheck("B", config.SUFFIX_SUMMARY_GEN, lg)):
        logger = MagicMock()
        assert precheck(logger) == ("unavailable", [])
        assert any("entity check could not run" in m and "source transcript missing" in m
                   for m in _warnings(logger)), _warnings(logger)


def test_rm2b5_judge_off_is_not_a_pass(monkeypatch, tmp_path):
    """D1: with the judge off, the real check_faithfulness returns PASS ("judge
    disabled"). The abstract precheck read that as a pass and the stage logged
    "passed faithfulness + grounding" though no claim was judged."""
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", False, raising=False)
    text = ABSTRACT_NAME.replace(ABSTRACT_NAME_SENTENCE + " ", "")
    ok, saved, logger, feedback, base = _abstract_run(monkeypatch, tmp_path, text=text)
    assert ok is True and len(feedback) == 1
    assert ep._abstract_gate_precheck(base) == ("unavailable", [])
    infos = [str(c.args[0]) % c.args[1:] for c in logger.info.call_args_list]
    assert not any("passed faithfulness" in m for m in infos)
    assert any("faithfulness judge is off" in m for m in _warnings(logger))
    # With a rejected name it is still fed back on each attempt and then removed
    # ("fail", as in the summary's precheck).
    ok, saved, logger, feedback, _ = _abstract_run(monkeypatch, tmp_path / "named")
    assert ok is True and "Ann Example" not in saved
    assert len(feedback) == 3 and all("Ann Example" in str(f) for f in feedback[1])
    # learning-qa #3: no claim was judged, so the message must not say none was flagged.
    msgs = _warnings(logger)
    assert "the faithfulness judge is off, so no claim was judged" in msgs[-1]
    assert not any("no claim was flagged" in m or "could not run" in m for m in msgs)


def test_rm2b5_summary_judge_off_names_message(monkeypatch, tmp_path):
    """P5 (learning-qa #3): the summary loop said "no claim was flagged" with the judge
    off, as the abstract did."""
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", False, raising=False)
    _entity_reads_file(monkeypatch, tmp_path, config.SUFFIX_SUMMARY_GEN)
    ok, path, logger, _ = _loop(monkeypatch, tmp_path, drafts=[NAME_TEXT, NAME_TEXT],
                                issues=[NAME_FLAG])
    assert ok is True and "Ann Example" not in path.read_text(encoding="utf-8")
    assert "the faithfulness judge is off, so no claim was judged" in _warnings(logger)[-1]


# --- RM4: the end-of-run list -----------------------------------------------------------

def _recorded_run(monkeypatch, tmp_path):
    from datetime import datetime, timedelta
    start = datetime.now() - timedelta(seconds=1)
    _entity_pass(monkeypatch)
    _, path, _, _ = _loop(monkeypatch, tmp_path)
    return start, path


def test_rm4a_lists_this_run_only(monkeypatch, tmp_path):
    from datetime import datetime, timedelta
    start, _ = _recorded_run(monkeypatch, tmp_path)
    text = rr.format_run_removals("B", start)
    assert text.startswith("--- Sentences removed this run (1) ---")
    assert f'1. "{FLAG}"' in text
    assert "Why: judge: unsupported — No tour is mentioned." in text
    assert 'Now followed by: "The first lecture traces the history of cosmology."' in text
    assert str(rr.record_path("B")) in text
    later = datetime.now() + timedelta(seconds=5)
    assert rr.format_run_removals("B", later) == "Removed sentences: none this run."


def test_rm4a_changed_file_not_shown(monkeypatch, tmp_path):
    start, path = _recorded_run(monkeypatch, tmp_path)
    path.write_text(SUMMARY, encoding="utf-8")  # edited (or regenerated) since
    text = rr.format_run_removals("B", start)
    assert "Summary: the file has changed since the removal" in text
    assert FLAG not in text


def test_rm4a_none_says_so(monkeypatch, tmp_path):
    from datetime import datetime
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    assert rr.format_run_removals("B", datetime.now()) == "Removed sentences: none this run."


STEM = "Kerr Talk - Michael Kerr - 2025-01-01"


def _fake_removal(stem, suffix, artifact):
    """A stand-in for a generation stage that removed one sentence and recorded it."""
    def run(*a, **k):
        final = SUMMARY.replace(FLAG + " ", "")
        (config.PROJECTS_DIR / stem / f"{stem}{suffix}").write_text(final, encoding="utf-8")
        rr.write_entry(stem, artifact, suffix, draft_before=SUMMARY, final_text=final,
                       removed=[fr.Removed(FLAG, "", "", fr.FAITHFULNESS, {}, False)], kept=[])
        return True
    return run


def test_rm4c_cli_prints_list(monkeypatch, tmp_path, capsys):
    """learning-qa F2: transcript_summarize (the script that writes the structured
    summary) prints the run's list."""
    import transcript_summarize as ts
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    (tmp_path / STEM).mkdir()
    (tmp_path / STEM / f"{STEM}{config.SUFFIX_YAML}").write_text("x", encoding="utf-8")
    monkeypatch.setattr(ts, "summarize_transcript",
                        _fake_removal(STEM, config.SUFFIX_SUMMARY_GEN, "summary"))
    monkeypatch.setattr("sys.argv", ["transcript_summarize.py", STEM, "--generate-structured"])
    assert ts.main() == 0
    out = capsys.readouterr().out
    assert "--- Sentences removed this run (1) ---" in out and f'1. "{FLAG}"' in out


def test_rm4c_overview_cli_prints_list(monkeypatch, tmp_path, capsys):
    import transcript_overview as to
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config.settings, "PROJECTS_DIR", tmp_path)
    project = tmp_path / STEM
    project.mkdir()
    for sfx in (config.SUFFIX_YAML, config.SUFFIX_STRUCTURAL_THEMES, config.SUFFIX_TOPICS,
                config.SUFFIX_KEY_TERMS, config.SUFFIX_ABSTRACT_GEN):
        (project / f"{STEM}{sfx}").write_text("x", encoding="utf-8")
    monkeypatch.setattr(to, "setup_logging", lambda name: logging.getLogger(name))
    monkeypatch.setattr(to.pipeline, "summarize_transcript",
                        _fake_removal(STEM, config.SUFFIX_OVERVIEW, "overview"))
    assert to.main([str(project)]) == 0
    out = capsys.readouterr().out
    assert "Overview (1):" in out and f'1. "{FLAG}"' in out


def test_rm4a_unreadable_record_not_reported_as_none(monkeypatch, tmp_path):
    """Cold sweep (learning-qa #5): a record that cannot be read said "none this run"."""
    from datetime import datetime
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    (tmp_path / "B").mkdir()
    for bad in ("{not json", '{"artifacts": []}'):
        rr.record_path("B").write_text(bad, encoding="utf-8")
        text = rr.format_run_removals("B", datetime.now())
        assert "could not be read" in text and "none this run" not in text


def test_rm4c_list_printed_once_under_transcript_process(monkeypatch, tmp_path, capsys):
    """Cold sweep (correctness #7): transcript_summarize, run by transcript_process,
    printed the list and then transcript_process printed it again."""
    import transcript_process
    from datetime import datetime
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setenv(rr.LISTED_BY_PARENT_ENV, "1")
    rr.print_run_removals("B", datetime.now())
    assert capsys.readouterr().out == ""
    monkeypatch.delenv(rr.LISTED_BY_PARENT_ENV)
    rr.print_run_removals("B", datetime.now())
    assert "none this run" in capsys.readouterr().out
    # The flag goes to the scripts it runs, not to transcript_process itself.
    assert rr.LISTED_BY_PARENT_ENV not in os.environ
    calls = []
    monkeypatch.setattr(transcript_process.subprocess, "run",
                        lambda cmd, **kw: calls.append(kw) or MagicMock(returncode=0))
    transcript_process.run_script(tmp_path / "x.py", [], "step")
    assert calls[0]["env"][rr.LISTED_BY_PARENT_ENV] == "1"
    assert rr.LISTED_BY_PARENT_ENV not in os.environ


def test_rm4c_process_cli_prints_list_on_both_exits():
    """transcript_process.main is interactive, so its source is checked: the list is
    printed in a ``finally`` right after step 4, so every later exit (failure, Ctrl-C,
    a prompt answered no) has shown it, once (re-sweep, learning-qa #4)."""
    import inspect
    import transcript_process
    src = inspect.getsource(transcript_process.main)
    call = "removal_record.print_run_removals(base_name, start_time)"
    step4 = src.index("SUMMARIZE_SCRIPT,")
    assert src.count(call) == 1
    assert step4 < src.index("finally:", step4) < src.index(call) < src.index(
        'print("\\n❌ Summary generation failed.")')


# --- RM5: config -----------------------------------------------------------------------

def test_rm5_config_values():
    assert config.FAITHFULNESS_REMOVE_FLAGGED is True
    assert set(config.FAITHFULNESS_REMOVE_ARTIFACTS) == {"summary", "overview", "abstract"}
    assert 0 < config.FAITHFULNESS_REMOVE_MAX_SHARE < 1
    assert config.SUFFIX_REMOVED_SENTENCES.endswith(".json")
    assert config.FAITHFULNESS_SEVERITY_MODE == "off"  # D1
    assert config.FAITHFULNESS_SEVERITY_MODE in config.FAITHFULNESS_SEVERITY_MODES
