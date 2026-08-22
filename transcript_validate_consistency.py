#!/usr/bin/env python3
"""
Cross-artifact consistency check for a trans-summary output folder.

Deterministic, no API calls. Catches the error class that per-artifact
validators miss because every artifact is checked against the TRANSCRIPT but
never against each other (and never against the transcript's domain density).

Checks
------
1. Sparsity vs density — a content-derived artifact that is empty/near-empty
   while the transcript is clearly dense in that artifact's domain (the confirmed
   "empty Bowen references on a Bowen-dense talk" bug).
2. Key-term grounding — every key term should appear in the transcript (a
   lightweight redundancy against hallucinated terms).
3. Cross-artifact keyword overlap — informational: how much the abstract shares
   vocabulary with the extracted topics, and whether topics cover the transcript.

Usage
-----
    python transcript_validate_consistency.py --project-dir "<output folder>"
    python transcript_validate_consistency.py --project-dir "<output folder>" --output /tmp/consistency.md

The transcript is auto-resolved from the folder: prefer " - formatted.md", then
" - yaml.md", then the largest "*.txt".
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Keep in sync with extraction_pipeline._BOWEN_CONCEPT_PATTERN.
_BOWEN_TERMS = (
    "differentiation", "undifferentiation", "triangle", "triangles", "triangling",
    "triangulation", "fusion", "cutoff", "projection", "sibling position",
    "multigenerational", "togetherness", "individuality", "emotional system",
    "emotional process", "emotional unit", "relationship system", "societal",
    "anxiety", "reactivity", "reactive", "systems thinking", "feeling system",
    "intellectual system", "symbiosis", "symbiotic",
)

# Artifact suffix -> (label, parser kind)
ARTIFACTS = {
    " - bowen-references.md": ("Bowen references", "bowen"),
    " - emphasis-scored.md": ("Emphasis (scored)", "emphasis"),
    " - key-terms.md": ("Key terms", "terms"),
    " - topics.md": ("Topics", "topics"),
    " - abstract-generated.md": ("Abstract", "abstract"),
}

# Minimum meaningful size: below this, a content-derived artifact is "empty".
MIN_WORDS_ABSTRACT = 30


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, drop hyphens/apostrophes for matching."""
    t = str(text).lower()
    t = t.replace("-", " ").replace("'", " ").replace("\u2019", " ")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def strip_frontmatter(text: str) -> str:
    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    return text[m.end():] if m else text


def count_bowen_occurrences(text: str) -> int:
    norm = normalize(text)
    total = 0
    for term in _BOWEN_TERMS:
        total += norm.count(normalize(term))
    return total


def distinct_bowen_terms(text: str) -> set:
    norm = normalize(text)
    return {t for t in _BOWEN_TERMS if normalize(t) in norm}


def resolve_transcript(project_dir: Path) -> Path | None:
    for suffix in (" - formatted.md", " - yaml.md"):
        hits = sorted(project_dir.glob(f"*{suffix}"))
        if hits:
            return hits[0]
    # Fall back to the largest .txt (the raw/validated transcript).
    txts = sorted(project_dir.glob("*.txt"), key=lambda p: p.stat().st_size, reverse=True)
    return txts[0] if txts else None


def find_artifact(project_dir: Path, suffix: str) -> Path | None:
    hits = sorted(project_dir.glob(f"*{suffix}"))
    return hits[0] if hits else None


def count_items(text: str, kind: str) -> int:
    """Count 'items' in an artifact by its known markdown shape."""
    text = strip_frontmatter(text)
    if kind in ("bowen", "terms", "topics"):
        # "### Concept/Term/Topic" headers (the on-disk format).
        n = len(re.findall(r"^###\s", text, re.MULTILINE))
        if n:
            return n
        # Older blockquote format: "> **Concept:** \"quote\""
        return len(re.findall(r"^>\s*\*\*", text, re.MULTILINE))
    if kind == "emphasis":
        n = len(re.findall(r"(?m)^\s*(?:\[|Explicit|Implicit|-|\*|\d+\.)", text))
        if n:
            return n
        return len(re.findall(r"Rank:\s*\d+%", text))
    return 0


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", strip_frontmatter(text)))


