#!/usr/bin/env python3
"""JS6 measurement: does the severity step downgrade only NOT QUITE RIGHT flags?

Parts (docs/plan_judge_severity_2026-10-19.md#JS6):

  c  Injected: four WRONG claims (W1-W4) added to a held-out real summary (Why Families
     Repeat, tests/fixtures/prose_real); judged 3 times. Each must be flagged and kept
     WRONG in every run.
  d  Held-out first drafts: 2 summary first drafts from each of 6 talks the review did
     not use, made by the summary stage itself (`generate_structured_summary`, one
     attempt, working-copy prompt). One judge run per draft gives both outcomes: old =
     any confirmed flag fails; new = only a WRONG flag fails (the step runs only on
     confirmed flags, so the old flags are the same).
  e  Regression: 10 gate checks (`release_gate.check_faithfulness`, fresh cache each)
     of the Kerr 2026-09-13 project files. The exact CF.6 files were overwritten after
     2026-10-11 (their hashes no longer match), so the current files are used and their
     hashes recorded.
  f  Development set: the review's 43 claims (docs/judge_flag_review_2026-10-18.md)
     through the severity step, 3 runs. Not a ship criterion.

Every project folder is copied into a scratch folder first, so no real project file is
written; config.LOGS_DIR (judge cache, token log) points into the scratch folder too.

Blind classification (part d): ``blind_flags.md`` lists every confirmed flag with its
talk and the sentence before it, but not what the severity step decided. The step's
decisions are only in the results JSON and the log, which are read after the hand
labels are written. Nothing is printed to stdout but progress counts.

Usage:
  .venv/bin/python docs/calibration/2026-10-19_judge_severity/measure_severity.py \\
      --scratch <dir outside the repo> --out <results.json> [--parts cdef]

Spec: docs/plan_judge_severity_2026-10-19.md#JS6
"""
import argparse
import csv
import hashlib
import json
import logging
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import extraction_pipeline as ep  # noqa: E402
import faithfulness_judge as fj  # noqa: E402
import release_gate as rg  # noqa: E402

PROSE = ROOT / "tests" / "fixtures" / "prose_real"
KCFC = Path("/Volumes/CrucialX9/1 MY DISK/KCFC ALL/projects")
WHY = "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13"
DRAFT_TALKS = [
    PROSE / "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid",
    KCFC / "2021 Webcast Jan Societal Regression - Michael Kerr - 2021-01-21",
    KCFC / "2021 Webcast Feb - KCFC - 2021-02-xx",
    KCFC / "2021 Webinar Mar - KCFC - 2021-03-xx",
    KCFC / "2021 Webinar April - KCFC - 2021-04-xx",
    KCFC / "2021 Webcast Jun - KCFC - 2021-06-xx",
]
REGRESSION_PROJECT = Path("/Users/davemini2/projects") / WHY
SKIP_SUFFIXES = (".pdf", ".docx", ".html", ".zip")

# Part c. Each claim is WRONG against the Why Families transcript (checked by hand):
#  W1 no study, year or number of families is mentioned;
#  W2 the transcript (section 7): "Years later, she said to me" — his mother, not father;
#  W3 "I fell into that trap again" is the interviewer's (section 16), not Kerr's;
#  W4 Kerr mentions his second book; no third book or publishing plan of his.
INJECTED = {
    "W1": ("Kerr cites a 1998 Georgetown study of 400 families, which found that the most "
           "protected child was three times as likely to develop schizophrenia.", "1998 Georgetown"),
    "W2": ("Kerr adds that it was his father who told him, years later, \"Michael, I love "
           "you, but I love Billy the most.\"", "his father who"),
    "W3": ("Kerr says that when family members poke him, he reacts without noticing, and two "
           "seconds later he thinks, \"Oh, I fell into that trap again.\"", "two seconds later"),
    "W4": ("Kerr announces that he will publish a third book, on societal regression, next "
           "year.", "third book"),
}
# Where each injected sentence goes: after the paragraph that starts with this text.
INJECT_AFTER = {
    "W1": "Bowen's central concept, the family projection process",
    "W2": "Kerr's entry into Bowen theory came",
    "W3": "Throughout the conversation, the interviewer presses",
    "W4": "Kerr's final recommendation is direct",
}

# Part f. The review's sections and the sources it read (its "Sources and method").
SCRATCH_SRC = Path("/private/tmp/claude-501/-Users-davemini2-ProjectsLocal-Projects-"
                   "trans-summary/cf0d1adc-3559-4fc4-a622-a1abdb54920e/scratchpad/src")
