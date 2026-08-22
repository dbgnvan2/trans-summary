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
        # A "passing" verdict for EITHER judge: the faithfulness judge's ENTAILED, the
        # theme judge's GROUNDED, or the key-terms semantic judge's CORRECT. (Without
        # the theme/key-terms labels here, `unfaithful` would list every verdict —
        # grounded ones included — in a theme/key-terms FAIL report.)
        return self.label in ("entailed", "grounded", "correct")


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
    skip_labels = {s.lower() for s in config.FAITHFULNESS_SKIP_LINE_LABELS}
    strip_prefixes = {s.lower() for s in config.FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES}
    # Strip markdown scaffolding — ``---``/fenced ```yaml front matter, heading
    # lines, bold-only label lines, and leading bold labels — via the SAME helper
    # the entity/name detector uses (single source of truth, P19). Without this, a
    # Title-Case topic/term label ("**Systems Biology and Cancer Niche Theory.**")
    # or a ```yaml metadata block (slug:/focus_keyword:/q:/a:) is extracted and
    # judged as an "unsupported" claim and false-BLOCKs the faithful artifact.
    from abstract_validation import _strip_scaffolding
    for raw_line in _strip_scaffolding(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # drop list markers, blockquote markers, and any residual bold field label
        line = re.sub(r"^\s*(?:[-*>]+\s*)+", "", line)
        line = line.replace("**", "").replace("__", "").strip()
        # skip a structured-artifact scaffolding / meta line ("Coverage / role:",
        # "Document:", "Key evidence:") — meta-commentary, not a source claim.
        label = line.split(":", 1)[0].strip().lower() if ":" in line else ""
        if label and label in skip_labels:
            continue
        # Strip a leading GENERIC field-label prefix ("Description: <claim>") so the
        # claim itself is judged — but ONLY for known scaffolding labels (config
        # allowlist). A non-allowlisted prefix (e.g. a fabricated "Stanford study:"
        # attribution) is LEFT IN PLACE so the judge sees and can flag it; stripping
        # an arbitrary pre-colon specific let a fabricated attribution ride through the
        # armed gate UNJUDGED (gate bypass; review H11 / P7 / P20).
        m_prefix = re.match(r"^([A-Za-z][^:\n]{0,40}):\s*", line)
        if m_prefix and m_prefix.group(1).strip().lower() in strip_prefixes:
            line = line[m_prefix.end():]
        # strip a leading list/theme enumerator ("1. ", "2) ") so a numbered theme
        # header doesn't split into a bare-number "1." fragment.
        line = re.sub(r"^\d+[.)]\s+", "", line).strip()
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


# --------------------------------------------------------------------------- chunked judging (long transcripts)
# A single batched judge call over a LONG source degrades attention, especially the
# middle of the transcript, and can near the context limit (gap #1). Instead, split the
# source into overlapping word-windows and judge each claim against the window it most
# lexically resembles; a claim that resembles no single window (a summary-level
# inference connecting material across the source) is judged against the FULL source.
_STOP_WORDS = {
    "about", "also", "among", "and", "are", "as", "at", "been", "being", "but",
    "can", "could", "for", "from", "had", "has", "have", "her", "his", "how",
    "into", "its", "not", "our", "out", "she", "that", "the", "their", "them",
    "they", "this", "was", "were", "what", "when", "which", "who", "will",
    "with", "would", "your",
}


def _significant_words(text: str) -> set:
    """Lowercased, stopword-free words of length >= 4 — the vocabulary used for
    lexical claim->window routing (a deterministic relevance proxy)."""
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP_WORDS}


