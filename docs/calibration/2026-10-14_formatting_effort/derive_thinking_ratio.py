"""Derive config.FORMATTING_THINKING_RATIO / _MAX from logged Format runs (no API calls).

The ratio is defined the way the code uses it. T is the transcript estimate
(transcript_utils.estimate_token_count of the footer-stripped source). The cost estimate
assumes output = T x (1 + RATIO); the single-pass length check and the "may be cut off"
warning assume output = T x (FORMATTING_OUTPUT_EXPANSION + RATIO). So per run:
    cost_ratio   = output_tokens / T - 1
    length_ratio = output_tokens / T - FORMATTING_OUTPUT_EXPANSION
How the 2026-10-11 values (3.5 / 5.0) were computed was not recorded; this script
re-computes those runs too ("high_round2") with the same definitions.

Inputs:
- "medium": results_medium_*.json next to this script (output_tokens per run).
- "high_round2", "high_e2e" and "medium_e2e" (only with --token-log): logs/token_usage.csv
  (gitignored, cleared by Archive Logs; the JSON keeps a copy of the rows used).
  high_round2 = the six Sonnet runs of docs/calibration/2026-10-11_formatting_haiku/
  results_round2.json, whose token counts are only in the log (2026-10-11 22:30-23:08).
  high_e2e / medium_e2e = GUI or e2e-runner Format calls of the same talks as "medium",
  before / since Format moved to "medium" (commit cc87ae1), found by the size of their
  cached input. Compare medium_e2e with FORMATTING_THINKING_RATIO_MAX.
The config ratio is cost_ratio (typical) and length_ratio (maximum); thinking_ratio
(output minus the formatted text) is shown for comparison only.
- SOURCE files: the raw transcripts. A source matches a run when its name starts with the
  run's file name (without "_validated.txt") and its footer-stripped word count equals
  the run's raw_words. A run with no matching source stops the script.

Usage: python derive_thinking_ratio.py [--token-log logs/token_usage.csv] SOURCE [SOURCE...]
Writes thinking_ratio.json next to this script.
"""
import csv
import glob
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
import config  # noqa: E402
import formatting_pipeline as fp  # noqa: E402
import transcript_utils as tu  # noqa: E402

MODEL = "claude-sonnet-5-5"
ROUND2 = ROOT / "docs/calibration/2026-10-11_formatting_haiku/results_round2.json"
ROUND2_WINDOW = ("2026-10-11 22:30", "2026-10-11 23:08")
MEDIUM_ADOPTED = "2026-10-17 11:25"  # commit cc87ae1; GUI Format calls before it ran at "high"


def load_sources(paths):
    out = []
    for p in paths:
        raw = fp.strip_transcript_validation_footer(Path(p).read_text(encoding="utf-8"))
        out.append({"name": Path(p).name, "words": len(raw.split()), "chars": len(raw),
                    "T": tu.estimate_token_count(raw)})
    return out


def match_source(sources, file_name, raw_words):
    stem = file_name.removesuffix("_validated.txt")
    hits = [s for s in sources if s["name"].startswith(stem) and s["words"] == raw_words]
    if not hits:
        sys.exit(f"no source for {file_name} with {raw_words} words; pass it as a SOURCE")
    if len({s["T"] for s in hits}) > 1:
        sys.exit(f"sources for {file_name} disagree on T: {hits}")
    return hits[0]


def ratios(output_tokens, t, raw_words=None, formatted_words=None):
    row = {"T": t, "output_tokens": output_tokens,
           "out_per_T": round(output_tokens / t, 3),
           "cost_ratio": round(output_tokens / t - 1, 3),
           "length_ratio": round(output_tokens / t - config.FORMATTING_OUTPUT_EXPANSION, 3)}
    if formatted_words:  # thinking only: output minus the formatted text, scaled by words
        row["thinking_ratio"] = round((output_tokens - t * formatted_words / raw_words) / t, 3)
    return row


def summary(rows):
    out = {"n": len(rows)}
    for key in ("out_per_T", "cost_ratio", "length_ratio", "thinking_ratio"):
        v = [r[key] for r in rows if key in r]
        if v:
            out[key] = {"min": min(v), "median": round(statistics.median(v), 3),
                        "mean": round(statistics.mean(v), 3), "max": max(v)}
    return out


