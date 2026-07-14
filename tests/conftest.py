import os
import sys
from unittest.mock import MagicMock

import pytest

# Add the project root directory to sys.path
# This allows tests to import modules from the root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch):
    """Stop any test from popping a REAL Tk dialog.

    Several headless GUI tests exercise `do_run_selected`, which calls
    tkinter `messagebox` functions (e.g. the "nothing checked" warning). With
    no display those calls can block indefinitely, and whether they block
    depends on whether an earlier test happened to create a Tk root -- an
    order-dependent hang. Replacing the dialog functions with non-blocking
    mocks makes every test hermetic. Tests that assert on a specific dialog
    still `patch(...)` it themselves (overriding this default, then restoring
    to it); tests that expect the confirm dialog to proceed get a truthy
    askyesno by default.
    """
    try:
        import tkinter.messagebox as mb
    except Exception:
        return
    for name, default in (
        ("showwarning", None),
        ("showinfo", None),
        ("showerror", None),
        ("askyesno", True),
        ("askokcancel", True),
        ("askyesnocancel", True),
    ):
        monkeypatch.setattr(mb, name, MagicMock(return_value=default), raising=False)
