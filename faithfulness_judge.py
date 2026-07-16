"""M2 — semantic faithfulness judge (spec §M2).

Purpose: lexical grounding cannot catch a fluent hallucination — a wrong-but-
on-topic definition and a fabricated proper name both pass keyword checks (why the
entity blocker only catches multi-word names). This adds a claim-level *entailment*
check for narrative artifacts (abstract, summary, overview, blog, themes): each
atomic claim must be entailed by the source transcript, or the artifact FAILs with
the offending sentence.

The judge is judged (M2.B): its decision threshold is pinned against a curated gold
set (`tests/fixtures/faithfulness_gold/`) gated on precision/recall. The judge fails
closed (M2.C): its own API/parse error is an ERROR (blocks publish), never a PASS.

Design:
  * ``extract_claims``  — deterministic sentence-level atomic claims (no LLM call).
  * ``judge_artifact``  — ONE batched judge call scoring every claim of an artifact,
    returning per-claim {entailed | contradicted | unsupported, rationale}. Any
    contradicted/unsupported claim -> FAIL. Hardened via ``call_claude_with_retry``
    (timeout + retry + backoff, P5). Any exception or unparseable response -> ERROR.

Spec:  docs/spec_unattended_robustness_2026-07-15.md#M2
Tests: tests/test_faithfulness_judge.py
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import config

# Labels the judge assigns each claim.
ENTAILED = "entailed"
CONTRADICTED = "contradicted"
UNSUPPORTED = "unsupported"
_LABELS = {ENTAILED, CONTRADICTED, UNSUPPORTED}

# Result statuses (mirror release_gate.Status values; kept as bare strings so this
# module has no import dependency on the gate — the gate maps them to a Verdict).
PASS = "PASS"
FAIL = "FAIL"
ERROR = "ERROR"


@dataclass
class ClaimVerdict:
    claim: str
    label: str
    rationale: str = ""

    @property
    def faithful(self) -> bool:
        return self.label == ENTAILED


@dataclass
class FaithfulnessResult:
    status: str  # PASS | FAIL | ERROR
    detail: str = ""
    claims: list = field(default_factory=list)

    @property
    def unfaithful(self) -> list:
        return [c for c in self.claims if not c.faithful]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "detail": self.detail,
            "unfaithful": [
                {"claim": c.claim, "label": c.label, "rationale": c.rationale}
                for c in self.unfaithful
            ],
        }


# --------------------------------------------------------------------------- claim extraction
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
# Tokens that end with a period but are NOT a sentence boundary — so "Dr. Malorni"
# and "J. Ewing" (a single initial) are not split into two claims.
_ABBREV = {
    "dr", "mr", "mrs", "ms", "prof", "st", "sr", "jr", "vs", "etc",
    "e.g", "i.e", "no", "inc", "co", "dept", "gen", "rev", "hon",
}


def _ends_with_abbrev(text: str) -> bool:
    m = re.search(r"(\S+)\s*$", text.rstrip())
    if not m:
        return False
    tok = m.group(1).rstrip(".").lower()
    return tok in _ABBREV or (len(tok) == 1 and tok.isalpha())


def _split_sentences(line: str) -> list:
    """Split a line into sentences, re-joining a fragment that was split after a
    common abbreviation / single initial (so 'Dr. Malorni' stays one claim)."""
    out: list = []
    for part in _SENTENCE_SPLIT.split(line):
        if out and _ends_with_abbrev(out[-1]):
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    return out


def extract_claims(text: str) -> list:
    """Split a narrative artifact into atomic, judgeable claims (sentence-level).

    Strips markdown headings, list markers, bold/italic wrappers, and the leading
    ``# Abstract`` / ``**Description:**`` scaffolding — a heading is not a claim.
    Returns claims long enough to carry a verifiable assertion (>= config bound),
    in document order. Deterministic: no LLM call here (cost + reproducibility)."""
    if not text:
        return []
    claims: list = []
    dropped = 0
    for raw_line in _strip_frontmatter(text).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "---":
            continue
        # drop list markers, blockquote markers, and a leading bold field label
        line = re.sub(r"^\s*(?:[-*>]+\s*)+", "", line)
        line = re.sub(r"^\*\*[^*\n]{1,40}:\*\*\s*", "", line)  # **Description:** ...
        line = line.replace("**", "").replace("__", "").strip()
        if not line:
            continue
        for sentence in _split_sentences(line):
            s = sentence.strip()
            if _is_claim(s):
                claims.append(s)
            elif s:
                dropped += 1
    if dropped:
        logging.getLogger("faithfulness_judge").debug(
            "extract_claims: dropped %d non-claim fragment(s) of %d",
            dropped, dropped + len(claims))
    return claims


def _is_claim(s: str) -> bool:
    """A judgeable claim. A long sentence qualifies; a SHORT sentence still counts
    when it states a concrete specific — a number or a proper noun (a capitalized
    word past the first). Without the concrete-short rule, a short fabricated
    declarative ('He married in 1975.', 'He died in Boston.') would be silently
    dropped and never judged — a fail-closed coverage hole in exactly the
    contradicted/unsupported class the judge exists to catch (P2/P9)."""
    if len(s) >= config.FAITHFULNESS_MIN_CLAIM_CHARS:
        return True
    if re.search(r"\d", s):
        return True
    return any(w[:1].isupper() for w in s.split()[1:])


def _strip_frontmatter(content: str) -> str:
    m = re.match(r"^\s*---\s*\n.*?\n---\s*\n", content, re.DOTALL)
    return content[m.end():] if m else content


# --------------------------------------------------------------------------- the judge
_JUDGE_INSTRUCTIONS = """\
You are a strict faithfulness auditor. You are given a SOURCE transcript and a \
numbered list of CLAIMS taken from a summary of that transcript. For EACH claim, \
decide whether the source supports it, using exactly one label:

