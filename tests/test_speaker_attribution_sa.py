"""SA — who-said-what in transcripts without speaker labels.

Without labels the transcript cannot show which participant said a passage, so the
judge is told so and does not fail a claim only for naming the interviewer, host or
presenter as the one who said grounded content (user decision 2026-10-12).

Spec: docs/plan_speaker_attribution_2026-10-12.md
"""
from pathlib import Path

import config
import faithfulness_judge as fj
import release_gate
import transcript_utils as tu

PROSE = Path(__file__).parent / "fixtures" / "prose_real"


def _formatted(prefix):
    d = next(p for p in PROSE.iterdir() if p.name.startswith(prefix))
    return next(d.glob("*formatted.md")).read_text(encoding="utf-8")


def test_sa1_detects_labels_in_fixtures():
    assert tu.has_speaker_labels(_formatted("Where Roots"))
    assert tu.has_speaker_labels(_formatted("Why Families"))
    assert not tu.has_speaker_labels(_formatted("Societal"))
    assert not tu.has_speaker_labels(_formatted("Systems Biology"))


def test_sa1a_single_or_inline_bold_is_not_labels():
    """Adversarial: text that looks labelled but is not."""
    assert not tu.has_speaker_labels("**Note:** the audio drops here.\n\nHe went on.")
    inline = "He said **Bowen:** was the point. And **Kerr:** too.\nThen **Amy:** again."
    assert not tu.has_speaker_labels(inline)
    assert not tu.has_speaker_labels("")
    assert tu.has_speaker_labels("**Interviewer:** Why?\n\n**Michael Kerr:** Because.")


def test_sa1b_other_label_shapes_count_as_labels():
    """SA review: a labelled transcript in another shape must not be told it has no
    labels (that would relax the judge on a transcript that does show who spoke)."""
    for text in ("**Speaker 1**: hi\n**Speaker 2**: yes",
                 "**Audience Member (Jane):** a\n**Q&A:** b",
                 "**Kerr, M.:** a\n**Kerr, M.:** b",
                 "Kerr: a\nInterviewer: b",
                 "  > **Kerr:** a\n- **Host:** b",
                 "*Kerr:* a\n__Host:__ b",
                 "Speaker 1: a\nSpeaker 2: b"):
        assert tu.has_speaker_labels(text), text
    # Lower-case prose before a colon is not a label.
    assert not tu.has_speaker_labels("The idea: one thing.\nthe point: another.")


def test_sa2_note_added_only_without_labels():
    base = "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13"
    unlabeled = "He said the family was anxious.\n\nThen they talked about school."
    labeled = "**Interviewer:** Why?\n\n**Michael Kerr:** Because the family was anxious."
    out = release_gate.with_recording_metadata(base, unlabeled)
    assert config.UNLABELED_SPEAKERS_NOTE in out
    assert out.startswith("Recording metadata") and out.endswith(unlabeled)
    out = release_gate.with_recording_metadata(base, labeled)
    assert config.UNLABELED_SPEAKERS_NOTE not in out


def test_sa2_note_without_filename_metadata():
    """A file name with no parseable metadata still gets the note."""
    out = release_gate.with_recording_metadata("x", "Plain text with no labels at all.")
    assert config.UNLABELED_SPEAKERS_NOTE in out
    assert release_gate.with_recording_metadata("x", "   ") == "   "


def test_sa3_rule_only_with_note():
    """The rule is added only for a source with the note; a labelled source is judged
    with exactly the base prompt (the always-on rule judged a labelled blog more
    strictly in calibration)."""
    noted = "x\n" + config.UNLABELED_SPEAKERS_NOTE + "\n\ntext"
    assert fj.instructions_for("**A:** x\n**B:** y") == fj._JUDGE_INSTRUCTIONS
    assert "SPEAKER ATTRIBUTION" not in fj._JUDGE_INSTRUCTIONS
    full = fj.instructions_for(noted)
    assert fj._SPEAKER_RULE.strip() in full
    assert full.index("SPEAKER ATTRIBUTION") < full.index("Return ONLY a JSON array")
    content = fj.build_judge_prompt(["c"], noted)
    assert "SPEAKER ATTRIBUTION" in content[0]["text"]
    assert "SPEAKER ATTRIBUTION" not in fj.build_judge_prompt(["c"], "plain **A:** x")[0]["text"]


