"""Domain-semantic judge for key-term definitions (gap #4).

Lexical grounding (``validate_key_terms_fidelity``) cannot catch a definition that
is lexically plausible but semantically WRONG — a key term defined as the wrong
concept, or swapped with a sibling term, while still using transcript vocabulary
(the same failure class the faithfulness judge closes for narrative claims). This
adds a semantic judge: for each key term, does its DEFINITION correctly capture
what the term means in the domain (Bowen family systems theory), consistent with
how the transcript discusses it?

This is deliberately a DIFFERENT question from the theme/faithfulness judges, which
ask "is this grounded in the source?" — those cannot call a swapped definition
wrong, because both definitions are grounded (each appears in the transcript). The
domain-semantic judge is allowed to use outside Bowen-theory knowledge to catch a
definition that says the wrong THING about a term.

The judge is judged before arming: its threshold is evaluated against a labeled set
(correct vs swapped definitions) via ``binary_key_terms_metrics`` / the head-to-head
harness. It fails closed: any API/parse error is an ERROR, never a PASS.

Design mirrors ``faithfulness_judge``:
  * ``judge_key_terms``          — ONE batched call scoring every (term, definition).
  * ``judge_key_terms_artifact`` — parse the key-terms.md artifact and judge it,
                                    returning a ``FaithfulnessResult``.
  * ``binary_key_terms_metrics`` — precision/recall/accuracy of the INCORRECT class
                                    (the calibration primitive, mirrors M2.B).

Tests: tests/test_key_terms_semantic_judge.py
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import config
from faithfulness_judge import (
    ERROR,
    FAIL,
    PASS,
    ClaimVerdict,
    FaithfulnessResult,
    cached_judge_content,
    parse_judge_response,
)

# Labels the judge assigns each key term's definition.
CORRECT = "correct"
INCORRECT = "incorrect"
_LABELS = {CORRECT, INCORRECT}

_JUDGE_INSTRUCTIONS = """\
You are auditing key-term definitions extracted from a transcript about Bowen family \
systems theory. For each TERM + DEFINITION pair, decide whether the definition \
CORRECTLY describes the term's meaning.

This is a DOMAIN-SEMANTIC check, not a lexical one: a definition can use the right \
vocabulary yet describe the WRONG concept. Use your knowledge of Bowen family systems \
theory (differentiation of self, emotional cutoff, triangles, fusion, anxiety, the \
individuality/togetherness life forces, homeostasis, emotional objectivity, the \
emotional-salience and executive-control networks, blocked ontogeny, etc.) AND the \
transcript to judge whether the definition captures what the term actually means:

- "correct": the definition accurately states the term's meaning in Bowen theory — \
even if paraphrased in different words — and does not contradict the transcript.
- "incorrect": the definition misstates the term — it describes a DIFFERENT concept, \
swaps the definition of one term for another's, reverses a relationship, or asserts \
a meaning that contradicts Bowen theory or the transcript.

Judge ONLY the term-definition pairing: does the definition say the RIGHT thing \
about the term? A vague-but-not-wrong definition is "correct"; a definition that is \
confidently about something else is "incorrect". Do not require verbatim wording.

