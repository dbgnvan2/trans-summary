"""Tests for reading the transcription tool's "incomplete" warning (plan IT1-IT3).

Spec: docs/plan_incomplete_transcript_2026-10-19.md

The incomplete header is copied word for word from the real Systems Biology raw
transcript (BTA processed projects, Systems Biology ... _20260718_155038_v-valid-5m).
The complete headers are copied from real KCFC raw transcripts.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
import release_gate
import source_completeness as sc
import ts_gui

REAL_INCOMPLETE_HEADER = """TRANSCRIPT
==========
Source file:  Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25.mp3
Date:         2026-07-18
Duration:     01:28:00
Speakers:     Unknown
Warnings:     Cloud transcription used chunked upload (12 part(s), 480s each).; Cloud transcription incomplete: transcribed 5 of 12 chunks; missing time ranges (approx.): 00:24:00-00:32:00, 00:32:00-00:40:00, 00:40:00-00:48:00, 00:56:00-01:04:00, 01:04:00-01:12:00, 01:12:00-01:20:00, 01:28:00-01:36:00

--------------------------------------------------


[00:00:00]

Okay, well, good afternoon or good morning, whichever it is, wherever you are.
"""

# Real headers without the warning (KCFC ALL/2021 videos).
CHUNKED_ONLY_HEADER = """TRANSCRIPT
==========
Source file:  June 2021.mp4
Date:         2026-07-10
Duration:     01:32:08
Speakers:     Unknown
Warnings:     Cloud transcription used chunked upload (12 part(s), 480s each).

--------------------------------------------------

[00:00:00]

Welcome, everyone.
"""

WHISPERX_HEADER = """TRANSCRIPT
==========
Source file:  April 2021.mp4
Date:         2026-07-09
Duration:     01:33:23
Speakers:     Unknown
Warnings:     Initial prompt truncated to 224 tokens.; initial_prompt not supported by this WhisperX version; skipped.; HF token missing. Diarization disabled.

--------------------------------------------------

[00:00:00]

Welcome, everyone.
"""

DROPPED_SEGMENTS_HEADER = """TRANSCRIPT
==========
Source file:  Dec 2021.mp4
Date:         2026-08-05
Duration:     01:27:13
Speakers:     Unknown
Warnings:     Cloud transcription used chunked upload (11 part(s), 480s each).; Dropped 6 of 650 segment(s) as suspected hallucination (repeated phrase and/or high no-speech probability).

--------------------------------------------------

[00:00:00]

Welcome, everyone.
"""

NO_WARNINGS_LINE_HEADER = """TRANSCRIPT
==========
Source file:  Sept 2021-2.mp4
Date:         2026-07-10
Duration:     00:18:37
Speakers:     Unknown

--------------------------------------------------

[00:00:00]