def test_sa3_prompt_rule_present():
    p = fj.instructions_for(config.UNLABELED_SPEAKERS_NOTE)
    section = p.split("SPEAKER ATTRIBUTION", 1)[1].split("Return ONLY", 1)[0]
    low = section.lower()
    # The rule names the note the judge will see in the source.
    assert "no speaker labels" in low
    # The content itself must still be in the source; outside attribution still checked.
    assert "content" in low and "in the source" in low
    assert "outside the conversation" in low
    assert "labels" in low and "as usual" in low
    # SA review: the role must exist, and a swapped or inverted stance is not entailed.
    assert "actually has" in low
    assert "stance" in low and ("rejected" in low or "disputed" in low)
    assert "does not show who said it" in low
    assert "includes a transcript note" in low
    # No quoted examples (nothing can be worded after a measured case).
    assert '"' not in section.replace('\\"', "")


def test_sa4_cache_key_covers_label_logic():
    assert config.JUDGE_LOGIC_VERSION == "2026-10-12e"
    fns = release_gate._judge_input_functions()
    assert tu.has_speaker_labels in fns
    assert release_gate.with_recording_metadata in fns
    assert fj.instructions_for in fns


def test_sa4_rule_text_changes_the_key():
    from unittest.mock import patch
    before = release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS)
    with patch.object(fj, "_SPEAKER_RULE", fj._SPEAKER_RULE + " x"):
        assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != before


def test_sa4_threshold_and_note_change_the_key():
    """Changing the label threshold or the note text must invalidate cached verdicts."""
    from unittest.mock import patch
    before = release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS)
    with patch.object(config, "SPEAKER_LABEL_MIN_TURNS", 5):
        assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != before
    with patch.object(config, "UNLABELED_SPEAKERS_NOTE", "other"):
        assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != before


def test_sa2_pass_detail_records_note():
    assert release_gate._speaker_note_suffix("x\n" + config.UNLABELED_SPEAKERS_NOTE + "\ny")
    assert release_gate._speaker_note_suffix("**A:** x\n**B:** y") == ""
    assert release_gate._speaker_note_suffix(None) == ""


def test_sa5_gold_sources_built_as_the_gate_builds_them():
    """SA review: the gold harness judged raw sources, so the note never reached it."""
    import json
    import judge_recalibration as jr
    gold = json.loads(jr.FAITH_GOLD.read_text(encoding="utf-8"))
    src = jr.gold_sources(gold)
    assert set(src) == set(gold["sources"])
    assert config.UNLABELED_SPEAKERS_NOTE in src["kerr_unlabeled"]
    assert config.UNLABELED_SPEAKERS_NOTE in src["systems_biology"]
    assert config.UNLABELED_SPEAKERS_NOTE not in src["kerr_families"]
    assert src["kerr_unlabeled"].startswith("Recording metadata")
    # SA gold cases cover entailed role attribution and both adversarial shapes.
    sa = {c["id"]: c["label"] for c in gold["cases"] if c["id"].startswith("sa")}
    assert sa == {"sa1": "entailed", "sa2": "entailed", "sa3": "contradicted",
                  "sa4": "unsupported", "sa5": "contradicted"}


def test_sa5_gold_source_without_base_is_an_error():
    import judge_recalibration as jr
    import pytest
    with pytest.raises(ValueError):
        jr.gold_sources({"sources": {"x": "dave_g_test2/formatted.md"}, "source_bases": {}})


def test_sa6_flag_survives_source_note(tmp_path, monkeypatch):
    """SA review (P6, dirty state): an artifact flagged before the note was added is
    still flagged after the note changes the source text, so it needs two PASSes."""
    from test_judge_cache_pass_only_d2 import _cold, _result
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(fj, "judge_artifact", lambda a, s, c, logger=None: _result(fj.FAIL, ["x"]))
    _cold(monkeypatch)
    release_gate._judge_cached(fj, "art", "src", object(), None)  # flagged, no note
    results = [_result(fj.PASS), _result(fj.FAIL, ["x"])]
    monkeypatch.setattr(fj, "judge_artifact", lambda a, s, c, logger=None: results.pop(0))
    _cold(monkeypatch)
    noted = config.UNLABELED_SPEAKERS_NOTE + "\n\nsrc"
    assert release_gate._judge_cached(fj, "art", noted, object(), None).status == fj.FAIL
    assert results == []
    # A different artifact against the same source is not flagged by it.
    monkeypatch.setattr(fj, "judge_artifact", lambda a, s, c, logger=None: _result(fj.PASS))
    _cold(monkeypatch)
    calls = []
    monkeypatch.setattr(fj, "judge_artifact",
                        lambda a, s, c, logger=None: calls.append(1) or _result(fj.PASS))
    assert release_gate._judge_cached(fj, "other", noted, object(), None).status == fj.PASS
    assert calls == [1]


