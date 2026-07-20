"""L9 (review 2026-07-18): a single git failure must not poison _current_git_revision's
cache with 'unknown' for the whole session — only a successful revision is cached, and a
later call retries."""
import ts_gui


def test_l9_git_failure_is_not_cached_and_success_recovers(monkeypatch):
    monkeypatch.setattr(ts_gui, "_GIT_REVISION_CACHE", None)

    def boom(*args, **kwargs):
        raise OSError("git not available")

    monkeypatch.setattr(ts_gui.subprocess, "check_output", boom)
    assert ts_gui._current_git_revision() == "unknown"
    assert ts_gui._GIT_REVISION_CACHE is None, "a git failure must NOT be cached"

    # a subsequent call, once git works, returns and caches the real revision
    monkeypatch.setattr(ts_gui.subprocess, "check_output", lambda *a, **k: "abc1234\n")
    assert ts_gui._current_git_revision() == "abc1234"
    assert ts_gui._GIT_REVISION_CACHE == "abc1234"
