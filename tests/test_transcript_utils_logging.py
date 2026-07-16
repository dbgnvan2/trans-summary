import logging

import transcript_utils


def test_setup_logging_replaces_handlers_per_logger(tmp_path, monkeypatch):
    monkeypatch.setattr(transcript_utils.config, "LOGS_DIR", tmp_path)

    logger = transcript_utils.setup_logging("unit_logger")
    first_handlers = list(logger.handlers)

    logger = transcript_utils.setup_logging("unit_logger")
    second_handlers = list(logger.handlers)
    second_paths = [
        getattr(handler, "baseFilename", None)
        for handler in second_handlers
        if hasattr(handler, "baseFilename")
    ]

    assert len(second_handlers) == 2
    assert logger.propagate is False
    assert first_handlers != second_handlers
    assert len(second_paths) == 1
    assert second_paths[0] is not None
    assert second_paths[0].startswith(str(tmp_path))

    logging.getLogger("unit_logger").handlers.clear()