def chunk_source(source: str, *, chunk_words: Optional[int] = None,
                 overlap_words: Optional[int] = None) -> list:
    """Split the source transcript into overlapping word-windows. Reuses the same
    windowing as the lexical validators (config.VALIDATION_CHUNK_SIZE/OVERLAP), read
    at call time so a test (or runtime) config change is honoured."""
    chunk_words = chunk_words or config.VALIDATION_CHUNK_SIZE
    overlap_words = overlap_words or config.VALIDATION_CHUNK_OVERLAP
    words = source.split()
    total = len(words)
    if total <= chunk_words:
        return [source]
    chunks = []
    start = 0
    while start < total:
        end = min(start + chunk_words, total)
        # merge a small trailing remainder into the prior window (no stub window)
        if 0 < total - end < chunk_words * 0.3:
            end = total
        chunks.append(" ".join(words[start:end]))
        if end >= total:
            break
        start = max(end - overlap_words, start + 1)
    return chunks


def route_claims_to_chunks(claims: list, chunks: list, min_overlap: float) -> tuple:
    """Return ``(routed, unrouted)``.

    ``routed`` maps window-index -> [claim-index] for claims whose source-anchored
    content lives entirely within ONE window. ``unrouted`` lists claim-indexes that
    must be judged against the FULL source: either the claim's significant words barely
    appear in the source (below ``min_overlap``), or they are SPREAD across windows — a
    cross-window summary-level inference no single window can fairly verify.

    Spread is detected structurally, not by a best-vs-second margin: a claim routes to a
    window only if that window contains EVERY significant word of the claim that appears
    anywhere in the source. A margin only catches a *balanced* split; an unbalanced
    split (5 words in window A, 3 in window B) still routes to the dominant window and
    drops the minority element from the judge's context, which can false-BLOCK a
    faithful abstraction (precision).
    """
    routed: dict = {}
    unrouted: list = []
    chunk_words = [_significant_words(c) for c in chunks]
    for ci, claim in enumerate(claims):
        cw = _significant_words(claim)
        if not cw:
            unrouted.append(ci)
            continue
        # The claim's significant words that appear somewhere in the source
        # ("source-anchored"). Per-chunk counts tell us where each is found.
        anchored: set = set()
        per_chunk: list = []
        for kw in chunk_words:
            hit = cw & kw
            per_chunk.append(len(hit))
            anchored |= hit
        if not anchored:
            # No significant word appears anywhere -> judge against the full source.
            unrouted.append(ci)
            continue
        best_idx = max(range(len(chunks)), key=lambda k: per_chunk[k])
        # Route only if the best window holds EVERY anchored word (no spread) AND the
        # claim is non-trivially present in the source (min_overlap floor on the
        # anchored fraction). Any anchored word outside the best window means the
        # claim's content spans windows -> full source.
        if per_chunk[best_idx] == len(anchored) and \
                (per_chunk[best_idx] / len(cw)) >= min_overlap:
            routed.setdefault(best_idx, []).append(ci)
        else:
            unrouted.append(ci)
    return routed, unrouted


def judge_claims_chunked(claims: list, source: str, client, *,
                         model: Optional[str] = None, logger=None) -> list:
    """Judge claims against bounded source windows (long transcripts), returning
    verdicts in the ORIGINAL claim order. Routed claims -> their best window;
    low-overlap claims -> the full source."""
    chunks = chunk_source(source)
    routed, unrouted = route_claims_to_chunks(
        claims, chunks, config.FAITHFULNESS_JUDGE_ROUTE_MIN_OVERLAP)
    verdicts: list = [None] * len(claims)
    for k, idxs in routed.items():
        sub = judge_claims([claims[i] for i in idxs], chunks[k], client,
                           model=model, logger=logger)
        for local, ci in enumerate(idxs):
            verdicts[ci] = sub[local]
    if unrouted:
        sub = judge_claims([claims[i] for i in unrouted], source, client,
                           model=model, logger=logger)
        for local, ci in enumerate(unrouted):
            verdicts[ci] = sub[local]
    # Fail-closed reassembly guard (P2/P14): a future routing or judge_claims change
    # that dropped/reordered a verdict would otherwise surface as an unhandled
    # AttributeError on None downstream — raise here so the gate maps it to ERROR.
    if len(verdicts) != len(claims) or any(v is None for v in verdicts):
        raise ValueError(
            f"chunked judge returned {sum(1 for v in verdicts if v is not None)}/"
            f"{len(claims)} verdicts — reassembly contract violated")
    return verdicts


