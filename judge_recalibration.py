#!/usr/bin/env python3
"""Run the judge calibration for one model + effort and save the results (JC.0).

LIVE: spends Anthropic API. Each run reports the gold-set metrics for the
faithfulness and theme judges, the real-abstract checks, the injected-fabrication
check, and (optionally) every claim verdict on the prose_real artifacts, plus the
cost taken from logs/token_usage.csv.

    .venv/bin/python judge_recalibration.py --model claude-sonnet-5-5 --effort medium \
        --repeats 3 --prose-real --out docs/calibration/sonnet55_medium.json

Spec:  docs/plan_judge_recalibration_sonnet55_2026-10-10.md#JC.0
Tests: tests/test_judge_recalibration_jc.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import config
import faithfulness_judge as fj

FIX = Path(__file__).resolve().parent / "tests" / "fixtures"
FAITH_GOLD = FIX / "faithfulness_gold" / "gold.json"
THEME_GOLD = FIX / "theme_gold" / "gold.json"
PROSE_REAL = FIX / "prose_real"
PROSE_SUFFIXES = (" - abstract-generated.md", " - summary-generated.md", " - overview.md", " - blog.md")

# (label, source, artifact, expected status, a word the FAIL must name)
_DG = FIX / "dave_g_test2"
_RB = FIX / "roots_bowen_test"
_WR = FIX / "where_roots" / "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"
REAL_ABSTRACTS = [
    ("roots_bowen", _RB / "formatted.md", _RB / "abstract-generated.md", "PASS", None),
    ("where_roots", _WR / f"{_WR.name} - formatted.md", _WR / f"{_WR.name} - abstract-generated.md",
     "FAIL", "Malorni"),
    ("dave_g", _DG / "formatted.md", _DG / "abstract-generated.md", "FAIL", "nubbin"),
]


def faithfulness_gold(client, model: str) -> dict:
    gold = json.loads(FAITH_GOLD.read_text(encoding="utf-8"))
    sources = {k: (FIX / v).read_text(encoding="utf-8") for k, v in gold["sources"].items()}
    by_source = defaultdict(list)
    for case in gold["cases"]:
        by_source[case["source"]].append(case)
    rows, pairs = [], []
    for sid, group in by_source.items():
        verdicts = fj.judge_claims([c["claim"] for c in group], sources[sid], client, model=model)
        for case, v in zip(group, verdicts):
            pairs.append((case["label"], v.label))
            rows.append({"id": case["id"], "truth": case["label"], "pred": v.label,
                         "miss": fj.is_unfaithful(case["label"]) != fj.is_unfaithful(v.label),
                         "rationale": v.rationale, "claim": case["claim"]})
    return {"metrics": fj.binary_faithfulness_metrics(pairs), "rows": rows}


def real_abstracts(client, model: str) -> list:
    out = []
    for label, src, art, expect, must in REAL_ABSTRACTS:
        r = fj.judge_artifact(art.read_text(encoding="utf-8"), src.read_text(encoding="utf-8"),
                              client, model=model)
        flagged = [c.claim for c in r.unfaithful]
        ok = r.status == expect and (must is None or any(must in c for c in flagged))
        out.append({"artifact": label, "status": r.status, "expect": expect, "ok": ok,
                    "flagged": flagged})
    return out


def injected_fabrication(client, model: str) -> dict:
    src = (_RB / "formatted.md").read_text(encoding="utf-8")
    clean = (_RB / "abstract-generated.md").read_text(encoding="utf-8").rstrip()
    text = clean + (" The webinar was funded by a 2021 grant from the "
                    "Vienna Institute for Family Systems.")
    r = fj.judge_artifact(text, src, client, model=model)
    caught = r.status == "FAIL" and any("Vienna" in c.claim or "grant" in c.claim for c in r.unfaithful)
    return {"status": r.status, "caught": caught}


def theme_gold(client, model: str) -> dict:
    import artifact_contracts as ac
    gold = json.loads(THEME_GOLD.read_text(encoding="utf-8"))
    rows = []
    for ga in gold["grounded_artifacts"]:
        src = (FIX / gold["sources"][ga["source"]]).read_text(encoding="utf-8")
        text = (FIX / ga["dir"] / f"{ga['suffix']}.md").read_text(encoding="utf-8")
        items = fj.with_theme_evidence(ac.codec("themes").parse_markdown(text, ga["kind"])["items"], text)
        for t, v in zip(items, fj.judge_themes(items, src, client, model=model)):
            rows.append({"truth": "grounded", "pred": v.label, "name": t["name"]})
    for ut in gold["ungrounded_themes"]:
        src = (FIX / gold["sources"][ut["source"]]).read_text(encoding="utf-8")
        theme = {k: ut[k] for k in ("name", "description", "evidence") if k in ut}
        v = fj.judge_themes([theme], src, client, model=model)[0]
        rows.append({"truth": "ungrounded", "pred": v.label, "name": ut["name"]})
    ung = fj.UNGROUNDED
    tp = sum(r["truth"] == ung and r["pred"] == ung for r in rows)
    fp = sum(r["truth"] != ung and r["pred"] == ung for r in rows)
    fn = sum(r["truth"] == ung and r["pred"] != ung for r in rows)
    return {"metrics": {"tp": tp, "fp": fp, "fn": fn,
                        "recall": tp / (tp + fn) if tp + fn else 1.0,
                        "precision": tp / (tp + fp) if tp + fp else 1.0},
            "rows": rows}


def prose_real(client, model: str) -> dict:
    """{artifact path: {claim: label}} for every prose artifact in prose_real."""
    out = {}
    for talk in sorted(p for p in PROSE_REAL.iterdir() if p.is_dir()):
        src = talk / f"{talk.name} - formatted.md"
        if not src.exists():
            continue
        source = src.read_text(encoding="utf-8")
        for suffix in PROSE_SUFFIXES:
            art = talk / f"{talk.name}{suffix}"
            if not art.exists():
                continue
            claims = fj.extract_claims(art.read_text(encoding="utf-8"), source=source)
            if not claims:
                continue
            if fj._should_chunk(source):
                verdicts = fj.judge_claims_chunked(claims, source, client, model=model)
            else:
                verdicts = fj.judge_claims(claims, source, client, model=model)
            out[f"{talk.name}{suffix}"] = {v.claim: v.label for v in verdicts}
    return out


def passes_bars(run: dict) -> bool:
    f, t = run["faithfulness"]["metrics"], run["themes"]["metrics"]
    return (f["recall"] >= config.FAITHFULNESS_MIN_RECALL_UNFAITHFUL
            and f["precision"] >= config.FAITHFULNESS_MIN_PRECISION_UNFAITHFUL
            and t["recall"] >= config.THEME_JUDGE_MIN_RECALL_UNGROUNDED
            and t["precision"] >= config.THEME_JUDGE_MIN_PRECISION_UNGROUNDED
            and all(a["ok"] for a in run["real_abstracts"])
            and run["injected"]["caught"])


def flips(runs: list) -> list:
    """Gold cases whose pass/fail verdict differs between repeated runs (JC.4).
    For faithfulness only the class counts (entailed vs not): contradicted <->
    unsupported both block, so a change between them is not a flip."""
    seen = defaultdict(set)
    for run in runs:
        for r in run["faithfulness"]["rows"]:
            seen[("faithfulness", r["id"])].add(
                "unfaithful" if fj.is_unfaithful(r["pred"]) else "entailed")
        for i, r in enumerate(run["themes"]["rows"]):
            seen[("themes", f"{i}:{r['name'][:40]}")].add(r["pred"])
        for a in run["real_abstracts"]:
            seen[("real", a["artifact"])].add(a["status"])
    return [{"set": k[0], "case": k[1], "labels": sorted(v)} for k, v in seen.items() if len(v) > 1]


class _ParseRetryCounter:
    """Counts the judges' "not valid JSON … asking again" warnings (JC.4)."""

    def __init__(self):
        import logging
        self.count = 0
        outer = self

        class _H(logging.Handler):
            def emit(self, record):
                if "not valid JSON" in record.getMessage():
                    outer.count += 1
        self.handler = _H()
        for name in ("faithfulness_judge", "theme_judge"):
            logging.getLogger(name).addHandler(self.handler)


