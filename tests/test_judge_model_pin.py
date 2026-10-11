"""H12 (review 2026-07-18): the armed faithfulness/theme judges are calibrated on an
exact model string. Anthropic publishes no dated snapshot for claude-sonnet-4-6, so this
string pin is the guard: any change here fails this test, forcing whoever changes the
model to re-run the live calibration (RUN_FAITHFULNESS_CALIBRATION=1 ...) and update this
pin. Prevents a silent, un-recalibrated model move (P6/P20).
"""
import config

# The model the judges were last calibrated on: 2026-10-10, claude-sonnet-5-5 at its
# default effort — faithfulness recall 0.91-0.95 / precision 1.00, themes 1.00/1.00
# over 3 runs (docs/calibration_sonnet55_2026-10-10.md).
CALIBRATED_JUDGE_MODEL = "claude-sonnet-5-5"
CALIBRATED_JUDGE_EFFORT = None


def test_jc6_judge_effort_is_calibrated_value():
    assert config.JUDGE_EFFORT == CALIBRATED_JUDGE_EFFORT, (
        "JUDGE_EFFORT changed — re-run the calibration and update this pin (P20).")


def test_h12_faithfulness_judge_model_is_calibrated_value():
    assert config.FAITHFULNESS_JUDGE_MODEL == CALIBRATED_JUDGE_MODEL, (
        "FAITHFULNESS_JUDGE_MODEL changed — re-run the live calibration and update "
        "CALIBRATED_JUDGE_MODEL here (P20).")


def test_h12_theme_judge_model_is_calibrated_value():
    assert config.THEME_JUDGE_MODEL == CALIBRATED_JUDGE_MODEL, (
        "THEME_JUDGE_MODEL changed — re-run the live calibration and update "
        "CALIBRATED_JUDGE_MODEL here (P20).")
