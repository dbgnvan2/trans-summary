"""Shared Bowen person-attribution detection.

Single source of truth for "does this text recount Murray Bowen HIMSELF" —
attribution to the person, NOT "Bowen theory" abstractions. Used by both the
extraction pipeline (to filter candidate Bowen references) and the
cross-artifact consistency check (to estimate person-recollection density), so
the two definitions can never drift apart.

The regexes below are byte-for-byte identical to the pre-refactor
``extraction_pipeline._has_bowen_source_attribution``; the only change is that
they now live in this stdlib-only module (``re``) so the consistency check can
import them without pulling in the pipeline's API clients.
"""

from __future__ import annotations

import re

# ---- verb lists -------------------------------------------------------------
# NOTE: the original had TWO different verb lists. The "Bowen theory" rejection
# check uses the SHORT list; the primary attribution pattern uses the LONG list.
# Do not unify them — that changes the rejection semantics.

# Short list — used ONLY by the "Bowen theory" rejection check.
_REJECTION_VERBS = (
    r"said|says|saying|wrote|writes|thought|believed|described|"
    r"referred|called|commented|noted|observed|argued|stated|told|"
    r"quoted?|talk(?:ed)?\s+about|used\s+to\s+talk|was\s+very\s+clear\s+about"
)

# Long list — used ONLY by the primary "Bowen said / did / predicted ..." pattern.
_ATTRIBUTION_VERBS = (
    r"said|says|saying|wrote|writes|thought|believed|described|"
    r"referred|called|commented|noted|observed|argued|stated|told|did|does|do|"
    r"predicted|switched|shifted|suggested|concluded|found|identified|saw|"
    r"quoted?|talk(?:ed)?\s+about|used\s+to\s+talk|was\s+very\s+clear\s+about"
)

# "murray" (bare) — the rejection anchor's "Murray" needs no surname, unlike the
# primary pattern's "murray(?:\s+bowen)?".
_THEORY_PERSON_VERB_PATTERN = (
    r"\b(?:murray|dr\.?\s*bowen|bowen(?!\s+theory)(?:'s)?)\b"
    r"[^.!?\n]{0,80}\b"
    rf"(?:{_REJECTION_VERBS})\b"
)

# Primary person-verb pattern: "Bowen said / wrote / believed / described / did /
# predicted ..." etc.
_PERSON_VERB_PATTERN = (
    r"\b(?:murray(?:\s+bowen)?|dr\.?\s*bowen|bowen(?!\s+theory)(?:'s)?)\b"
    r"[^.!?\n]{0,80}\b"
    rf"(?:{_ATTRIBUTION_VERBS})\b"
)

_ATTRIBUTION_PATTERNS = (
    _PERSON_VERB_PATTERN,
    # "to quote Bowen" / "quote from Bowen"
    r"\b(?:to\s+quote\s+bowen|quote\s+from\s+bowen)\b",
    # Possessive attribution: "Bowen's [adjectives] idea/observation/insight/…"
    # Allow up to two intervening words so "Bowen's basic ideas", "Bowen's very
    # insightful observation", "all Bowen's key points" all match — previously
    # only an immediately-adjacent noun (or "key") was recognised, so a common
    # phrasing like "Bowen's basic ideas" was silently dropped.
    r"\bbowen'?s\s+(?:\w+\s+){0,2}"
    r"(?:ideas?|concepts?|points?|observations?|insights?|views?|"
    r"approach|framework|thinking|conclusions?|predictions?|comments?|"
    r"quotes?|switch|work|writings?|teachings?)\b",
    # "I remember (talking to) Murray ... he said"
    r"\bi\s+remember\s+(?:talking\s+to\s+)?murray\b[^.!?\n]{0,120}\bhe\s+said\b",
    # "a tape / video / recording Murray Bowen made / did"
    r"\b(?:tape|video|recording|session)\s+(?:\w+\s+){0,4}murray\s+bowen\b",
    # "What did Bowen do / say"
    r"\bwhat\s+did\s+bowen\b",
    # "favorite Bowen quotes"
    r"\bbowen\s+quotes?\b",
)

# Sentence units for density counting. Split on newline runs (rough dictation
# often separates sentences with newlines and no terminal punctuation) AND on
# terminal punctuation followed by whitespace.
_UNIT_SPLIT = re.compile(r"\n+|[.!?]\s+")


def _is_bowen_person_attribution(quote_l: str) -> bool:
    """Core check on an already-lowercased, whitespace-collapsed unit of text."""
    # Explicitly reject non-source actor patterns.
    if re.search(r"\bbowen\s+theorists?\b", quote_l):
        return False
    # "Bowen theory says X" is theory exposition, not a recollection of Bowen —
    # unless the same clause also carries a person-attribution verb.
    if re.search(r"\bbowen\s+theory\b", quote_l) and not re.search(
        _THEORY_PERSON_VERB_PATTERN, quote_l
    ):
        return False
    return any(re.search(p, quote_l) for p in _ATTRIBUTION_PATTERNS)


def has_bowen_source_attribution(quote: str) -> bool:
    """Return True only when ``quote`` itself ties the statement to Murray/Dr.
    Bowen as the source (person, not theory)."""
    if not quote:
        return False
    quote_l = " ".join(str(quote).split()).strip().lower()
    if not quote_l:
        return False
    return _is_bowen_person_attribution(quote_l)


def find_bowen_person_attributions(text: str) -> list[str]:
    """Return the sentence-units of ``text`` that recount Bowen the person.

    Each returned string is a lowercased matching unit. ``len(...)`` is the
    person-recollection density used by the cross-artifact consistency check;
    the strings themselves are the recollections for reporting.

    Units are split on newlines and terminal punctuation (so a rough-dictation
    transcript with newline-separated, unpunctuated sentences still yields one
    unit per recollection), then normalised the same way the extractor does.
    """
    if not text:
        return []
    out = []
    for u in _UNIT_SPLIT.split(str(text)):
        u_l = " ".join(u.split()).strip().lower()
        if u_l and _is_bowen_person_attribution(u_l):
            out.append(u_l)
    return out
