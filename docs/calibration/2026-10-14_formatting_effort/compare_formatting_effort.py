"""Format at a lower thinking level (FORMATTING_EFFORT) on claude-sonnet-5-5.

Formats a raw transcript REPEATS times at one effort level (nothing written to the
projects folders), applies the same post-processing as format_transcript, and runs
verify_source_fidelity with no review approvals ("passed" = no review item and within
the gross limits). Records output tokens and cost from the API usage of each call.
Based on docs/calibration/2026-10-11_formatting_haiku/compare_formatting_models.py; that
script set the GUI Effort, which Format no longer reads (it uses FORMATTING_EFFORT).

Usage: python compare_formatting_effort.py OUT_DIR EFFORT REPEATS FILE
Public talks only.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/davemini2/ProjectsLocal/Projects/trans-summary")
import formatting_pipeline as fp  # noqa: E402
import model_specs  # noqa: E402

MODEL = "claude-sonnet-5-5"


def main():
    out_dir, effort, repeats, f = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
    out_dir.mkdir(parents=True, exist_ok=True)
    fp.config.FORMATTING_EFFORT = None if effort == "default" else effort  # in-process only
    usage = {}
    real_call = fp.call_claude_with_retry

    def capture(*a, **k):
        msg = real_call(*a, **k)
        usage["u"] = msg.usage
        return msg
    fp.call_claude_with_retry = capture
    price = model_specs.PRICING[MODEL]
    prompt = fp.load_prompt()
    raw = fp.strip_transcript_validation_footer(f.read_text(encoding="utf-8"))
    results_path = out_dir / f"results_{effort}_{f.stem[:20]}.json"
    results = []
    for r in range(repeats):
        tag = f"{f.stem[:40]}__{effort}__r{r + 1}"
        t0 = time.time()
        try:
            text = fp.format_transcript_with_claude(raw, prompt, model=MODEL)
            u = usage["u"]
            cost = (u.input_tokens * price["input"] + u.output_tokens * price["output"]
                    + (getattr(u, "cache_creation_input_tokens", 0) or 0) * price["cache_write"]
                    + (getattr(u, "cache_read_input_tokens", 0) or 0) * price["cache_read"]) / 1e6
            text, _sic = fp.strip_sic_annotations(text)
            text, _title = fp.strip_leading_title(text)
            text, rewrites = fp.normalize_heading_timestamps(text, raw)
            out = fp.verify_source_fidelity(raw, text)
            c = out["comparison"]
            (out_dir / f"{tag}.md").write_text(text, encoding="utf-8")
            row = {"seconds": round(time.time() - t0, 1), "passed": out["passed"],
                   "review_items": len(out["unresolved"]), "errors": len(out["errors"]),
                   "error_sample": out["errors"][:3],
                   "unresolved_sample": [str(x)[:200] for x in out["unresolved"][:5]],
                   "mismatch_count": c.get("mismatch_count"),
                   "max_contiguous_run": c.get("max_contiguous_run"),
                   "headings": sum(1 for ln in text.splitlines() if ln.startswith("## Section")),
                   "output_tokens": u.output_tokens, "cost": round(cost, 4),
                   "raw_words": len(raw.split()), "formatted_words": len(text.split())}
        except Exception as e:  # record, keep going
            row = {"error": f"{type(e).__name__}: {e}", "seconds": round(time.time() - t0, 1)}
        row.update(file=f.name, effort=effort, repeat=r + 1)
        results.append(row)
        print(json.dumps(row), flush=True)
        results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
