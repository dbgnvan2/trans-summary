"""JR — a judge reply whose rationale contains unescaped double quotes (seen
2026-10-12: "rationale":"The "June video" detail is absent…") is read verdict by
verdict instead of becoming an ERROR that blocks publication. Fail closed is kept:
every claim must still get a valid label.

Spec: docs/calibration_fx_examples_2026-10-12.md (judge reply format)
"""
import pytest

import faithfulness_judge as fj

BAD = ('[\n{"index":1,"label":"unsupported","rationale":"The "June video" detail is absent; '
       'the recording date is 2022-02-18."},\n'
       '{"index":2,"label":"entailed","rationale":"Kerr explores the roots; \'predictive power\' '
       'is a mild stretch."},\n'
       '{"index":3,"label":"contradicted","rationale":"He says "never", not "always"."}\n]')


def test_jr1_unescaped_quotes_in_rationale_are_read():
    verdicts = fj._parse_judge_response(BAD, ["a", "b", "c"])
    assert [v.label for v in verdicts] == ["unsupported", "entailed", "contradicted"]
    assert '"June video"' in verdicts[0].rationale


def test_jr1_still_fails_closed_when_a_verdict_is_missing():
    two = BAD.replace(',\n{"index":3,"label":"contradicted","rationale":"He says "never", not "always"."}', "")
    with pytest.raises(ValueError):
        fj._parse_judge_response(two, ["a", "b", "c"])


def test_jr1_invalid_label_still_fails_closed():
    bad_label = BAD.replace('"label":"entailed"', '"label":"probably fine"')
    with pytest.raises(ValueError):
        fj._parse_judge_response(bad_label, ["a", "b", "c"])


def test_jr1_valid_json_unchanged():
    ok = '[{"index":1,"label":"entailed","rationale":"fine"}]'
    assert fj._extract_json_array(ok) == [{"index": 1, "label": "entailed", "rationale": "fine"}]


def test_jr1_prose_still_raises():
    with pytest.raises(ValueError):
        fj._extract_json_array("I cannot judge these claims.")


def test_jr2_two_arrays_do_not_override_a_flag():
    """Adversarial (review): a draft array then a "correction" must not let the later
    entailed verdict replace the first flag — repeated index -> ERROR (fail closed)."""
    two = ('[{"index":1,"label":"unsupported","rationale":"The "X" is absent."},'
           '{"index":2,"label":"entailed","rationale":"ok"}]\nCorrection:\n'
           '[{"index":1,"label":"entailed","rationale":"ok"}]')
    with pytest.raises(ValueError):
        fj._parse_judge_response(two, ["a", "b"])


def test_jr2_repeated_index_in_valid_json_fails_closed():
    dup = ('[{"index":1,"label":"unsupported","rationale":"x"},'
           '{"index":1,"label":"entailed","rationale":"y"}]')
    with pytest.raises(ValueError):
        fj._parse_judge_response(dup, ["a"])


def test_jr2_fallback_use_is_logged_and_counted(caplog):
    before = fj.REPLY_REPAIRS["count"]
    with caplog.at_level("WARNING"):
        fj._parse_judge_response(BAD, ["a", "b", "c"])
    assert fj.REPLY_REPAIRS["count"] == before + 1
    assert any("not valid JSON" in r.message and "read verdict by verdict" in r.message
               for r in caplog.records)


def test_jr2_repeated_index_after_an_invalid_label_fails_closed():
    dup = ('[{"index":1,"label":"maybe","rationale":"x"},'
           '{"index":1,"label":"entailed","rationale":"y"}]')
    with pytest.raises(ValueError):
        fj._parse_judge_response(dup, ["a"])
