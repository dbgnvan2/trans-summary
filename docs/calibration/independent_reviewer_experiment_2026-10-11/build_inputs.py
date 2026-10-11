"""Throwaway (2026-10-11): build inputs.json for the DeepSeek experiment.
Run from the repo root: PYTHONPATH=. .venv/bin/python <dir>/build_inputs.py <outdir>
Public gold sources only (D6); dave_g is excluded."""
import json, sys
from pathlib import Path
import faithfulness_judge as fj
S = Path(sys.argv[1]); FIX = Path("tests/fixtures")
gold = json.loads((FIX / "faithfulness_gold/gold.json").read_text())
batches = []
for sid in sorted({"where_roots", "roots_bowen", "kerr_families"}):
    cases = [c for c in gold["cases"] if c["source"] == sid]
    batches.append({"id": f"gold:{sid}", "source": (FIX / gold["sources"][sid]).read_text(),
                    "claims": [c["claim"] for c in cases], "case_ids": [c["id"] for c in cases],
                    "truth": [c["label"] for c in cases]})
WR = FIX / "where_roots" / "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"
for label, src, art in [("roots_bowen", FIX / "roots_bowen_test/formatted.md", FIX / "roots_bowen_test/abstract-generated.md"),
                        ("where_roots", WR / f"{WR.name} - formatted.md", WR / f"{WR.name} - abstract-generated.md")]:
    source = src.read_text()
    batches.append({"id": f"real:{label}", "source": source,
                    "claims": fj.extract_claims(art.read_text(), source=source)})
(S / "inputs.json").write_text(json.dumps(batches))
