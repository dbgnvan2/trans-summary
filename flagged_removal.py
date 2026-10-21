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
STILL_IN_FRONT_MATTER = "removed from the body; still in the front matter"

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
# A line with nothing left but list markers and a plain label ("Note:", "- Note:"). It
# goes only when the label is one the judge strips (RM1.b.4).
_LABEL_ONLY = re.compile(rf"^\s*{_MARKER_RUN}([A-Za-z][^:\n]{{0,40}}):\s*$")
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
    loose: bool = False     # placed only since RM1.b.3: with other whitespace than the
                            # judge's, or after such a sentence in its line

    @property
    def own(self) -> str:
        """The sentence without the label the judge reads with it: the words cut."""
        return self.text[len(self.label):]


@dataclass
class _Target:
    sentence: _Sentence
    flag: str
    reason: str
    new: bool = False  # a name cut only since RM1.b.5 ("_Zed Example_"), for the retry


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
    """(start, end) of the sentence ``text`` in ``body`` from ``cursor``, or None. The
    judge joins the parts of a sentence split after an abbreviation with one space, so
    where the line has other whitespace there (a tab, a non-breaking space, two spaces)
    any run of whitespace in ``text`` matches any run in ``body`` (RM1.b.3). The first
    copy is found, with the judge's spacing or not.

    Purpose: Place a sentence as the judge reads it in its line.
    Spec:    docs/plan_removal_open_items_2026-10-20.md#RM1.b.3
    Tests:   tests/test_remove_flagged_rm.py::test_rm1b3_name_in_sentence_with_odd_space_removed,
             tests/test_remove_flagged_rm.py::test_rm1b3_m1_line_still_refused,
             tests/test_remove_flagged_rm.py::test_rm1b3_sentence_placed_at_first_copy
    """
    m = re.compile(r"\s+".join(map(re.escape, text.split()))).search(body, cursor)
    return (m.start(), m.end()) if m else None


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
    and its markers (RM1.b.1). A span takes the bold markers around its sentence, and
    the opening marker of a bold run that closes inside it (RM1.b.5).

    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM1.i.1, #RM1.b.1;
             docs/plan_removal_open_items_2026-10-20.md#RM1.b.5
    Tests:   tests/test_remove_flagged_rm.py::test_rm1b5_bold_run_opening_sentence_cut_whole,
             tests/test_remove_flagged_rm.py::test_rm1b5_opening_marker_taken_only_when_run_closes_inside,
             tests/test_remove_flagged_rm.py::test_rm1i1_name_before_number_split_takes_only_its_sentence,
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
    out, unplaced, cursor, loose = [], [], 0, False
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
        # A bold run that opens the sentence and closes inside it ("**Zed Example**
        # spoke.") is cut with its opening marker, so no stray "**" is left (RM1.b.5).
        if (first >= 2 and raw[first - 2:first] in _MARKERS
                and raw[first:last].count(raw[first - 2:first]) % 2):
            first -= 2
        # Before RM1.b.3 this sentence and the rest of the line were not placed.
        loose = loose or body[at:end] != text
        sentence = _Sentence(index, first, last, text, group=len(out), label=label,
                             loose=loose)
        # Without a bold label the judge reads with it: after a cut, the label is read
        # with the next sentence ("Kerr Agreed: 2.").
        marks += _sentence_marks(sentence.own, strip_prefixes)
        after_abbreviation = bool(out) and _joined_to_previous(out[-1].text)
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
    """(new lines, indexes of lines dropped) after cutting the targets. A line left with
    only list markers, a bold label, or an allowlisted plain label ("Note:") is dropped.

    Spec:    docs/plan_removal_open_items_2026-10-20.md#RM1.b.4
    Tests:   tests/test_remove_flagged_rm.py::test_rm1b4_plain_label_left_alone_line_goes,
             tests/test_remove_flagged_rm.py::test_rm1b4_label_not_allowlisted_unchanged,
             tests/test_remove_flagged_rm.py::test_rm1b4_only_allowlisted_label_line_dropped
    """
    strip_prefixes = {s.lower() for s in config.FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES}
    spans: dict = {}
    for t in targets:
        # Two flags can name one sentence (a claim and a name in it): cut it once.
        spans.setdefault(t.sentence.line, set()).add((t.sentence.start, t.sentence.end))
    new, dropped = list(lines), set()
    for i, line_spans in spans.items():
        cut = _cut(lines[i], line_spans)
        label_only = _LABEL_ONLY.match(cut)
        if _EMPTY_LINE.match(cut) or (label_only
                                      and label_only.group(1).strip().lower() in strip_prefixes):
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


