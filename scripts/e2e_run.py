"""End-to-end run of every GUI stage on real transcripts, without the window.

Usage:
    .venv/bin/python scripts/e2e_run.py --out <folder> <transcript.txt> [...]
    options: --model claude-sonnet-5-5  --stages init_val,format,...  --terms <file>
             --estimate-only

It calls the GUI's own stage runners (ts_gui.TranscriptProcessorGUI.stage_runners)
in STAGE_DEFINITIONS order, with the GUI's own logger adapter, so it runs the same
code as Run Selected. Differences from a GUI run, on purpose:

- It works in its own folder (--out). Each transcript is copied to <out>/source and
  every project is written under <out>/projects. Real projects and
  logs/runtime_settings.json are not touched. Token usage is still logged to
  logs/token_usage.csv, and the judge cache in logs/ is shared.
- It does not stop at the first failure. A stage runs when its inputs exist; every
  failure, warning and error is collected into <out>/report.md (and report.json).
- Format differences that need a person's review are counted, not opened in a
  dialog. The GUI pauses there; this run records it as a Format failure and goes on
  with the formatted file as written.
- Core runs without Bowen/Emphasis; the separate Bowen + Emphasis stage runs them,
  so they are not paid for twice.

Only use public talks: every stage sends the transcript to the model provider.
"""
import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import analyze_token_usage  # noqa: E402
import config  # noqa: E402
import format_review  # noqa: E402
import transcript_cost_estimator  # noqa: E402
import ts_gui  # noqa: E402
from transcript_utils import clean_project_name  # noqa: E402

ERROR_MARKS = ("❌", "[BLOCKER", "FAILED")
WARNING_MARKS = ("⚠️", "[WARN]")


class _Var:
    """Stand-in for a tk variable (get/set)."""

    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class _Root:
    """Stand-in for the Tk root: UI refreshes scheduled with after() are dropped."""

    def after(self, *args, **kwargs):
        return None

    def update_idletasks(self):
        return None


class _ModuleWarnings(logging.Handler):
    """Collects WARNING+ from module loggers that do not go through the GUI adapter."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append((record.levelname, f"[{record.name}] {record.getMessage()}"))
        except Exception:  # a bad format string must not stop the run
            self.lines.append((record.levelname, f"[{record.name}] {record.msg}"))


class Run:
    """One transcript's run: the GUI instance, its log, and the per-stage results."""

    def __init__(self, source: Path, log_path: Path):
        self.log_fh = open(log_path, "a", encoding="utf-8")
        self.lines = []  # (level, text) for the current stage
        self.review_items = None
        gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
        gui.root = _Root()
        gui.processing = False
        gui._log_file_enabled = False
        gui.selected_file = source
        gui.base_name = clean_project_name(source.stem)
        gui.formatted_file = (config.PROJECTS_DIR / gui.base_name
                              / f"{gui.base_name}{config.SUFFIX_FORMATTED}")
        gui.validation_mode_var = _Var("v2")
        gui.include_bowen_core = _Var(False)
        gui.include_emphasis_core = _Var(False)
        gui.pattern_set_var = None
        gui.log = self.log
        gui.set_status = lambda *a, **k: None
        gui.set_final_status = lambda *a, **k: None
        gui._open_review_if_needed = self._record_review
        gui.logger = ts_gui.GuiLoggerAdapter(gui)
        self.gui = gui

    def log(self, message, *args):
        if args:
            try:
                text = str(message) % args
            except TypeError:
                text = f"{message} {args}"
        else:
            text = str(message)
        self.log_fh.write(f"{datetime.now():%H:%M:%S} {text}\n")
        self.log_fh.flush()
        if any(m in text for m in ERROR_MARKS):
            self.lines.append(("ERROR", text))
        elif any(m in text for m in WARNING_MARKS):
            self.lines.append(("WARNING", text))

    def _record_review(self):
        """Headless replacement for the review dialog: count, don't pause."""
        try:
            items = format_review.pending_items(self.gui.base_name)
        except Exception as e:  # noqa: BLE001 - reported, not raised
            self.log("⚠️ Could not load differences for review: %s", e)
            return False
        self.review_items = len(items)
        if items:
            self.log("❌ Format: %d difference(s) need a person's review (the GUI would "
                     "pause here).", len(items))
        return False

    def missing_inputs(self, key):
        """Labels of input groups with no artifact on disk (STAGE_DEPENDENCIES)."""
        missing = []
        for group in ts_gui.STAGE_DEPENDENCIES.get(key, []):
            if not any(self.gui._stage_artifact_path(attr).exists() for _p, attr in group):
                missing.append(" or ".join(ts_gui.ARTIFACT_LABELS.get(attr, attr)
                                           for _p, attr in group))
        return missing


def estimate(source: Path, logger) -> float:
    est = transcript_cost_estimator.CostEstimator(source, logger=logger)
    est.run_full_estimation()
    return sum(c["cost"] for c in est.costs)


