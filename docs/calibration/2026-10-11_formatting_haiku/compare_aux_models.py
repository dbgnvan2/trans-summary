"""U5 — compare AUX_MODEL candidates on the AUX tasks, on copies of the public
prose_real fixture projects (nothing written to the real projects or logs folders).

Tasks per project and model (REPEATS each):
  - structured abstract generation (includes the gate's faithfulness pre-check and
    regeneration): final gate status, attempts, word count
  - header validation: PASS/WARN/FAIL verdict counts
  - stated-purpose extraction: the sentence
  - summary coverage check (only where a summary exists): pass/fail

Usage: python compare_aux_models.py OUT_DIR MODEL [MODEL...]
"""
import json
import logging
import shutil
import sys
import time
from pathlib import Path

REPO = Path("/Users/davemini2/ProjectsLocal/Projects/trans-summary")
sys.path.insert(0, str(REPO))
import config  # noqa: E402

REPEATS = 2
FIX = REPO / "tests" / "fixtures" / "prose_real"
PROJECTS = [
    "Societal Emotional Process - Michael Kerr - 2021-12-12_v-valid",
    "Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25_20260718_155038",
    "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid",
]


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(f"{record.levelname}: {record.getMessage()}")


def set_aux(model):
    config.settings.AUX_MODEL = model
    config.AUX_MODEL = model


def main():
    out_dir = Path(sys.argv[1])
    models = sys.argv[2:]
    out_dir.mkdir(parents=True, exist_ok=True)
    import abstract_pipeline
    import extraction_pipeline as ep
    import release_gate
    import transcript_utils as tu
    import validation_pipeline as vp

    rows = []
    for model in models:
        for r in range(REPEATS):
            work = out_dir / f"{model}_r{r + 1}"
            projects = work / "projects"
            if work.exists():
                shutil.rmtree(work)
            for name in PROJECTS:
                shutil.copytree(FIX / name, projects / name)
            config.PROJECTS_DIR = projects
            config.settings.PROJECTS_DIR = projects
            config.LOGS_DIR = work / "logs"
            config.settings.LOGS_DIR = work / "logs"
            release_gate._FAITHFULNESS_CACHE.clear()
            release_gate._THEME_JUDGE_CACHE.clear()
            set_aux(model)
            for name in PROJECTS:
                logger = logging.getLogger(f"u5.{model}.{r}.{name[:10]}")
                logger.setLevel(logging.INFO)
                h = ListHandler()
                logger.addHandler(h)
                row = {"model": model, "repeat": r + 1, "project": name}
                proj = projects / name
                # abstract (with the gate's faithfulness pre-check + regeneration)
                abstract_file = proj / f"{name}{config.SUFFIX_ABSTRACT_GEN}"
                abstract_file.unlink(missing_ok=True)
                t0 = time.time()
                try:
                    row["abstract_ok"] = ep.generate_structured_abstract(name, logger, model=model)
                except Exception as e:
                    row["abstract_error"] = f"{type(e).__name__}: {e}"
                row["abstract_seconds"] = round(time.time() - t0, 1)
                row["abstract_attempts"] = sum("Generating abstract via API" in ln for ln in h.lines)
                text = abstract_file.read_text(encoding="utf-8") if abstract_file.exists() else ""
                row["abstract_words"] = len(text.split())
                v = release_gate.check_faithfulness(name, logger, suffixes=[config.SUFFIX_ABSTRACT_GEN])
                row["abstract_gate"] = v.status.value if hasattr(v.status, "value") else str(v.status)
                row["abstract_gate_detail"] = v.detail[:300]
                (out_dir / f"abstract__{model}__r{r + 1}__{name[:30]}.md").write_text(text, encoding="utf-8")
                # header validation
                formatted = f"{name}{config.SUFFIX_FORMATTED}"
                try:
                    row["headers_ok"] = vp.validate_headers(formatted, model=model, logger=logger)
                    reports = sorted(proj.glob("*header*"), key=lambda p: p.stat().st_mtime)
                    if reports:
                        row["header_verdicts"] = tu.count_header_verdicts(reports[-1].read_text(encoding="utf-8"))
                except Exception as e:
                    row["headers_error"] = f"{type(e).__name__}: {e}"
                # stated purpose
                transcript = (proj / formatted).read_text(encoding="utf-8")
                sections = transcript.count("## Section")
                try:
                    row["purpose"] = abstract_pipeline.extract_opening_purpose(transcript, sections)
                except Exception as e:
                    row["purpose_error"] = f"{type(e).__name__}: {e}"
                # summary coverage (only where a summary exists)
                if (proj / f"{name}{config.SUFFIX_SUMMARY_GEN}").exists():
                    try:
                        row["summary_coverage_ok"] = vp.validate_summary_coverage(name, logger=logger, model=model)
                    except Exception as e:
                        row["summary_coverage_error"] = f"{type(e).__name__}: {e}"
                row["log_errors"] = [ln for ln in h.lines if ln.startswith(("ERROR", "WARNING"))][:12]
                logger.removeHandler(h)
                rows.append(row)
                print(json.dumps({k: row[k] for k in row if k != "log_errors"}), flush=True)
                (out_dir / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
