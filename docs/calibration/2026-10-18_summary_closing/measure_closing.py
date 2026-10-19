#!/usr/bin/env python3
"""SC1.d measurement: does the new summary closing instruction stop invented closings
without losing a closing point the speaker does make?

Each case's project folder is copied into a scratch projects folder, so no real project
file is written; the logs folder (judge cache, token log) is redirected there too. Each
prompt (old: the summary prompt at commit 714a344; new: the
working copy) makes N first drafts through the stage itself
(`generate_structured_summary` with one attempt), so the production model, prompt build
and faithfulness check (`_faithfulness_precheck`) are used. A flagged claim counts as a
closing flag when it is in the Closing Paragraph. Then the real stage (three attempts,
with revision) runs once on the Holt case with the new prompt.

Usage:
  .venv/bin/python docs/calibration/2026-10-18_summary_closing/measure_closing.py \
      --scratch <dir> --out <results.json> [--drafts 2] [--skip-stage]

Spec: docs/plan_summary_closing_2026-10-18.md#SC1.d
"""
import argparse
import csv
import difflib
import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import extraction_pipeline as ep  # noqa: E402
import summary_pipeline as sp  # noqa: E402

OLD_PROMPT_COMMIT = "714a344"
CASES = [
    ("holt", Path("/Volumes/davemini/Downloads/projects/1 A and B Heartland Conference 2007 "
                  "joe Holt interview - Michael Kerrr - 2026-01-26"),
     "recording stops one paragraph into a panel discussion"),
    ("sep_part1", Path("/Volumes/CrucialX9/1 MY DISK/KCFC ALL/projects/"
                       "2021 Webcast Sep Part 1 - Michael Kerr - 2021-09-"),
     "Part 1 stops mid-sentence"),
    ("societal", ROOT / "tests/fixtures/prose_real/"
     "Societal Emotional Process - Michael Kerr - 2021-12-12_v-valid",
     "speaker gives a closing point (identity as the key issue), then goodbyes"),
    ("systems_biology", ROOT / "tests/fixtures/prose_real/"
     "Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - "
     "2021-06-25_20260718_155038",
     "ends in Q&A with no closing statement"),
]
SKIP_SUFFIXES = (".pdf", ".docx", ".html", ".zip")
# A sentence that says the talk has no conclusion (TODO "Meta-claims about the talk").
META_CLAIM = re.compile(
    r"no (?:explicit |clear |formal |stated )?(?:conclusion|closing)"
    r"|(?:does not|doesn't) (?:state|offer|reach|draw|give) (?:a|any) "
    r"(?:explicit |clear |formal )?conclusion"
    r"|without (?:a|any) (?:explicit |clear |formal )?conclusion"
    r"|ends without", re.IGNORECASE)
CLOSING = re.compile(r"^#{2,4}\s*Closing[^\n]*\n(.*?)(?=^#{1,4}\s|\Z)", re.M | re.S)


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


def closing_text(draft: str) -> str:
    m = CLOSING.search(draft)
    return m.group(1).strip() if m else ""


def in_closing(issue: str, closing: str) -> bool:
    """Is a flagged claim (or an ungrounded name) in the closing paragraph?"""
    name = re.match(r"the name '(.+)' does not appear in the source", issue)
    if name:
        return name.group(1).lower() in closing.lower()
    claim = _norm(re.sub(r"\s*\[in answer to:.*\]\s*$", "", issue))
    norm = _norm(closing)
    if not claim or not norm:
        return False
    if claim in norm or claim[:60] in norm:
        return True
    sentences = re.split(r"(?<=[.!?])\s+", norm)
    return any(difflib.SequenceMatcher(None, claim, s).ratio() > 0.85 for s in sentences)


def check_scratch(scratch: Path) -> None:
    """Refuse a scratch folder that is, or is inside, this repo, the real projects folder
    or a case's parent folder: `copy_case` deletes and rewrites folders there, and the
    stage and logs write into it (learning-qa review, P39). Added after the 2026-10-18
    run; it does not change what the script measures."""
    s = scratch.resolve()
    protected = {ROOT.resolve(), Path(config.PROJECTS_DIR).resolve()}
    protected |= {src.parent.resolve() for _, src, _ in CASES}
    for p in sorted(protected):
        if s == p or s.is_relative_to(p):
            sys.exit(f"--scratch {scratch} is inside {p}; use a new folder outside it")


def copy_case(src: Path, scratch: Path) -> str:
    dst = scratch / src.name
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for f in src.iterdir():
        if f.is_file() and not f.name.endswith(SKIP_SUFFIXES):
            shutil.copy2(f, dst / f.name)
    return src.name


