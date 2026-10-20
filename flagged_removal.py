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

_MARKERS = ("**", "__")
_LINE_LEAD = re.compile(r"^\s*(?:[-*>]+\s*)*")       # as _clean_claim_line strips it
_ENUMERATOR = re.compile(r"^\d+[.)]\s+")
_LABEL_PREFIX = re.compile(r"^([A-Za-z][^:\n]{0,40}):\s*")
_BOLD_ONLY = re.compile(r"^\*\*[^*\n]+\*\*\s*$")
# A line with nothing left but a list marker and/or a bold label. Bold text that ends
# like a sentence ("**Kerr says X.**") is a sentence, not a label: the line stays.
_EMPTY_LINE = re.compile(
    r"^\s*(?:[-*+>•]\s*|\d+[.)]\s*)*"
    r"(?:(?:\*\*|__)(?:[^*_\n]*[^*_\n.!?])?(?:\*\*|__)\s*)?[:.—–-]?\s*$")
_FAQ_ANSWER = re.compile(
    r'^(?P<lead>\s*(?:-\s+)?a:\s*)"(?P<value>(?:[^"\\]|\\.)*)"(?P<trail>\s*)$')
_FAQ_QUESTION = re.compile(r"^\s*-\s+q:\s*")
_TOKEN = re.compile(r'[^\s"]+|"')
_YAML_KEY = re.compile(r"^\s*(?:-\s+)?([A-Za-z_][\w-]*):", re.MULTILINE)
# A split the judge's splitter makes but may not be a sentence end: after a token with
# two periods ("U.S.", "Ph.D.") or a listed abbreviation ("Sen.", "Jan."), or before a
# number (config.FAITHFULNESS_REMOVE_UNSURE_ABBREVIATIONS).
_DOUBTFUL_END = re.compile(
    r"(?:(?<!\S)\S*\.\S*\.|\b(?:"
    + "|".join(map(re.escape, config.FAITHFULNESS_REMOVE_UNSURE_ABBREVIATIONS))
    + r")\.)$", re.IGNORECASE)
_DOUBTFUL_START = re.compile(r"^\d")


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
    """One removed sentence, as the judge read it (bold markers removed), with the
    sentences on either side of it in the result."""
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
    group: int = 0          # sentences joined by uncertain splits share a group
    doubtful: bool = False  # a boundary with a neighbour may not be a sentence end


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


def _line_sentences(raw: str, index: int, strip_prefixes: set) -> list:
    """The sentences of one body line as extract_claims splits them, each with its
    span in the raw line. A sentence that cannot be placed ends the line's list, so
    it and the rest are not removable (they are reported as not found)."""
    s = raw.strip()
    if not s or _is_heading(raw) or _BOLD_ONLY.match(s):
        return []
    m = _INLINE_BOLD_LABEL.match(raw)
    clean, where = _clean_with_map(raw, m.start("rest") if m else 0)
    lead = _LINE_LEAD.match(clean).end()
    m_prefix = _LABEL_PREFIX.match(clean[lead:])
    if m_prefix and m_prefix.group(1).strip().lower() in strip_prefixes:
        lead += m_prefix.end()
    m_enum = _ENUMERATOR.match(clean[lead:])
    if m_enum:
        lead += m_enum.end()
    body = clean[lead:].rstrip()
    out, cursor = [], 0
    for part in fj._split_sentences(body):
        text = part.strip()
        if not text:
            continue
        at = body.find(text, cursor)
        if at < 0:
            break
        first, last = where[lead + at], where[lead + at + len(text) - 1] + 1
        # A sentence wrapped in bold takes its markers with it.
        while (first >= 2 and raw[first - 2:first] in _MARKERS
               and raw[last:last + 2] == raw[first - 2:first]):
            first, last = first - 2, last + 2
        sentence = _Sentence(index, first, last, text, group=len(out))
        if out and (_DOUBTFUL_END.search(out[-1].text) or _DOUBTFUL_START.match(text)):
            # Removing either side would leave a fragment ("He trained with the U.S.").
            out[-1].doubtful = sentence.doubtful = True
            sentence.group = out[-1].group
        out.append(sentence)
        cursor = at + len(text)
    return out


