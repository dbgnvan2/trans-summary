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

# Scaffold words: the plain >=4-char tokens a recollection is MATCHED on (the
# person name + the attribution verbs), DERIVED from the verb regex lists above —
# the single source of truth — so the consistency check's "strip attribution
# before judging content" can never drift from the detector's actual vocabulary
# (the recurring two-hand-maintained-lists failure). "quote"/"quoted" are added
# explicitly because the "quoted?" alternation only surfaces "quoted" to the
# tokenizer; "dr" rides along as a name token.
ATTRIBUTION_SCAFFOLD_WORDS = frozenset(
    {w for verb_re in (_REJECTION_VERBS, _ATTRIBUTION_VERBS)
     for alt in verb_re.split("|")
     for w in re.findall(r"[a-z]{4,}", alt)}
    | {"bowen", "murray", "dr", "quote", "quoted"}
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

# Sentence-level split for density counting. Split on terminal punctuation only;
# newlines are handled inside find_bowen_person_attributions so a recollection
# whose person name and verb straddle a newline is still counted.
_SENTENCE_SPLIT = re.compile(r"[.!?]\s+")


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

    Splitting strategy (handles both failure modes):
    * terminal punctuation delimits sentences;
    * newlines further split a sentence into lines (rough dictation often
      separates unpunctuated sentences with newlines);
    * a line that doesn't match on its own is re-tried joined with the FOLLOWING
      lines (space-normalised), growing until it matches, so a recollection whose
      name and verb straddle several newlines ("Murray Bowen\n…\nsaid …") is
      still counted (within the pattern's own 80-char name→verb window) —
      matching the extractor's newline-collapsing normalisation. The grow stops
      before any line that itself matches (that line is its own recollection and
      must not be consumed).
    """
    if not text:
        return []
    out: list[str] = []
    for seg in _SENTENCE_SPLIT.split(str(text)):
        lines = [" ".join(x.split()).strip().lower() for x in seg.split("\n")]
        lines = [x for x in lines if x]
        i = 0
        while i < len(lines):
            if _is_bowen_person_attribution(lines[i]):
                out.append(lines[i])
                i += 1
                continue
            # Bridge: grow the join across following lines (space-normalised)
            # until it matches, stopping before any line that itself matches.
            joined = lines[i]
            j = i
            matched = False
            while j + 1 < len(lines):
                nxt = lines[j + 1]
                if _is_bowen_person_attribution(nxt):
                    break
                joined = joined + " " + nxt
                j += 1
                if _is_bowen_person_attribution(joined):
                    out.append(joined)
                    i = j + 1
                    matched = True
                    break
            if not matched:
                i += 1
    return out