def _joined_to_previous(previous: str) -> bool:
    """Whether the judge's split after ``previous`` may be inside one sentence: after a
    token with two periods ("U.S.") or a listed abbreviation ("Sen."). Removal groups the
    two parts of a line (a name takes both), and FAQ answers are read the same way
    (RM1.e.2)."""
    return bool(_DOUBTFUL_END.search(previous))


def _answer_sentences(value: str) -> list:
    """The sentences of a double-quoted FAQ answer, each a list of the judge's parts as
    ``(as written, unescaped)``, with a part after an abbreviation joined to the one
    before it (``_joined_to_previous``).

    Spec:    docs/plan_removal_open_items_2026-10-20.md#RM1.e.2
    Tests:   tests/test_remove_flagged_rm.py::test_rm1e2_faq_sentence_after_abbreviation_kept
    """
    sentences = []
    for part in fj._split_sentences(value):
        part = part.strip()
        if not part:
            continue
        pair = (part, part.replace('\\"', '"').replace("\\\\", "\\"))
        if sentences and _joined_to_previous(sentences[-1][-1][1]):
            sentences[-1].append(pair)
        else:
            sentences.append([pair])
    return sentences


def _faq_sentences(head: str) -> Counter:
    """Each sentence of the front matter's double-quoted FAQ answers, as the tuple of
    its parts, unescaped (``_answer_sentences``)."""
    return Counter(tuple(plain for _, plain in sentence)
                   for line in head.split("\n") if (m := _FAQ_ANSWER.match(line))
                   for sentence in _answer_sentences(m["value"]))


_YAML_ESCAPE = re.compile(r"\\(\r?\n[ \t]*|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|x[0-9a-fA-F]{2}|.)|''",
                          re.DOTALL)
# Every escape of a double-quoted YAML value (YAML 1.1, as yaml.safe_load reads it).
_YAML_ESCAPED = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n",
                 "v": "\v", "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"',
                 "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0", "L": "\u2028",
                 "P": "\u2029"}


def _yaml_unescape(m: re.Match) -> str:
    code = m.group(1)
    if code is None:  # '' in a single-quoted value
        return "'"
    if code[0] in "\r\n":  # a line break escaped at the end of a line
        return ""
    if code[0] in "uUx" and len(code) > 1:
        value = int(code[1:], 16)
        return chr(value) if value <= 0x10FFFF else m.group()
    return _YAML_ESCAPED.get(code, m.group())


def _yaml_plain(text: str) -> str:
    """Front matter ``text`` as a double-quoted value reads: YAML's escapes undone in one
    pass (\\", \\\\, \\u2019, a backslash at a line's end, '') and each run of
    whitespace one space (learning-qa on RM1.e.1). An escaped surrogate pair is one
    character, as in the body. Used only to find copies left, never in the deletion
    check, and only on the front matter: a body sentence is markdown, not YAML
    (``_head_readings``)."""
    plain = _spaced(_YAML_ESCAPE.sub(_yaml_unescape, text))
    return plain.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")


def _spaced(text: str) -> str:
    return " ".join(text.split())


def _head_readings(head: str) -> tuple:
    """The front matter read two ways, to find a copy left there however it is quoted:
    with YAML's escapes undone (``_yaml_plain``, a double-quoted value), and as written
    with only '' undone (a plain or single-quoted value), each spaced. A body sentence
    with a backslash may match the as-written reading of a double-quoted value that YAML
    reads otherwise ("C:\\temp" there is a tab): that lists a copy as kept that is not
    there, an over-report."""
    return _yaml_plain(head), _spaced(head.replace("''", "'"))


def _copy_in(sentence: str, readings: tuple) -> bool:
    """Whether a body sentence, only spaced, is in either reading of the front matter."""
    return any(_spaced(sentence) in reading for reading in readings)


def _is_run(parts: tuple, whole: tuple) -> bool:
    """Whether ``parts`` are some of ``whole``'s parts, next to each other and in order,
    one of them holding the name it was cut for. ``whole`` is the cut sentence's parts
    as (text, holds the name it was cut for) pairs (``_cut_groups``)."""
    n = len(parts)
    return any(tuple(text for text, _ in whole[i:i + n]) == parts
               and any(mine for _, mine in whole[i:i + n])
               for i in range(len(whole) - n + 1))