class Recorder:
    """Wraps the stage's precheck to record each judged draft and its verdict."""

    def __init__(self):
        self.records, self._orig = [], ep._faithfulness_precheck

    def __call__(self, base, suffix, logger=None):
        status, issues = self._orig(base, suffix, logger)
        draft = (config.PROJECTS_DIR / base / f"{base}{suffix}").read_text(encoding="utf-8")
        closing = closing_text(draft)
        self.records.append({
            "status": status, "issues": issues, "words": len(draft.split()),
            "closing": closing,
            "closing_issues": [i for i in issues if in_closing(i, closing)],
            "meta_claim": bool(META_CLAIM.search(closing)),
            "closing_heading_found": bool(CLOSING.search(draft)),
        })
        return status, issues


def run_stage(base: str, attempts: int, prompt_text: str, log) -> tuple:
    """Run generate_structured_summary with ``attempts`` tries and ``prompt_text`` as
    the summary prompt; return (ok, judged-draft records). Restores what it patches."""
    rec = Recorder()
    saved = (ep._faithfulness_precheck, sp.load_prompt, config.GENERATION_FAITHFULNESS_ATTEMPTS)
    ep._faithfulness_precheck, sp.load_prompt = rec, (lambda: prompt_text)
    config.GENERATION_FAITHFULNESS_ATTEMPTS = attempts
    try:
        ok = ep.generate_structured_summary(base, logger=log)
    finally:
        (ep._faithfulness_precheck, sp.load_prompt,
         config.GENERATION_FAITHFULNESS_ATTEMPTS) = saved
    return ok, rec.records


def cost_since(start: datetime) -> float:
    total = 0.0
    path = config.LOGS_DIR / "token_usage.csv"
    if not path.exists():
        return 0.0
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                when = datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S")
            except (KeyError, ValueError):
                continue
            if when >= start:
                total += float(row.get("Estimated Cost ($)") or 0)
    return round(total, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--drafts", type=int, default=2)
    ap.add_argument("--skip-stage", action="store_true")
    args = ap.parse_args()

    check_scratch(args.scratch)
    start = datetime.now().replace(microsecond=0)
    args.scratch.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(args.out.with_suffix(".log")),
                                  logging.StreamHandler(sys.stdout)])
    log = logging.getLogger("measure_closing")
    config.PROJECTS_DIR = args.scratch
    config.LOGS_DIR = args.scratch / "logs"  # judge cache and token log stay in scratch
    config.LOGS_DIR.mkdir(exist_ok=True)

    prompts = {
        "old": subprocess.run(
            ["git", "show", f"{OLD_PROMPT_COMMIT}:prompts/{config.PROMPT_STRUCTURED_SUMMARY_FILENAME}"],
            cwd=ROOT, check=True, capture_output=True, text=True).stdout,
        "new": (config.PROMPTS_DIR / config.PROMPT_STRUCTURED_SUMMARY_FILENAME).read_text(
            encoding="utf-8"),
    }
    assert prompts["old"] != prompts["new"], "working-copy prompt is unchanged"
    results = {"started": start.isoformat(), "model": config.settings.DEFAULT_MODEL,
               "judge_model": config.FAITHFULNESS_JUDGE_MODEL,
               "old_prompt_commit": OLD_PROMPT_COMMIT, "drafts": [], "stage": None}

    for case, src, ending in CASES:
        base = copy_case(src, args.scratch)
        for variant in ("old", "new"):
            for k in range(1, args.drafts + 1):
                log.info("=== %s / %s prompt / draft %d", case, variant, k)
                try:
                    ok, records = run_stage(base, 1, prompts[variant], log)
                except Exception as e:  # noqa: BLE001 — record and go on
                    log.error("draft failed: %s", e)
                    results["drafts"].append({"case": case, "prompt": variant, "k": k,
                                              "error": str(e)})
                    continue
                rec = records[-1] if records else {"status": "not judged"}
                results["drafts"].append({"case": case, "ending": ending, "prompt": variant,
                                          "k": k, "stage_ok": ok, **rec})
                log.info("-> %s, %d issue(s), %d in closing, meta-claim %s",
                         rec.get("status"), len(rec.get("issues", [])),
                         len(rec.get("closing_issues", [])), rec.get("meta_claim"))
                args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    if not args.skip_stage:
        case, src, ending = CASES[0]
        base = copy_case(src, args.scratch)
        log.info("=== stage run: %s, new prompt, %d attempts", case,
                 config.GENERATION_FAITHFULNESS_ATTEMPTS)
        ok, records = run_stage(base, config.GENERATION_FAITHFULNESS_ATTEMPTS,
                                prompts["new"], log)
        kept = (args.scratch / base / f"{base}{config.SUFFIX_SUMMARY_GEN}").read_text(
            encoding="utf-8")
        results["stage"] = {"case": case, "ok": ok, "tries": records,
                            "kept_closing": closing_text(kept)}
        log.info("-> stage ok=%s after %d judged tries", ok, len(records))

    results["cost_usd"] = cost_since(start)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    log.info("cost since start: $%.4f", results["cost_usd"])


if __name__ == "__main__":
    main()
