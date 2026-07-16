#!/usr/bin/env python3
"""log_token_usage must never crash the pipeline — token logging is informational.

These tests pin that contract with REAL assertions (they were previously print-only
/ vacuous, flagged by the M6.B vacuity checker): a normal call writes the usage row;
a file-system, CSV, or unexpected error is swallowed (not raised) and surfaced on the
appropriate channel. LOGS_DIR is redirected to a per-test tmp dir by the root-conftest
`_isolate_logs_dir` autouse fixture.
"""
import csv
import logging
from unittest.mock import Mock, patch

import config
from transcript_utils import log_token_usage


def _usage():
    u = Mock()
    u.input_tokens = 1000
    u.output_tokens = 500
    u.cache_creation_input_tokens = 0
    u.cache_read_input_tokens = 0
    return u


def test_normal_operation_writes_a_row():
    """A normal call writes the usage row to the cost CSV."""
    log_token_usage("test_script", "claude-3-5-sonnet-20241022", _usage(), "end_turn")
    csv_path = config.LOGS_DIR / "token_usage.csv"
    assert csv_path.exists()
    rows = list(csv.reader(csv_path.open(encoding="utf-8")))
    assert any("test_script" in r and "1000" in r and "500" in r for r in rows), rows


def test_permission_error_is_swallowed_not_raised(capsys):
    """A PermissionError writing the log is caught (never propagated) and reported."""
    with patch("builtins.open", side_effect=PermissionError("Access denied")):
        log_token_usage("test_script", "m", _usage(), "end_turn")  # must not raise
    assert "file system error" in capsys.readouterr().out


def test_csv_error_is_swallowed_not_raised(capsys):
    """A csv.Error while formatting the row is caught (never propagated)."""
    with patch("builtins.open"), patch("csv.writer", side_effect=csv.Error("bad")):
        log_token_usage("test_script", "m", _usage(), "end_turn")  # must not raise
    assert "data formatting error" in capsys.readouterr().out


def test_unexpected_error_is_logged_with_stacktrace(caplog):
    """An unexpected error is caught and logged with a stack trace (exc_info)."""
    with patch("builtins.open", side_effect=RuntimeError("boom")):
        with caplog.at_level(logging.ERROR, logger="token_usage"):
            log_token_usage("test_script", "m", _usage(), "end_turn")  # must not raise
    assert any(
        "Unexpected error logging token usage" in r.getMessage() for r in caplog.records
    )
    assert any(r.exc_info for r in caplog.records)  # stack trace captured