def parse_key_terms(text: str) -> list[str]:
    """Extract key-term names from the key-terms artifact."""
    text = strip_frontmatter(text)
    terms: list[str] = []
    # "### Term Name" blocks
    for m in re.findall(r"^###\s+([^\n]+)", text, re.MULTILINE):
        t = m.strip()
        if t and t.lower() not in ("key terms",):
            terms.append(t)
    if terms:
        return terms
    # "**Term**: definition" fallback
    for m in re.findall(r"^\*\*([^*]+)\*\*\s*[:|-]", text, re.MULTILINE):
        terms.append(m.strip())
    return terms


def parse_topics(text: str) -> list[str]:
    """Extract topic titles from the topics artifact."""
    text = strip_frontmatter(text)
    out = []
    for m in re.findall(r"^###\s+([^\n]+)", text, re.MULTILINE):
        t = m.strip()
        if t and t.lower() not in ("topics", "key topics"):
            out.append(t)
    return out


def keyword_overlap(a: str, b: str) -> float:
    """Fraction of a's meaningful keywords present in b (0..1)."""
    stop = {
        "about", "also", "among", "analysis", "and", "are", "as", "at", "be", "by",
        "can", "discussion", "examining", "examination", "exploration", "explores",
        "for", "from", "how", "in", "including", "into", "is", "it", "its", "like",
        "models", "of", "on", "or", "presentation", "process", "research", "showing",
        "systems", "that", "the", "their", "these", "this", "to", "with",
    }
    aw = {w for w in re.findall(r"[a-zA-Z]{4,}", a.lower()) if w not in stop}
    if not aw:
        return 0.0
    bw = set(re.findall(r"[a-zA-Z]{4,}", b.lower()))
    return sum(1 for w in aw if w in bw) / len(aw)


