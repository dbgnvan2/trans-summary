"""The artifact_contracts logger must be created once per process, not once per
saved artifact — otherwise every save spawns a new timestamped log file and a
console 'Logging initialized' line (terminal + logs/ clutter)."""

import logging

import config
import extraction_pipeline as ep


def test_artifact_contracts_logger_cached_single_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    saved = ep._ARTIFACT_CONTRACTS_LOGGER
    try:
        ep._ARTIFACT_CONTRACTS_LOGGER = None
        logging.getLogger("artifact_contracts").handlers.clear()

        loggers = [ep._artifact_contracts_logger() for _ in range(5)]

        assert all(l is loggers[0] for l in loggers)  # one cached logger, reused
        # exactly one artifact_contracts log file, not five
        assert len(list(tmp_path.glob("artifact_contracts_*.log"))) == 1
    finally:
        lg = logging.getLogger("artifact_contracts")
        for h in list(lg.handlers):
            h.close()
            lg.removeHandler(h)
        ep._ARTIFACT_CONTRACTS_LOGGER = saved