def _faq_goes(parts: tuple, cut, joined, riders) -> bool:
    """Whether an FAQ answer's sentence (its parts, ``_answer_sentences``) may go: each
    part was cut for its own flag; or its parts run on in one sentence cut whole from the
    body (``joined``: the parts of a sentence split after an abbreviation) and one of
    them holds the name it was cut for ("The U.S. Navy sent Zed Example to Washington,
    D.C." from a body sentence that goes on after "D.C."). A part cut only for a name
    that is not in its own words (``riders``: split off the name's sentence, or after a
    label that holds the name) is, alone in an answer, a sentence without the name, so
    it stays (learning-qa on RM1.e.2). Whether a part of a joined sentence holds the name
    is read at its place in that sentence, not by its text, which may be cut for itself
    on another line (learning-qa third review). A claim cut on an uncertain part of the
    name's sentence (RM1.i.3) does not mark a run: with a rider, it is an answer
    sentence without the name."""
    if not all(p in cut for p in parts):
        return False
    if not any(p in riders for p in parts):
        return True
    return any(_is_run(parts, whole) for whole in joined)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _faq_items(head: str) -> list:
    """Each FAQ item of the front matter as the list of its lines: a "- q:" line and the
    lines indented under it (blank lines inside it included)."""
    lines, items, i = head.split("\n"), [], 0
    while i < len(lines):
        if not _FAQ_QUESTION.match(lines[i]):
            i += 1
            continue
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or _indent(lines[j]) > _indent(lines[i])):
            j += 1
        while j > i + 1 and not lines[j - 1].strip():
            j -= 1
        items.append(lines[i:j])
        i = j
    return items


def _edit_front_matter(head: str, sentences: set, joined=frozenset(),
                       riders=frozenset()) -> tuple:
    """(new head, sentences removed from it, sentences left in it): a removed
    sentence is also removed from the front matter's FAQ answers; an answer left
    empty removes its q/a pair. An answer whose pair cannot be found, or whose item has
    another key ("source:"), is left as is. An answer's sentence goes as ``_faq_goes``
    says: one split after an abbreviation goes only when every part of it was removed
    (RM1.e.2).

    Spec:    docs/plan_removal_open_items_2026-10-20.md#RM1.e.2
    Tests:   tests/test_remove_flagged_rm.py::test_rm1e2_faq_sentence_after_abbreviation_kept,
             tests/test_remove_flagged_rm.py::test_rm1e2_whole_joined_sentence_goes_from_answer,
             tests/test_remove_flagged_rm.py::test_rm1e2_part_split_off_with_name_stays_in_answer,
             tests/test_remove_flagged_rm.py::test_rm1e1_faq_pair_with_other_key_kept
    """
    lines = head.split("\n")
    drop, found, left = set(), set(), set()
    for i, line in enumerate(lines):
        m = _FAQ_ANSWER.match(line)
        if not m:
            continue
        answer = _answer_sentences(m["value"])
        goes = [_faq_goes(tuple(plain for _, plain in sentence), sentences, joined, riders)
                for sentence in answer]
        hit = {plain for sentence, g in zip(answer, goes) if g for _, plain in sentence}
        if not hit:
            continue
        rest = [raw for sentence, g in zip(answer, goes) if not g for raw, _ in sentence]
        nxt = next((ln for ln in lines[i + 1:] if ln.strip()), "")
        if rest:
            lines[i] = f'{m["lead"]}"{" ".join(rest)}"{m["trail"]}'
            found |= hit
        elif (i > 0 and _FAQ_QUESTION.match(lines[i - 1])
              and _indent(nxt) <= _indent(lines[i - 1])):
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