Welcome, everyone.
"""

PLAIN_TRANSCRIPT = "[00:00:03] A: Okay.\n[00:00:05] A: Welcome.\n"


def _with_warnings(value: str) -> str:
    return REAL_INCOMPLETE_HEADER.replace(
        REAL_INCOMPLETE_HEADER.splitlines()[6], f"Warnings:     {value}")


# --------------------------------------------------------------------------- IT1

def test_it1a_real_incomplete_header_is_parsed():
    c = sc.read_header(REAL_INCOMPLETE_HEADER)
    assert c.has_header is True
    assert c.incomplete is True
    assert c.details_readable is True
    assert (c.chunks_transcribed, c.chunks_total) == (5, 12)
    assert len(c.missing_ranges) == 7
    assert c.missing_ranges[0] == ("00:24:00", "00:32:00")
    assert c.missing_ranges[-1] == ("01:28:00", "01:36:00")
    assert c.warnings == [
        "Cloud transcription used chunked upload (12 part(s), 480s each).",
        "Cloud transcription incomplete: transcribed 5 of 12 chunks; missing time ranges "
        "(approx.): 00:24:00-00:32:00, 00:32:00-00:40:00, 00:40:00-00:48:00, "
        "00:56:00-01:04:00, 01:04:00-01:12:00, 01:12:00-01:20:00, 01:28:00-01:36:00",
    ]
    assert c.incomplete_warning == c.warnings[1]

    # The incomplete warning ends with a range, not a period; a warning after it is
    # still kept apart (it starts with a capital).
    dropped = ("Dropped 6 of 650 segment(s) as suspected hallucination (repeated phrase "
               "and/or high no-speech probability).")
    joined = sc.read_header(_with_warnings(
        REAL_INCOMPLETE_HEADER.splitlines()[6].split(":", 1)[1].strip() + "; " + dropped))
    assert joined.warnings[1:] == [c.incomplete_warning, dropped]
    assert joined.incomplete_warning == c.incomplete_warning
    assert joined.details_readable is True


def test_it1b_complete_headers_not_flagged():
    chunked = sc.read_header(CHUNKED_ONLY_HEADER)
    assert chunked.has_header and not chunked.incomplete
    assert chunked.warnings == ["Cloud transcription used chunked upload (12 part(s), 480s each)."]

    whisperx = sc.read_header(WHISPERX_HEADER)
    assert whisperx.has_header and not whisperx.incomplete
    # The tool separates warnings with ".;"; one warning itself contains "; ".
    assert whisperx.warnings == [
        "Initial prompt truncated to 224 tokens.",
        "initial_prompt not supported by this WhisperX version; skipped.",
        "HF token missing. Diarization disabled.",
    ]

    dropped = sc.read_header(DROPPED_SEGMENTS_HEADER)
    assert dropped.has_header and not dropped.incomplete
    assert dropped.warnings[1] == (
        "Dropped 6 of 650 segment(s) as suspected hallucination (repeated phrase "
        "and/or high no-speech probability).")

    no_line = sc.read_header(NO_WARNINGS_LINE_HEADER)
    assert no_line.has_header and not no_line.incomplete
    assert no_line.warnings == []


def test_it1c_malformed_header_still_flagged():
    cases = [
        "Cloud transcription incomplete.",  # no counts, no ranges
        "Cloud transcription incomplete: transcribed 5 of 12 chunks",  # no ranges
        "Cloud transcription incomplete: transcribed 5 of 12 chunks; missing time ranges "
        "(approx.): 00:24-00:32, 00:56-01:04",  # ranges not hh:mm:ss
    ]
    for value in cases:
        c = sc.read_header(_with_warnings(value))
        assert c.incomplete is True, value
        assert c.details_readable is False, value
        message = sc.incomplete_message(c, "x.txt")
        assert value.rstrip(".") in message, value
        assert "could not be read" in message, value


def test_it1c_reworded_warning_still_flagged():
    ranges = ("00:24:00-00:32:00, 00:32:00-00:40:00, 00:40:00-00:48:00, 00:56:00-01:04:00, "
              "01:04:00-01:12:00, 01:12:00-01:20:00, 01:28:00-01:36:00")
    readable = [
        f"Cloud transcription was incomplete: transcribed 5 of 12 chunks; missing time "
        f"ranges (approx.): {ranges}",
        f"Cloud transcription failed for 7 of 12 chunks; transcribed 5 of 12 chunks; "
        f"missing time ranges (approx.): {ranges}",
    ]
    for value in readable:
        c = sc.read_header(_with_warnings(value))
        assert c.incomplete and c.details_readable, value
        assert (c.chunks_transcribed, c.chunks_total) == (5, 12), value
    unreadable = [
        "Cloud transcription stopped early: transcribed 5 of 12 chunks.",  # count only
        f"Some audio was skipped; missing time ranges (approx.): {ranges}",  # ranges only
    ]
    for value in unreadable:
        c = sc.read_header(_with_warnings(value))
        assert c.incomplete and not c.details_readable, value


def test_it1c_range_count_mismatch_is_unreadable():
    # 5 of 12 chunks means 7 missing ranges; only 2 here, so the details don't add up
    # and the tool's own words are quoted instead of a partial list.
    value = ("Cloud transcription incomplete: transcribed 5 of 12 chunks; missing time "
             "ranges (approx.): 00:24:00-00:32:00, 00:56:00-01:04:00")
    c = sc.read_header(_with_warnings(value))
    assert c.incomplete and not c.details_readable
    assert value in sc.incomplete_message(c, "x.txt")


def test_it1d_plain_transcript_and_bom():
    plain = sc.read_header(PLAIN_TRANSCRIPT)
    assert plain.has_header is False
    assert plain.incomplete is False
    assert plain.warnings == []

    bom = sc.read_header("﻿" + REAL_INCOMPLETE_HEADER)
    assert bom.has_header and bom.incomplete
    assert (bom.chunks_transcribed, bom.chunks_total) == (5, 12)


def test_it1d_header_found_wherever_the_fidelity_check_finds_it():
    # Whatever detect_transcript_source_format treats as a header (and the source-
    # fidelity check strips) is read here too: a leading blank line, an indented
    # Warnings line, a line above TRANSCRIPT.
    from formatting_pipeline import detect_transcript_source_format
    lines = REAL_INCOMPLETE_HEADER.splitlines(keepends=True)
    variants = {
        "leading blank line": "\n" + REAL_INCOMPLETE_HEADER,
        "indented Warnings": "".join(lines[:6]) + "  " + "".join(lines[6:]),
        "line above TRANSCRIPT": "Systems Biology talk\n" + REAL_INCOMPLETE_HEADER,
    }
    for name, text in variants.items():
        assert detect_transcript_source_format(text) == "trx_whisper_wrapped", name
        c = sc.read_header(text)
        assert c.has_header and c.incomplete and c.details_readable, name


def test_it1e_body_text_and_near_miss_not_flagged():
    body_mention = CHUNKED_ONLY_HEADER + (
        "\nWarnings: Cloud transcription incomplete: transcribed 1 of 9 chunks\n"
        "He said the transcription incomplete warning was a joke.\n")
    c = sc.read_header(body_mention)
    assert c.incomplete is False
    assert c.warnings == ["Cloud transcription used chunked upload (12 part(s), 480s each)."]

    near_miss = sc.read_header(WHISPERX_HEADER)  # "truncated", not the marker
    assert near_miss.incomplete is False

    all_chunks = sc.read_header(_with_warnings("Cloud transcription: transcribed 12 of 12 chunks."))
    assert all_chunks.incomplete is False


def test_it1f_message_joins_touching_ranges():
    c = sc.read_header(REAL_INCOMPLETE_HEADER)
    message = sc.incomplete_message(c, "Systems Biology.txt")
    assert "transcribed 5 of 12 chunks" in message
    assert "00:24:00-00:48:00, 00:56:00-01:20:00, 01:28:00-01:36:00" in message
    assert "00:32:00" not in message  # joined into 00:24:00-00:48:00
    assert "Systems Biology.txt" in message
    assert "minute" not in message  # no minutes-missing figure
    assert sc.join_ranges([("00:00:00", "00:08:00"), ("00:16:00", "00:24:00")]) == [
        ("00:00:00", "00:08:00"), ("00:16:00", "00:24:00")]


def test_it1f_notices_levels():
    notices = sc.notices(sc.read_header(REAL_INCOMPLETE_HEADER), "s.txt")
    assert [level for level, _ in notices] == ["info", "warning"]
    assert notices[0][1].startswith("Transcription tool warnings (s.txt): ")
    assert sc.notices(sc.read_header(CHUNKED_ONLY_HEADER), "s.txt")[0][0] == "info"
    assert len(sc.notices(sc.read_header(CHUNKED_ONLY_HEADER), "s.txt")) == 1
    assert sc.notices(sc.read_header(PLAIN_TRANSCRIPT), "s.txt") == []


# --------------------------------------------------------------------------- IT3

def _project(tmp_path, monkeypatch, raw_text, base="Talk - Speaker - 2021-06-25"):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "SOURCE_DIR", tmp_path / "source")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    proj = tmp_path / "projects" / base
    proj.mkdir(parents=True)
    if raw_text is not None:
        (proj / f"{base}{config.SUFFIX_RAW_SOURCE}").write_text(raw_text, encoding="utf-8")
    return base, proj


def test_it3a_gate_warns_with_missing_ranges(tmp_path, monkeypatch):
    base, _ = _project(tmp_path, monkeypatch, REAL_INCOMPLETE_HEADER)
    v = release_gate.check_source_completeness(base)
    assert v.status is release_gate.Status.WARN
    assert "transcribed 5 of 12 chunks" in v.detail
    assert len(v.items) == 1
    item = v.items[0]
    assert item["file"] == f"{base}{config.SUFFIX_RAW_SOURCE}"
    assert (item["chunks_transcribed"], item["chunks_total"]) == (5, 12)
    assert item["missing_ranges"][0] == "00:24:00-00:32:00"
    assert len(item["missing_ranges"]) == 7
    assert item["warning"].startswith("Cloud transcription incomplete")


def test_it3b_complete_and_plain_sources_pass(tmp_path, monkeypatch):
    base, proj = _project(tmp_path, monkeypatch, CHUNKED_ONLY_HEADER)
    v = release_gate.check_source_completeness(base)
    assert v.status is release_gate.Status.PASS
    assert "no known incomplete-transcript warning" in v.detail

    (proj / f"{base}{config.SUFFIX_RAW_SOURCE}").write_text(PLAIN_TRANSCRIPT, encoding="utf-8")
    v = release_gate.check_source_completeness(base)
    assert v.status is release_gate.Status.PASS
    assert "not stated" in v.detail


def test_it3c_missing_source_is_nonblocking_error(tmp_path, monkeypatch):
    base, _ = _project(tmp_path, monkeypatch, None)
    v = release_gate.check_source_completeness(base)
    assert v.status is release_gate.Status.ERROR
    assert release_gate.decide([v]).decision is release_gate.Decision.ALLOW_WITH_WARNINGS


def test_it3d_incomplete_source_allows_with_warnings(tmp_path, monkeypatch):
    assert "source_completeness" in [n for n, _ in release_gate.DEFAULT_CHECKS]
    assert "source_completeness" not in config.GATE_BLOCKING_CHECKS
    base, _ = _project(tmp_path, monkeypatch, REAL_INCOMPLETE_HEADER)
    checks = [("source_completeness", release_gate.check_source_completeness)]
    decision = release_gate.run_gate(base, checks=checks)
    assert decision.decision is release_gate.Decision.ALLOW_WITH_WARNINGS
    assert decision.blockers == []


def test_it3e_manifest_records_missing_ranges(tmp_path, monkeypatch):
    base, proj = _project(tmp_path, monkeypatch, REAL_INCOMPLETE_HEADER)
    decision = release_gate.run_gate(
        base, checks=[("source_completeness", release_gate.check_source_completeness)])
    path = release_gate.write_manifest(base, decision, "2026-10-19T00:00:00")
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    verdict = manifest["gate"]["verdicts"][0]
    assert verdict["check"] == "source_completeness"
    assert verdict["status"] == "WARN"
    assert verdict["items"][0]["missing_ranges"][-1] == "01:28:00-01:36:00"


def test_it3f_malformed_source_warns(tmp_path, monkeypatch):
    base, _ = _project(tmp_path, monkeypatch,
                       _with_warnings("Cloud transcription incomplete."))
    v = release_gate.check_source_completeness(base)
    assert v.status is release_gate.Status.WARN
    assert "could not be read" in v.detail
    assert v.items[0]["missing_ranges"] == []


def test_it3g_replaced_source_clears_the_warning(tmp_path, monkeypatch):
    base, proj = _project(tmp_path, monkeypatch, REAL_INCOMPLETE_HEADER)
    assert release_gate.check_source_completeness(base).status is release_gate.Status.WARN
    (proj / f"{base}{config.SUFFIX_RAW_SOURCE}").write_text(CHUNKED_ONLY_HEADER, encoding="utf-8")
    assert release_gate.check_source_completeness(base).status is release_gate.Status.PASS


def test_it3a_reads_the_source_fidelity_matched(tmp_path, monkeypatch):
    # Without a raw-source copy, several source files can match the project name.
    # Completeness reads the one source_fidelity judges the formatted transcript
    # against, so the two checks name the same file.
    import formatting_pipeline as fp

    base, proj = _project(tmp_path, monkeypatch, None)
    src = tmp_path / "source"
    src.mkdir()
    (src / f"{base}.txt").write_text(CHUNKED_ONLY_HEADER, encoding="utf-8")
    (src / f"{base}_validated.txt").write_text(REAL_INCOMPLETE_HEADER, encoding="utf-8")
    formatted = proj / f"{base}{config.SUFFIX_FORMATTED}"

    def fake_verify(raw, formatted_text, approvals=None):
        passed = formatted_text.strip() in raw
        return {"passed": passed, "errors": [] if passed else ["differs"],
                "comparison": {"mismatch_count": 0}}

    with patch.object(fp, "verify_source_fidelity", fake_verify):
        formatted.write_text("Welcome, everyone.", encoding="utf-8")  # the complete file
        assert f"{base}.txt" in release_gate.check_source_fidelity(base).detail
        v = release_gate.check_source_completeness(base)
        assert v.status is release_gate.Status.PASS
        assert "(1 source file(s))" in v.detail

        formatted.write_text("Okay, well, good afternoon", encoding="utf-8")  # the partial one
        assert f"{base}_validated.txt" in release_gate.check_source_fidelity(base).detail
        v = release_gate.check_source_completeness(base)
        assert v.status is release_gate.Status.WARN
        assert [i["file"] for i in v.items] == [f"{base}_validated.txt"]

    # No formatted transcript to choose by: every candidate is read, and one
    # incomplete file is enough to warn.
    formatted.unlink()
    v = release_gate.check_source_completeness(base)
    assert v.status is release_gate.Status.WARN
    assert [i["file"] for i in v.items] == [f"{base}_validated.txt"]


# --------------------------------------------------------------------------- IT2 (GUI)

def _gui(tmp_path, monkeypatch, selected_text, base="Talk - Speaker - 2021-06-25"):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = base
    gui.logger = object()
    gui.log = MagicMock()
    gui.processing = False
    if selected_text is None:
        gui.selected_file = tmp_path / "source" / f"{base}_validated.txt"  # does not exist
    else:
        (tmp_path / "source").mkdir(exist_ok=True)
        gui.selected_file = tmp_path / "source" / f"{base}_validated.txt"
        gui.selected_file.write_text(selected_text, encoding="utf-8")
    return gui


def _logged(gui):
    return [str(c.args[0]) % c.args[1:] if len(c.args) > 1 else str(c.args[0])
            for c in gui.log.call_args_list]


def test_it2b_run_log_warns_before_first_stage(tmp_path, monkeypatch):
    gui = _gui(tmp_path, monkeypatch, REAL_INCOMPLETE_HEADER)
    order = []
    gui.log.side_effect = lambda *a, **_k: order.append(("log", str(a[0])))

    def _runner(key):
        def run():
            order.append(("stage", key))
            return True
        return run

    gui.stage_runners = {k: _runner(k) for k, _ in ts_gui.STAGE_DEFINITIONS}
    with patch.object(gui, "_run_cost_estimation", return_value=True), \
         patch("ts_gui.analyze_token_usage.generate_usage_report", return_value="report"):
        assert gui._run_selected_stages({"structured_summary", "gen_abstract"}) is True

    warn_at = next(i for i, (kind, text) in enumerate(order)
                   if kind == "log" and text.startswith("⚠️ The source transcript is incomplete"))
    first_stage = next(i for i, (kind, _) in enumerate(order) if kind == "stage")
    assert warn_at < first_stage
    assert [t for kind, t in order if kind == "stage"] == ["structured_summary", "gen_abstract"]
    assert "00:24:00-00:48:00" in order[warn_at][1]


def test_it2c_confirm_dialog_names_missing_ranges(tmp_path, monkeypatch):
    for text, expect in ((REAL_INCOMPLETE_HEADER, True), (CHUNKED_ONLY_HEADER, False)):
        gui = _gui(tmp_path, monkeypatch, text)
        gui.stage_vars = {k: MagicMock(get=MagicMock(return_value=k == "structured_summary"))
                          for k, _ in ts_gui.STAGE_DEFINITIONS}
        with patch.object(gui, "_validate_stage_dependencies", return_value=[]), \
             patch("ts_gui.messagebox.askyesno", return_value=False) as ask, \
             patch.object(gui, "run_task_in_thread") as run:
            gui.do_run_selected()
        run.assert_not_called()  # the dialog answered No
        dialog_text = ask.call_args.args[1]
        assert ("The source transcript is incomplete" in dialog_text) is expect
        assert ("01:28:00-01:36:00" in dialog_text) is expect
        assert dialog_text.rstrip().endswith("Continue?")


def test_it2d_missing_source_is_reported_not_fatal(tmp_path, monkeypatch):
    gui = _gui(tmp_path, monkeypatch, None)
    gui.stage_runners = {k: MagicMock(return_value=True) for k, _ in ts_gui.STAGE_DEFINITIONS}
    with patch.object(gui, "_run_cost_estimation", return_value=True), \
         patch("ts_gui.analyze_token_usage.generate_usage_report", return_value="report"):
        assert gui._run_selected_stages({"structured_summary"}) is True
    assert any(line.startswith("Could not check whether the source transcript is complete")
               for line in _logged(gui))
    gui.stage_runners["structured_summary"].assert_called_once()


def test_it2d_falls_back_to_the_raw_source_copy(tmp_path, monkeypatch):
    gui = _gui(tmp_path, monkeypatch, None)
    proj = tmp_path / "projects" / gui.base_name
    proj.mkdir(parents=True)
    (proj / f"{gui.base_name}{config.SUFFIX_RAW_SOURCE}").write_text(
        REAL_INCOMPLETE_HEADER, encoding="utf-8")
    gui._log_source_completeness()
    assert any(line.startswith("⚠️ The source transcript is incomplete")
               and config.SUFFIX_RAW_SOURCE.strip(" -") in line for line in _logged(gui))


def test_it2d_reads_the_file_the_run_uses(tmp_path, monkeypatch):
    # Format reads the selected file; later stages reuse the formatted transcript,
    # which was checked against the raw-source copy (the file the gate reads).
    for case, (selected, copy) in enumerate(((CHUNKED_ONLY_HEADER, REAL_INCOMPLETE_HEADER),
                                             (REAL_INCOMPLETE_HEADER, CHUNKED_ONLY_HEADER))):
        root = tmp_path / f"case{case}"
        root.mkdir()
        gui = _gui(root, monkeypatch, selected)
        proj = root / "projects" / gui.base_name
        proj.mkdir(parents=True)
        (proj / f"{gui.base_name}{config.SUFFIX_RAW_SOURCE}").write_text(copy, encoding="utf-8")
        later = gui._source_incomplete_message({"structured_summary"})
        with_format = gui._source_incomplete_message({"format", "structured_summary"})
        assert (later is not None) is (copy is REAL_INCOMPLETE_HEADER)
        assert (with_format is not None) is (selected is REAL_INCOMPLETE_HEADER)
        if later:
            assert config.SUFFIX_RAW_SOURCE.strip(" -") in later
        if with_format:
            assert gui.selected_file.name in with_format


def test_it2e_all_transcriber_warnings_logged(tmp_path, monkeypatch):
    gui = _gui(tmp_path, monkeypatch, DROPPED_SEGMENTS_HEADER)
    gui._log_source_completeness()
    lines = _logged(gui)
    warn_lines = [l for l in lines if l.startswith("Transcription tool warnings")]
    assert len(warn_lines) == 1
    assert ("Cloud transcription used chunked upload (11 part(s), 480s each).; Dropped 6 of "
            "650 segment(s) as suspected hallucination") in warn_lines[0]
    assert not any("incomplete" in l for l in lines)


def test_it2e_plain_source_says_not_stated(tmp_path, monkeypatch):
    gui = _gui(tmp_path, monkeypatch, PLAIN_TRANSCRIPT)
    gui._log_source_completeness()
    assert any("completeness not stated" in l for l in _logged(gui))
