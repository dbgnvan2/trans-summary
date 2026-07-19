"""H12 (review 2026-07-18): the armed faithfulness/theme judges are calibrated on an
exact model string. Anthropic publishes no dated snapshot for claude-sonnet-4-6, so this
string pin is the guard: any change here fails this test, forcing whoever changes the
model to re-run the live calibration (RUN_FAITHFULNESS_CALIBRATION=1 ...) and update this
pin. Prevents a silent, un-recalibrated model move (P6/P20).
"""
import config

# The model the judges were last calibrated on (2026-07-19, recall/precision 1.0).
CALIBRATED_JUDGE_MODEL = "claude-sonnet-4-6"


def test_h12_faithfulness_judge_model_is_calibrated_value():
    assert config.FAITHFULNESS_JUDGE_MODEL == CALIBRATED_JUDGE_MODEL, (
        "FAITHFULNESS_JUDGE_MODEL changed — re-run the live calibration and update "
        "CALIBRATED_JUDGE_MODEL here (P20).")


def test_h12_theme_judge_model_is_calibrated_value():
    assert config.THEME_JUDGE_MODEL == CALIBRATED_JUDGE_MODEL, (
        "THEME_JUDGE_MODEL changed — re-run the live calibration and update "
        "CALIBRATED_JUDGE_MODEL here (P20).")
