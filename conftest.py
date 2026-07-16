"""Pytest configuration for stable local/offline runs."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_logs_dir(tmp_path, monkeypatch):
    """Redirect the logs directory (esp. token_usage.csv and runtime_settings.json)
    to a per-test temp dir so no test can write into the real logs/.

    `log_token_usage` appends to `config.LOGS_DIR / "token_usage.csv"`; several
    tests call it (directly, or via code that logs usage with a mock model/logger),
    which previously left junk rows — `test_script`, `<MagicMock …>`, nameless
    `unknown_script` — in the production cost log. Redirecting LOGS_DIR makes the
    whole suite hermetic. Tests that set their own LOGS_DIR still override this.
    """
    try:
        import config
    except Exception:
        return
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path, raising=False)
    monkeypatch.setattr(config.settings, "LOGS_DIR", tmp_path, raising=False)


@pytest.fixture(autouse=True)
def _faithfulness_judge_offline(monkeypatch):
    """Keep the LLM faithfulness judge (M2) OFF and hermetic across the WHOLE suite.

    The shipped default is ENABLED (calibration passed 2026-07-15), so a test that
    runs the real gate would otherwise make a live Anthropic call (the key resolves
    from the shared keys file) or, with no key, ERROR->BLOCK — breaking deterministic
    gate tests and spending API. Force it disabled here; the enabled path is
    exercised with a MOCKED judge by tests that opt in via their own monkeypatch
    (which runs after this and overrides it). Also clear the process-lifetime verdict
    cache so a memoized result can't leak between tests (P8)."""
    try:
        import config
        monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", False, raising=False)
        monkeypatch.setattr(config, "THEME_JUDGE_ENABLED", False, raising=False)
    except Exception:
        return
    try:
        import release_gate
        release_gate._FAITHFULNESS_CACHE.clear()
        release_gate._THEME_JUDGE_CACHE.clear()
    except Exception:
        pass
    # Second layer (defense-in-depth, F5): default NO resolvable key, unless a live
    # calibration opts in. So even a test that re-enables the judge but forgets to
    # supply a key cannot reach a live API call — check_faithfulness ERRORs on the
    # missing key instead. A test exercising the enabled path must EXPLICITLY patch
    # resolve_anthropic_key to a value (and mock the judge), making the opt-in loud.
    if not os.getenv("RUN_FAITHFULNESS_CALIBRATION"):
        try:
            import transcript_utils
            monkeypatch.setattr(transcript_utils, "resolve_anthropic_key",
                                lambda: None, raising=False)
        except Exception:
            pass


def _live_api_enabled(config: pytest.Config) -> bool:
    """Enable live API tests only when explicitly requested."""
    return config.getoption("--live-api") or os.getenv("RUN_LIVE_API_TESTS") == "1"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live-api",
        action="store_true",
        default=False,
        help="Run tests marked as live_api (network/API dependent).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_api: marks tests that require live network/API access",
    )
    config.addinivalue_line(
        "markers",
        "integration: marks integration tests",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _live_api_enabled(config):
        return

    skip_live = pytest.mark.skip(
        reason="live_api test skipped (use --live-api or RUN_LIVE_API_TESTS=1)"
    )
    for item in items:
        if "live_api" in item.keywords:
            item.add_marker(skip_live)