def _should_chunk(source: str) -> bool:
    """Use the chunked path only for a genuinely long source; short transcripts are
    cheaply and accurately judged in one call."""
    return len(source.split()) >= config.FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS


# --------------------------------------------------------------------------- the judge
_JUDGE_INSTRUCTIONS = """\
You are a strict faithfulness auditor. You are given a SOURCE transcript and a \
numbered list of CLAIMS taken from a summary of that transcript. For EACH claim, \
decide whether the source supports it, using exactly one label:

- "entailed": the claim is directly stated in the source OR is a fair paraphrase, \
aggregation, generalization, or reasonable summary-level inference from the source. \
A summary legitimately abstracts, connects, and generalizes across the source — \
that is faithful, not a fabrication.
- "contradicted": the claim DIRECTLY conflicts with a specific fact stated in the \
source (a wrong name, date, number, relationship, or outcome — the source says X, \
the claim says not-X). A broader generalization or interpretation is NOT a \
contradiction; only a factual clash is.
- "unsupported": the claim asserts something the source neither states nor supports. \
This is the hallucination case, and it has TWO forms: (i) a fabricated concrete \
specific (a named person, place, date, quantity, or cited study absent from the \
source), AND (ii) an invented claim of substance — a specific conclusion, stance, \
recommendation, causal claim, or attribution — that has NO basis in the source (the \
source is silent on it, and it does not follow from what the source does say). Form \
(ii) counts even when the claim contains no proper noun.

Judge ONLY against the source; do not use outside knowledge. Default to "entailed" \
for thematic summaries, interpretations, and reasonable inferences that fairly \
reflect the source. Reserve "contradicted" for a direct factual clash.

The distinction that matters — apply this test:
- A summary that generalizes, groups, frames, or CONNECTS material whose elements \
are each present in the source is "entailed" — faithful abstraction, not \
fabrication. In particular, a claim that connects or relates two things is \
"entailed" when BOTH things appear in the source, EVEN IF the source never states \
the connection in those words (e.g. "connects this history to Bowen theory by \
introducing the DOS equation" is entailed when the history, Bowen theory, and the \
DOS equation are all in the source). Reasonable inference from grounded material is \
faithful.
- "unsupported" is for a claim whose core element or assertion is ABSENT from the \
source entirely — an invented fact, a cited study, or a specific conclusion / stance \
/ causal claim the source never makes and that does not follow from what it says \
(e.g. "attributes recovery to medication" when medication appears nowhere in the \
source). This holds even when the claim names no specific entity.

When unsure whether the source supports a claim built from grounded elements, prefer \
"entailed". Reserve "unsupported" for a claim introducing substance the source does \
not contain, and "contradicted" for a direct factual clash.

Return ONLY a JSON array, one object per claim, in order:
[{"index": 1, "label": "entailed|contradicted|unsupported", "rationale": "<= 20 words"}]
No prose before or after the JSON."""


def _cached_judge_content(instructions: str, source: str, tail: str) -> list:
    """Two-block user content: an [instructions + SOURCE] prefix marked as a cache
    breakpoint, followed by the small per-call tail (claims/themes). The two blocks
    concatenate to the EXACT single-string prompt the judge used before — the model
    sees identical text — but the constant transcript prefix is now cache-reusable, so
    it is not re-billed across the 4-6 judge calls per publish run (review H1). Before
    this split the varying claims sat inside the same block, so the cache breakpoint
    fell after them and never hit."""
    prefix = f"{instructions}\n\n=== SOURCE ===\n{source}\n\n"
    return [
        {"type": "text", "text": prefix, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": tail},
    ]


def build_judge_prompt(claims: list, source: str) -> list:
    numbered = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims))
    tail = f"=== CLAIMS ({len(claims)}) ===\n{numbered}\n"
    return _cached_judge_content(_JUDGE_INSTRUCTIONS, source, tail)


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


