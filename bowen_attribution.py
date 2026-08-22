"""Shared Bowen person-attribution detection.

Single source of truth for "does this text recount Murray Bowen HIMSELF" —
attribution to the person, NOT "Bowen theory" abstractions. Used by both the
extraction pipeline (to filter candidate Bowen references) and the
cross-artifact consistency check (to estimate person-recollection density), so
the two definitions can never drift apart.

Stdlib-only (``re``) so the consistency check can import it without pulling in
the pipeline's API clients.
"""

from __future__ import annotations

import re

# ---- person-attribution verb list (shared with the rejection below) ----------
_ATTRIBUTION_VERBS = (
    r"said|says|saying|wrote|writes|thought|believed|described|"
    r"referred|called|commented|noted|observed|argued|stated|told|did|does|do|"
    r"predicted|switched|shifted|suggested|concluded|found|identified|saw|"
    r"quoted?|talk(?:ed)?\s+about|used\s+to\s+talk|was\s+very\s+clear\s+about"
)

# "Bowen said / wrote / believed / described / did / predicted ..." etc.
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

# Sentence units for density counting (period / bang / question-mark boundary).
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _is_bowen_person_attribution(quote_l: str) -> bool:
    """Core check on an already-lowercased, whitespace-collapsed unit of text."""
    # Explicitly reject non-source actor patterns.
    if re.search(r"\bbowen\s+theorists?\b", quote_l):
        return False
    # "Bowen theory says X" is theory exposition, not a recollection of Bowen —
    # unless the same clause also carries a person-attribution verb.
    if re.search(r"\bbowen\s+theory\b", quote_l) and not re.search(
        _PERSON_VERB_PATTERN, quote_l
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
    """
    if not text:
        return []
    norm = " ".join(str(text).split()).strip().lower()
    if not norm:
        return []
    units = _SENTENCE_SPLIT.split(norm)
    return [u.strip() for u in units if u.strip() and _is_bowen_person_attribution(u)]
