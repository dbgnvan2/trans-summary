"""Archive Logs must zip only the log files, never its own archives folder.

On 2026-10-09 the GUI's Archive Logs zipped the whole logs/ directory, including
logs/archives/ where the zip was being written: the zip grew by reading itself
(20 GB in 9 minutes against a few MB of logs) until the GUI was killed.
"""
import zipfile
from unittest.mock import MagicMock

import config
import transcript_clean_logs
import transcript_utils as tu
import ts_gui


def _logs_dir(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    (logs / "archives").mkdir(parents=True)
    (logs / "gui_1.log").write_text("line\n", encoding="utf-8")
    (logs / "generate_pdf_1.log").write_text("pdf\n", encoding="utf-8")
    (logs / "token_usage.csv").write_text("a,b\n", encoding="utf-8")
    for keep in ("runtime_settings.json", "gate_judge_cache.json", "validation_memory.json"):
        (logs / keep).write_text("{}", encoding="utf-8")
    # An earlier archive that must not be swallowed into the new one.
    (logs / "archives" / "logs_old.zip").write_bytes(b"x" * 100_000)
    monkeypatch.setattr(config, "LOGS_DIR", logs)
    return logs


def test_archive_contains_only_log_files(tmp_path, monkeypatch):
    logs = _logs_dir(tmp_path, monkeypatch)
    path = tu.archive_logs(MagicMock())
    assert path is not None and path.parent == logs / "archives"
    names = sorted(zipfile.ZipFile(path).namelist())
    assert names == ["generate_pdf_1.log", "gui_1.log", "token_usage.csv"]
    assert path.stat().st_size < 10_000  # not the 100 kB old archive inside it
    # Originals removed; non-log state and the old archive kept.
    assert not list(logs.glob("*.log")) and not (logs / "token_usage.csv").exists()
    for keep in ("runtime_settings.json", "gate_judge_cache.json", "validation_memory.json"):
        assert (logs / keep).exists()
    assert (logs / "archives" / "logs_old.zip").exists()
    assert not list((logs / "archives").glob("*.tmp"))


def test_archive_failure_keeps_originals(tmp_path, monkeypatch):
    logs = _logs_dir(tmp_path, monkeypatch)

    def _boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(tu.zipfile, "ZipFile", _boom)
    assert tu.archive_logs(MagicMock()) is None
    assert (logs / "gui_1.log").exists() and (logs / "token_usage.csv").exists()
    assert sorted(p.name for p in (logs / "archives").iterdir()) == ["logs_old.zip"]


def test_gui_and_cli_use_the_shared_archiver(tmp_path, monkeypatch):
    # P5: the GUI button and the CLI must not have separate archive code.
    _logs_dir(tmp_path, monkeypatch)  # never the real logs/
    called = []

    def _fake(logger=None):
        called.append(1)
        return tmp_path / "x.zip"

    monkeypatch.setattr(tu, "archive_logs", _fake)
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.logger = MagicMock()
    gui.log = lambda *a, **k: None
    assert gui._run_archive_logs() is True
    transcript_clean_logs.archive_logs()
    assert len(called) == 2


def test_archive_reports_originals_it_could_not_remove(tmp_path, monkeypatch):
    logs = _logs_dir(tmp_path, monkeypatch)
    real_unlink = type(logs).unlink

    def _unlink(self, *a, **k):
        if self.name == "gui_1.log":
            raise PermissionError("locked")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(type(logs), "unlink", _unlink)
    logger = MagicMock()
    assert tu.archive_logs(logger) is not None
    assert "removed %d of %d" in logger.info.call_args.args[0]
    assert logger.info.call_args.args[3:5] == (2, 3)
    assert "gui_1.log" in logger.warning.call_args.args[1]


def test_archive_does_not_include_its_own_log(tmp_path, monkeypatch):
    # P39: with no logger passed, setup_logging creates a log file in logs/;
    # it must not be zipped and deleted by the same call.
    logs = _logs_dir(tmp_path, monkeypatch)
    created = []

    def _setup(name):
        p = logs / f"{name}_now.log"
        p.write_text("", encoding="utf-8")
        created.append(p)
        return MagicMock()

    monkeypatch.setattr(tu, "setup_logging", _setup)
    path = tu.archive_logs()
    assert "archive_logs_now.log" not in zipfile.ZipFile(path).namelist()
    assert created[0].exists()


def test_delete_logs_keeps_token_usage(tmp_path, monkeypatch):
    # User decision 2026-10-09: deleting logs must not delete the API cost history.
    logs = _logs_dir(tmp_path, monkeypatch)
    assert tu.delete_logs(MagicMock()) is True
    assert not list(logs.glob("*.log"))
    assert (logs / "token_usage.csv").read_text(encoding="utf-8") == "a,b\n"
    for keep in ("runtime_settings.json", "gate_judge_cache.json", "validation_memory.json"):
        assert (logs / keep).exists()