def _usage_rows() -> list:
    path = Path(config.LOGS_DIR) / "token_usage.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def _cost(rows: list) -> float:
    total = 0.0
    for row in rows:
        try:
            total += float(row[-1])
        except (ValueError, IndexError):
            continue
    return round(total, 4)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=config.FAITHFULNESS_JUDGE_MODEL)
    ap.add_argument("--effort", default=None, choices=[None, *config.settings.EFFORT_CHOICES])
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--prose-real", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    from transcript_utils import get_anthropic_client, resolve_anthropic_key
    key = resolve_anthropic_key()
    if not key:
        print("No Anthropic API key found.", file=sys.stderr)
        return 2
    client = get_anthropic_client(key)
    config.JUDGE_EFFORT = args.effort  # the judges send config.JUDGE_EFFORT

    before = len(_usage_rows())
    retries = _ParseRetryCounter()
    runs = []
    for i in range(args.repeats):
        run = {"faithfulness": faithfulness_gold(client, args.model),
               "real_abstracts": real_abstracts(client, args.model),
               "injected": injected_fabrication(client, args.model),
               "themes": theme_gold(client, args.model)}
        run["passes_bars"] = passes_bars(run)
        runs.append(run)
        f, t = run["faithfulness"]["metrics"], run["themes"]["metrics"]
        print(f"run {i + 1}/{args.repeats}: faithfulness recall={f['recall']:.2f} "
              f"precision={f['precision']:.2f} | themes recall={t['recall']:.2f} "
              f"precision={t['precision']:.2f} | real abstracts "
              f"{sum(a['ok'] for a in run['real_abstracts'])}/{len(run['real_abstracts'])} | "
              f"injected caught={run['injected']['caught']} | bars={'PASS' if run['passes_bars'] else 'FAIL'}")
        for r in run["faithfulness"]["rows"]:
            if r["miss"]:
                print(f"   MISS {r['id']:5} truth={r['truth']:12} pred={r['pred']:12} {r['claim'][:70]}")
        for r in run["themes"]["rows"]:
            if r["truth"] != r["pred"]:
                print(f"   THEME MISS truth={r['truth']:10} pred={r['pred']:10} {r['name'][:60]}")
    result = {"model": args.model, "effort": args.effort, "repeats": args.repeats,
              "runs": runs, "flips": flips(runs)}
    if args.prose_real:
        result["prose_real"] = prose_real(client, args.model)
    result["cost_usd"] = _cost(_usage_rows()[before:])
    result["parse_retries"] = retries.count
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"flips across runs: {len(result['flips'])}; malformed replies retried: "
          f"{result['parse_retries']}; cost ${result['cost_usd']}; saved {out}")
    return 0 if all(r["passes_bars"] for r in runs) and not result["flips"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
