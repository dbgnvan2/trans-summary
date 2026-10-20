"""RM: remove sentences still flagged after revision (docs/plan_remove_flagged_2026-10-19.md)."""
import json
import logging
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
    _EMPTY_LINE backtrack exponentially (22 dashes took 0.6 s; each one doubles it)."""
    import time
    start = time.monotonic()
    assert fr._EMPTY_LINE.match("-" * 60 + " text") is None
    assert fr._EMPTY_LINE.match("*" * 60 + " text") is None
    assert fr._EMPTY_LINE.match("- **Label:**") is not None
    flag = "The speaker said ten things in the opening part."
    text = "### Body\n\n" + "-" * 40 + " " + flag + " The speaker also said more here.\n"
    out, removed, _ = _remove(text, [flag])
    assert [r.sentence for r in removed] == [flag]
    assert time.monotonic() - start < 1.0


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
    assert not rr.record_path("B").exists()
    assert any("the removal was not applied" in m for m in _warnings(logger))


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


def test_rm4c_process_cli_prints_list_on_both_exits():
    """transcript_process.main is interactive, so its source is checked: the list is
    printed on the summary-failure exit and before the token report at the end."""
    import inspect
    import transcript_process
    src = inspect.getsource(transcript_process.main)
    call = "removal_record.print_run_removals(base_name, start_time)"
    fail = src.index('print("\\n❌ Summary generation failed.")')
    assert src.index(call, fail) < src.index("return 1", fail)
    end = src.index("analyze_token_usage.generate_usage_report(since_timestamp=start_time)")
    assert src.rindex(call, 0, end) > fail


# --- RM5: config -----------------------------------------------------------------------

def test_rm5_config_values():
    assert config.FAITHFULNESS_REMOVE_FLAGGED is True
    assert set(config.FAITHFULNESS_REMOVE_ARTIFACTS) == {"summary", "overview", "abstract"}
    assert 0 < config.FAITHFULNESS_REMOVE_MAX_SHARE < 1
    assert config.SUFFIX_REMOVED_SENTENCES.endswith(".json")
    assert config.FAITHFULNESS_SEVERITY_MODE == "off"  # D1
    assert config.FAITHFULNESS_SEVERITY_MODE in config.FAITHFULNESS_SEVERITY_MODES
