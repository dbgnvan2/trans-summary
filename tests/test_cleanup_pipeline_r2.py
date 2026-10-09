"""R2 (review G11): cleanup deletes only this transcript's own _vN files.

Spec: docs/plan_review_fixes_2026-10-04.md#R2
"""
from unittest.mock import MagicMock

import pytest

import cleanup_pipeline
import config

BASE = "T - P - 2025-01-01"


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    source = tmp_path / "source"
    processed = tmp_path / "processed"
    source.mkdir()
    monkeypatch.setattr(config, "SOURCE_DIR", source)
    monkeypatch.setattr(config, "PROCESSED_DIR", processed)
    (source / f"{BASE}.txt").write_text("orig", encoding="utf-8")
    return source


def _clean():
    cleanup_pipeline.cleanup_transcript_files(BASE, logger=MagicMock())


def test_r2a_prefix_sibling_survives(dirs):
    """Another transcript whose name starts with BASE keeps its versions."""
    sibling = [dirs / f"{BASE} Part 2_v{i}.txt" for i in (1, 3)]
    for f in sibling:
        f.write_text("other transcript", encoding="utf-8")
    _clean()
    for f in sibling:
        assert f.exists(), f"cleanup of {BASE!r} deleted {f.name}"


def test_r2b_own_versions_removed(dirs):
    own = [dirs / f"{BASE}_v{i}.txt" for i in (1, 2, 10)]
    for f in own:
        f.write_text("v", encoding="utf-8")
    _clean()
    for f in own:
        assert not f.exists()


def test_r2c_timestamped_variant_not_deleted(dirs):
    """No producer writes "<base>_<timestamp>_vN.txt", so it is not ours to delete."""
    f = dirs / f"{BASE}_20250101_101010_v2.txt"
    f.write_text("x", encoding="utf-8")
    _clean()
    assert f.exists()


def test_r2d_regex_metacharacters_in_base_name(tmp_path, monkeypatch):
    """Parentheses/dots in a title must be matched literally."""
    base = "Q&A (Part 1). Kerr - 2020"
    source = tmp_path / "s"
    source.mkdir()
    monkeypatch.setattr(config, "SOURCE_DIR", source)
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "p")
    own = source / f"{base}_v1.txt"
    lookalike = source / "Q&A XPart 1Y. Kerr - 2020_v1.txt"
    own.write_text("v", encoding="utf-8")
    lookalike.write_text("v", encoding="utf-8")
    cleanup_pipeline.cleanup_transcript_files(base, logger=MagicMock())
    assert not own.exists()
    assert lookalike.exists()