def main():
    args = sys.argv[1:]
    log_path = None
    if args[:1] == ["--token-log"]:
        log_path, args = Path(args[1]), args[2:]
    sources = load_sources(args)
    log = list(csv.DictReader(open(log_path, encoding="utf-8"))) if log_path else []
    result = {"definition": __doc__.split("\n\n")[1], "sources": {}, "medium": []}

    for f in sorted(glob.glob(str(HERE / "results_medium_*.json"))):
        for r in json.loads(Path(f).read_text(encoding="utf-8")):
            s = match_source(sources, r["file"], r["raw_words"])
            result["sources"][r["file"]] = {k: s[k] for k in ("name", "words", "chars", "T")}
            row = {"file": r["file"], "repeat": r["repeat"], "source_row": f"{Path(f).name} r{r['repeat']}",
                   "raw_words": r["raw_words"], "formatted_words": r["formatted_words"]}
            row.update(ratios(r["output_tokens"], s["T"], r["raw_words"], r["formatted_words"]))
            result["medium"].append(row)

    if log:
        sonnet = [x for x in log if x["Model"] == MODEL and x["Tokens Sent"] == "4"]
        # round 2: the six Sonnet Format calls in the window, in results_round2.json order
        calls = [x for x in sonnet if ROUND2_WINDOW[0] <= x["Timestamp"][:16] < ROUND2_WINDOW[1]]
        runs = [r for r in json.loads(ROUND2.read_text(encoding="utf-8"))["results"] if r["model"] == MODEL]
        if len(calls) != len(runs):
            sys.exit(f"round 2: {len(calls)} log rows for {len(runs)} runs")
        result["high_round2"] = []
        for r, x in zip(runs, calls):
            s = match_source(sources, r["file"], r["raw_words"])
            result["sources"][r["file"]] = {k: s[k] for k in ("name", "words", "chars", "T")}
            row = {"file": r["file"], "repeat": r["repeat"], "source_row": f"token_usage.csv {x['Timestamp']}",
                   "raw_words": r["raw_words"], "formatted_words": r["formatted_words"]}
            row.update(ratios(int(x["Tokens Response"]), s["T"], r["raw_words"], r["formatted_words"]))
            result["high_round2"].append(row)
        # e2e: the cached input size of each medium run identifies its talk in the log
        size = {}
        for row in result["medium"]:
            hits = [x for x in sonnet if int(x["Tokens Response"]) == row["output_tokens"]
                    and x["Script Name"] != "GuiLogger" and x["Timestamp"] < MEDIUM_ADOPTED]
            if len(hits) != 1:
                sys.exit(f"{row['source_row']}: {len(hits)} log rows with {row['output_tokens']} output tokens")
            x = hits[0]
            size[row["file"]] = int(x["Cache Creation Tokens"] or 0) or int(x["Cache Read Tokens"] or 0)
        # medium_e2e: the same talks run through the GUI or e2e runner at "medium", for
        # checking _MAX against real runs. Every stop reason is kept: a Format call cut
        # off at max_tokens is the case _MAX is meant to predict.
        result["high_e2e"], result["medium_e2e"] = [], []
        for x in sonnet:
            created = int(x["Cache Creation Tokens"] or 0)
            talk = next((f for f, n in size.items() if abs(created - n) <= 2), None)
            if not (talk and x["Script Name"] == "GuiLogger"):
                continue
            row = {"file": talk, "source_row": f"token_usage.csv {x['Timestamp']}",
                   "stop_reason": x["Stop Reason"]}
            row.update(ratios(int(x["Tokens Response"]), result["sources"][talk]["T"]))
            if x["Timestamp"] >= MEDIUM_ADOPTED:
                result["medium_e2e"].append(row)
            elif x["Stop Reason"] == "end_turn":
                result["high_e2e"].append(row)
        print(f"medium_e2e: {len(result['medium_e2e'])} Format calls at \"medium\" in the log",
              file=sys.stderr)

    keys = ("medium", "medium_e2e", "high_round2", "high_e2e")
    result["summary"] = {k: summary(result[k]) for k in keys if k in result}
    (HERE / "thinking_ratio.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