def run(project_dir: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (fails, warns, info)."""
    fails: list[str] = []
    warns: list[str] = []
    info: list[str] = []

    transcript_path = resolve_transcript(project_dir)
    if transcript_path is None:
        fails.append("No transcript found in folder (expected ' - formatted.md'/' - yaml.md'/'.txt').")
        return fails, warns, info

    transcript = strip_frontmatter(transcript_path.read_text(encoding="utf-8", errors="replace"))
    tw = word_count(transcript)
    info.append(f"Transcript: {transcript_path.name} ({tw} words)")

    # ---- Bowen density signal ------------------------------------------------
    bowen_occ = count_bowen_occurrences(transcript)
    bowen_terms = distinct_bowen_terms(transcript)
    info.append(f"Bowen signal: {bowen_occ} term occurrences across {len(bowen_terms)} distinct concepts "
                f"({', '.join(sorted(bowen_terms))})")

    # ---- Sparsity vs density ------------------------------------------------
    bowen_path = find_artifact(project_dir, " - bowen-references.md")
    if bowen_path is not None:
        n = count_items(bowen_path.read_text(encoding="utf-8", errors="replace"), "bowen")
        if n == 0 and bowen_occ >= 10:
            fails.append(
                f"Bowen references are EMPTY ({n} items) but the transcript is Bowen-dense "
                f"({bowen_occ} term occurrences across {len(bowen_terms)} concepts). "
                f"Likely the attribution filter over-dropped — check {bowen_path.name}."
            )
        elif n == 0:
            warns.append(f"Bowen references are empty ({n} items) with only {bowen_occ} Bowen-term occurrences.")
        else:
            info.append(f"Bowen references: {n} items.")
    else:
        warns.append("No bowen-references.md artifact present.")

    emph_path = find_artifact(project_dir, " - emphasis-scored.md")
    if emph_path is not None:
        n = count_items(emph_path.read_text(encoding="utf-8", errors="replace"), "emphasis")
        if n == 0 and tw >= 500:
            warns.append(f"Emphasis is empty ({n} items) on a {tw}-word transcript.")
        else:
            info.append(f"Emphasis: {n} items.")
    else:
        warns.append("No emphasis-scored.md artifact present.")

    terms_path = find_artifact(project_dir, " - key-terms.md")
    if terms_path is not None:
        n = count_items(terms_path.read_text(encoding="utf-8", errors="replace"), "terms")
        if n == 0 and tw >= 500:
            warns.append(f"Key terms empty ({n} items) on a {tw}-word transcript.")
        else:
            info.append(f"Key terms: {n} items.")
    else:
        info.append("No key-terms.md artifact present (stage skipped?).")

    topics_path = find_artifact(project_dir, " - topics.md")
    if topics_path is not None:
        n = count_items(topics_path.read_text(encoding="utf-8", errors="replace"), "topics")
        if n == 0:
            warns.append("Topics artifact present but empty.")
        else:
            info.append(f"Topics: {n} topics.")
    else:
        info.append("No topics.md artifact present (stage skipped?).")

    abstract_path = find_artifact(project_dir, " - abstract-generated.md")
    if abstract_path is not None:
        w = word_count(abstract_path.read_text(encoding="utf-8", errors="replace"))
        if w < MIN_WORDS_ABSTRACT:
            warns.append(f"Abstract is only {w} words (< {MIN_WORDS_ABSTRACT}).")
        else:
            info.append(f"Abstract: {w} words.")
    else:
        info.append("No abstract-generated.md artifact present (stage skipped?).")

    # ---- Key-term grounding (light) -----------------------------------------
    if terms_path is not None:
        terms_text = terms_path.read_text(encoding="utf-8", errors="replace")
        norm_t = normalize(transcript)
        missing = []
        for term in parse_key_terms(terms_text):
            # ground on the best alias part (slash-joined aliases never appear verbatim)
            parts = [p.strip() for p in re.split(r"\s*/\s*", term) if p.strip()] or [term]
            if not any(normalize(p) in norm_t for p in parts):
                missing.append(term)
        if missing:
            fails.append(f"{len(missing)} key term(s) not found in transcript: {', '.join(missing)}")
        else:
            info.append("All key terms grounded in transcript.")

    # ---- Cross-artifact keyword overlap (informational) ---------------------
    if topics_path is not None and abstract_path is not None:
        topics = parse_topics(topics_path.read_text(encoding="utf-8", errors="replace"))
        abstract = abstract_path.read_text(encoding="utf-8", errors="replace")
        if topics:
            top_overlap = max(
                keyword_overlap(t, abstract) for t in topics
            )
            info.append(f"Abstract↔topics max keyword overlap: {top_overlap:.2f}")
            if top_overlap < 0.05:
                warns.append("Abstract shares almost no vocabulary with any extracted topic — may not reflect them.")
    if topics_path is not None:
        topics = parse_topics(topics_path.read_text(encoding="utf-8", errors="replace"))
        uncovered = [t for t in topics if keyword_overlap(t, transcript) < 0.05]
        if uncovered:
            warns.append(f"{len(uncovered)} topic(s) weakly grounded in transcript: {', '.join(uncovered)}")

    return fails, warns, info


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-artifact consistency check for a trans-summary folder.")
    ap.add_argument("--project-dir", required=True, help="Path to one transcript output folder.")
    ap.add_argument("--output", help="Write markdown report to this path (default: stdout).")
    args = ap.parse_args()

    project_dir = Path(args.project_dir).expanduser()
    if not project_dir.is_dir():
        print(f"Not a directory: {project_dir}", file=sys.stderr)
        return 2

    fails, warns, info = run(project_dir)

    lines = [f"# Cross-Artifact Consistency: {project_dir.name}", ""]
    lines.append(f"## Result: {'FAIL' if fails else ('WARN' if warns else 'PASS')}")
    lines.append("")
    if fails:
        lines.append("## Fails")
        lines += [f"- {f}" for f in fails]
        lines.append("")
    if warns:
        lines.append("## Warnings")
        lines += [f"- {w}" for w in warns]
        lines.append("")
    lines.append("## Detail")
    lines += [f"- {i}" for i in info]
    report = "\n".join(lines) + "\n"

    if args.output:
        out = Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"Wrote report: {out}")
    else:
        print(report)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
