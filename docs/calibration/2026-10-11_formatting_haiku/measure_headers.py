"""HV measurement: batched header validation on real formatted transcripts.
Usage: python measure_headers.py OUT_DIR MODEL [MODEL...] -- FORMATTED.md [...]"""
import csv, json, logging, shutil, sys
from pathlib import Path
sys.path.insert(0, "/Users/davemini2/ProjectsLocal/Projects/trans-summary")
import config, transcript_utils as tu, transcript_validate_headers as tvh
args = sys.argv[1:]; out = Path(args[0]); sep = args.index("--")
models, files = args[1:sep], args[sep + 1:]
rows = []
for model in models:
    for f in files:
        base = f"Talk {len(rows)} - Michael Kerr - 2021-01-01"
        work = out / f"{model}_{len(rows)}"; proj = work / "projects" / base
        proj.mkdir(parents=True, exist_ok=True)
        dst = proj / f"{base}{config.SUFFIX_FORMATTED}"; shutil.copy(f, dst)
        config.PROJECTS_DIR = config.settings.PROJECTS_DIR = work / "projects"
        config.LOGS_DIR = config.settings.LOGS_DIR = work / "logs"
        logger = logging.getLogger(f"hv.{len(rows)}"); logger.setLevel(logging.INFO)
        lines = []
        h = logging.Handler(); h.emit = lambda r, L=lines: L.append(f"{r.levelname}: {r.getMessage()}"); logger.addHandler(h)
        ok = tvh.HeaderValidator(tu.resolve_anthropic_key(), logger).run(dst, model=model)
        report = (proj / f"{base}{config.SUFFIX_HEADER_VAL_REPORT}").read_text(encoding="utf-8")
        usage = []
        for c in (work / "logs").rglob("token_usage.csv"):
            with open(c) as fh:
                for r in csv.reader(fh):
                    if r and r[0][:2] == "20": usage.append(int(r[6]))  # "Tokens Response"
        row = {"model": model, "file": Path(f).name[:40], "ok": ok,
               "sections": dst.read_text().count("\n## ") + 1,
               "verdicts": tu.count_header_verdicts(report),
               "batch_output_tokens": usage,
               "errors": [l for l in lines if l.startswith("ERROR")][:5]}
        rows.append(row); print(json.dumps(row), flush=True)
(out / "results.json").write_text(json.dumps(rows, indent=2))