DEV_SOURCES = {
    "Holt": ("1 A and B Heartland Conference 2007 joe Holt interview - Michael Kerrr - 2026-01-26",
             SCRATCH_SRC / "holt.md"),
    "2021 Webcast Sep Part 1": (
        "2021 Webcast Sep Part 1 - Michael Kerr - 2021-09-",
        KCFC / "2021 Webcast Sep Part 1 - Michael Kerr - 2021-09-"
        / "2021 Webcast Sep Part 1 - Michael Kerr - 2021-09- - formatted.md"),
    "Societal Emotional Process": (
        "Societal Emotional Process - Michael Kerr - 2021-12-12_v-valid",
        PROSE / "Societal Emotional Process - Michael Kerr - 2021-12-12_v-valid"
        / "Societal Emotional Process - Michael Kerr - 2021-12-12_v-valid - formatted.md"),
    "Systems Biology": (
        "Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25_20260718_155038",
        PROSE / "Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25_20260718_155038"
        / "Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25_20260718_155038 - formatted.md"),
}
REVIEW = ROOT / "docs" / "judge_flag_review_2026-10-18.md"
ROW = re.compile(r"^\| ([RSL]\d+) \([^)]*\) \| (.+?) \| (.+?) \|")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def check_scratch(scratch: Path) -> None:
    """Refuse a scratch folder inside the repo or a folder a case is copied from:
    `copy_case` deletes and rewrites folders there (P39)."""
    s = scratch.resolve()
    protected = {ROOT.resolve(), Path(config.PROJECTS_DIR).resolve(), REGRESSION_PROJECT.parent}
    protected |= {t.parent.resolve() for t in DRAFT_TALKS}
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


def claim_records(result) -> list:
    """Every claim of one judged artifact, in order, with the sentence before it."""
    out = []
    for i, c in enumerate(result.claims):
        out.append({"claim": c.claim, "context": result.claims[i - 1].claim if i else "",
                    "label": c.label, "rationale": c.rationale, "severity": c.severity,
                    "type": c.severity_type, "evidence": c.evidence,
                    "votes": c.severity_votes, "note": c.severity_note})
    return out


def outcome(records: list) -> dict:
    flagged = [r for r in records if fj.is_unfaithful(r["label"])]
    wrong = [r for r in flagged if r["severity"] != fj.NOT_QUITE_RIGHT]
    return {"flags": len(flagged), "wrong": len(wrong),
            "old": "FAIL" if flagged else "PASS", "new": "FAIL" if wrong else "PASS"}


class JudgeRecorder:
    """Records each judge_artifact result (full claim list) while the stage runs."""

    def __init__(self):
        self.results = []
        self.orig = fj.judge_artifact

    def install(self):
        rec, orig = self, self.orig

        def judge_artifact(artifact_text, source, client, *, model=None, logger=None):
            r = orig(artifact_text, source, client, model=model, logger=logger)
            rec.results.append({"text": artifact_text, "status": r.status, "detail": r.detail,
                                "claims": claim_records(r)})
            return r
        fj.judge_artifact = judge_artifact

    def remove(self):
        fj.judge_artifact = self.orig


def client():
    from transcript_utils import get_anthropic_client, resolve_anthropic_key
    key = resolve_anthropic_key()
    if not key:
        sys.exit("No Anthropic API key found.")
    return get_anthropic_client(key)


def part_c(cl, log) -> dict:
    talk = PROSE / WHY
    text = (talk / f"{WHY} - summary-generated.md").read_text(encoding="utf-8")
    for k, (sentence, _) in INJECTED.items():
        start = text.index(INJECT_AFTER[k])
        end = text.find("\n\n", start)
        end = len(text.rstrip()) if end == -1 else end
        text = text[:end] + " " + sentence + text[end:]
    source = rg.with_recording_metadata(WHY, (talk / f"{WHY} - formatted.md").read_text(encoding="utf-8"))
    runs = []
    for n in range(1, 4):
        log.info("part c run %d", n)
        r = fj.judge_artifact(text, source, cl, logger=log)
        records = claim_records(r)
        found = {}
        for k, (_, key) in INJECTED.items():
            hit = next((c for c in records if key in c["claim"]), None)
            found[k] = {"claim": hit["claim"] if hit else None,
                        "label": hit["label"] if hit else "not extracted",
                        "severity": hit["severity"] if hit else "",
                        "type": hit["type"] if hit else "", "votes": hit["votes"] if hit else [],
                        "kept_wrong": bool(hit) and fj.is_unfaithful(hit["label"])
                        and hit["severity"] != fj.NOT_QUITE_RIGHT}
        runs.append({"status": r.status, "detail": r.detail, "injected": found,
                     "claims": records, **outcome(records)})
        print(f"c run {n}: {sum(f['kept_wrong'] for f in found.values())}/4 injected kept", flush=True)
    return {"text": text, "summary_sha": sha(talk / f"{WHY} - summary-generated.md"),
            "transcript_sha": sha(talk / f"{WHY} - formatted.md"), "runs": runs,
            "pass": all(f["kept_wrong"] for r in runs for f in r["injected"].values())}


