"""HN: the name check stops flagging generated headings and written-out dates as
invented names, and still flags made-up names.

HN.1  A Title-Case heading/label run whose words are not in the source counts as a
      name only when one of its words is a given name or is not an English word.
HN.2  A span whose significant words are all month or weekday names is a date.

Spec: docs/plan_heading_names_2026-10-14.md
"""
import logging

import pytest

import abstract_validation as av
import config
import faithfulness_judge as fj
import release_gate as rg
from release_gate import Status

# A source that holds none of the heading words below.
SOURCE = (
    "Today I want to talk about differentiation of self and the family emotional "
    "system. Bowen described chronic anxiety in the nuclear family. Michael Kerr "
    "spoke about cancer and systems thinking."
)
# Flagged as names in e2e runs 9 and 10 (each cost a revision).
LOGGED_HEADINGS = ["Closing Advice", "Multigenerational Roots", "Patterns Identified",
                   "Swapping One Culprit", "Replacing One Culprit", "Final Reflections",
                   "Hurtful Remark"]


@pytest.mark.parametrize("heading", LOGGED_HEADINGS)
@pytest.mark.parametrize("shape", ["## {}\n\nA line about the family.",
                                   "**{}:** A line about the family.",
                                   "**{}**\n\nA line about the family."])
def test_hn1_generated_headings_not_flagged(heading, shape):
    text = "The family emotional system shapes anxiety.\n\n" + shape.format(heading)
    assert av.find_ungrounded_names(text, SOURCE) == []


@pytest.mark.parametrize("heading,name", [
    ("How Jane Doerfler Changed Family Therapy", "Jane Doerfler"),  # given + non-English
    ("Notes From Sarah Miller", "Sarah Miller"),                     # given name + English word
    ("Notes From Grace Walker", "Grace Walker"),       # given name that is also an English word
    ("What Robert Feldstein Found", "Robert Feldstein"),
    ("José García On Systems", "José García"),                       # accented, not English
    ("The Work of Tomasz Wierzbicki", "Tomasz Wierzbicki"),
    # Review (learning-qa): census given names, short given names, surnames that read
    # as English only through an inflection rule.
    ("What Sophia Turner Found", "Sophia Turner"),
    ("Maya Collins On Anxiety", "Maya Collins"),
    ("Notes From Amy Turner", "Amy Turner"),
    ("What Ben Walker Found", "Ben Walker"),
    ("Mark Turner On Systems", "Mark Turner"),          # given name that is also a word
    ("Lessons From Gilbert Walker", "Gilbert Walker"),
    ("What Peter Rogers Found", "Peter Rogers"),
    ("Lessons From Walker Hall", "Walker Hall"),         # two surnames that are words
    ("Jennifer Speaks", "Jennifer"),                      # a listed given name, not a word
    ("Notes From Abigail Lee", "Abigail Lee"),            # short surname kept at the end
    ("Ben Kerman Speaks", "Ben Kerman"),                  # short given name kept at the start
])
def test_hn1_made_up_names_in_headings_still_flagged(heading, name):
    """P7: a made-up person in a heading is still a name."""
    flagged = av.find_ungrounded_names(f"## {heading}\n\nA line.", SOURCE)
    assert any(name in f for f in flagged), flagged


@pytest.mark.parametrize("label", ["Luciano Malorni", "Sophia Turner"])
def test_hn1_made_up_name_in_bold_label_still_flagged(label):
    flagged = av.find_ungrounded_names(f"**{label}:** said the tumor is a system.", SOURCE)
    assert flagged == [label]


@pytest.mark.parametrize("heading", ["Modern Art", "Related Fields", "Young Adults",
                                     "Hope And Change", "Case Conclusions",
                                     # short given names at the end are dropped (review 2)
                                     "Black Art", "Christmas Eve", "Faith And Joy",
                                     "Young Guy"])
def test_hn1_word_that_is_also_a_name_alone_is_not_a_name(heading):
    """A given name or surname that is an ordinary word ("Hope", "Fields") is weak
    evidence: alone in a heading it does not make a name."""
    assert av.find_ungrounded_names(f"## {heading}\n\nA line.", SOURCE) == []


def test_hn1_prose_names_still_checked_strictly():
    """The rule is for headings only: in prose, a Title-Case span of English words
    absent from the source is still flagged."""
    assert av.find_ungrounded_names("The talk ended and Gilbert Walker spoke.", SOURCE) == [
        "Gilbert Walker"]


@pytest.mark.parametrize("heading", ["Notes From Willow Green", "Notes From Hope Walker",
                                     "Alcoholics Anonymous"])
def test_hn1_known_residual_english_word_name_in_heading(heading):
    """Documented residual: a made-up name of English words with at most one
    name-like word (a given name missing from the lists that is also a word, "Willow",
    "Hope", with an English surname; an organisation of common words), written only
    as a heading, is not caught (prose still is, above)."""
    assert av.find_ungrounded_names(f"## {heading}\n\nA line.", SOURCE) == []


def test_hn1_known_false_flag_short_given_name_at_start():
    """Documented residual false flag: a short given name that is not a word, at the
    start of a generic heading ("Max Effort"), still reads as a name."""
    assert av.find_ungrounded_names("## Max Effort\n\nA line.", SOURCE) == ["Max Effort"]


@pytest.mark.parametrize("word,english", [
    ("reflections", True), ("identified", True), ("replacing", True), ("swapping", True),
    ("multigenerational", True), ("hurtful", True), ("closing", True),
    ("swapped", True), ("planning", True),  # doubled consonant; not in the list as is
    ("doerfler", False), ("malorni", False), ("wierzbicki", False),
    # A prefix must leave 4+ letters: "re"+"yes" and "un"+"win" are surnames, not words.
    ("reyes", False), ("unwin", False),
])
def test_hn1_english_word_forms(word, english):
    words = av._word_list(str(config.NAME_CHECK_ENGLISH_WORDS_PATH))
    assert av._english_word(word, words) is english