def deletion_problems(before: str, after: str, removed, dropped_lines=(), *,
                      joined=frozenset(), riders=frozenset()) -> list:
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

    The front matter's double-quoted FAQ answers are compared sentence by sentence, a
    part after an abbreviation joined to the one before (RM1.e.2): no sentence may be
    added or changed, and one may go only as ``_faq_goes`` says, with ``joined`` (the
    parts of each sentence cut whole, each marked with whether it holds the name it was
    cut for there) and ``riders`` (parts cut only for a name that is not in their own
    words: split off the name's sentence, or after a label that holds the name). FAQ
    items are also compared one by one, in order: an item keeps its lines, except an
    answer that loses whole sentences, and an item may go only when it is a question and
    a double-quoted answer whose every sentence may go.

    Purpose: Use a removal only when it deletes and changes nothing else.
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM1.g, #RM1.g.1, #RM1.g.2, #RM1.g.3;
             docs/plan_removal_open_items_2026-10-20.md#RM1.g.4, #RM1.g.5, #RM1.e.2
    Tests:   tests/test_remove_flagged_rm.py::test_rm1e2_faq_content_change_refused,
             tests/test_remove_flagged_rm.py::test_rm1e2_faq_items_compared_in_order,
             tests/test_remove_flagged_rm.py::test_rm1e2_part_split_off_with_name_stays_in_answer,
             tests/test_remove_flagged_rm.py::test_rm1e1_faq_pair_with_other_key_kept,
             tests/test_remove_flagged_rm.py::test_rm1g4_unplaced_sentence_on_dropped_line_not_excused,
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
    # FAQ answers, sentence by sentence and joined as the FAQ edit reads them (RM1.e.2):
    # none may be added or changed, and one goes only as ``_faq_goes`` says.
    faq_before, faq_after = _faq_sentences(head_before), _faq_sentences(head_after)
    for parts in faq_after - faq_before:
        problems.append(f"an FAQ answer sentence was added or changed: {' '.join(parts)[:80]!r}")
    cut_set = set(cut_texts)

    def _may_go(parts):
        return _faq_goes(parts, cut_set, joined, riders)
    for parts in faq_before - faq_after:
        if not _may_go(parts):
            problems.append("an FAQ answer sentence was lost that was not flagged: "
                            f"{' '.join(parts)[:80]!r}")
    problems += _faq_item_problems(head_before, head_after, _may_go)
    old_head_lines = set(head_before.split("\n"))
    for line in head_after.split("\n"):
        if line not in old_head_lines and not _FAQ_ANSWER.match(line):
            problems.append(f"a front-matter line is no longer well formed: {line[:80]!r}")
    old_lines = set(body_before.split("\n"))
    for line in body_after.split("\n"):
        if line not in old_lines and any(line.count(m) % 2 for m in _MARKERS):
            problems.append(f"a line was left with an unpaired bold marker: {line[:80]!r}")
    return problems


def _answer_parts(line: str):
    """The sentences of a double-quoted answer line, each the tuple of its unescaped
    parts, or None when the line is not one."""
    m = _FAQ_ANSWER.match(line)
    return ([tuple(plain for _, plain in s) for s in _answer_sentences(m["value"])]
            if m else None)


def _item_may_go(item: list, may_go) -> bool:
    """Whether a whole FAQ item may go: a question and a double-quoted answer only, and
    every sentence of the answer may go."""
    parts = _answer_parts(item[1]) if len(item) == 2 else None
    return parts is not None and all(may_go(p) for p in parts)


def _faq_item_problems(head_before: str, head_after: str, may_go) -> list:
    """The FAQ items of ``head_before`` and ``head_after``, compared in order (learning-qa
    on RM1.e.2): the questions left are the same and in order; a kept item has the same
    lines, except a double-quoted answer whose sentences are the old ones in order with
    some gone, each as ``may_go`` allows; an item that goes is a question and a
    double-quoted answer only, whose every sentence may go."""
    problems, before = [], _faq_items(head_before)
    k = 0
    for item in _faq_items(head_after):
        same_q = [j for j in range(k, len(before)) if before[j][0] == item[0]]
        if not same_q:
            problems.append(f"an FAQ item was added or changed: {item[0].strip()[:80]!r}")
            continue
        # Two items may ask the same question: the item left is the first of them it
        # matches (learning-qa re-review of RM1.e.2).
        j = next((j for j in same_q if not _item_changes(before[j], item, may_go)),
                 same_q[0])
        problems += [f"an FAQ item was lost: {old[0].strip()[:80]!r}"
                     for old in before[k:j] if not _item_may_go(old, may_go)]
        problems += _item_changes(before[j], item, may_go)
        k = j + 1
    problems += [f"an FAQ item was lost: {old[0].strip()[:80]!r}"
                 for old in before[k:] if not _item_may_go(old, may_go)]
    return problems


def _item_changes(old: list, item: list, may_go) -> list:
    """What is wrong with ``item`` as ``old`` after removal: the same lines, except a
    double-quoted answer whose sentences are the old ones in order with some gone, each
    as ``may_go`` allows."""
    if len(old) != len(item):
        return [f"an FAQ item's lines changed: {item[0].strip()[:80]!r}"]
    problems = []
    for was, now in zip(old, item):
        if was == now:
            continue
        was_parts, now_parts = _answer_parts(was), _answer_parts(now)
        if (was_parts is None or now_parts is None
                or not _is_subsequence(now_parts, was_parts)
                or not all(may_go(p) for p in Counter(was_parts) - Counter(now_parts))):
            problems.append(f"an FAQ item's answer changed: {now.strip()[:80]!r}")
    return problems


def _names(sentence: _Sentence, word, raw: str, spans: list) -> bool:
    """Whether removing ``sentence`` takes out the name ``word`` matches: the name is in
    the sentence's own words, or only in the label the judge reads with it and the cut
    leaves the line empty, so the label goes with the line. Cutting the sentence after
    a label that keeps the name would remove a sentence and leave the name (RM1.b.2).
    ``spans`` are the parts of the sentence split after an abbreviation, which a name
    takes together (RM1.i), so the line empties only when all of them are cut."""
    if word.search(sentence.own):
        return True
    return bool(sentence.label and word.search(sentence.label)
                and _EMPTY_LINE.match(_cut(raw, spans)))


def _name_word(name: str) -> re.Pattern:
    """The name as a word. "_" is not read as part of a word, so a name in "__…__"
    (bold) or "_…_" (italics) is found (RM1.b.5)."""
    return re.compile(rf"(?<![^\W_]){re.escape(name)}(?![^\W_])")


def _cut_for_itself(target: _Target) -> bool:
    """Whether a target's own words hold what it was cut for: a claim, or the name of a
    name flag. A part split off a name's sentence (RM1.i.2), or a sentence whose name
    is only in the label the judge reads with it (RM1.b.2), was not."""
    if getattr(target.flag, "kind", "claim") != "name":
        return True
    return bool(_name_word(target.flag.name).search(target.sentence.own))


def _cut_groups(targets: list) -> tuple:
    """(joined, riders) for the FAQ edit and the check (``_faq_goes``): the parts of each
    sentence split after an abbreviation that is cut whole, as a tuple in line order of
    (text, holds the name it was cut for) pairs; and the parts cut only for a name that is
    not in their own words.

    Spec:    docs/plan_removal_open_items_2026-10-20.md#RM1.e.2
    Tests:   tests/test_remove_flagged_rm.py::test_rm1e2_part_split_off_with_name_stays_in_answer,
             tests/test_remove_flagged_rm.py::test_rm1e2_name_only_in_label_sentence_stays_in_answer,
             tests/test_remove_flagged_rm.py::test_rm1e2_run_of_cut_sentence_with_name_goes_from_answer
    """
    groups: dict = {}
    for t in sorted(targets, key=lambda t: (t.sentence.line, t.sentence.start)):
        parts = groups.setdefault((t.sentence.line, t.sentence.group), {})
        # A claim on an uncertain part of the name's sentence (RM1.i.3) is cut there for
        # its own flag, but only a part that holds the name marks a run (``_is_run``).
        named = getattr(t.flag, "kind", "claim") == "name" and _cut_for_itself(t)
        mine = parts.get(t.sentence.start, ("", False))[1] or named
        parts[t.sentence.start] = (t.sentence.own, mine)
    joined = frozenset(tuple(parts.values()) for parts in groups.values() if len(parts) > 1)
    own = {t.sentence.own for t in targets if _cut_for_itself(t)}
    riders = frozenset(t.sentence.own for t in targets) - own
    return joined, riders


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
    body's words, or when the result fails ``deletion_problems``, except by the retry
    below.

    A sentence after a bold label is cut without the label (RM1.b.1); a claim flag the
    judge read with that label is then also listed as kept (``LABEL_LEFT``) while the
    label stays. A name only in such a label is removed only with its line (RM1.b.2).
    Every copy of a removed sentence left in the front matter is listed as kept
    (``STILL_IN_FRONT_MATTER``) for each flag that cut it, a name flag only while its
    name is there; ``Removed.in_front_matter`` is true only when the sentence was taken
    from an FAQ answer and no copy is left (RM1.e.1).

    A claim's copy on an uncertain split goes only where a name flag takes its whole
    sentence; the removal then gives both reasons and the claim's record, and a claim
    with a copy left is listed as removed in part (RM1.i.3). When the deletion check
    or the cap refuses the removal, it is tried again with smaller sets, among them only
    the name flags' sentences (and the claim flags on them), and last only the claims on
    no name's sentence; the first set that passes is cut and each other flag is kept
    with the first refusal's reason. A cut made only by a newer rule is left out of the
    older sets. The sets are fixed, not a search, so a mix of refused cuts can keep a
    claim or a name copy an earlier version removed (TODO.md). A section that would be
    emptied keeps its claim sentences, and its name sentences only when it has no other
    flagged sentence (RM1.g.6).

    Purpose: Take out a sentence that is still flagged after the last revision.
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM1.a-#RM1.i, #RM1.i.1, #RM1.i.2,
             #RM1.b.1, #RM1.b.2; docs/plan_removal_open_items_2026-10-20.md#RM1.e.1,
             #RM1.i.3, #RM1.g.6, #RM2.h.1
    Tests:   tests/test_remove_flagged_rm.py::test_rm1a_flagged_sentence_removed_rest_unchanged,
             tests/test_remove_flagged_rm.py::test_rm1d_part_of_longer_sentence_not_removed,
             tests/test_remove_flagged_rm.py::test_rm1h_cap_keeps_draft_and_announces,
             tests/test_remove_flagged_rm.py::test_rm1i1_name_before_number_split_takes_only_its_sentence,
             tests/test_remove_flagged_rm.py::test_rm1i2_split_part_without_name_has_own_reason,
             tests/test_remove_flagged_rm.py::test_rm1b1_last_sentence_after_marked_label_line_goes,
             tests/test_remove_flagged_rm.py::test_rm1b1_claim_flag_after_marked_label,
             tests/test_remove_flagged_rm.py::test_rm1e_faq_copy_left_listed_for_each_flag,
             tests/test_remove_flagged_rm.py::test_rm1e1_second_unquoted_faq_copy_listed_as_kept,
             tests/test_remove_flagged_rm.py::test_rm1e1_name_copy_listed_only_when_name_left,
             tests/test_remove_flagged_rm.py::test_rm1b2_name_only_in_marked_label_kept,
             tests/test_remove_flagged_rm.py::test_rm1b2_name_label_line_split_after_abbreviation_goes,
             tests/test_remove_flagged_rm.py::test_rm1i3_unsure_claim_removed_by_name_not_kept,
             tests/test_remove_flagged_rm.py::test_rm1i3_unsure_claim_partly_removed_listed,
             tests/test_remove_flagged_rm.py::test_rm2h1_name_flag_first_claim_record_kept,
             tests/test_remove_flagged_rm.py::test_rm1g6_name_removed_when_claim_removal_refused,
             tests/test_remove_flagged_rm.py::test_rm1g6_nothing_removed_when_name_attempt_also_refused,
             tests/test_remove_flagged_rm.py::test_rm1g6_cap_refusal_retries_names_only,
             tests/test_remove_flagged_rm.py::test_rm1g6_names_only_tried_before_older_cuts,
             tests/test_remove_flagged_rm.py::test_rm1g6_section_guard_keeps_claim_not_name,
             tests/test_remove_flagged_rm.py::test_rm1g6_section_and_cap_grid_claim_never_keeps_name,
             tests/test_remove_flagged_rm.py::test_rm1g6_section_name_cut_left_out_of_retry,
             tests/test_remove_flagged_rm.py::test_rm1b2_label_line_left_out_of_retry_at_cap,
             tests/test_remove_flagged_rm.py::test_rm1g6_name_over_cap_does_not_keep_removable_claim,
             tests/test_remove_flagged_rm.py::test_rm1g6_name_refused_does_not_keep_removable_claim,
             tests/test_remove_flagged_rm.py::test_rm1i3_claim_on_sentence_with_old_and_new_name_stays_in_retry
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
    # A copy in the front matter may be escaped or folded there (``_head_readings``).
    scaffolding_readings = _head_readings(scaffolding)

    spans = {}  # a sentence split after an abbreviation -> its parts, cut together
    for s in sentences:
        spans.setdefault((s.line, s.group), []).append((s.start, s.end))

    targets, kept, seen = [], [], set()
    partly = {}  # flag -> why one of its sentences was kept while others go
    unsure = []  # (claim flag, its copies on an uncertain split), settled below
    for flag in flags:
        if flag in seen:
            continue
        seen.add(flag)
        if getattr(flag, "kind", "claim") == "name":
            word = _name_word(flag.name)
            hits = [s for s in sentences
                    if _names(s, word, lines[s.line], spans[(s.line, s.group)])]
            reason = f"name '{flag.name}'"
            # The name pattern before RM1.b.5 read "_" as part of a word, and a label
            # line was read one part at a time before RM1.b.2 took the whole sentence; a
            # sentence only the new rules take is newly cut, which the retry needs to
            # know (RM1.g.6).
            was = re.compile(rf"(?<!\w){re.escape(flag.name)}(?!\w)")
            known = {(s.line, s.group) for s in hits
                     if _names(s, was, lines[s.line], [(s.start, s.end)])}
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
        if len(sure) < len(hits):
            unsure.append((flag, [s for s in hits if s.doubtful]))
        if sure:
            targets.extend(_Target(s, flag, part_reason.get((s.line, s.start), reason),
                                   new=getattr(flag, "kind", "claim") == "name"
                                   and (s.line, s.group) not in known)
                           for s in sure)
        elif hits:
            pass  # every copy is on an uncertain split: settled below
        elif getattr(flag, "kind", "claim") != "name" and fj._claim_body(flag) in headings:
            kept.append(Kept(flag, A_HEADING))
        elif _copy_in(flag.name if getattr(flag, "kind", "") == "name"
                      else fj._claim_body(flag), scaffolding_readings):
            kept.append(Kept(flag, IN_SCAFFOLDING))
        else:
            kept.append(Kept(flag, NOT_FOUND))
    # A claim's copy on an uncertain split is not cut alone, which could leave a fragment
    # ("Army in 1990."); it goes when a name flag takes its whole sentence (RM1.i.3).
    named = {}  # sentence -> whether only names first cut since RM1.b.5 take it
    for t in targets:
        if getattr(t.flag, "kind", "claim") == "name":
            key = (t.sentence.line, t.sentence.start)
            named[key] = named.get(key, True) and t.new
    for flag, doubtful in unsure:
        with_name = [s for s in doubtful if (s.line, s.start) in named]
        targets.extend(_Target(s, flag, FAITHFULNESS, new=named[(s.line, s.start)])
                       for s in with_name)
        if len(with_name) < len(doubtful):
            if any(t.flag == flag for t in targets):
                partly[flag] = UNSURE_BOUNDARY
            else:
                kept.append(Kept(flag, UNSURE_BOUNDARY))

    def _keep(target, reason):
        targets.remove(target)
        if any(t.flag == target.flag for t in targets):
            partly.setdefault(target.flag, reason)
        else:
            partly.pop(target.flag, None)
            kept.append(Kept(target.flag, reason))

    spared = set()  # name sentences the section rule cuts since RM1.g.6, for the retry
    while targets:
        changed = False
        for heading, section_lines in _emptied_sections(lines, targets, sentences):
            here = [t for t in targets if t.sentence.line in section_lines]
            # Keeping the claim sentences is enough to leave the section with text, and
            # a kept claim is only a warning, while a kept name fails the stage (entity
            # check). A claim in a name's sentence goes with it. The names are kept only
            # in a section with no other flagged sentence (RM1.g.6).
            named = {(t.sentence.line, t.sentence.start) for t in here
                     if getattr(t.flag, "kind", "claim") == "name"}
            claims = [t for t in here if (t.sentence.line, t.sentence.start) not in named]
            if claims:
                spared |= {(t.sentence.line, t.sentence.group) for t in here
                           if t not in claims}
                here = claims
            for t in here:
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

    def _attempt(chosen):
        """Cut ``chosen``: ((new_text, dropped, new_head, in_head, left_in_head), "") or
        (None, why); the cap, the front-matter edit and the deletion check."""
        new_lines, dropped = _build(lines, chosen)
        new_body = "\n".join(new_lines)
        body_words = len(body.split())
        share = (body_words - len(new_body.split())) / body_words if body_words else 1.0
        if share > max_share:
            return None, f"would remove {share:.0%} of the words (cap {max_share:.0%})"
        # The words cut, without a label the judge reads with them (RM1.b.1).
        removed_text = {t.sentence.own for t in chosen}
        joined, riders = _cut_groups(chosen)
        new_head, in_head, left_in_head = _edit_front_matter(head, removed_text, joined,
                                                             riders)
        # Every copy left in the front matter is reported (RM1.e.1): in an answer the FAQ
        # edit cannot read (unquoted, single-quoted, folded), under another key, or
        # inside an answer's sentence that the edit kept whole (RM1.e.2), also when a
        # quoted copy was taken out. It is looked for with YAML's escapes undone and
        # as written (``_head_readings``).
        head_readings = _head_readings(new_head)
        left_in_head |= {s for s in removed_text if _copy_in(s, head_readings)}
        new_text = lead + new_head + new_body
        cut_once = {(t.sentence.line, t.sentence.start): t.sentence.text for t in chosen}
        problems = deletion_problems(text, new_text, Counter(cut_once.values()),
                                     [lines[i] for i in dropped], joined=joined,
                                     riders=riders)
        if problems:
            return None, "deletion check failed: " + "; ".join(problems)
        return (new_text, dropped, new_head, in_head, left_in_head), ""

    result, why = _attempt(targets)
    if result is None and why.startswith(("deletion check failed", "would remove")):
        # One refused removal (the deletion check or the cap) kept every flag, and a kept
        # name fails the stage (entity check), while a kept claim is only a warning. Try
        # again, and cut the first set that passes, each held to the same cap. The cuts
        # made only since RM1.b.3 and RM1.b.5 (a sentence placed with other spacing, a
        # name in "_…_") were never made before, so they are left out first, except a
        # name flag's; then the name flags' sentences only, and the claim flags on those
        # sentences (RM1.g.6); then without any of the new cuts, so a new cut that is
        # refused or takes the removal over the cap does not keep what was removed
        # before; then the names without the new cuts. The names-only set comes before
        # the older cuts, so a claim never keeps a name the name's own cut would remove.
        # Last, the claims on no name's sentence: when no set with a name passes, the
        # names are kept either way, and a name sentence over the cap or refused does
        # not keep the claims. A sentence split after an abbreviation is left out whole,
        # so a name takes both parts or neither (RM1.i).
        named = {(t.sentence.line, t.sentence.start) for t in targets
                 if getattr(t.flag, "kind", "claim") == "name"}
        names_only = [t for t in targets if (t.sentence.line, t.sentence.start) in named]
        newly = {(t.sentence.line, t.sentence.group) for t in targets
                 if t.sentence.loose} | spared
        old = [t for t in targets
               if not t.new and (t.sentence.line, t.sentence.group) not in newly]
        tried = []
        for chosen in ([t for t in targets if t in old or t in names_only], names_only, old,
                       [t for t in names_only if t in old],
                       [t for t in targets if t not in names_only]):
            if not chosen or len(chosen) == len(targets) or chosen in tried:
                continue
            tried.append(chosen)
            retried, _ = _attempt(chosen)
            if retried is None:
                continue
            left = [t for t in targets if t not in chosen]
            for f in dict.fromkeys(t.flag for t in left):
                if any(t.flag == f for t in chosen):
                    partly[f] = why
                else:
                    kept.append(Kept(f, why))
            result, targets = retried, chosen
            break
    if result is None:
        flags_hit = list(dict.fromkeys(t.flag for t in targets))
        return text, [], kept + [Kept(f, why) for f in flags_hit]
    new_text, dropped, new_head, in_head, left_in_head = result
    head_readings = _head_readings(new_head)
    flags_of: dict = {}
    for t in targets:
        flags_of.setdefault(t.sentence.own, {})[t.flag] = None
    # A claim the judge read with a bold label: the label stays on its line and is now
    # read with the next sentence, which no judge has seen with it (RM1.b.1).
    label_left = {t.flag: None for t in targets
                  if getattr(t.flag, "kind", "claim") != "name" and t.sentence.label
                  and t.sentence.line not in dropped}

    def _left_in_head(flag):
        # A name flag's part ("He trained in the U.S.") may be in the front matter only
        # inside a longer sentence; the flag is kept there only if its name is (RM1.e.1).
        return (getattr(flag, "kind", "claim") != "name"
                or any(_name_word(flag.name).search(reading) for reading in head_readings))
    kept += [Kept(f, STILL_IN_FRONT_MATTER + (f"; {LABEL_STAYS}" if f in label_left else ""))
             for f in dict.fromkeys(f for s in sorted(left_in_head) for f in flags_of[s])
             if _left_in_head(f)]
    # A flag removed in one place may still be in another (a section's only text, a
    # bold label, a heading): it is listed as kept, so no flag goes unreported (P2).
    left_claims = {fj._claim_body(c) for c in fj.extract_claims(new_text)}
    listed = {str(k.claim) for k in kept}
    for flag in dict.fromkeys(t.flag for t in targets):
        if str(flag) in listed:
            continue
        if getattr(flag, "kind", "claim") == "name":
            name = _name_word(flag.name)
            # A folded answer may break the name onto two lines (``_head_readings``).
            still = name.search(new_text) or any(name.search(r) for r in head_readings)
        else:
            still = fj._claim_body(flag) in left_claims or flag in partly
        if still:
            what = (flag.name if getattr(flag, "kind", "claim") == "name"
                    else fj._claim_body(flag))
            why = partly.get(flag) or (IN_SCAFFOLDING if _copy_in(what, scaffolding_readings)
                                       else NOT_FOUND)
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
                               t.sentence.own in in_head - left_in_head))
    return new_text, removed, kept
