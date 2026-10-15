#!/usr/bin/env python3
"""RS.6 measurement: after a draft fails the faithfulness check, does revising the
flagged sentences pass the check more often than rewriting with the claims as
feedback?

Cases are drafts that failed every try in an end-to-end run (public talks only).
Each case: the kept draft is judged again to get its current flagged claims; then
each trial makes one retry by each method, saves it where the stage saves it and
runs the stage's own check. The retry functions are the ones the stage itself
builds (captured from `summarize_transcript` / `generate_structured_abstract`), so
the measurement uses the production prompts, models and limits.

Usage:
  .venv/bin/python docs/calibration/2026-10-14_revise_flagged/measure_revise.py \
      --scratch <dir holding e2e_runN/> --out <results.txt> [--trials 5 3]

Spec: docs/plan_run_safe_2026-10-14.md#RS.6
"""
import argparse
import csv
import difflib
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import extraction_pipeline as ep  # noqa: E402

CASES = [
    ("e2e_run8", "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13", "overview"),
    ("e2e_run7", "Beautiful Boy Review - Kathleen Kerr - 2023-02-16", "abstract"),
    ("e2e_run2", "Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25",
     "abstract"),
]


class _Stop(Exception):
    pass


def overview_callables(stem, logger):
    """generate(feedback), revise(draft, claims), write(text) exactly as the overview
    stage builds them, plus the stage's check."""
    got = {}

    def capture(what, base_name, suffix, lg, generate, write, precheck=None,
                advisory=False, revise=None):
        got.update(generate=generate, write=write, revise=revise)
        return True
    original = ep._generate_until_faithful
    ep._generate_until_faithful = capture
    try:
        ep.summarize_transcript(f"{stem}{config.SUFFIX_YAML}", config.settings.DEFAULT_MODEL,
                                "Family Systems", "General public", True, True, True, True,
                                False, logger=logger)
    finally:
        ep._generate_until_faithful = original
    check = lambda: ep._faithfulness_precheck(stem, config.SUFFIX_OVERVIEW, logger)  # noqa: E731
    return got["generate"], got["revise"], got["write"], check


def abstract_callables(stem, logger):
    """The abstract stage's generate and revise calls (same arguments), and its check."""
    got = {}

    def capture(ai, client, model=None, system=None, feedback_claims=None):
        got.update(ai=ai, client=client, model=model, system=system)
        raise _Stop()
    original = ep.abstract_pipeline.generate_abstract
    ep.abstract_pipeline.generate_abstract = capture
    try:
        ep.generate_structured_abstract(stem, logger, model=config.settings.AUX_MODEL)
    finally:
        ep.abstract_pipeline.generate_abstract = original
    path = config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_ABSTRACT_GEN}"

    def generate(feedback):
        return original(got["ai"], got["client"], model=got["model"], system=got["system"],
                        feedback_claims=feedback)

    def revise(draft, claims):
        return ep._revise_flagged("abstract", draft, claims, model=got["model"],
                                  system=got["system"], logger=logger, min_length=150,
                                  max_words=config.ABSTRACT_HARD_MAX_WORDS - 1,
                                  word_limits="soft").strip()

    def write(text):
        path.write_text(text, encoding="utf-8")
    return generate, revise, write, lambda: ep._abstract_gate_precheck(stem, logger)


def changed_share(a, b):
    return 1 - difflib.SequenceMatcher(None, a.split(), b.split()).ratio()


def cost_since(start):
    total = 0.0
    with open(ROOT / "logs" / "token_usage.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["Timestamp"] >= start:
                total += float(row["Estimated Cost ($)"] or 0)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--trials", nargs=2, type=int, default=[5, 3],
                    help="trials per method: overview, abstract")
    ap.add_argument("--model", default="claude-sonnet-5-5",
                    help="main model, as scripts/e2e_run.py sets it (the overview's model)")
    ap.add_argument("--cases", default="", help="comma-separated kinds to run (overview,abstract)")
    args = ap.parse_args()
    config.settings.set_default_model(args.model)  # not saved to runtime_settings.json
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    root = args.scratch / "rs6_measure" / "projects"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    config.PROJECTS_DIR = root
    logging.basicConfig(filename=args.out.with_suffix(".log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("rs6_measure")
    out = [f"RS.6 measurement {started}; models main={config.settings.DEFAULT_MODEL} "
           f"aux={config.settings.AUX_MODEL}", ""]
    totals = {"revise": [0, 0], "rewrite": [0, 0]}
    for run, stem, kind in CASES:
        if args.cases and kind not in args.cases.split(","):
            continue
        shutil.copytree(args.scratch / run / "projects" / stem, root / stem)
        suffix = config.SUFFIX_OVERVIEW if kind == "overview" else config.SUFFIX_ABSTRACT_GEN
        draft = (root / stem / f"{stem}{suffix}").read_text(encoding="utf-8")
        get = overview_callables if kind == "overview" else abstract_callables
        generate, revise, write, check = get(stem, logger)
        write(draft)
        status, claims = check()
        out.append(f"== {run} {kind}: {stem}")
        out.append(f"   kept draft ({len(draft.split())} words) judged again: {status}; "
                   f"claims: {claims}")
        if status != "fail":
            out.append("   skipped: the kept draft has no flagged claim now")
            continue
        trials = args.trials[0] if kind == "overview" else args.trials[1]
        for method in ("revise", "rewrite"):
            for t in range(1, trials + 1):
                try:
                    text = revise(draft, claims) if method == "revise" else generate(claims)
                except Exception as e:  # noqa: BLE001 - recorded, not raised
                    out.append(f"   {method} {t}: ERROR {type(e).__name__}: {e}")
                    continue
                write(text)
                echoed = [c for c in claims if c in text]
                st, issues = ("fail", echoed) if echoed else check()
                totals[method][0] += st == "pass"
                totals[method][1] += 1
                out.append(f"   {method} {t}: {st:5} words={len(text.split())} "
                           f"changed={changed_share(draft, text):.0%} "
                           f"{'echoed ' if echoed else ''}claims={issues}")
        write(draft)
        out.append("")
    for method, (passed, n) in totals.items():
        out.append(f"{method}: {passed}/{n} passed the check on one retry")
    out.append(f"cost: ${cost_since(started):.2f} (token log since {started})")
    args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
