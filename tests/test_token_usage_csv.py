"""M10 (review 2026-07-18): the token_usage.csv header labels must match the data they
carry — 'Model' holds the model and 'Stop Reason' holds the stop_reason (they were
mislabeled 'Items'/'Status'). Round-trip: write via the real logger, read via DictReader.
"""
import csv
import types

import config
import model_specs
import transcript_utils


def test_m10_csv_header_labels_match_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    usage = types.SimpleNamespace(
        input_tokens=10, output_tokens=5,
        cache_creation_input_tokens=0, cache_read_input_tokens=0)
    valid_model = next(iter(model_specs.PRICING))

    transcript_utils.log_token_usage("myscript", valid_model, usage, "end_turn")

    with open(tmp_path / "token_usage.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows, "no row written"
    row = rows[0]
    assert row["Model"] == valid_model, "model must be under the 'Model' header"
    assert row["Stop Reason"] == "end_turn", "stop_reason must be under the 'Stop Reason' header"
    # the mislabeled headers are gone
    assert "Items" not in row and "Status" not in row
