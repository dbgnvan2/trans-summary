"""Generate a GEO-optimized overview post for a single project directory.

Usage:
  python3 transcript_overview.py "<path/to/project_dir>"
  python3 transcript_overview.py "<path>" --focus-keyword "Bowen theory" \
                                          --target-audience "Clinicians"

The project directory is expected to contain the four upstream artifacts:
  - <stem> - yaml.md            (formatted transcript)
  - <stem> - abstract-initial.md  (or abstract-generated.md)
  - <stem> - structural-themes.md
  - <stem> - topics.md
  - <stem> - key-terms.md

The stem is auto-detected from the ` - yaml.md` filename inside the dir.

Purpose: Run the overview-post generator on standalone project folders
         that the GUI cannot resolve directly (e.g., when the folder
         lives outside the configured PROJECTS_DIR or has a non-default
         layout).
Spec:    docs/implementation_plan_2026-05-13.md
"""
import argparse
import sys
from pathlib import Path

import config
import pipeline
from transcript_utils import setup_logging


def _detect_stem(project_dir: Path) -> str:
    """Detect the project stem by finding the unique ' - yaml.md' file."""
    candidates = list(project_dir.glob(f"*{config.SUFFIX_YAML}"))
    if not candidates:
        raise FileNotFoundError(
            f"No '{config.SUFFIX_YAML.strip()}' file found in {project_dir}"
        )
    if len(candidates) > 1:
        names = "\n  ".join(c.name for c in candidates)
        raise ValueError(
            f"Multiple yaml.md files in {project_dir}; expected exactly one:\n  {names}"
        )
    return candidates[0].name[: -len(config.SUFFIX_YAML)]


def _verify_inputs(project_dir: Path, stem: str) -> list[str]:
    """Return a list of missing-input suffixes (empty if all present)."""
    required = [
        config.SUFFIX_YAML,
        config.SUFFIX_STRUCTURAL_THEMES,
        config.SUFFIX_TOPICS,
        config.SUFFIX_KEY_TERMS,
    ]
    abstract_alts = [config.SUFFIX_ABSTRACT_GEN, config.SUFFIX_ABSTRACT_INIT]
    missing = []
    for sfx in required:
        if not (project_dir / f"{stem}{sfx}").exists():
            missing.append(sfx)
    if not any((project_dir / f"{stem}{sfx}").exists() for sfx in abstract_alts):
        missing.append("/".join(abstract_alts))
    return missing


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a GEO-optimized overview post for one project directory."
    )
    parser.add_argument(
        "project_dir",
        type=Path,
        help="Path to the project directory containing the four upstream artifacts.",
    )
    parser.add_argument(
        "--focus-keyword",
        default="Bowen theory",
        help="SEO focus keyword (default: 'Bowen theory').",
    )
    parser.add_argument(
        "--target-audience",
        default="Family systems clinicians and students",
        help="Target audience (default: 'Family systems clinicians and students').",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model override (defaults to config.settings.DEFAULT_MODEL).",
    )
    args = parser.parse_args(argv)

    project_dir = args.project_dir.expanduser().resolve()
    if not project_dir.is_dir():
        print(f"ERROR: not a directory: {project_dir}", file=sys.stderr)
        return 1

    try:
        stem = _detect_stem(project_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    missing = _verify_inputs(project_dir, stem)
    if missing:
        print(
            f"ERROR: required artifacts missing for stem '{stem}':", file=sys.stderr
        )
        for sfx in missing:
            print(f"  - {sfx}", file=sys.stderr)
        return 1

    # Point PROJECTS_DIR at the folder's parent so PROJECTS_DIR/stem resolves
    # to project_dir. Update both singleton and module-level globals; do NOT
    # persist to runtime_settings.json.
    parent_dir = project_dir.parent
    config.settings.PROJECTS_DIR = parent_dir
    config.PROJECTS_DIR = parent_dir

    model = args.model or config.settings.DEFAULT_MODEL
    logger = setup_logging("transcript_overview")
    logger.info("Project dir:    %s", project_dir)
    logger.info("Stem:           %s", stem)
    logger.info("Focus keyword:  %s", args.focus_keyword)
    logger.info("Target audience: %s", args.target_audience)
    logger.info("Model:          %s", model)

    ok = pipeline.summarize_transcript(
        f"{stem}{config.SUFFIX_YAML}",
        model,
        args.focus_keyword,
        args.target_audience,
        True,   # skip_extracts_summary
        True,   # skip_emphasis
        True,   # skip_bowen
        True,   # skip_blog
        False,  # skip_overview
        logger=logger,
    )

    overview_path = project_dir / f"{stem}{config.SUFFIX_OVERVIEW}"
    print(f"\nsummarize_transcript returned: {ok}")
    print(f"Overview file: {overview_path}")
    print(f"Exists: {overview_path.exists()}")
    if overview_path.exists():
        content = overview_path.read_text(encoding="utf-8")
        print(f"Size: {len(content)} chars, {len(content.split())} words")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
