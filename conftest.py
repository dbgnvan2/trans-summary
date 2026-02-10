"""Pytest configuration for stable local/offline runs."""

from __future__ import annotations

import os

import pytest


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
