"""AQ measurement: regenerate a talk's abstract N times through the real stage
(extraction_pipeline.generate_structured_abstract, with its faithfulness judge and
retries, model = AUX_MODEL as in the GUI) and report whether it passed and its Q&A
sentence.

    python measure_abstract_qa.py <projects dir (a copy)> "<base name>" <N> > results.txt

Public talks only. The projects dir is modified (abstract files are overwritten).
"""
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import abstract_pipeline as ap  # noqa: E402
import config  # noqa: E402
import extraction_pipeline as ep  # noqa: E402
from transcript_utils import load_project_transcript, strip_yaml_frontmatter  # noqa: E402


def main(projects: Path, base: str, n: int) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    log = logging.getLogger("aq")
    config.PROJECTS_DIR = projects
    pct, _topics = ap.calculate_qa_percentage(
        load_project_transcript(base, logger=log), ep.parse_filename_metadata(base).get("presenter"))
    print(f"{base}: Q&A share {pct}% -> include_qa_note "
          f"{pct > config.ABSTRACT_QA_NOTE_MIN_PCT}; model {config.settings.AUX_MODEL}")
    for k in range(1, n + 1):
        ok = ep.generate_structured_abstract(base, log, model=config.settings.AUX_MODEL)
        text = strip_yaml_frontmatter(
            (projects / base / f"{base}{config.SUFFIX_ABSTRACT_GEN}").read_text(encoding="utf-8"))
        qa = [s for s in re.split(r"(?<=[.!?])\s+", text)
              if re.search(r"question|q&a|audience|asked|discussion|participant", s, re.I)]
        print(f"run {k}: {'PASS' if ok else 'FAIL'} | {len(text.split())} words | Q&A sentence: {qa}")
        sys.stdout.flush()


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]))