def run_one(source: Path, stages, out: Path, module_warnings: _ModuleWarnings):
    run = Run(source, out / f"{clean_project_name(source.stem)}.log")
    results = []
    run.log("E2E runtime: commit=%s model=%s aux=%s formatting=%s effort=%s terms=%s",
            ts_gui._current_git_revision(), config.settings.DEFAULT_MODEL,
            config.settings.AUX_MODEL, config.settings.FORMATTING_MODEL,
            config.settings.EFFORT, config.VALIDATION_APPROVED_TERMS_PATH)
    for key, label in ts_gui.STAGE_DEFINITIONS:
        if key not in stages:
            continue
        run.lines = []
        module_warnings.lines = []
        run.log("\n--- %s ---", label)
        missing = run.missing_inputs(key)
        if missing:
            results.append({"stage": label, "status": "SKIPPED",
                            "detail": "missing input: " + "; ".join(missing),
                            "seconds": 0, "errors": [], "warnings": []})
            print(f"  {label:28} SKIPPED (missing {'; '.join(missing)})", flush=True)
            continue
        started = time.monotonic()
        try:
            ok = run.gui.stage_runners[key]()
            status = "PASS" if ok else "FAIL"
            detail = ""
        except Exception as e:  # noqa: BLE001 - the GUI's _execute_task also catches all
            status, detail = "EXCEPTION", f"{type(e).__name__}: {e}"
            run.log("❌ %s raised %s", label, detail)
        seconds = round(time.monotonic() - started, 1)
        lines = run.lines + module_warnings.lines
        errors = [t for lvl, t in lines if lvl in ("ERROR", "CRITICAL")]
        warnings = [t for lvl, t in lines if lvl == "WARNING"]
        if key == "format" and run.review_items:
            detail = f"{run.review_items} difference(s) need review"
        results.append({"stage": label, "status": status, "detail": detail,
                        "seconds": seconds, "errors": errors, "warnings": warnings})
        print(f"  {label:28} {status:9} {seconds:7.1f}s  "
              f"{len(errors)} error(s), {len(warnings)} warning(s) {detail}", flush=True)
    run.log_fh.close()
    return run.gui.base_name, results


def write_report(out: Path, header: dict, talks: list):
    (out / "report.json").write_text(json.dumps({"header": header, "talks": talks},
                                                indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    md = ["# End-to-end run", ""]
    md += [f"- {k}: {v}" for k, v in header.items()]
    for talk in talks:
        md += ["", f"## {talk['project']}", "",
               f"Estimated cost: ${talk['estimate']:.2f}", "",
               "| Stage | Result | Time (s) | Errors | Warnings | Detail |",
               "|---|---|---|---|---|---|"]
        for r in talk["results"]:
            md.append(f"| {r['stage']} | {r['status']} | {r['seconds']} | "
                      f"{len(r['errors'])} | {len(r['warnings'])} | {r['detail']} |")
        for r in talk["results"]:
            if r["errors"] or r["warnings"]:
                md += ["", f"### {r['stage']}", ""]
                md += [f"- ERROR: {t.strip()[:400]}" for t in r["errors"]]
                md += [f"- WARNING: {t.strip()[:400]}" for t in r["warnings"]]
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sources", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="claude-sonnet-5-5",
                    help="Main model (the GUI's DEFAULT_MODEL); default as in your GUI runs")
    ap.add_argument("--stages", default="",
                    help="Comma-separated stage keys; default every stage")
    ap.add_argument("--terms", type=Path,
                    default=Path.home() / "transcripts" / "approve_terms.txt",
                    help="Approved-terms file for Init Val")
    ap.add_argument("--estimate-only", action="store_true")
    args = ap.parse_args(argv)

    keys = [k for k, _l in ts_gui.STAGE_DEFINITIONS]
    stages = set(args.stages.split(",")) if args.stages else set(keys)
    unknown = stages - set(keys)
    if unknown:
        ap.error(f"unknown stage(s): {', '.join(sorted(unknown))}; known: {', '.join(keys)}")

    out = args.out.resolve()
    (out / "source").mkdir(parents=True, exist_ok=True)
    config.set_transcripts_base(out)  # source/ and projects/ under --out
    config.settings.VALIDATION_APPROVED_TERMS_PATH = args.terms
    config.VALIDATION_APPROVED_TERMS_PATH = args.terms
    config.settings.set_default_model(args.model)  # not saved to runtime_settings.json

    module_warnings = _ModuleWarnings()
    logging.getLogger().addHandler(module_warnings)
    est_logger = logging.getLogger("e2e.estimate")
    est_logger.propagate = False  # the estimate report is not a run warning

    started = datetime.now()
    header = {"started": f"{started:%Y-%m-%d %H:%M}",
              "commit": ts_gui._current_git_revision(),
              "models": f"main={config.settings.DEFAULT_MODEL} aux={config.settings.AUX_MODEL} "
                        f"formatting={config.settings.FORMATTING_MODEL} "
                        f"effort={config.settings.EFFORT or 'model default'}",
              "stages": ", ".join(k for k in keys if k in stages),
              "terms": str(args.terms)}
    talks = []
    for src in args.sources:
        dest = out / "source" / src.name
        if not dest.exists():
            shutil.copy2(src, dest)
        cost = estimate(dest, est_logger)
        print(f"\n{dest.name}: estimated ${cost:.2f} (judges and retries not included)",
              flush=True)
        if args.estimate_only:
            talks.append({"project": clean_project_name(dest.stem), "estimate": cost,
                          "results": []})
            continue
        project, results = run_one(dest, stages, out, module_warnings)
        talks.append({"project": project, "estimate": cost, "results": results})
        write_report(out, header, talks)  # after each talk, so a crash keeps the rest

    if not args.estimate_only:
        usage = analyze_token_usage.generate_usage_report(since_timestamp=started)
        (out / "token_usage.txt").write_text(str(usage), encoding="utf-8")
    write_report(out, header, talks)
    print(f"\nReport: {out / 'report.md'}")
    failed = [r for t in talks for r in t["results"] if r["status"] not in ("PASS",)]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