- "entailed": the claim is directly stated in the source OR is a fair paraphrase, \
aggregation, or reasonable summary-level inference from the source.
- "contradicted": the claim conflicts with a specific fact in the source (wrong \
name, date, number, relationship, or outcome).
- "unsupported": the claim introduces a specific fact (a named person, place, date, \
quantity, event, or attribution) that is NOT present in and NOT derivable from the \
source. This is the hallucination case.

Judge ONLY against the source; do not use outside knowledge. When a claim is a \
high-level thematic summary that fairly reflects the source, label it "entailed". \
Reserve "unsupported" for concrete fabricated specifics.

Return ONLY a JSON array, one object per claim, in order:
[{"index": 1, "label": "entailed|contradicted|unsupported", "rationale": "<= 20 words"}]
No prose before or after the JSON."""


def build_judge_prompt(claims: list, source: str) -> str:
    numbered = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims))
    return (
        f"{_JUDGE_INSTRUCTIONS}\n\n"
        f"=== SOURCE ===\n{source}\n\n"
        f"=== CLAIMS ({len(claims)}) ===\n{numbered}\n"
    )


def _extract_json_array(text: str) -> list:
    """Pull the JSON array from a judge response, tolerating code fences / stray
    prose. Raises ValueError if no array parses (caller maps that to ERROR — a
    silent empty here would let a hallucination through, P14/P19)."""
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no JSON array found in judge response")
        candidate = text[start:end + 1]
    data = json.loads(candidate)
    if not isinstance(data, list):
        raise ValueError("judge response JSON is not an array")
    return data


def _parse_judge_response(response_text: str, claims: list) -> list:
    """Map the judge's JSON verdicts back onto the claims by 1-based index. Every
    claim must receive a valid label; a missing/invalid verdict raises (-> ERROR),
    never defaults to entailed (fail closed)."""
    data = _extract_json_array(response_text)
    by_index = {}
    for obj in data:
        if not isinstance(obj, dict) or "index" not in obj:
            continue
        try:
            idx = int(obj["index"])
        except (TypeError, ValueError):
            continue
        label = str(obj.get("label", "")).strip().lower()
        if label in _LABELS:
            by_index[idx] = (label, str(obj.get("rationale", "")).strip())
    verdicts = []
    for i, claim in enumerate(claims, start=1):
        if i not in by_index:
            raise ValueError(f"judge returned no valid verdict for claim {i}")
        label, rationale = by_index[i]
        verdicts.append(ClaimVerdict(claim=claim, label=label, rationale=rationale))
    return verdicts


def judge_claims(claims: list, source: str, client, *,
                 model: Optional[str] = None, logger=None) -> list:
    """Judge every claim against the source in ONE batched call. Returns a list of
    ``ClaimVerdict``. Raises on API/parse failure so the caller fails closed."""
    from transcript_utils import call_claude_with_retry

    model = model or config.FAITHFULNESS_JUDGE_MODEL
    prompt = build_judge_prompt(claims, source)
    message = call_claude_with_retry(
        client=client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=config.FAITHFULNESS_JUDGE_MAX_TOKENS,
        temperature=config.TEMP_STRICT,
        min_length=1,
        logger=logger or logging.getLogger("faithfulness_judge"),
        timeout=config.TIMEOUT_DEFAULT,
    )
    text = message.content[0].text
    return _parse_judge_response(text, claims)


def judge_artifact(artifact_text: str, source: str, client, *,
                   model: Optional[str] = None, logger=None) -> FaithfulnessResult:
    """Judge one narrative artifact for faithfulness against the source (M2.A).

    * No claims to judge -> PASS (nothing asserted).
    * Every claim entailed -> PASS.
    * Any contradicted/unsupported claim -> FAIL, naming the offending sentence(s).
    * Any judge exception (API error/timeout) or unparseable response -> ERROR
      (fail closed, M2.C) — never silently PASS on a judge failure (P1/P14)."""
    log = logger or logging.getLogger("faithfulness_judge")
    if not source or not source.strip():
        return FaithfulnessResult(ERROR, "source transcript missing — cannot verify")
    claims = extract_claims(artifact_text)
    if not claims:
        return FaithfulnessResult(PASS, "no judgeable claims in artifact")
    try:
        verdicts = judge_claims(claims, source, client, model=model, logger=log)
    except Exception as e:  # noqa: BLE001 — judge failure must fail closed, not pass
        log.error("Faithfulness judge failed (fail-closed ERROR): %s", e, exc_info=True)
        return FaithfulnessResult(ERROR, f"judge error: {type(e).__name__}: {e}")
    unfaithful = [v for v in verdicts if not v.faithful]
    if unfaithful:
        first = unfaithful[0]
        return FaithfulnessResult(
            FAIL,
            f"{len(unfaithful)} of {len(verdicts)} claim(s) not entailed by source; "
            f"first: [{first.label}] {first.claim[:120]!r}",
            claims=verdicts,
        )
    return FaithfulnessResult(PASS, f"all {len(verdicts)} claim(s) entailed", claims=verdicts)


# --------------------------------------------------------------------------- M2.B calibration
def is_unfaithful(label: str) -> bool:
    """The 'dangerous' class the judge must catch: contradicted OR unsupported."""
    return label in (CONTRADICTED, UNSUPPORTED)


def binary_faithfulness_metrics(pairs: list) -> dict:
    """Precision/recall of detecting the UNFAITHFUL class, collapsing
    contradicted+unsupported vs entailed. ``pairs`` = [(true_label, pred_label)].

    Recall is load-bearing: FN = a real unfaithful claim the judge called entailed
    (a hallucination waved through). Returns tp/fp/fn/tn + precision/recall/accuracy.
    Recall/precision are 1.0 by convention when their denominator is 0 (no positives
    / no predicted positives) so an all-entailed slice doesn't read as a failure."""
    tp = fp = fn = tn = 0
    for true_label, pred_label in pairs:
        t, p = is_unfaithful(true_label), is_unfaithful(pred_label)
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


def classify_claim(claim: str, source: str, client, *,
                   model: Optional[str] = None, logger=None) -> str:
    """Judge a single claim against a source and return its label — the primitive
    the gold-set calibration (M2.B) grades. Raises on API/parse failure."""
    return judge_claims([claim], source, client, model=model, logger=logger)[0].label
