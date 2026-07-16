"""M8.C — mut_harness must restore its target file byte-identically.

The harness mutates a module in place (via ast.unparse, which also reformats it)
and restores the original in a finally block. A kill (timeout/SIGKILL) before the
finally previously left a reformatted, mutated file on disk — a real footgun that
corrupted validation_pipeline.py twice during the Step-2 work. run_campaign now
keeps a sidecar backup and self-heals, so the target is byte-identical after a
normal run, after a crash mid-run, and after a prior killed run.
"""
import mut_harness


TINY = b"def f(x):\n    if x > 0:\n        return True\n    return False\n"


def _quiet(*_a, **_k):
    pass


def test_m8c1_mut_harness_preserves_bytes(tmp_path):
    mod = tmp_path / "tinymod.py"
    mod.write_bytes(TINY)
    result = mut_harness.run_campaign(mod, {"f"}, suite_fn=lambda: False, stream=_quiet)
    assert mod.read_bytes() == TINY  # byte-identical, no ast.unparse reformat left behind
    assert result["mutants"] >= 1
    assert not mut_harness._sidecar_path(mod).exists()


def test_m8c1_mut_harness_restores_on_crash(tmp_path):
    mod = tmp_path / "tinymod.py"
    mod.write_bytes(TINY)

    def boom():
        raise RuntimeError("suite crashed mid-campaign")

    try:
        mut_harness.run_campaign(mod, {"f"}, suite_fn=boom, stream=_quiet)
    except RuntimeError:
        pass
    assert mod.read_bytes() == TINY  # restored despite the crash
    assert not mut_harness._sidecar_path(mod).exists()


def test_m8c1_mut_harness_self_heals_prior_kill(tmp_path):
    """A leftover sidecar means a previous run was SIGKILLed mid-mutation and the
    target on disk is a corrupt mutant; the next run restores the good bytes."""
    mod = tmp_path / "tinymod.py"
    corrupt = b"def f(x):\n    if x != 0:\n        return True\n    return False\n"
    mod.write_bytes(corrupt)  # leftover mutated copy from a prior killed run
    mut_harness._sidecar_path(mod).write_bytes(TINY)  # sidecar holds the good bytes

    mut_harness.run_campaign(mod, {"f"}, suite_fn=lambda: False, stream=_quiet)
    assert mod.read_bytes() == TINY  # self-healed, then preserved
    assert not mut_harness._sidecar_path(mod).exists()
