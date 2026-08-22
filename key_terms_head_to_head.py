"""Claude-vs-<model> head-to-head calibration for the key-terms domain-semantic
judge (gap #4).

Builds a labeled set from a real run — the extracted key terms are the CORRECT
class; each term's definition swapped with a DIFFERENT term's is the INCORRECT
class — runs the judge over it, and reports precision/recall/accuracy on the
INCORRECT class. The judge clears for arming only if it meets
``config.KEY_TERMS_JUDGE_MIN_RECALL_INCORRECT`` / ``..._PRECISION_INCORRECT``.

This is a ONE-TIME validation activity (choose Claude vs a candidate second judge
for the domain-semantic layer), not a permanent pipeline step. Run it once per
candidate model and compare the reported metrics.

Usage:
    python key_terms_head_to_head.py --source <formatted.md> --terms <key-terms.md> \
        [--model claude-sonnet-4-6] [--limit N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import config
import key_terms_semantic_judge as kj


def build_labeled_set(terms: list) -> list:
    """Return [(term, definition, true_label)] — the real definitions are CORRECT,
    each term's definition cyclically swapped with the next term's is INCORRECT.

    A swap between two terms whose OWN definitions are near-duplicates (near-synonym
    terms) is AMBIGUOUS rather than clearly wrong — the judge reasonably calling it
    "correct" would pollute the recall-on-INCORRECT metric. Such swaps are skipped;
    add hand-authored plausible-but-wrong definitions for the hard-middle negatives
    the swap cannot produce."""
    from transcript_validate_consistency import keyword_overlap

    labeled = [(t, d, kj.CORRECT) for (t, d) in terms]
    n = len(terms)
    if n >= 2:
        for i, (t, own_def) in enumerate(terms):
            wrong_def = terms[(i + 1) % n][1]
            if keyword_overlap(own_def, wrong_def) >= 0.6:
                continue  # near-duplicate definitions -> ambiguous, not clearly wrong
            labeled.append((t, wrong_def, kj.INCORRECT))
    return labeled


def run_head_to_head(source: str, terms: list, client, model: str,
                     logger=None) -> dict:
    """Run the judge over the labeled set and return metrics + the paired labels.
    Raises on an empty term set — no evidence must never read as a perfect judge."""
    if not terms:
        raise ValueError("no key terms to calibrate against")
    labeled = build_labeled_set(terms)
    verdicts = kj.judge_key_terms(
        [(t, d) for (t, d, _l) in labeled], source, client, model=model, logger=logger)
    pairs = [(true_label, v.label)
             for (true_label, v) in zip([l for (_t, _d, l) in labeled], verdicts)]
    metrics = kj.binary_key_terms_metrics(pairs)
    metrics["pairs"] = pairs
    metrics["n"] = len(pairs)
    metrics["missed"] = [t for (t, _d, l), v in zip(labeled, verdicts)
                         if l == kj.INCORRECT and v.label == kj.CORRECT]
    return metrics


def main() -> int:
    ap = argparse.ArgumentParser(description="Key-terms domain-semantic judge calibration.")
    ap.add_argument("--source", required=True, help="Transcript (formatted.md) path.")
    ap.add_argument("--terms", required=True, help="key-terms.md path.")
    ap.add_argument("--model", default=config.KEY_TERMS_JUDGE_MODEL)
    ap.add_argument("--limit", type=int, default=0,
                    help="Cap the number of real terms used (0 = all).")
    args = ap.parse_args()

    source = Path(args.source).expanduser().read_text(encoding="utf-8", errors="replace")
    terms = kj.parse_key_terms_artifact(
        Path(args.terms).expanduser().read_text(encoding="utf-8", errors="replace"))
    if args.limit:
        terms = terms[: args.limit]
    if not terms:
        print("No key terms parsed — cannot calibrate.", file=sys.stderr)
        return 2

    from transcript_utils import resolve_anthropic_key
    api_key = resolve_anthropic_key()
    if not api_key:
        print("No Anthropic API key resolved.", file=sys.stderr)
        return 2
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    print(f"Judging {len(terms)} real terms + {len(terms)} swapped (incorrect) with model {args.model} ...")
    metrics = run_head_to_head(source, terms, client, args.model)

    print("\n=== Key-terms domain-semantic judge — head-to-head ===")
    print(f"model     : {args.model}")
    print(f"examples  : {metrics['n']}")
    print(f"tp={metrics['tp']} fp={metrics['fp']} fn={metrics['fn']} tn={metrics['tn']}")
    print(f"recall    : {metrics['recall']:.3f}  (min {config.KEY_TERMS_JUDGE_MIN_RECALL_INCORRECT:.2f})")
    print(f"precision : {metrics['precision']:.3f}  (min {config.KEY_TERMS_JUDGE_MIN_PRECISION_INCORRECT:.2f})")
    print(f"accuracy  : {metrics['accuracy']:.3f}")
    clears = (metrics["recall"] >= config.KEY_TERMS_JUDGE_MIN_RECALL_INCORRECT
              and metrics["precision"] >= config.KEY_TERMS_JUDGE_MIN_PRECISION_INCORRECT)
    print(f"\nCLEARS arming thresholds: {'YES' if clears else 'NO'}")
    if metrics["fn"]:
        print("\nMissed (false-negative) swaps — wrong definitions the judge called correct:")
        for t in metrics["missed"]:
            print(f"  [MISSED] {t!r}")
    return 0 if clears else 1


if __name__ == "__main__":
    raise SystemExit(main())
