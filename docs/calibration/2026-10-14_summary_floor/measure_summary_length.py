"""SL3 measurement: summary length and coverage gate status for the summary prompt as it
is on disk (run once with the asked minimum removed from the prompt, once with it).

For each talk in a copied end-to-end project folder, generate N summaries the way
extraction_pipeline.generate_structured_summary does (same input, model, cached
transcript), with the accepted floor switched off so each draft's own length shows, then run the
real coverage validation (validation_pipeline.validate_summary_coverage) on it.

    python measure_summary_length.py <projects dir (a copy)> <N> > results.txt

Public talks only. The projects dir is modified (summary files are overwritten).
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import config  # noqa: E402
import extraction_pipeline as ep  # noqa: E402
import summary_pipeline as sp  # noqa: E402
import validation_pipeline as vp  # noqa: E402
from transcript_utils import create_system_message_with_cache, get_anthropic_client  # noqa: E402

MODEL = "claude-sonnet-5-5"  # the end-to-end runs' main model


def main(projects: Path, n: int) -> None:
    logging.basicConfig(level=logging.WARNING)
    log = logging.getLogger("sl3")
    config.PROJECTS_DIR = projects
    floor, ceiling = config.summary_word_bounds(config.DEFAULT_SUMMARY_WORD_COUNT)
    config.SUMMARY_LENGTH_ACCEPT_MIN_RATIO = 0.0  # measure the drafts as written
    client = get_anthropic_client()
    print(f"model={MODEL} target={config.DEFAULT_SUMMARY_WORD_COUNT} "
          f"accepted floor (not applied here)={floor} max={ceiling}")
    for talk in sorted(p for p in projects.iterdir() if p.is_dir()):
        base = talk.name
        transcript = ep.load_project_transcript(base, logger=log)
        topics = ep._load_section_from_project_file(base, config.SUFFIX_TOPICS,
                                                    ["Topics", "Key Topics"])
        themes = ep._load_section_from_project_file(
            base, config.SUFFIX_INTERPRETIVE_THEMES,
            ["Interpretive Themes", "Themes", "Key Themes", "Interpretive / Process Themes"])
        si = sp.prepare_summary_input(metadata=ep.parse_filename_metadata(base),
                                      topics_markdown=topics, themes_markdown=themes,
                                      transcript=transcript,
                                      target_word_count=config.DEFAULT_SUMMARY_WORD_COUNT)
        system = create_system_message_with_cache(transcript)
        for k in range(1, n + 1):
            text = sp.generate_summary(si, client, model=MODEL, system=system)
            words = len(text.split())
            out = talk / f"{base}{config.SUFFIX_SUMMARY_GEN}"
            out.write_text(text, encoding="utf-8")
            (talk / f"{base}{config.SUFFIX_SUMMARY_GEN}.sl3-{k}").write_text(text, encoding="utf-8")
            vp.validate_summary_coverage(base, logger=log)
            report = (talk / f"{base}{config.SUFFIX_SUMMARY_VAL}").read_text(encoding="utf-8")
            gate = next((l for l in report.splitlines() if l.startswith("Gate status")), "?")
            missing = [l.strip() for l in report.splitlines() if "MISSING [REQUIRED]" in l]
            print(f"{base[:30]:30s} draft {k}: {words} words "
                  f"({'under' if words < floor else 'within'} floor {floor}) | {gate} | {missing}")
            sys.stdout.flush()


if __name__ == "__main__":
    main(Path(sys.argv[1]), int(sys.argv[2]))
