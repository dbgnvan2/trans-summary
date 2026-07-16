"""Smoke test: run the overview-post generator against the real Michael Kerr
fixture on /Volumes/CrucialX9.

Usage:  python3 scripts/run_overview_smoke_test.py

This script:
1. Points config.PROJECTS_DIR at the external-volume projects/ directory.
2. Verifies the four upstream artifacts exist for the test stem.
3. Invokes summarize_transcript with skip_overview=False.
4. Reports where the generated overview file landed.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import pipeline  # noqa: E402
from transcript_utils import setup_logging  # noqa: E402


EXTERNAL_PROJECTS_DIR = Path(
    "/Volumes/CrucialX9/1 MY DISK/BTA ALL/"
    "BTA Video Project - 03 Processed Transcripts ( Trans-Summ)/projects"
)
STEM = "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"


def main():
    if not EXTERNAL_PROJECTS_DIR.exists():
        print(f"ERROR: external projects dir not found: {EXTERNAL_PROJECTS_DIR}")
        return 1

    project_dir = EXTERNAL_PROJECTS_DIR / STEM
    if not project_dir.exists():
        print(f"ERROR: project dir not found: {project_dir}")
        return 1

    required_inputs = [
        config.SUFFIX_YAML,
        config.SUFFIX_ABSTRACT_INIT,
        config.SUFFIX_STRUCTURAL_THEMES,
        config.SUFFIX_TOPICS,
        config.SUFFIX_KEY_TERMS,
    ]
    print(f"Project dir: {project_dir}")
    print("Required input artifacts:")
    for sfx in required_inputs:
        p = project_dir / f"{STEM}{sfx}"
        status = "OK" if p.exists() else "MISSING"
        print(f"  [{status}] {sfx}  -> {p.name}")
        if not p.exists():
            print("ABORT: missing required input.")
            return 1

    # Override PROJECTS_DIR for this run only (singleton + module-level globals,
    # without persisting to runtime_settings.json).
    config.settings.PROJECTS_DIR = EXTERNAL_PROJECTS_DIR
    config.PROJECTS_DIR = EXTERNAL_PROJECTS_DIR

    logger = setup_logging("overview_smoke_test")
    ok = pipeline.summarize_transcript(
        f"{STEM}{config.SUFFIX_YAML}",
        config.settings.DEFAULT_MODEL,
        "Bowen theory",
        "Family systems clinicians and students",
        True,   # skip_extracts_summary
        True,   # skip_emphasis
        True,   # skip_bowen
        True,   # skip_blog
        False,  # skip_overview
        logger=logger,
    )

    overview_path = project_dir / f"{STEM}{config.SUFFIX_OVERVIEW}"
    print("\n=== RESULT ===")
    print(f"summarize_transcript returned: {ok}")
    print(f"Overview file: {overview_path}")
    print(f"Exists: {overview_path.exists()}")
    if overview_path.exists():
        content = overview_path.read_text(encoding="utf-8")
        print(f"Size: {len(content)} chars, {len(content.split())} words")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