def _parse_judge_response(response_text: str, claims: list,
                          valid_labels: Optional[set] = None) -> list:
    """Map the judge's JSON verdicts back onto the claims by 1-based index. Every
    claim must receive a valid label; a missing/invalid verdict raises (-> ERROR),
    never defaults to a pass label (fail closed). ``valid_labels`` defaults to the
    faithfulness label set; the theme judge passes its own {grounded, ungrounded}."""
    valid = valid_labels if valid_labels is not None else _LABELS
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
        if label in valid:
            by_index[idx] = (label, str(obj.get("rationale", "")).strip())
    verdicts = []
    for i, claim in enumerate(claims, start=1):
        if i not in by_index:
            raise ValueError(f"judge returned no valid verdict for claim {i}")
        label, rationale = by_index[i]
        verdicts.append(ClaimVerdict(claim=claim, label=label, rationale=rationale))
    return verdicts


# Public names for cross-module reuse — the key-terms domain-semantic judge imports
# these to reuse the fail-closed parse + the cache-breakpoint prompt. The underscore
# names stay canonical (in-module call sites are unchanged); these aliases are the
# stable cross-module surface.
parse_judge_response = _parse_judge_response
cached_judge_content = _cached_judge_content


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
        if _should_chunk(source):
            # Long source: judge each claim against its most-relevant window (and
            # summary-level inference claims against the full source) — bounded
            # per-call attention instead of one giant call over the whole transcript.
            verdicts = judge_claims_chunked(claims, source, client, model=model, logger=log)
        else:
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


# ===========================================================================
# THEME GROUNDING JUDGE — a DIFFERENT check for interpretive artifacts.
# ===========================================================================
# Structural/interpretive THEMES legitimately interpret, generalize, and apply
# frameworks beyond the literal source, so the source-ENTAILMENT judge above
# false-flags them (confirmed empirically). The theme judge asks a different
# question: is the theme GROUNDED — does its subject matter actually appear in /
# follow from the transcript — rather than "is it literally stated?".
GROUNDED = "grounded"
UNGROUNDED = "ungrounded"
_THEME_LABELS = {GROUNDED, UNGROUNDED}

_THEME_JUDGE_INSTRUCTIONS = """\
You are auditing whether each THEME extracted from a transcript is GROUNDED in that
transcript. A theme is a synthesized, INTERPRETIVE summary — it legitimately
generalizes, names patterns, draws connections, and applies analytical frameworks
(e.g. "Bowen theory") to the source. That interpretation is its PURPOSE, so do NOT
penalize a theme for going beyond the literal wording or for being bold.

Judge ONLY whether the theme is grounded — whether the people, events, topics,
claims, and dynamics it describes actually appear in, or reasonably follow from, the
transcript:

- "grounded": the theme interprets, synthesizes, or draws conclusions from content
  that IS present in the transcript. A reasonable (even bold, framework-laden)
  reading of real material is grounded.
- "ungrounded": the theme is built on people, events, topics, or claims that are NOT
  in the transcript (fabricated subject matter), OR it asserts something the
  transcript directly contradicts, OR it is not a defensible reading of anything the
  source contains. A theme is ALSO ungrounded if — even when its general subject is
  grounded — it weaves in a fabricated CONCRETE SPECIFIC: a named person, institution,
  place, date, award, or cited study that does NOT appear in the source. A single
  fabricated specific makes the whole theme ungrounded.

Judge ONLY against the source; do not use outside knowledge. When the theme's
subject matter is present in the source and the interpretation is a fair reading —
and it introduces no fabricated concrete specific — label "grounded". Reserve
"ungrounded" for a theme whose substance the transcript does not contain OR that
injects an invented specific. Do not penalize a bold or framework-laden reading of
REAL material; but a fabricated name/date/institution is always ungrounded, however
grounded the surrounding narrative.

Return ONLY a JSON array, one object per theme, in order:
[{"index": 1, "label": "grounded|ungrounded", "rationale": "<= 20 words"}]
No prose before or after the JSON."""


