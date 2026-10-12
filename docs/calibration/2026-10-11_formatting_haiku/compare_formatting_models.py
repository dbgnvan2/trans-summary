"""U3 — compare formatting models on the same raw transcripts.

Formats each transcript with each model (no pattern set, nothing written to the
projects folders), applies the same post-processing as format_transcript, and
runs verify_source_fidelity with no review approvals. Writes one JSON with all
counts plus the formatted text of each run.

Usage: python compare_formatting_models.py OUT_DIR MODEL [MODEL...] -- FILE [FILE...]
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/davemini2/ProjectsLocal/Projects/trans-summary")
import formatting_pipeline as fp  # noqa: E402
import model_specs  # noqa: E402

REPEATS = 2


def run_one(raw, prompt, model):
    t0 = time.time()
    text = fp.format_transcript_with_claude(raw, prompt, model=model)
    elapsed = time.time() - t0
    text, sic = fp.strip_sic_annotations(text)
    text, title = fp.strip_leading_title(text)
    text, rewrites = fp.normalize_heading_timestamps(text, raw)
    out = fp.verify_source_fidelity(raw, text)
    c = out["comparison"]
    headings = sum(1 for ln in text.splitlines() if ln.startswith("## Section"))
    return text, {
        "seconds": round(elapsed, 1),
        "passed": out["passed"],
        "errors": len(out["errors"]),
        "error_sample": out["errors"][:5],
        "warnings": len(out["warnings"]),
        "headings": headings,
        "heading_ts_rewrites": len(rewrites),
        "mismatch_count": c.get("mismatch_count"),
        "mismatch_ratio": round(c.get("mismatch_ratio", 0), 5),
        "max_contiguous_run": c.get("max_contiguous_run"),
        "items": len(out["items"]),
        "unresolved": len(out["unresolved"]),
        "raw_words": len(raw.split()),
        "formatted_words": len(text.split()),
    }


def main():
    args = sys.argv[1:]
    out_dir = Path(args[0])
    sep = args.index("--")
    models, files = args[1:sep], args[sep + 1:]
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = fp.load_prompt()
    results = []
    for f in files:
        raw = fp.strip_transcript_validation_footer(Path(f).read_text(encoding="utf-8"))
        for model in models:
            for r in range(REPEATS):
                tag = f"{Path(f).stem[:40]}__{model}__r{r + 1}"
                try:
                    text, row = run_one(raw, prompt, model)
                    (out_dir / f"{tag}.md").write_text(text, encoding="utf-8")
                except Exception as e:  # record, keep going
                    row = {"error": f"{type(e).__name__}: {e}"}
                row.update(file=Path(f).name, model=model, repeat=r + 1)
                results.append(row)
                print(json.dumps(row), flush=True)
                (out_dir / "results.json").write_text(json.dumps(
                    {"prompt_file": str(fp.config.PROMPT_FORMATTING_FILENAME),
                     "pricing": {m: model_specs.PRICING.get(m) for m in models},
                     "results": results}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