_FAQ = """```yaml
faq:
  - q: "Does moving away solve it?"
    a: "According to Kerr, it does not."
```

## Frequently asked questions

### Does moving away from my family solve the problem?

According to Michael Kerr, it does not. Bowen called distance emotional cutoff.

### Key ideas

According to Michael Kerr, it does not matter where you start reading.

### What is chronic anxiety?

### What is societal regression?

Societal regression is chronic anxiety spreading through a society.
"""


def test_fq_answer_opener_carries_question():
    """FQ: the FAQ answer's first sentence is judged with its question attached."""
    claims = fj.extract_claims(_FAQ)
    tagged = [c for c in claims if "[in answer to:" in c]
    assert ("According to Michael Kerr, it does not. "
            "[in answer to: Does moving away from my family solve the problem?]") in tagged
    assert ("Societal regression is chronic anxiety spreading through a society. "
            "[in answer to: What is societal regression?]") in tagged
    # Only openers: the answer's second sentence is judged as before.
    assert "Bowen called distance emotional cutoff." in claims
    # The fenced yaml block stays metadata: its q/a lines are not claims.
    assert not any("Does moving away solve it" in c for c in claims)


def test_fq_non_question_heading_and_empty_answer_do_not_tag():
    """Adversarial: a sentence under a heading that is not a question is not tagged,
    and a question heading followed directly by another heading tags nothing."""
    _marked, questions = fj._mark_question_answers(_FAQ)
    assert questions == ["Does moving away from my family solve the problem?",
                         "What is societal regression?"]
    claims = fj.extract_claims(_FAQ)
    assert "According to Michael Kerr, it does not matter where you start reading." in claims
    assert not any("What is chronic anxiety" in c for c in claims)


def test_fq_tag_goes_to_the_answer_not_an_earlier_twin():
    """SA/FQ review: an identical sentence earlier in the document must not take the
    tag, and the real answer must keep it."""
    text = ("It does not work that way here.\n\n### Does it work?\n\n"
            "It does not work that way here. Bowen said so.\n")
    claims = fj.extract_claims(text)
    assert claims[0] == "It does not work that way here."
    assert claims[1] == "It does not work that way here. [in answer to: Does it work?]"


def test_fq_answer_with_bold_label_or_number_is_tagged():
    for line in ("**Short answer:** No, according to Kerr it does not help at all.",
                 "1. No, according to Kerr it does not help at all.",
                 "- No, according to Kerr it does not help at all."):
        claims = fj.extract_claims(f"### Does distance help?\n\n{line}\n")
        assert any(c.endswith("[in answer to: Does distance help?]") and "Kerr" in c
                   for c in claims), (line, claims)
        assert not any("\ue000" in c for c in claims)


def test_fq_name_in_question_heading_is_still_judged():
    """SA/FQ review (P7): a fabricated name in a question heading must still be
    emitted as its own claim; the tag does not count as covering it."""
    text = ("### Did Luciano Malorni prove that moving away works?\n\n"
            "According to Michael Kerr, it does not.\n")
    claims = fj.extract_claims(text, source="Michael Kerr talks about families.")
    assert "Luciano Malorni" in claims


def test_fq_tag_keeps_the_answer_content():
    """Adversarial: tagging must not hide a fabricated answer — the claim still
    carries the answer's own words for the judge."""
    text = "### Who funded the study?\n\nThe Gates Foundation funded it in 1987.\n"
    claims = fj.extract_claims(text)
    assert claims == ["The Gates Foundation funded it in 1987. [in answer to: Who funded the study?]"]


def test_fq_functions_in_cache_key():
    fns = release_gate._judge_input_functions()
    assert fj._mark_question_answers in fns and fj._clean_claim_line in fns
    assert fj._claim_body in fns


def test_sa_chunk_windows_use_base_prompt(monkeypatch):
    """SA review: a chunk window gets the base prompt even when it holds the note
    (the rule's role and stance tests need the whole source); the full-source
    re-judge gets the rule."""
    seen = []

    def fake_judge(claims, source, client, *, model=None, logger=None, speaker_rule=True):
        seen.append(("SPEAKER ATTRIBUTION" in fj.build_judge_prompt(
            claims, source, speaker_rule=speaker_rule)[0]["text"], source is full))
        return [fj.ClaimVerdict(claim=c, label="unsupported", rationale="r") for c in claims]

    full = config.UNLABELED_SPEAKERS_NOTE + "\n\n" + " ".join(["word"] * 50)
    monkeypatch.setattr(fj, "judge_claims", fake_judge)
    monkeypatch.setattr(fj, "chunk_source", lambda src: [full[:200]])
    monkeypatch.setattr(fj, "route_claims_to_chunks", lambda claims, chunks, m: ({0: [0]}, []))
    fj.judge_claims_chunked(["a claim"], full, object())
    assert seen == [(False, False), (True, True)]