def build_theme_judge_prompt(themes: list, source: str) -> list:
    numbered = "\n\n".join(
        f"{i + 1}. {t['name']}\n{t.get('description', '')}" for i, t in enumerate(themes)
    )
    tail = f"=== THEMES ({len(themes)}) ===\n{numbered}\n"
    return _cached_judge_content(_THEME_JUDGE_INSTRUCTIONS, source, tail)


def judge_themes(themes: list, source: str, client, *,
                 model: Optional[str] = None, logger=None) -> list:
    """Judge every theme against the source in ONE batched call -> ``ClaimVerdict``
    list (label in {grounded, ungrounded}, ``claim`` = the theme name). Raises on
    API/parse failure so the caller fails closed."""
    from transcript_utils import call_claude_with_retry

    model = model or config.THEME_JUDGE_MODEL
    message = call_claude_with_retry(
        client=client,
        model=model,
        messages=[{"role": "user", "content": build_theme_judge_prompt(themes, source)}],
        max_tokens=config.FAITHFULNESS_JUDGE_MAX_TOKENS,
        temperature=config.TEMP_STRICT,
        min_length=1,
        logger=logger or logging.getLogger("theme_judge"),
        timeout=config.TIMEOUT_DEFAULT,
    )
    names = [t["name"] for t in themes]
    return _parse_judge_response(message.content[0].text, names, valid_labels=_THEME_LABELS)


def judge_themes_artifact(themes_markdown: str, source: str, kind: str, client, *,
                          model: Optional[str] = None, logger=None) -> FaithfulnessResult:
    """Judge one themes artifact for GROUNDING against the source. Parses the themes
    via the M3 codec (so only real themes, not scaffolding, are judged), then labels
    each grounded/ungrounded. Any ungrounded theme -> FAIL naming it; a judge error
    or missing source -> ERROR (fail closed). No themes -> PASS."""
    log = logger or logging.getLogger("theme_judge")
    if not source or not source.strip():
        return FaithfulnessResult(ERROR, "source transcript missing — cannot verify themes")
    try:
        import artifact_contracts as ac
        obj = ac.codec("themes").parse_markdown(themes_markdown, kind)
        themes = obj["items"]
    except Exception as e:  # noqa: BLE001 — a codec/parse failure must fail closed
        log.error("Theme parse failed (fail-closed ERROR): %s", e, exc_info=True)
        return FaithfulnessResult(ERROR, f"theme parse error: {type(e).__name__}: {e}")
    if not themes:
        return FaithfulnessResult(PASS, "no themes to judge")
    try:
        verdicts = judge_themes(themes, source, client, model=model, logger=log)
    except Exception as e:  # noqa: BLE001 — judge failure fails closed, never passes
        log.error("Theme judge failed (fail-closed ERROR): %s", e, exc_info=True)
        return FaithfulnessResult(ERROR, f"theme judge error: {type(e).__name__}: {e}")
    ungrounded = [v for v in verdicts if v.label != GROUNDED]
    if ungrounded:
        first = ungrounded[0]
        return FaithfulnessResult(
            FAIL,
            f"{len(ungrounded)} of {len(verdicts)} theme(s) ungrounded; "
            f"first: {first.claim[:100]!r}",
            claims=verdicts,
        )
    return FaithfulnessResult(PASS, f"all {len(verdicts)} theme(s) grounded", claims=verdicts)


def classify_theme(theme: dict, source: str, client, *,
                   model: Optional[str] = None, logger=None) -> str:
    """Judge a single theme and return its grounding label — the calibration primitive."""
    return judge_themes([theme], source, client, model=model, logger=logger)[0].label
