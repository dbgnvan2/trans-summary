"""Remove the sentences a faithfulness check still flags after the last revision.

Pure text functions: no file, judge or API access. The caller saves the text, writes
the record (``removal_record``) and logs what was removed and what was kept.

A removed sentence is found the way the judge's claim extractor reads the artifact
(``faithfulness_judge.extract_claims``), so a claim is removed only where it is a
whole sentence of the body. The result is used only if it passes the deletion-only
check (``deletion_problems``); otherwise the text comes back unchanged.

Spec: docs/plan_remove_flagged_2026-10-19.md#RM1
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

import config
import faithfulness_judge as fj
from abstract_validation import _INLINE_BOLD_LABEL, _strip_fenced_block, _strip_front_matter

FAITHFULNESS = "faithfulness"
NOT_FOUND = "not found as a whole sentence"
IN_SCAFFOLDING = "only in a heading, a label or the front matter"
A_HEADING = "a heading (headings are not edited)"
UNSURE_BOUNDARY = "sentence boundary uncertain (an abbreviation or a number at the split)"
SAME_SENTENCE_AS_NAME = "same sentence as name '{}' (uncertain split)"
LABEL_STAYS = "its bold label stays and is now read with the next sentence"
LABEL_LEFT = f"removed in part; {LABEL_STAYS}"
IN_FAQ = "removed from the body; still in the front matter's FAQ answers"

_MARKERS = ("**", "__")
_LINE_LEAD = re.compile(r"^\s*(?:[-*>]+\s*)*")       # as _clean_claim_line strips it
_ENUMERATOR = re.compile(r"^\d+[.)]\s+")
_LABEL_PREFIX = re.compile(r"^([A-Za-z][^:\n]{0,40}):\s*")
_BOLD_ONLY = re.compile(r"^\*\*[^*\n]+\*\*\s*$")
# List, quote and number markers, one per repetition (no backtracking on a long run).
_MARKER_RUN = r"(?:(?:[-*+>•]|\d+[.)])\s*)*"
_MARKER_PREFIX = re.compile(rf"^\s*{_MARKER_RUN}")
# A bold label after any such markers ("1. **Label:** ", "> - **Label:** "), in the
# label shapes of _INLINE_BOLD_LABEL, which matches only after "- " or "• ". After
# other markers the judge reads the label as the start of the first sentence. Not
# "**X.**": the judge reads on past that period only when it is no sentence end
# ("**Dr.** Zed ..."), and then it is part of the sentence.
_MARKED_LABEL = re.compile(
    rf"^(?P<lead>\s*{_MARKER_RUN})"
    r"(?P<run>\*\*(?P<label>[^*\n]+?)(?:[:—–-]\*\*|\*\*[ \t]*[:—–-]))[ \t]*(?P<rest>.*)$")
# A line with nothing left but a list marker and/or a bold label. Bold text that ends
# like a sentence ("**Kerr says X.**") is a sentence, not a label: the line stays.
_EMPTY_LINE = re.compile(
    r"^\s*(?:[-*+>•]\s*|\d+[.)]\s*)*"
    r"(?:(?:\*\*|__)(?:[^*_\n]*[^*_\n.!?])?(?:\*\*|__)\s*)?[:.—–-]?\s*$")
_FAQ_ANSWER = re.compile(
    r'^(?P<lead>\s*(?:-\s+)?a:\s*)"(?P<value>(?:[^"\\]|\\.)*)"(?P<trail>\s*)$')
_FAQ_QUESTION = re.compile(r"^\s*-\s+q:\s*")
_TOKEN = re.compile(r'[^\s"—–]+|["—–]')
_YAML_KEY = re.compile(r"^\s*(?:-\s+)?([A-Za-z_][\w-]*):", re.MULTILINE)
# A split the judge's splitter makes but may not be a sentence end: after a token with
# two periods ("U.S.", "Ph.D.") or a listed abbreviation ("Sen.", "Jan."), or before a
# number (config.FAITHFULNESS_REMOVE_UNSURE_ABBREVIATIONS).
_DOUBTFUL_END = re.compile(
    r"(?:(?<!\S)\S*\.\S*\.|\b(?:"
    + "|".join(map(re.escape, config.FAITHFULNESS_REMOVE_UNSURE_ABBREVIATIONS))
    + r")\.)$", re.IGNORECASE)
_DOUBTFUL_START = re.compile(r"^\d")
# A sentence the judge splits off that is only a list number ("... the move. 2. The ...").
_NUMBER_ONLY = re.compile(r"\d+[.)]")


class Flag(str):
    """A precheck issue: the text fed back to the reviser, carrying what removal
    needs. ``kind`` is "claim" (the text is the judge's claim) or "name" (the text says
    ``name`` is not in the source); ``record`` holds the judge's label, rationale and
    evidence. A plain string is read as a claim with no judge details.

    Spec:  docs/plan_remove_flagged_2026-10-19.md#RM2.h
    Tests: tests/test_remove_flagged_rm.py::test_rm2h_record_has_judge_rationale
    """

    def __new__(cls, text: str, *, kind: str = "claim", name: str = "",
                record: Optional[dict] = None):
        obj = super().__new__(cls, text)
        obj.kind = kind
        obj.name = name
        obj.record = dict(record or {})
        return obj


@dataclass
class Removed:
    """One removed sentence, as the judge read it (bold markers removed) but without a
    bold label it reads with it, which is not cut (RM1.b.1), with the sentences on
    either side of it in the result."""
    sentence: str
    before: str
    after: str
    reason: str
    record: dict = field(default_factory=dict)
    in_front_matter: bool = False


@dataclass
class Kept:
    """A flag that was not removed, and why."""
    claim: str
    reason: str


@dataclass
class _Sentence:
    line: int
    start: int   # span in the raw line, bold markers around it included
    end: int
    text: str    # as extract_claims reads it
    group: int = 0          # the parts of an abbreviation split share a group
    doubtful: bool = False  # a boundary with a neighbour may not be a sentence end
    label: str = ""         # the start of ``text`` that is a bold label, outside the span

    @property
    def own(self) -> str:
        """The sentence without the label the judge reads with it: the words cut."""
        return self.text[len(self.label):]


@dataclass
class _Target:
    sentence: _Sentence
    flag: str
    reason: str


def _split(text: str) -> tuple:
    """(leading whitespace, front matter, body) with lead + head + body == text."""
    stripped = text.lstrip()
    lead = text[: len(text) - len(stripped)]
    body = _strip_fenced_block(_strip_front_matter(stripped))
    return lead, stripped[: len(stripped) - len(body)], body


def _is_heading(line: str) -> bool:
    return line.strip().startswith("#")


def _clean_with_map(raw: str, start: int) -> tuple:
    """``raw[start:]`` without bold/underline markers, and the raw index of each
    character kept."""
    chars, where, i = [], [], start
    while i < len(raw):
        if raw.startswith(_MARKERS, i):
            i += 2
            continue
        chars.append(raw[i])
        where.append(i)
        i += 1
    return "".join(chars), where


def _find(body: str, text: str, cursor: int) -> Optional[tuple]:
    """(start, end) of the sentence ``text`` in ``body`` from ``cursor``, or None."""
    at = body.find(text, cursor)
    return None if at < 0 else (at, at + len(text))


def _sentence_marks(sentence: str, strip_prefixes: set) -> Counter:
    """What ``_without_line_label`` takes off the start of ``sentence`` (an allowlisted
    label, then a list number), or the sentence itself when it is only a list number
    ("2."). The check compares sentences without these, so it counts them (RM1.g.5)."""
    if _NUMBER_ONLY.fullmatch(sentence):
        return Counter({("list number", sentence): 1})
    out = Counter()
    m = _LABEL_PREFIX.match(sentence)
    if m and m.group(1).strip().lower() in strip_prefixes:
        out[("label", m.group(1).strip().lower())] += 1
        sentence = sentence[m.end():]
    m = _ENUMERATOR.match(sentence)
    if m:
        out[("list number", m.group().strip())] += 1
    return out


def _line_sentences(raw: str, index: int, strip_prefixes: set) -> list:
    """The sentences of one body line as extract_claims splits them, each with its
    span in the raw line. A sentence that cannot be placed ends the line's list, so
    it and the rest are not removable (they are reported as not found). A split that
    may not be a sentence end marks both sides ``doubtful``; one after an abbreviation
    also puts them in one ``group``, which a name removes whole.

    Where the judge reads a bold label as the start of the first sentence ("1. **Kerr
    Agreed:** Zed ..." is "Kerr Agreed: Zed ..."), that sentence keeps the judge's
    reading as ``text``, but its span starts after the label, so a cut leaves the label
    and its markers (RM1.b.1).

    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM1.i.1, #RM1.b.1
    Tests:   tests/test_remove_flagged_rm.py::test_rm1i1_name_before_number_split_takes_only_its_sentence,
             tests/test_remove_flagged_rm.py::test_rm1i_name_in_unsure_split_takes_whole_sentence,
             tests/test_remove_flagged_rm.py::test_rm1b1_name_sentence_after_marked_label_takes_own_span,
             tests/test_remove_flagged_rm.py::test_rm1b1_claim_flag_after_marked_label,
             tests/test_remove_flagged_rm.py::test_rm1b1_abbreviation_in_bold_is_not_a_label
    """
    return _split_line(raw, index, strip_prefixes)[0]


def _split_line(raw: str, index: int, strip_prefixes: set) -> tuple:
    """(sentences, unplaced, marks, line_marks) for one body line: the sentences
    ``_line_sentences`` returns; each sentence from the first one that could not be
    placed (a ``_Sentence`` with no span); the labels, list numbers and bold-only line
    the deletion check counts (``_sentence_marks``, RM1.g.5); and of those, the ones
    that go with the line when it is removed whole: the label and list number at its
    start, or the bold-only line. The check reads a line's sentences as the judge
    splits them, placed or not (RM1.g.4).

    Purpose: Read one body line as extract_claims does, for removal and for the check.
    Spec:    docs/plan_removal_open_items_2026-10-20.md#RM1.g.4, #RM1.g.5
    Tests:   tests/test_remove_flagged_rm.py::test_rm1g4_unplaced_sentence_not_excused_when_placement_fails,
             tests/test_remove_flagged_rm.py::test_rm1g5_label_or_number_alone_deleted_refused
    """
    s = raw.strip()
    if not s or _is_heading(raw):
        return [], [], Counter(), Counter()
    if _BOLD_ONLY.match(s):
        bold_only = Counter({("bold-only line", s): 1})
        return [], [], bold_only, bold_only
    m = _INLINE_BOLD_LABEL.match(raw)
    clean, where = _clean_with_map(raw, m.start("rest") if m else 0)
    m_label = None if m else _MARKED_LABEL.match(raw)
    own_from = m_label.start("rest") if m_label else -1
    marks = Counter()
    lead = _LINE_LEAD.match(clean).end()
    m_prefix = _LABEL_PREFIX.match(clean[lead:])
    if m_prefix and m_prefix.group(1).strip().lower() in strip_prefixes:
        lead += m_prefix.end()
        marks[("label", m_prefix.group(1).strip().lower())] += 1
    m_enum = _ENUMERATOR.match(clean[lead:])
    if m_enum:
        lead += m_enum.end()
        marks[("list number", m_enum.group().strip())] += 1
    line_marks = Counter(marks)
    body = clean[lead:].rstrip()
    out, unplaced, cursor = [], [], 0
    for part in fj._split_sentences(body):
        text = part.strip()
        if not text:
            continue
        found = None if unplaced else _find(body, text, cursor)
        if found is None:
            # Not removable, but the check still reads it (RM1.g.4): as a first
            # sentence, without the bold label the judge reads with it.
            label = ""
            if not out and not unplaced and own_from >= 0:
                j = next((k for k in range(lead, len(clean)) if where[k] >= own_from), None)
                if j is not None and text.startswith(clean[lead:j]):
                    label = clean[lead:j]
            sentence = _Sentence(index, -1, -1, text, label=label)
            unplaced.append(sentence)
            marks += _sentence_marks(sentence.own, strip_prefixes)
            continue
        at, end = found
        lo, hi = lead + at, lead + end
        first, last = where[lo], where[hi - 1] + 1
        label = ""
        if not out and first < own_from < last:
            # The judge reads the label with this sentence; the label is not cut.
            j = next(k for k in range(lo, hi) if where[k] >= own_from)
            label, first = clean[lo:j], where[j]
        # A sentence wrapped in bold takes its markers with it.
        while (first >= 2 and raw[first - 2:first] in _MARKERS
               and raw[last:last + 2] == raw[first - 2:first]):
            first, last = first - 2, last + 2
        sentence = _Sentence(index, first, last, text, group=len(out), label=label)
        # Without a bold label the judge reads with it: after a cut, the label is read
        # with the next sentence ("Kerr Agreed: 2.").
        marks += _sentence_marks(sentence.own, strip_prefixes)
        after_abbreviation = bool(out) and bool(_DOUBTFUL_END.search(out[-1].text))
        if out and (after_abbreviation or _DOUBTFUL_START.match(text)):
            # Removing either side would leave a fragment ("He trained with the U.S.").
            out[-1].doubtful = sentence.doubtful = True
            if after_abbreviation:
                # One sentence cut in two: a name takes both parts. A split before a
                # number is often a real end ("... the move. 2020 was ..."), so a name
                # takes only its own part there (RM1.i.1).
                sentence.group = out[-1].group
        out.append(sentence)
        cursor = end
    return out, unplaced, marks, line_marks


def _cut(raw: str, spans: list) -> str:
    """``raw`` without the spans, each with the space that separated it from the next
    sentence (or, at the end of the line, from the one before). Spans that overlap are
    a bug in finding them: ``ValueError``, which the caller reports as a failed removal
    (RM1.g.7).

    Spec:    docs/plan_removal_open_items_2026-10-20.md#RM1.g.7
    Tests:   tests/test_remove_flagged_rm.py::test_rm1g7_cut_refuses_overlapping_spans,
             tests/test_remove_flagged_rm.py::test_rm1g7_overlap_keeps_draft
    """
    ordered = sorted(spans)
    for (s1, e1), (s2, e2) in zip(ordered, ordered[1:]):
        if s2 < e1:
            raise ValueError(f"overlapping cut spans {s1}-{e1} and {s2}-{e2}")
    for start, end in reversed(ordered):
        tail = raw[end:]
        if tail.strip():
            raw = raw[:start] + tail.lstrip(" \t")
        else:
            raw = raw[:start].rstrip(" \t")
    return raw


def _build(lines: list, targets: list) -> tuple:
    """(new lines, indexes of lines dropped) after cutting the targets."""
    spans: dict = {}
    for t in targets:
        # Two flags can name one sentence (a claim and a name in it): cut it once.
        spans.setdefault(t.sentence.line, set()).add((t.sentence.start, t.sentence.end))
    new, dropped = list(lines), set()
    for i, line_spans in spans.items():
        cut = _cut(lines[i], line_spans)
        if _EMPTY_LINE.match(cut):
            new[i] = None
            dropped.add(i)
        else:
            new[i] = cut
    out, after_drop = [], False
    for line in new:
        if line is None:
            after_drop = True
            continue
        if after_drop and not line.strip() and (not out or not out[-1].strip()):
            continue  # a dropped paragraph leaves one blank line, not two
        after_drop = False
        out.append(line)
    while out and not out[0].strip() and lines and lines[0].strip():
        out.pop(0)
    return out, dropped


def _sections(lines: list) -> list:
    """[(heading text, [line indexes under it])], the text before the first heading
    under heading ''."""
    out = [("", [])]
    for i, line in enumerate(lines):
        if _is_heading(line):
            out.append((line.strip().lstrip("#").replace("**", "").strip(), []))
        else:
            out[-1][1].append(i)
    return out


def _emptied_sections(lines: list, targets: list, sentences: list) -> list:
    """Headings whose sentences would all be removed by ``targets``."""
    cut = {(t.sentence.line, t.sentence.start) for t in targets}
    by_line: dict = {}
    for s in sentences:
        by_line.setdefault(s.line, []).append(s)
    emptied = []
    for heading, idxs in _sections(lines):
        own = [s for i in idxs for s in by_line.get(i, [])]
        if own and all((s.line, s.start) in cut for s in own):
            emptied.append((heading, {s.line for s in own}))
    return emptied


def _edit_front_matter(head: str, sentences: set) -> tuple:
    """(new head, sentences removed from it, sentences left in it): a removed
    sentence is also removed from the front matter's FAQ answers; an answer left
    empty removes its q/a pair. An answer whose pair cannot be found is left as is."""
    lines = head.split("\n")
    drop, found, left = set(), set(), set()
    for i, line in enumerate(lines):
        m = _FAQ_ANSWER.match(line)
        if not m:
            continue
        parts = [p.strip() for p in fj._split_sentences(m["value"]) if p.strip()]
        plain = [p.replace('\\"', '"').replace("\\\\", "\\") for p in parts]
        hit = {p for p in plain if p in sentences}
        if not hit:
            continue
        rest = [p for p, q in zip(parts, plain) if q not in hit]
        if rest:
            lines[i] = f'{m["lead"]}"{" ".join(rest)}"{m["trail"]}'
            found |= hit
        elif i > 0 and _FAQ_QUESTION.match(lines[i - 1]):
            drop |= {i - 1, i}
            found |= hit
        else:
            left |= hit
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop), found, left


def _tokens(text: str) -> list:
    """Words, with each double quote its own token: removing the last sentence of a
    quoted front-matter answer moves the closing quote onto the sentence before. A dash
    is its own token too: cutting the sentence after "**Kerr Agreed**—" joins the dash
    to the next word."""
    return _TOKEN.findall(text)


def _all_sentences(line: str, index: int, strip_prefixes: set) -> list:
    """Every sentence of one body line as the judge splits it (``_Sentence``): the ones
    removal placed, then each one it could not, with no span (RM1.g.4)."""
    placed, unplaced, *_ = _split_line(line, index, strip_prefixes)
    return placed + unplaced


def _body_sentences(text: str) -> list:
    """Every sentence of the body (``_Sentence``), short ones included, as the judge
    splits them, whether or not removal could place them (RM1.g.4)."""
    strip_prefixes = {s.lower() for s in config.FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES}
    lines = _split(text)[2].split("\n")
    return [s for i, line in enumerate(lines)
            for s in _all_sentences(line, i, strip_prefixes)]


def _body_marks(lines, strip_prefixes: set, whole_lines: bool = False) -> Counter:
    """The labels, list numbers and bold-only lines of ``lines`` (RM1.g.5); with
    ``whole_lines``, only the ones that go with a line removed whole (``line_marks``)."""
    at = 3 if whole_lines else 2
    return sum((_split_line(line, i, strip_prefixes)[at] for i, line in enumerate(lines)),
               Counter())


def _without_line_label(sentence: str, strip_prefixes: set) -> str:
    """``sentence`` without a leading label from ``strip_prefixes`` ("Note:") and then a
    leading enumerator ("2) "), as extract_claims reads the start of a line. Removing
    the sentence before one moves it to the start of its line (item C)."""
    m = _LABEL_PREFIX.match(sentence)
    if m and m.group(1).strip().lower() in strip_prefixes:
        sentence = sentence[m.end():]
    m = _ENUMERATOR.match(sentence)
    return sentence[m.end():] if m else sentence


def _label_runs(lines) -> Counter:
    """The bold labels at the start of ``lines`` after any markers, bold markers
    removed ("Kerr Agreed:")."""
    return Counter(m["run"].replace("**", "") for m in map(_MARKED_LABEL.match, lines) if m)


def _labelled_firsts(text: str, strip_prefixes: set) -> Counter:
    """(label, first sentence without it) for each body line of ``text`` that starts
    with a bold label: the judge may read the label with that sentence (RM1.g.2)."""
    out = Counter()
    for i, line in enumerate(_split(text)[2].split("\n")):
        m = _MARKED_LABEL.match(line)
        first = _line_sentences(line, i, strip_prefixes) if m else []
        if first:
            # As the judge reads it: "**2) Key point:**" after "1. " is "Key point:".
            read = _MARKER_PREFIX.sub("", first[0].label).strip()
            out[(read or m["run"].replace("**", ""), first[0].own)] += 1
    return out


def _unlabelled(claims: list, firsts: Counter) -> list:
    """``claims`` with the markers and bold label taken off each claim that is a
    labelled line's first sentence read with its label ("+ Kerr Agreed: X" -> "X"), one
    claim per line. Any other claim is left as it is, so a label or a "Label:" prefix
    lost elsewhere still changes a claim (RM1.g.2)."""
    left = Counter(firsts)
    labels = sorted({label for label, _ in left}, key=len, reverse=True)
    out = []
    for claim in claims:
        bare = _MARKER_PREFIX.sub("", claim, count=1)
        for label in labels:
            key = (label, bare[len(label):].lstrip())
            if bare.startswith(label) and left[key] > 0:
                left[key] -= 1
                claim = key[1]
                break
        out.append(claim)
    return out


def _without_lines(text: str, lines: list) -> str:
    """``text`` without one body line equal to each of ``lines``."""
    lead, head, body = _split(text)
    body_lines = body.split("\n")
    for line in lines:
        if line in body_lines:
            body_lines.remove(line)
    return lead + head + "\n".join(body_lines)


def _is_subsequence(short: list, long: list) -> bool:
    it = iter(long)
    return all(any(x == y for y in it) for x in short)


def deletion_problems(before: str, after: str, removed, dropped_lines=()) -> list:
    """What makes ``after`` more than ``before`` with sentences deleted; [] when it is
    only that. ``removed``: the removed sentences, a set or a Counter (how many copies of
    each were cut); ``dropped_lines``: the text of lines removed whole. Such a line also
    takes the claims extract_claims loses when only that line is deleted, beyond its
    sentences (a bold label, "Kerr Agreed"), one copy each. No more copies of a claim or
    a sentence may go than were cut.

    Claims and sentences are compared without a leading "Note:"-style label or
    enumerator (RM1.g.1): the one after a removed sentence may now start its line,
    where extract_claims strips it. The text keeps the label. A line's first sentence
    is also compared without the bold label it starts with (RM1.g.2): after "1. " or
    "> " the judge reads the label with that sentence, which after a cut is the next
    one. Only that sentence of that line is read without it, and no more bold labels
    may go than lines removed whole had. A claim in ``after`` that was a sentence of
    ``before`` but not a claim is not an added claim (RM1.g.3): a label or a question's
    tag moved onto it.

    A line's sentences are read as the judge splits them, not as removal placed them,
    so one removal could not place is still checked (RM1.g.4). What the comparison
    leaves out is counted instead (RM1.g.5): each allowlisted label and list number at
    the start of a line or a sentence, each sentence that is only a list number ("2.",
    the same item as "2. " starting a line), and each bold-only line. None may be added;
    one may go only with a removed sentence that starts with it, or, when it starts its
    line or is a bold-only line, with that line. A number-only sentence left on a line
    removed whole is lost, not excused. A bold-only line may be new: a cut can leave a
    bold lead sentence alone on its line.

    Purpose: Use a removal only when it deletes and changes nothing else.
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM1.g, #RM1.g.1, #RM1.g.2, #RM1.g.3;
             docs/plan_removal_open_items_2026-10-20.md#RM1.g.4, #RM1.g.5
    Tests:   tests/test_remove_flagged_rm.py::test_rm1g4_unplaced_sentence_on_dropped_line_not_excused,
             tests/test_remove_flagged_rm.py::test_rm1g4_unplaced_sentence_not_excused_when_placement_fails,
             tests/test_remove_flagged_rm.py::test_rm1g4_change_after_unplaced_split_seen,
             tests/test_remove_flagged_rm.py::test_rm1g5_number_sentence_moves_to_line_start,
             tests/test_remove_flagged_rm.py::test_rm1g5_label_or_number_alone_deleted_refused,
             tests/test_remove_flagged_rm.py::test_rm1g5_bold_only_line_deleted_refused,
             tests/test_remove_flagged_rm.py::test_rm1g_check_names_each_problem,
             tests/test_remove_flagged_rm.py::test_rm1g_changed_text_rejected_draft_unchanged,
             tests/test_remove_flagged_rm.py::test_rm1g1_label_after_removed_name_removed,
             tests/test_remove_flagged_rm.py::test_rm1g1_unflagged_label_sentence_lost_still_caught,
             tests/test_remove_flagged_rm.py::test_rm1g1_short_claim_copy_on_other_line_does_not_excuse_loss,
             tests/test_remove_flagged_rm.py::test_rm1g1_sentence_on_line_judge_skipped_does_not_excuse_loss,
             tests/test_remove_flagged_rm.py::test_rm1g1_dropped_line_text_does_not_excuse_loss,
             tests/test_remove_flagged_rm.py::test_rm1g1_dropped_line_sentence_counted_once,
             tests/test_remove_flagged_rm.py::test_rm1g1_label_claim_goes_with_its_line,
             tests/test_remove_flagged_rm.py::test_rm1g1_label_line_under_question_heading_goes,
             tests/test_remove_flagged_rm.py::test_rm1g1_question_tagged_short_sentence_is_a_claim,
             tests/test_remove_flagged_rm.py::test_rm1g2_label_read_with_next_sentence_passes,
             tests/test_remove_flagged_rm.py::test_rm1g2_label_only_sentence_compared_as_is,
             tests/test_remove_flagged_rm.py::test_rm1g2_deleted_label_still_caught,
             tests/test_remove_flagged_rm.py::test_rm1g2_label_prefix_lost_on_other_line_caught,
             tests/test_remove_flagged_rm.py::test_rm1b1_number_inside_bold_label,
             tests/test_remove_flagged_rm.py::test_rm1g_dash_after_label_is_its_own_token,
             tests/test_remove_flagged_rm.py::test_rm1g3_label_makes_short_sentence_a_claim,
             tests/test_remove_flagged_rm.py::test_rm1g3_name_sentence_on_skip_label_line_removed,
             tests/test_remove_flagged_rm.py::test_rm1g3_question_tag_moves_to_next_sentence,
             tests/test_remove_flagged_rm.py::test_rm1g3_new_claim_that_was_no_sentence_still_refused
    """
    strip_prefixes = {s.lower() for s in config.FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES}

    def bare(sentence):
        return _without_line_label(sentence, strip_prefixes)

    def claims(text):
        bodies = [fj._claim_body(c) for c in fj.extract_claims(text)]
        return [bare(c) for c in _unlabelled(bodies, _labelled_firsts(text, strip_prefixes))]

    def sentences(text, keep=lambda s: True):
        return Counter(bare(s.own) for s in _body_sentences(text) if keep(s))

    problems = []
    if not _is_subsequence(_tokens(after), _tokens(before)):
        problems.append("text was added or changed, not only deleted")
    cut_texts = _unlabelled(list(Counter(removed).elements()),
                            _labelled_firsts(before, strip_prefixes))
    cut = Counter(map(bare, cut_texts))
    was, now = claims(before), claims(after)
    # A sentence the judge did not read as a claim may be one now; its words were in
    # the text before (the token check), so it is not an added claim (RM1.g.3).
    claims_before = set(was)
    sentences_before = sentences(before)
    if not _is_subsequence([c for c in now if c in claims_before
                            or c not in sentences_before], was):
        problems.append("a claim was added or changed")
    else:
        # A line removed whole also takes the claims the judge loses when only that line
        # is deleted, less its own sentences (counted as cut): its bold label, or under
        # a question heading its label and sentence read as one claim.
        was_n, now_n = Counter(was), Counter(now)
        from_lines = Counter()
        if dropped_lines:
            rest = Counter(claims(_without_lines(before, dropped_lines)))
            # The judge's sentences of the line, placed or not (RM1.g.4).
            own = Counter(bare(s.own) for line in dropped_lines
                          for s in _all_sentences(line, 0, strip_prefixes))
            from_lines = was_n - rest - own
        # A claim too short to be one without its label ("Note: Kerr agreed." ->
        # "Kerr agreed.") is not lost while its sentence is still in the text. Only
        # sentences that stopped being claims count: short ones in ``after`` the judge
        # does not return as claims, less every sentence it did not return as a claim
        # in ``before`` (too short, or on a line it skips). Both sides are counted
        # against the judge's own claims, so a short sentence it reads as a claim
        # (tagged with a question) is not counted. A sentence left on a line that came
        # to be skipped keeps its text, so it is short now only if it was before. The
        # sentence check below still catches a lost copy.
        short_now = sentences(after, lambda s: not fj._is_claim(s.text)) - now_n
        unjudged_before = sentences_before - was_n
        shorter = short_now - unjudged_before
        # A sentence that is only a list number is counted with the marks below: after
        # the sentence before it goes, it starts its line and is read as the number.
        for claim, n in (was_n - now_n).items():
            if (n > cut[claim] + shorter[claim] + from_lines[claim]
                    and not _NUMBER_ONLY.fullmatch(claim)):
                problems.append(f"a claim was lost that was not flagged: {claim[:80]!r}")
        # Sentences too short to be claims are checked too: only removed ones may go.
        lost = sentences_before - sentences(after)
        for sentence, n in lost.items():
            if n > cut[sentence] and not _NUMBER_ONLY.fullmatch(sentence):
                problems.append(f"a sentence was lost that was not flagged: {sentence[:80]!r}")
    _, head_before, body_before = _split(before)
    _, head_after, body_after = _split(after)
    # What the comparison leaves out is counted (RM1.g.5).
    marks_before = _body_marks(body_before.split("\n"), strip_prefixes)
    marks_after = _body_marks(body_after.split("\n"), strip_prefixes)
    # A line removed whole takes only the marks at its start. A sentence left on it
    # that is only a number ("1975.") is not excused: the cut left it alone and the
    # line went because it looked like a list marker. Marks at the start of a sentence
    # go only with that sentence, so none is counted twice.
    may_go = _body_marks(dropped_lines, strip_prefixes, whole_lines=True) + sum(
        (_sentence_marks(s, strip_prefixes) for s in cut_texts), Counter())
    for kind, what in marks_before - marks_after - may_go:
        problems.append(f"a {kind} was lost: {what[:80]!r}")
    for kind, what in marks_after - marks_before:
        # A cut can leave a bold lead sentence alone on its line ("**Kerr says X.** Y."
        # without "Y."): a bold-only line can be new, never lost.
        if kind != "bold-only line":
            problems.append(f"a {kind} was added: {what[:80]!r}")
    # A cut never takes a bold label; it goes only with its line.
    labels_lost = (_label_runs(body_before.split("\n")) - _label_runs(dropped_lines)
                   - _label_runs(body_after.split("\n")))
    for label in labels_lost:
        problems.append(f"a bold label was lost: {label[:80]!r}")
    if ([ln.strip() for ln in body_before.split("\n") if _is_heading(ln)]
            != [ln.strip() for ln in body_after.split("\n") if _is_heading(ln)]):
        problems.append("a heading changed")
    keys_before, keys_after = _YAML_KEY.findall(head_before), _YAML_KEY.findall(head_after)
    lost_keys = Counter(keys_before) - Counter(keys_after)
    if (not _is_subsequence(keys_after, keys_before) or set(lost_keys) - {"q", "a"}
            or lost_keys["q"] != lost_keys["a"]):
        problems.append("the front matter's keys changed")
    old_head_lines = set(head_before.split("\n"))
    for line in head_after.split("\n"):
        if line not in old_head_lines and not _FAQ_ANSWER.match(line):
            problems.append(f"a front-matter line is no longer well formed: {line[:80]!r}")
    old_lines = set(body_before.split("\n"))
    for line in body_after.split("\n"):
        if line not in old_lines and any(line.count(m) % 2 for m in _MARKERS):
            problems.append(f"a line was left with an unpaired bold marker: {line[:80]!r}")
    return problems


def _names(sentence: _Sentence, word, raw: str) -> bool:
    """Whether removing ``sentence`` takes out the name ``word`` matches: the name is in
    the sentence's own words, or only in the label the judge reads with it and the cut
    leaves the line empty, so the label goes with the line. Cutting the sentence after
    a label that keeps the name would remove a sentence and leave the name (RM1.b.2)."""
    if word.search(sentence.own):
        return True
    return bool(sentence.label and word.search(sentence.label)
                and _EMPTY_LINE.match(_cut(raw, [(sentence.start, sentence.end)])))


def remove_flagged_sentences(text: str, flags: list, *, max_share: float,
                             guard: Optional[Callable] = None) -> tuple:
    """Remove from ``text`` each sentence a flag names, and return
    ``(new_text, [Removed], [Kept])``. A claim flag removes every whole sentence of
    the body equal to the claim (its FQ tag ignored); a name flag (``Flag.kind ==
    "name"``) removes every sentence with that name as a whole word. Headings are
    never edited, a section is never emptied, and a sentence also in the front
    matter's FAQ answers is removed there too.

    ``guard(before, after)`` returns ``[(label, keywords)]`` for each item the
    removal would leave uncovered; the removed sentences with those keywords are kept.
    Nothing is removed when the removals would take more than ``max_share`` of the
    body's words, or when the result fails ``deletion_problems``.

    A sentence after a bold label is cut without the label (RM1.b.1); a claim flag the
    judge read with that label is then also listed as kept (``LABEL_LEFT``) while the
    label stays. A name only in such a label is removed only with its line (RM1.b.2).
    A sentence left in the FAQ answers is listed as kept for each flag that cut it.

    Purpose: Take out a sentence that is still flagged after the last revision.
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM1.a-#RM1.i, #RM1.i.1, #RM1.i.2,
             #RM1.b.1, #RM1.b.2
    Tests:   tests/test_remove_flagged_rm.py::test_rm1a_flagged_sentence_removed_rest_unchanged,
             tests/test_remove_flagged_rm.py::test_rm1d_part_of_longer_sentence_not_removed,
             tests/test_remove_flagged_rm.py::test_rm1h_cap_keeps_draft_and_announces,
             tests/test_remove_flagged_rm.py::test_rm1i1_name_before_number_split_takes_only_its_sentence,
             tests/test_remove_flagged_rm.py::test_rm1i2_split_part_without_name_has_own_reason,
             tests/test_remove_flagged_rm.py::test_rm1b1_last_sentence_after_marked_label_line_goes,
             tests/test_remove_flagged_rm.py::test_rm1b1_claim_flag_after_marked_label,
             tests/test_remove_flagged_rm.py::test_rm1e_faq_copy_left_listed_for_each_flag,
             tests/test_remove_flagged_rm.py::test_rm1b2_name_only_in_marked_label_kept
    """
    lead, head, body = _split(text)
    lines = body.split("\n")
    strip_prefixes = {s.lower() for s in config.FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES}
    sentences = [s for i, line in enumerate(lines)
                 for s in _line_sentences(line, i, strip_prefixes)]
    headings = {ln.strip().lstrip("#").replace("**", "").replace("__", "").strip()
                for ln in lines if _is_heading(ln)}
    labels = [m.group("label") for line in lines
              for m in (_INLINE_BOLD_LABEL.match(line) or _MARKED_LABEL.match(line),) if m]
    scaffolding = "\n".join([head, *labels, *(ln for ln in lines if _is_heading(ln)
                                                or _BOLD_ONLY.match(ln.strip()))])

    targets, kept, seen = [], [], set()
    partly = {}  # flag -> why one of its sentences was kept while others go
    for flag in flags:
        if flag in seen:
            continue
        seen.add(flag)
        if getattr(flag, "kind", "claim") == "name":
            word = re.compile(rf"(?<!\w){re.escape(flag.name)}(?!\w)")
            hits = [s for s in sentences if _names(s, word, lines[s.line])]
            reason = f"name '{flag.name}'"
        else:
            claim = fj._claim_body(flag)
            hits = [s for s in sentences if s.text == claim]
            reason = FAITHFULNESS
        part_reason = {}
        if getattr(flag, "kind", "claim") == "name":
            # A kept name blocks the stage (entity check): take the whole sentence, all
            # the parts an abbreviation split made of it. A part without the name says
            # why it went (RM1.i.2).
            with_name = {(s.line, s.start) for s in hits}
            groups = {(s.line, s.group) for s in hits}
            hits = [s for s in sentences if (s.line, s.group) in groups]
            part_reason = {(s.line, s.start): SAME_SENTENCE_AS_NAME.format(flag.name)
                           for s in hits if (s.line, s.start) not in with_name}
        sure = [s for s in hits if not s.doubtful or getattr(flag, "kind", "") == "name"]
        if sure:
            targets.extend(_Target(s, flag, part_reason.get((s.line, s.start), reason))
                           for s in sure)
            if len(sure) < len(hits):
                partly[flag] = UNSURE_BOUNDARY
        elif hits:
            kept.append(Kept(flag, UNSURE_BOUNDARY))
        elif getattr(flag, "kind", "claim") != "name" and fj._claim_body(flag) in headings:
            kept.append(Kept(flag, A_HEADING))
        elif (flag.name if getattr(flag, "kind", "") == "name"
              else fj._claim_body(flag)) in scaffolding:
            kept.append(Kept(flag, IN_SCAFFOLDING))
        else:
            kept.append(Kept(flag, NOT_FOUND))

    def _keep(target, reason):
        targets.remove(target)
        if any(t.flag == target.flag for t in targets):
            partly.setdefault(target.flag, reason)
        else:
            partly.pop(target.flag, None)
            kept.append(Kept(target.flag, reason))

    while targets:
        changed = False
        for heading, section_lines in _emptied_sections(lines, targets, sentences):
            for t in [t for t in targets if t.sentence.line in section_lines]:
                _keep(t, f"only text under heading '{heading}'" if heading
                      else "only text before the first heading")
                changed = True
        if guard is not None and targets:
            before = "\n".join(lines)
            after = "\n".join(_build(lines, targets)[0])
            for label, keywords in guard(before, after):
                # The keyword may be in the line's bold label, which goes with the
                # line when its last sentence is removed.
                hit = [t for t in targets
                       if any(k in t.sentence.text.lower()
                              or k in lines[t.sentence.line].lower() for k in keywords)]
                why = f"only mention of required item '{label}'"
                if not hit:
                    # Cannot tell which removal drops it: keep every claim sentence. A
                    # name sentence still goes: the entity check blocks a kept name; a
                    # claim in that sentence goes with it, so it is not listed as kept.
                    named = {(t.sentence.line, t.sentence.start) for t in targets
                             if getattr(t.flag, "kind", "claim") == "name"}
                    hit = [t for t in targets if getattr(t.flag, "kind", "claim") != "name"
                           and (t.sentence.line, t.sentence.start) not in named]
                    why = f"could not place required item '{label}'"
                for t in hit:
                    _keep(t, why)
                    changed = True
        if not changed:
            break
    if not targets:
        return text, [], kept

    new_lines, dropped = _build(lines, targets)
    new_body = "\n".join(new_lines)
    body_words = len(body.split())
    share = (body_words - len(new_body.split())) / body_words if body_words else 1.0
    if share > max_share:
        why = f"would remove {share:.0%} of the words (cap {max_share:.0%})"
        flags_hit = list(dict.fromkeys(t.flag for t in targets))
        return text, [], kept + [Kept(f, why) for f in flags_hit]

    # The words cut, without a label the judge reads with them (RM1.b.1).
    removed_text = {t.sentence.own for t in targets}
    new_head, in_head, left_in_head = _edit_front_matter(head, removed_text)
    # An answer the FAQ edit cannot read (unquoted, single-quoted, folded) keeps its copy.
    left_in_head |= {s for s in removed_text - in_head if s in new_head}
    new_text = lead + new_head + new_body
    cut_once = {(t.sentence.line, t.sentence.start): t.sentence.text for t in targets}
    problems = deletion_problems(text, new_text, Counter(cut_once.values()),
                                 [lines[i] for i in dropped])
    if problems:
        why = "deletion check failed: " + "; ".join(problems)
        flags_hit = list(dict.fromkeys(t.flag for t in targets))
        return text, [], kept + [Kept(f, why) for f in flags_hit]
    flags_of: dict = {}
    for t in targets:
        flags_of.setdefault(t.sentence.own, {})[t.flag] = None
    # A claim the judge read with a bold label: the label stays on its line and is now
    # read with the next sentence, which no judge has seen with it (RM1.b.1).
    label_left = {t.flag: None for t in targets
                  if getattr(t.flag, "kind", "claim") != "name" and t.sentence.label
                  and t.sentence.line not in dropped}
    kept += [Kept(f, IN_FAQ + (f"; {LABEL_STAYS}" if f in label_left else ""))
             for s in sorted(left_in_head) for f in flags_of[s]]
    # A flag removed in one place may still be in another (a section's only text, a
    # bold label, a heading): it is listed as kept, so no flag goes unreported (P2).
    left_claims = {fj._claim_body(c) for c in fj.extract_claims(new_text)}
    listed = {str(k.claim) for k in kept}
    for flag in dict.fromkeys(t.flag for t in targets):
        if str(flag) in listed:
            continue
        if getattr(flag, "kind", "claim") == "name":
            still = re.search(rf"(?<!\w){re.escape(flag.name)}(?!\w)", new_text)
        else:
            still = fj._claim_body(flag) in left_claims or flag in partly
        if still:
            what = (flag.name if getattr(flag, "kind", "claim") == "name"
                    else fj._claim_body(flag))
            why = partly.get(flag) or (IN_SCAFFOLDING if what in scaffolding else NOT_FOUND)
            kept.append(Kept(flag, f"removed in part; one copy kept: {why}"))
    listed = {str(k.claim) for k in kept}
    kept += [Kept(f, LABEL_LEFT) for f in label_left if str(f) not in listed]

    cut = {(t.sentence.line, t.sentence.start) for t in targets}
    order = {(s.line, s.start): n for n, s in enumerate(sentences)}

    def _neighbour(n, step):
        n += step
        while 0 <= n < len(sentences):
            if (sentences[n].line, sentences[n].start) not in cut:
                return sentences[n].text
            n += step
        return ""

    reasons: dict = {}  # a sentence two flags named is one removal with both reasons
    for t in sorted(targets, key=lambda t: t.reason != FAITHFULNESS):
        reasons.setdefault((t.sentence.line, t.sentence.start), []).append(t.reason)
    for at, why in reasons.items():
        # A part of a split sentence with its own reason gives that reason only.
        own = [r for r in why if not r.startswith(SAME_SENTENCE_AS_NAME.split("{")[0])]
        reasons[at] = own or why
    removed, listed_at = [], set()
    for t in sorted(targets, key=lambda t: (order[(t.sentence.line, t.sentence.start)],
                                            t.reason != FAITHFULNESS)):
        n = order[(t.sentence.line, t.sentence.start)]
        if n in listed_at:
            continue
        listed_at.add(n)
        why = list(dict.fromkeys(reasons[(t.sentence.line, t.sentence.start)]))
        removed.append(Removed(t.sentence.own, _neighbour(n, -1), _neighbour(n, 1),
                               why[0] + (f" (also {', '.join(why[1:])})" if why[1:] else ""),
                               dict(getattr(t.flag, "record", {}) or {}),
                               t.sentence.own in in_head))
    return new_text, removed, kept