def part_d(cl, scratch: Path, drafts: int, log) -> list:
    out = []
    for talk in DRAFT_TALKS:
        base = copy_case(talk, scratch)
        for k in range(1, drafts + 1):
            log.info("part d %s draft %d", base, k)
            rec = JudgeRecorder()
            rec.install()
            saved = config.GENERATION_FAITHFULNESS_ATTEMPTS
            config.GENERATION_FAITHFULNESS_ATTEMPTS = 1
            try:
                ok = ep.generate_structured_summary(base, logger=log)
                err = None
            except Exception as e:  # noqa: BLE001 — record and go on
                ok, err = False, f"{type(e).__name__}: {e}"
            finally:
                config.GENERATION_FAITHFULNESS_ATTEMPTS = saved
                rec.remove()
            if not rec.results:
                out.append({"talk": base, "k": k, "stage_ok": ok, "error": err or "not judged"})
                print(f"d {base[:40]} #{k}: not judged ({err})", flush=True)
                continue
            r = rec.results[-1]
            out.append({"talk": base, "k": k, "stage_ok": ok, "error": err,
                        "judge_calls": len(rec.results),
                        "transcript_sha": sha(talk / f"{base} - formatted.md"),
                        "draft": r["text"], "status": r["status"], "detail": r["detail"],
                        "claims": r["claims"], **outcome(r["claims"])})
            print(f"d {base[:40]} #{k}: {out[-1]['flags']} flag(s)", flush=True)
    return out


def part_e(cl, scratch: Path, checks: int, log) -> dict:
    base = copy_case(REGRESSION_PROJECT, scratch)
    files = {s: sha(scratch / base / f"{base}{s}") for s in config.FAITHFULNESS_ARTIFACT_SUFFIXES
             if (scratch / base / f"{base}{s}").exists()}
    logs_root, runs = config.LOGS_DIR, []
    try:
        for n in range(1, checks + 1):
            config.LOGS_DIR = logs_root / f"e_run{n}"  # fresh disk cache per check
            config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
            rg._FAITHFULNESS_CACHE.clear()
            rec = JudgeRecorder()
            rec.install()
            try:
                v = rg.check_faithfulness(base, log)
            finally:
                rec.remove()
            arts = [{"claims": r["claims"], **outcome(r["claims"])} for r in rec.results]
            old = "FAIL" if any(a["old"] == "FAIL" for a in arts) else str(v.status)
            runs.append({"status": str(v.status), "old_status": old, "detail": v.detail,
                         "artifacts": arts, "cost": cost_since(datetime.min)})
            print(f"e check {n}: old {old}, new {v.status}", flush=True)
    finally:
        config.LOGS_DIR = logs_root
    return {"files": files, "runs": runs}


def dev_claims() -> list:
    rows, section = [], None
    for line in REVIEW.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^### (.+?) \(\d+\)$", line)
        if m:
            section = m.group(1)
            continue
        m = ROW.match(line)
        if m and section in DEV_SOURCES:
            label = m.group(3)
            sev = fj.WRONG if "WRONG" in label else fj.NOT_QUITE_RIGHT
            typ = re.search(r"\b([WN]\d)\b", label).group(1)
            # JS0.b: true credentials not in the source (review's N4) are WRONG (W1).
            policy = fj.WRONG if typ == "N4" else sev
            rows.append({"id": m.group(1), "section": section, "claim": m.group(2).strip(),
                         "review": sev, "review_type": typ, "policy": policy})
    return rows


def part_f(cl, runs: int, log) -> dict:
    claims = dev_claims()
    sources = {s: rg.with_recording_metadata(b, p.read_text(encoding="utf-8"))
               for s, (b, p) in DEV_SOURCES.items()}
    for c in claims:
        c["runs"] = []
    for n in range(1, runs + 1):
        for section, source in sources.items():
            group = [c for c in claims if c["section"] == section]
            log.info("part f run %d %s (%d claims)", n, section, len(group))
            got = fj.classify_severity([c["claim"] for c in group], source, cl, logger=log)
            for c, v in zip(group, got):
                c["runs"].append({"severity": v.severity, "type": v.type, "evidence": v.evidence,
                                  "votes": v.votes, "note": v.note})
        print(f"f run {n}: done", flush=True)
    return {"source_shas": {s: sha(p) for s, (_, p) in DEV_SOURCES.items()}, "claims": claims}