Return ONLY a JSON array, one object per term, in order:
[{"index": 1, "label": "correct|incorrect", "rationale": "<= 20 words"}]
No prose before or after the JSON."""


def build_key_terms_judge_prompt(terms: list, source: str) -> list:
    """``terms`` = [(term, definition)]. Returns the cache-reusable content blocks."""
    numbered = "\n\n".join(
        f"{i + 1}. TERM: {t}\nDEFINITION: {d}" for i, (t, d) in enumerate(terms)
    )
    tail = f"=== KEY TERMS ({len(terms)}) ===\n{numbered}\n"
    return cached_judge_content(_JUDGE_INSTRUCTIONS, source, tail)


def judge_key_terms(terms: list, source: str, client, *,
                    model: Optional[str] = None, logger=None) -> list:
    """Judge every (term, definition) against the source in ONE batched call ->
    ``ClaimVerdict`` list (claim = the term, label in {correct, incorrect}). Raises
    on API/parse failure so the caller fails closed."""
    from transcript_utils import call_claude_with_retry

    model = model or config.KEY_TERMS_JUDGE_MODEL
    message = call_claude_with_retry(
        client=client,
        model=model,
        messages=[{"role": "user", "content": build_key_terms_judge_prompt(terms, source)}],
        max_tokens=config.KEY_TERMS_JUDGE_MAX_TOKENS,
        temperature=config.TEMP_STRICT,
        min_length=1,
        logger=logger or logging.getLogger("key_terms_semantic_judge"),
        timeout=config.TIMEOUT_DEFAULT,
    )
    names = [t for t, _ in terms]
    return parse_judge_response(message.content[0].text, names, valid_labels=_LABELS)


def parse_key_terms_artifact(markdown: str) -> list:
    """Extract ``[(term, definition)]`` pairs from a key-terms.md artifact. The
    definition is the prose under each ``### Term`` heading up to the next heading;
    falls back to the older bold ``**Term**: definition`` format."""
    text = re.sub(r"^---\s*\n.*?\n---\s*\n", "", markdown, flags=re.DOTALL)
    pairs = []
    for block in re.split(r"\n(?=###\s)", text):
        m = re.match(r"###\s+(.+?)\s*\n(.*)", block, re.DOTALL)
        if not m:
            continue
        term, definition = m.group(1).strip(), m.group(2).strip()
        if term and term.lower() != "key terms":
            pairs.append((term, definition))
    if pairs:
        return pairs
    # Fallback: bold `**Term**: definition` (the older key-terms format).
    for m in re.finditer(r"\*\*([^*\n]+)\*\*\s*[:|-]\s*(.+)", text):
        term, definition = m.group(1).strip(), m.group(2).strip()
        if term and term.lower() != "key terms":
            pairs.append((term, definition))
    return pairs


def judge_key_terms_artifact(key_terms_markdown: str, source: str, client, *,
                             model: Optional[str] = None, logger=None) -> FaithfulnessResult:
    """Judge a key-terms artifact for domain-semantic correctness. Any INCORRECT
    definition -> FAIL naming it; a judge error or missing source -> ERROR (fail
    closed). No terms -> PASS."""
    log = logger or logging.getLogger("key_terms_semantic_judge")
    if not source or not source.strip():
        return FaithfulnessResult(ERROR, "source transcript missing — cannot verify key terms")
    terms = parse_key_terms_artifact(key_terms_markdown)
    if not terms:
        # A header-only/blank artifact -> PASS (nothing to judge). A NON-empty body
        # that parsed to zero terms -> ERROR: a silent [] here would let a malformed
        # key-terms file through unjudged (P19), unlike a loud parse failure.
        body = re.sub(r"#+\s*key\s+terms\b", "", key_terms_markdown, flags=re.IGNORECASE)
        if body.strip():
            return FaithfulnessResult(ERROR, "key-terms artifact has content but no terms parsed")
        return FaithfulnessResult(PASS, "no key terms to judge")
    try:
        verdicts = judge_key_terms(terms, source, client, model=model, logger=log)
    except Exception as e:  # noqa: BLE001 — judge failure fails closed, never passes
        log.error("Key-terms semantic judge failed (fail-closed ERROR): %s", e, exc_info=True)
        return FaithfulnessResult(ERROR, f"judge error: {type(e).__name__}: {e}")
    incorrect = [v for v in verdicts if v.label != CORRECT]
    if incorrect:
        first = incorrect[0]
        return FaithfulnessResult(
            FAIL,
            f"{len(incorrect)} of {len(verdicts)} key-term definition(s) incorrect; "
            f"first: {first.claim[:100]!r}",
            claims=verdicts,
        )
    return FaithfulnessResult(PASS, f"all {len(verdicts)} key-term definition(s) correct",
                              claims=verdicts)


def binary_key_terms_metrics(pairs: list) -> dict:
    """Precision/recall/accuracy of detecting the INCORRECT class (the 'dangerous'
    class — a swapped/wrong definition the judge must not pass). ``pairs`` =
    [(true_label, pred_label)]. Recall is load-bearing: FN = a wrong definition the
    judge called correct. An EMPTY labeled set is a calibration error, not a perfect
    judge — raise rather than return a misleading 1.0 (P24)."""
    if not pairs:
        raise ValueError(
            "cannot compute key-terms metrics on an empty labeled set — "
            "empty must never read as a perfect (1.0) judge")
    tp = fp = fn = tn = 0
    for true_label, pred_label in pairs:
        t = true_label == INCORRECT
        p = pred_label == INCORRECT
        if t and p:
            tp += 1
        elif not t and p:
            fp += 1
        elif t and not p:
            fn += 1
        else:
            tn += 1
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    accuracy = (tp + tn) / len(pairs) if pairs else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": recall, "precision": precision, "accuracy": accuracy}
