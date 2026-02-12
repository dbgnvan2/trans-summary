from pathlib import Path
from types import SimpleNamespace

import transcript_config_check
from transcript_cost_estimator import CostEstimator


def test_cost_estimator_log_accepts_format_args(tmp_path):
    transcript_path = tmp_path / "sample.txt"
    transcript_path.write_text("hello world", encoding="utf-8")

    class Logger:
        def __init__(self):
            self.messages = []

        def info(self, msg):
            self.messages.append(msg)

    logger = Logger()
    estimator = CostEstimator(transcript_path, logger=logger)
    estimator._log("value=%d", 42)

    assert any("value=42" in m for m in logger.messages)


def test_check_model_availability_checks_all_active_models(monkeypatch):
    # Provide distinct model names to ensure all are checked.
    monkeypatch.setattr(transcript_config_check.config, "DEFAULT_MODEL", "m-default")
    monkeypatch.setattr(transcript_config_check.config, "AUX_MODEL", "m-aux")
    monkeypatch.setattr(
        transcript_config_check.config, "FORMATTING_MODEL", "m-format"
    )
    monkeypatch.setattr(
        transcript_config_check.config, "VALIDATION_MODEL", "m-validate"
    )
    monkeypatch.setattr(transcript_config_check.os, "getenv", lambda _k: "fake-key")

    called_models = []

    class FakeClient:
        class messages:
            @staticmethod
            def create(model, max_tokens, messages):
                called_models.append(model)
                return SimpleNamespace()

    monkeypatch.setattr(transcript_config_check.anthropic, "Anthropic", lambda api_key: FakeClient())

    ok = transcript_config_check.check_model_availability()

    assert ok is True
    assert called_models == ["m-default", "m-aux", "m-format", "m-validate"]