def write_blind(results: dict, path: Path) -> None:
    """Every confirmed flag of parts c, d and e, without the severity step's decision."""
    lines = ["# JS6 blind list: every confirmed flag, without the severity decision", "",
             "Classify each as WRONG or NOT QUITE RIGHT from the source before reading the "
             "results file.", ""]
    n = 0
    for d in results.get("d", []):
        flagged = [c for c in d.get("claims", []) if fj.is_unfaithful(c["label"])]
        for c in flagged:
            n += 1
            lines += [f"## D{n} — {d['talk']} (draft {d['k']})", "",
                      f"- Claim: {c['claim']}", f"- Before it: {c['context'] or '(none)'}",
                      f"- Judge label: {c['label']}", ""]
    m = 0
    seen = set()
    injected_keys = [key for _, key in INJECTED.values()]
    for part in ("c", "e"):
        res = results.get(part)
        if not res:
            continue
        for r in res["runs"]:
            arts = r.get("artifacts") or [{"claims": r.get("claims", [])}]
            for a in arts:
                for c in a["claims"]:
                    if part == "c" and any(key in c["claim"] for key in injected_keys):
                        continue  # the injected claims are WRONG by construction
                    if fj.is_unfaithful(c["label"]) and (part, c["claim"]) not in seen:
                        seen.add((part, c["claim"]))
                        m += 1
                        lines += [f"## {part.upper()}{m} — part {part}", "",
                                  f"- Claim: {c['claim']}",
                                  f"- Before it: {c['context'] or '(none)'}", ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"blind list: {n} draft flag(s), {m} other flag(s) -> {path}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--parts", default="cdef")
    ap.add_argument("--drafts", type=int, default=2)
    ap.add_argument("--checks", type=int, default=10)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    check_scratch(args.scratch)
    if config.FAITHFULNESS_SEVERITY_MODE == "off" or not config.FAITHFULNESS_JUDGE_ENABLED:
        sys.exit("the judge and its severity step must be on")
    start = datetime.now().replace(microsecond=0)
    args.scratch.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
                        handlers=[logging.FileHandler(args.out.with_suffix(".log"))])
    log = logging.getLogger("measure_severity")
    config.PROJECTS_DIR = args.scratch
    config.LOGS_DIR = args.scratch / "logs"
    config.LOGS_DIR.mkdir(exist_ok=True)

    cl = client()
    results = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    results.update({"started": start.isoformat(), "model": config.settings.DEFAULT_MODEL,
                    "judge_model": config.FAITHFULNESS_JUDGE_MODEL,
                    "judge_logic_version": config.JUDGE_LOGIC_VERSION,
                    "severity_mode": config.FAITHFULNESS_SEVERITY_MODE,
                    "severity_prompt_sha": hashlib.sha256(
                        fj.severity_instructions().encode()).hexdigest()[:12],
                    "summary_prompt_sha": sha(config.PROMPTS_DIR
                                              / config.PROMPT_STRUCTURED_SUMMARY_FILENAME),
                    "cache_version": rg._judge_logic_version(fj._JUDGE_INSTRUCTIONS)})

    def save():
        args.out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")

    if "c" in args.parts:
        results["c"] = part_c(cl, log)
        save()
    if "d" in args.parts:
        results["d"] = part_d(cl, args.scratch, args.drafts, log)
        save()
    if "e" in args.parts:
        results["e"] = part_e(cl, args.scratch, args.checks, log)
        save()
    if "f" in args.parts:
        results["f"] = part_f(cl, args.runs, log)
        save()
    # parts c, d, f log to scratch/logs; each part e check logs to its own folder
    results["cost_usd_this_call"] = cost_since(start)
    e_logs = sorted(config.LOGS_DIR.glob("e_run*/token_usage.csv"))
    results["cost_usd_part_e"] = round(sum(
        float(r.get("Estimated Cost ($)") or 0) for p in e_logs
        for r in csv.DictReader(p.open(encoding="utf-8"))), 4) if "e" in args.parts else 0.0
    save()
    write_blind(results, args.out.with_name("blind_flags.md"))
    print(f"cost: ${results['cost_usd_this_call']} + part e ${results['cost_usd_part_e']}", flush=True)


if __name__ == "__main__":
    main()