def test_hn1_given_name_list_excludes_ordinary_words():
    given = av._word_list(str(config.NAME_CHECK_FIRST_NAMES_PATH))
    assert {"jane", "sarah", "robert", "grace"} <= given
    assert not {"case", "root", "those", "list", "part"} & given


@pytest.mark.parametrize("attr", ["NAME_CHECK_ENGLISH_WORDS_PATH",
                                  "NAME_CHECK_FIRST_NAMES_PATH", "NAME_CHECK_SURNAMES_PATH"])
def test_hn1_unreadable_word_list_keeps_the_check_strict(tmp_path, monkeypatch, attr):
    """Dirty state (P8): a missing list must make the check stricter, never looser,
    and the failure is not cached (the next call reads the list again)."""
    monkeypatch.setattr(config, attr, tmp_path / "missing.txt")
    av._WORD_LISTS.clear()
    try:
        assert av.find_ungrounded_names("## Closing Advice\n\nA line.", SOURCE) == [
            "Closing Advice"]
        assert str(tmp_path / "missing.txt") not in av._WORD_LISTS
    finally:
        av._WORD_LISTS.clear()


def test_hn1_excused_runs_are_reported():
    """P2: a heading run that is not counted as a name is handed back, not dropped."""
    excused: list = []
    text = "## Closing Advice\n\n## Notes From Sarah Miller\n\nA line."
    flagged = av.find_ungrounded_names(text, SOURCE, excused=excused)
    assert excused == ["Closing Advice"]
    assert any("Sarah Miller" in f for f in flagged)


def test_hn1_generated_heading_not_sent_to_judge_as_name():
    """extract_claims re-emits ungrounded heading names as claims; a generated
    heading is no longer one, a made-up name still is."""
    text = ("The family emotional system shapes anxiety.\n\n## Closing Advice\n\n"
            "## Notes From Sarah Miller\n\nA line.")
    claims = fj.extract_claims(text, source=SOURCE)
    assert "Closing Advice" not in claims
    assert any("Sarah Miller" in c for c in claims)


@pytest.mark.parametrize("sentence", ["On June 25, 2021, Michael Kerr spoke about cancer.",
                                      "In June, the family met again.",
                                      "On Friday, June 25, the talk began."])
def test_hn2_written_out_date_is_not_a_name(sentence):
    assert av.find_ungrounded_names(sentence, SOURCE) == []


@pytest.mark.parametrize("heading", ["Friday Session Highlights", "Monday Morning Reflections",
                                     "Sunday Dinner Patterns", "September Workshop Notes"])
def test_hn2_weekday_and_month_words_in_headings_are_not_names(heading):
    """Webster's lists weekdays and months capitalised only; they are still words."""
    assert av.find_ungrounded_names(f"## {heading}\n\nA line.", SOURCE) == []


@pytest.mark.parametrize("sentence,name", [("June Carter spoke next.", "June Carter"),
                                           ("April Smith asked a question.", "April Smith")])
def test_hn2_month_word_inside_a_name_still_checked(sentence, name):
    """P7: a month word does not hide a name that has other words."""
    assert av.find_ungrounded_names(sentence, SOURCE) == [name]


BASE = "Some Talk - Michael Kerr - 2021-06-25"


def _project(tmp_path, monkeypatch, overview):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    proj = tmp_path / BASE
    proj.mkdir()
    (proj / f"{BASE}{config.SUFFIX_FORMATTED}").write_text(SOURCE, encoding="utf-8")
    (proj / f"{BASE}{config.SUFFIX_OVERVIEW}").write_text(overview, encoding="utf-8")


def test_hn_gate_passes_generated_headings_and_date(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch,
             "On June 25, 2021, Michael Kerr spoke about cancer.\n\n## Final Reflections\n\n"
             "**Patterns Identified:** chronic anxiety in the family.\n\n## Closing Advice\n\n"
             "Differentiation of self.")
    v = rg.check_entity_grounding(BASE, logging.getLogger("t"), suffixes=[config.SUFFIX_OVERVIEW])
    assert v.status is Status.PASS, v.detail
    # the excused headings are named in the verdict, not dropped silently (P2)
    assert "Final Reflections" in v.detail and "Closing Advice" in v.detail


def test_hn_gate_still_fails_made_up_name_in_heading(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch,
             "Michael Kerr spoke about cancer.\n\n## Notes From Sarah Miller\n\nA line.")
    v = rg.check_entity_grounding(BASE, logging.getLogger("t"), suffixes=[config.SUFFIX_OVERVIEW])
    assert v.status is Status.FAIL
    assert "Sarah Miller" in v.detail


def test_hn_blog_check_reports_excused_headings(tmp_path, monkeypatch):
    """P2: the blog's name check (advisory, not the entity gate) also names the
    heading phrases it did not count, and still reports a made-up name."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", False, raising=False)
    proj = tmp_path / BASE
    proj.mkdir()
    (proj / f"{BASE}{config.SUFFIX_FORMATTED}").write_text(SOURCE, encoding="utf-8")
    (proj / f"{BASE}{config.SUFFIX_BLOG}").write_text(
        "Michael Kerr spoke about cancer.\n\n## Closing Advice\n\n## Notes From Sarah Miller\n\n"
        "A line.", encoding="utf-8")
    status, names, detail = rg.blog_ungrounded_claims(BASE, logging.getLogger("t"))
    assert "Closing Advice" in detail
    assert any("Sarah Miller" in n for n in names)
