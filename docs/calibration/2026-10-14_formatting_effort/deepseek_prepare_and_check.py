"""Step 1 (prepare): write the exact formatting prompt Format sends for each transcript.
Step 3 (check): apply format_transcript's post-processing to each DeepSeek reply and run
verify_source_fidelity, as compare_formatting_effort.py does for Sonnet.

Usage: python deepseek_prepare_and_check.py prepare OUT_DIR FILE...
       python deepseek_prepare_and_check.py check OUT_DIR FILE...
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/davemini2/ProjectsLocal/Projects/trans-summary")
import formatting_pipeline as fp  # noqa: E402


def main():
    mode, out_dir, files = sys.argv[1], Path(sys.argv[2]), [Path(f) for f in sys.argv[3:]]
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = fp.load_prompt()
    for f in files:
        raw = fp.strip_transcript_validation_footer(f.read_text(encoding="utf-8"))
        short = f.stem[:20]
        if mode == "prepare":
            # Same text as format_transcript_with_claude's full_prompt.
            (out_dir / f"prompt_{short}.txt").write_text(
                f"{prompt}\n\n---\n\nRAW TRANSCRIPT:\n\n{raw}", encoding="utf-8")
            continue
        for meta_path in sorted(out_dir.glob(f"ds_{short}_r*.json")):
            meta = json.loads(meta_path.read_text())
            row = {"file": f.name, "run": meta_path.stem, **{k: meta.get(k) for k in
                   ("seconds", "finish_reason", "usage", "error")}}
            txt = meta_path.with_suffix(".txt")
            if txt.exists() and not meta.get("error"):
                text = txt.read_text(encoding="utf-8")
                text, _sic = fp.strip_sic_annotations(text)
                text, _title = fp.strip_leading_title(text)
                text, _rw = fp.normalize_heading_timestamps(text, raw)
                out = fp.verify_source_fidelity(raw, text)
                c = out["comparison"]
                row.update(passed=out["passed"], review_items=len(out["unresolved"]),
                           errors=len(out["errors"]), error_sample=out["errors"][:3],
                           unresolved_sample=[str(x)[:200] for x in out["unresolved"][:5]],
                           mismatch_count=c.get("mismatch_count"),
                           max_contiguous_run=c.get("max_contiguous_run"),
                           headings=sum(1 for ln in text.splitlines() if ln.startswith("## Section")),
                           raw_words=len(raw.split()), formatted_words=len(text.split()))
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