def _cut(raw: str, spans: list) -> str:
    """``raw`` without the spans, each with the space that separated it from the next
    sentence (or, at the end of the line, from the one before)."""
    for start, end in sorted(spans, reverse=True):
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
    quoted front-matter answer moves the closing quote onto the sentence before."""
    return _TOKEN.findall(text)


def _body_sentences(text: str) -> list:
    """Every sentence of the body, short ones included, as removal reads them."""
    strip_prefixes = {s.lower() for s in config.FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES}
    lines = _split(text)[2].split("\n")
    return [s.text for i, line in enumerate(lines)
            for s in _line_sentences(line, i, strip_prefixes)]


def _is_subsequence(short: list, long: list) -> bool:
    it = iter(long)
    return all(any(x == y for y in it) for x in short)


def deletion_problems(before: str, after: str, removed: set, dropped_lines=()) -> list:
    """What makes ``after`` more than ``before`` with sentences deleted; [] when it is
    only that. ``removed``: the removed sentences; ``dropped_lines``: the text of lines
    removed whole (a claim taken from such a line, e.g. a bold label, may go too).

    Purpose: Use a removal only when it deletes and changes nothing else.
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM1.g
    Tests:   tests/test_remove_flagged_rm.py::test_rm1g_check_names_each_problem,
             tests/test_remove_flagged_rm.py::test_rm1g_changed_text_rejected_draft_unchanged
    """
    problems = []
    if not _is_subsequence(_tokens(after), _tokens(before)):
        problems.append("text was added or changed, not only deleted")
    was = [fj._claim_body(c) for c in fj.extract_claims(before)]
    now = [fj._claim_body(c) for c in fj.extract_claims(after)]
    if not _is_subsequence(now, was):
        problems.append("a claim was added or changed")
    else:
        dropped_text = [d.replace("**", "").replace("__", "") for d in dropped_lines]
        for claim in (Counter(was) - Counter(now)):
            if claim not in removed and not any(claim in d for d in dropped_text):
                problems.append(f"a claim was lost that was not flagged: {claim[:80]!r}")
        # Sentences too short to be claims are checked too: only removed ones may go.
        lost = Counter(_body_sentences(before)) - Counter(_body_sentences(after))
        for sentence in lost:
            if sentence not in removed and not any(sentence in d for d in dropped_text):
                problems.append(f"a sentence was lost that was not flagged: {sentence[:80]!r}")
    _, head_before, body_before = _split(before)
    _, head_after, body_after = _split(after)
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

    Purpose: Take out a sentence that is still flagged after the last revision.
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM1.a-#RM1.i
    Tests:   tests/test_remove_flagged_rm.py::test_rm1a_flagged_sentence_removed_rest_unchanged,
             tests/test_remove_flagged_rm.py::test_rm1d_part_of_longer_sentence_not_removed,
             tests/test_remove_flagged_rm.py::test_rm1h_cap_keeps_draft_and_announces
    """
    lead, head, body = _split(text)
    lines = body.split("\n")
    strip_prefixes = {s.lower() for s in config.FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES}
    sentences = [s for i, line in enumerate(lines)
                 for s in _line_sentences(line, i, strip_prefixes)]
    headings = {ln.strip().lstrip("#").replace("**", "").replace("__", "").strip()
                for ln in lines if _is_heading(ln)}
    labels = [m.group("label") for m in map(_INLINE_BOLD_LABEL.match, lines) if m]
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
            hits = [s for s in sentences if word.search(s.text)]
            reason = f"name '{flag.name}'"
        else:
            claim = fj._claim_body(flag)
            hits = [s for s in sentences if s.text == claim]
            reason = FAITHFULNESS
        if getattr(flag, "kind", "claim") == "name":
            # A kept name blocks the stage (entity check): take the whole sentence, all
            # the parts an uncertain split made of it.
            groups = {(s.line, s.group) for s in hits}
            hits = [s for s in sentences if (s.line, s.group) in groups]
        sure = [s for s in hits if not s.doubtful or getattr(flag, "kind", "") == "name"]
        if sure:
            targets.extend(_Target(s, flag, reason) for s in sure)
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

    removed_text = {t.sentence.text for t in targets}
    new_head, in_head, left_in_head = _edit_front_matter(head, removed_text)
    # An answer the FAQ edit cannot read (unquoted, single-quoted, folded) keeps its copy.
    left_in_head |= {s for s in removed_text - in_head if s in new_head}
    new_text = lead + new_head + new_body
    problems = deletion_problems(text, new_text, removed_text,
                                 [lines[i] for i in dropped])
    if problems:
        why = "deletion check failed: " + "; ".join(problems)
        flags_hit = list(dict.fromkeys(t.flag for t in targets))
        return text, [], kept + [Kept(f, why) for f in flags_hit]
    flag_of = {t.sentence.text: t.flag for t in targets}
    kept += [Kept(flag_of[s], "removed from the body; still in the front matter's FAQ answers")
             for s in sorted(left_in_head)]
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
    removed, listed_at = [], set()
    for t in sorted(targets, key=lambda t: (order[(t.sentence.line, t.sentence.start)],
                                            t.reason != FAITHFULNESS)):
        n = order[(t.sentence.line, t.sentence.start)]
        if n in listed_at:
            continue
        listed_at.add(n)
        why = list(dict.fromkeys(reasons[(t.sentence.line, t.sentence.start)]))
        removed.append(Removed(t.sentence.text, _neighbour(n, -1), _neighbour(n, 1),
                               why[0] + (f" (also {', '.join(why[1:])})" if why[1:] else ""),
                               dict(getattr(t.flag, "record", {}) or {}),
                               t.sentence.text in in_head))
    return new_text, removed, kept
