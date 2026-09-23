"""
Tests for the 2026-09-23 reliability changes:
  - heading timestamps checked against where each section starts in the raw
  - format validation writes a record + raw-source copy; YAML Authenticity
    depends on a passing record for the exact text
  - release-gate source_fidelity check (blocking)
  - whole-quote coverage in verbatim_quotes (blocking)
  - topic / key-term faithfulness check (blocking, judge stubbed here)
  - claim-bearing headings are judged
"""

import logging
import re
import shutil
from pathlib import Path

import pytest

import config
import faithfulness_judge as fj
import formatting_pipeline as fp
import release_gate as rg
import validation_pipeline as vp
from release_gate import Status
from transcript_utils import strip_yaml_frontmatter

FX = Path(__file__).parent / "fixtures"
WR = FX / "where_roots"
BASE = "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"
LOG = logging.getLogger("reliability")


def _raw():
    return (WR / BASE / f"{BASE}.txt").read_text(encoding="utf-8-sig")


def _formatted():
    return strip_yaml_frontmatter(
        (WR / BASE / f"{BASE}{config.SUFFIX_FORMATTED}").read_text(encoding="utf-8-sig"))


@pytest.fixture
def cloned(tmp_path, monkeypatch):
    dst = tmp_path / "projects"
    shutil.copytree(WR, dst)
    monkeypatch.setattr(config, "PROJECTS_DIR", dst)
    monkeypatch.setattr(config, "SOURCE_DIR", tmp_path / "source")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    return dst / BASE


# ------------------------------------------------------------ heading positions


def test_heading_positions_real_fixture_clean():
    errors, warnings = fp.check_heading_timestamp_positions(_formatted(), _raw())
    assert errors == []
    assert warnings == []


def test_heading_position_swapped_timestamp_detected():
    fmt = _formatted()
    heads = re.findall(r"^## Section.*$", fmt, flags=re.M)
    ts10 = re.search(r"\[\d\d:\d\d:\d\d\]", heads[9])[0]
    ts20 = re.search(r"\[\d\d:\d\d:\d\d\]", heads[19])[0]
    bad = fmt.replace(heads[9], heads[9].replace(ts10, ts20))
    errors, _ = fp.check_heading_timestamp_positions(bad, _raw())
    assert len(errors) == 1 and errors[0].startswith("Section 10:")


def test_heading_positions_skipped_without_raw_timestamps():
    fmt = "## Section 1 – Some Talk About Things ([00:05:00]).\n\nHello there world.\n"
    assert fp.check_heading_timestamp_positions(fmt, "Hello there world.") == ([], [])


def test_heading_position_mss_raw_format():
    raw = "Speaker 1  0:04\nOkay welcome everyone.\n\nSpeaker 1  1:11\nNow the second part.\n"
    good = ("## Section 1 – Welcome to the Talk Today ([00:00:04]).\n\nOkay welcome everyone.\n\n"
            "## Section 2 – The Second Part Begins Here ([00:01:11]).\n\nNow the second part.\n")
    assert fp.check_heading_timestamp_positions(good, raw)[0] == []
    bad = good.replace("[00:01:11]", "[00:00:04]")
    assert fp.check_heading_timestamp_positions(bad, raw)[0]


# ------------------------------------------------------------ record + YAML


def test_validate_format_writes_record_and_raw_copy(cloned, tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    (src / f"{BASE}.txt").write_text(_raw(), encoding="utf-8")
    assert fp.validate_format(f"{BASE}.txt", logger=LOG) is True
    record = fp.load_format_validation_record(BASE)
    assert record["passed"] is True
    assert fp.raw_source_copy_path(BASE).read_text(encoding="utf-8") == _raw()
    formatted = (cloned / f"{BASE}{config.SUFFIX_FORMATTED}").read_text(encoding="utf-8")
    assert fp.format_validation_passed_for(BASE, formatted)
    assert not fp.format_validation_passed_for(BASE, formatted + "\nedited")


def test_yaml_authenticity_reflects_validation():
    meta = {"title": "T", "presenter": "P", "date": "2020-01-01", "year": "2020"}
    unverified = fp._generate_yaml_front_matter(meta, "x.mp4")
    assert "NOT VERIFIED" in unverified
    authenticity = unverified.split("Authenticity:", 1)[1].split("\nVersion:", 1)[0]
    assert "recording" not in authenticity.lower()
    verified = fp._generate_yaml_front_matter(
        meta, "x.mp4", {"comparison": {"review": {"accept": 5, "edit": 1, "reject": 2}}})
    assert "6 difference(s) reviewed and approved by a person (1 edited)" in verified
    assert "NOT VERIFIED" not in verified


# ------------------------------------------------------------ gate: source fidelity


def test_gate_source_fidelity_passes_on_real_run(cloned):
    v = rg.check_source_fidelity(BASE, LOG)
    assert v.status is Status.PASS, v.detail


def test_gate_source_fidelity_fails_on_truncated_formatted(cloned):
    f = cloned / f"{BASE}{config.SUFFIX_FORMATTED}"
    text = f.read_text(encoding="utf-8")
    f.write_text(text[: int(len(text) * 0.9)], encoding="utf-8")
    v = rg.check_source_fidelity(BASE, LOG)
    assert v.status is Status.FAIL
    assert "source_fidelity" in config.GATE_BLOCKING_CHECKS


def test_gate_source_fidelity_error_without_raw(cloned):
    (cloned / f"{BASE}.txt").unlink()
    v = rg.check_source_fidelity(BASE, LOG)
    assert v.status is Status.ERROR


def test_gate_finds_processed_rename(cloned, tmp_path):
    raw_path = cloned / f"{BASE}.txt"
    processed = tmp_path / "processed"
    processed.mkdir()
    shutil.move(str(raw_path), processed / f"{BASE}_v2 - Processed (1).txt")
    v = rg.check_source_fidelity(BASE, LOG)
    assert v.status is Status.PASS, v.detail


def test_gate_prefers_project_raw_copy(cloned):
    (cloned / f"{BASE}{config.SUFFIX_RAW_SOURCE}").write_text("completely different text")
    v = rg.check_source_fidelity(BASE, LOG)
    assert v.status is Status.FAIL


# ------------------------------------------------------------ quotes


def _passage(n=40):
    paras = [p for p in _formatted().split("\n\n") if not p.startswith("#") and len(p.split()) > 60]
    return paras[10].split()[:n]


def test_quote_coverage_catches_changed_middle():
    t = _formatted()
    words = _passage()
    assert vp._quote_word_coverage(" ".join(words), t) == 1.0
    negated = words[:14] + "differentiation is not possible for anyone".split() + words[20:]
    assert vp._quote_word_coverage(" ".join(negated), t) < config.QUOTE_MIN_WORD_COVERAGE
    one_word = words[:20] + ["never"] + words[21:]
    assert vp._quote_word_coverage(" ".join(one_word), t) < config.QUOTE_MIN_WORD_COVERAGE


def test_quote_coverage_ignores_omissions_and_typography():
    t = _formatted()
    words = _passage()
    elided = " ".join(words[:15]) + " … " + " ".join(words[25:])
    assert vp._quote_word_coverage(elided, t) == 1.0
    curly = " ".join(words).replace("'", "\u2019")
    assert vp._quote_word_coverage(curly, t) == 1.0


def test_gate_verbatim_quotes_blocks_changed_middle(cloned):
    emp = cloned / f"{BASE}{config.SUFFIX_EMPHASIS_SCORED}"
    text = emp.read_text(encoding="utf-8")
    m = re.search(r'^"([^"\n]{150,})"', text, flags=re.M)
    assert m, "fixture should contain a long quote"
    quote = m.group(1).split()
    altered = quote[:10] + ["absolutely", "never", "ever"] + quote[13:]
    emp.write_text(text.replace(m.group(1), " ".join(altered)), encoding="utf-8")
    v = rg.check_verbatim_quotes(BASE, LOG)
    assert v.status is Status.FAIL
    assert any(i["word_coverage"] < 1.0 for i in v.items)


def test_gate_verbatim_quotes_pass_on_real_run(cloned):
    assert rg.check_verbatim_quotes(BASE, LOG).status is Status.PASS


# ------------------------------------------------------------ topics / key terms


def test_topics_terms_as_claims_drops_metadata_and_prefixes_title():
    md = (FX / "dave_g_test2" / "topics.md").read_text(encoding="utf-8")
    claims = fj.extract_claims(rg.topics_terms_as_claims(md))
    assert claims
    assert not any("of transcript" in c for c in claims)
    assert claims[0].startswith("Family-of-Origin Structure and Parental Relationship: ")


def _stub_judge(monkeypatch, status):
    class _Claim:
        claim = "x"

    class _Res:
        pass

    res = _Res()
    res.status = status
    res.detail = "d"
    res.unfaithful = [_Claim()] if status == fj.FAIL else []
    seen = []

    def _fake(fjudge, text, source, client, logger=None):
        seen.append(text)
        return res

    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True)
    monkeypatch.setattr(rg, "_judge_cached", _fake)
    monkeypatch.setattr("transcript_utils.resolve_anthropic_key", lambda: "k")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key=None: object())
    return seen


def _topic_project(tmp_path, monkeypatch, topics=True, terms=True):
    base = "Talk - A Person - 2021-01-01"
    proj = tmp_path / base
    proj.mkdir(parents=True)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    (proj / f"{base}{config.SUFFIX_FORMATTED}").write_text("spoken words", encoding="utf-8")
    if topics:
        (proj / f"{base}{config.SUFFIX_TOPICS}").write_text(
            "## Topics\n\n### Anxiety\nThe talk covers anxiety in families.\n"
            "*_(~20% of transcript; Sections 1-2)_*\n", encoding="utf-8")
    if terms:
        (proj / f"{base}{config.SUFFIX_KEY_TERMS}").write_text(
            "### Triangle\nA three-person relationship system described by the speaker.\n",
            encoding="utf-8")
    return base


def test_topic_term_faithfulness_pass(tmp_path, monkeypatch):
    base = _topic_project(tmp_path, monkeypatch)
    seen = _stub_judge(monkeypatch, fj.PASS)
    v = rg.check_topic_term_faithfulness(base, LOG)
    assert v.status is Status.PASS
    assert len(seen) == 2
    assert "Anxiety: The talk covers anxiety in families." in seen[0]
    assert "of transcript" not in seen[0]


def test_topic_term_faithfulness_fail_blocks(tmp_path, monkeypatch):
    base = _topic_project(tmp_path, monkeypatch)
    _stub_judge(monkeypatch, fj.FAIL)
    v = rg.check_topic_term_faithfulness(base, LOG)
    assert v.status is Status.FAIL
    assert "topic_term_faithfulness" in config.GATE_BLOCKING_CHECKS


def test_topic_term_faithfulness_nothing_to_judge_is_error(tmp_path, monkeypatch):
    base = _topic_project(tmp_path, monkeypatch, topics=False, terms=False)
    _stub_judge(monkeypatch, fj.PASS)
    assert rg.check_topic_term_faithfulness(base, LOG).status is Status.ERROR


def test_topic_term_faithfulness_disabled_is_noop(tmp_path, monkeypatch):
    base = _topic_project(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", False)
    assert rg.check_topic_term_faithfulness(base, LOG).status is Status.PASS


# ------------------------------------------------------------ heading claims


def test_claim_bearing_headings_are_judged():
    text = ("# Abstract\n\n## Key Takeaways\n\n## Bowen's 1954 Study at Harvard\n\n"
            "## The Role of Anxiety in Family Systems\n\nBody sentence that is long enough to count.\n")
    claims = fj.extract_claims(text)
    assert "Bowen's 1954 Study at Harvard" in claims
    assert "The Role of Anxiety in Family Systems" in claims
    assert "Abstract" not in claims
    assert "Key Takeaways" not in claims


# ------------------------------------------------------------ formatting output


def test_strip_leading_title_removes_echoed_prompt_title():
    text = "# Transcript Formatting - v12\n\n## Section 1 – A Talk About Things ([00:00:01]).\n\nx"
    cleaned, removed = fp.strip_leading_title(text)
    assert cleaned.startswith("## Section 1")
    assert removed == ["# Transcript Formatting - v12"]
    body = "Intro prose\n## Section 1 – A Talk About Things ([00:00:01]).\n\nx"
    assert fp.strip_leading_title(body) == (body, [])


def test_formatting_max_tokens_uses_documented_model_limit():
    assert fp.formatting_max_tokens("claude-haiku-4-5-20251001") == 64000
    assert fp.formatting_max_tokens("unknown-model") == config.MAX_TOKENS_FORMATTING


def test_yaml_transcriber_is_configurable_and_default_honest():
    meta = {"title": "T", "presenter": "P", "date": "2020-01-01", "year": "2020"}
    assert 'Transcriber: "Automated"' in fp._generate_yaml_front_matter(meta, "x.mp4")


def test_max_tokens_stop_is_not_retried(monkeypatch):
    import transcript_utils as tu

    calls = []

    from types import SimpleNamespace

    msg = SimpleNamespace(
        stop_reason="max_tokens", model="m", type="message", role="assistant",
        content=[SimpleNamespace(text="partial", type="text")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )

    class _Client:
        class messages:
            @staticmethod
            def create(**kw):
                calls.append(kw)
                return msg

    with pytest.raises(RuntimeError):
        tu.call_claude_with_retry(client=_Client(), model="m",
                                  messages=[{"role": "user", "content": "x"}],
                                  max_tokens=10, stream=False, max_retries=3)
    assert len(calls) == 1


# ------------------------------------------------------------ stale YAML / webpage text


def test_gate_fails_on_stale_yaml_transcript(cloned):
    formatted = (cloned / f"{BASE}{config.SUFFIX_FORMATTED}").read_text(encoding="utf-8")
    yaml_path = cloned / f"{BASE}{config.SUFFIX_YAML}"
    front = fp._generate_yaml_front_matter(
        {"title": "T", "presenter": "P", "date": "d", "year": "y"}, "x.mp4")
    yaml_path.write_text(front + formatted, encoding="utf-8")
    assert rg.check_source_fidelity(BASE, LOG).status is Status.PASS
    yaml_path.write_text(front + formatted.replace("heliocentric", "geocentric", 1),
                         encoding="utf-8")
    v = rg.check_source_fidelity(BASE, LOG)
    assert v.status is Status.FAIL and "stale YAML" in v.detail


def _render_page(tmp_path, monkeypatch):
    import html_generator as hg
    from transcript_utils import (
        load_bowen_references,
        load_emphasis_items,
        markdown_to_html,
    )

    monkeypatch.setattr(config, "PROJECTS_DIR", WR)
    fmt = _formatted()
    body = hg._highlight_html_content(
        markdown_to_html(fmt), load_bowen_references(BASE), load_emphasis_items(BASE))
    meta = hg._extract_webpage_metadata(BASE)
    meta["abstract"] = hg._load_abstract(BASE)
    page = hg._generate_html_page(BASE, body, meta, hg._load_summary(BASE),
                                  load_bowen_references(BASE), load_emphasis_items(BASE))
    html_file = tmp_path / "page.html"
    html_file.write_text(page, encoding="utf-8")
    return html_file, WR / BASE / f"{BASE}{config.SUFFIX_FORMATTED}"


def test_webpage_transcript_text_identical(tmp_path, monkeypatch):
    import transcript_validate_webpage as tvw
    html_file, formatted_file = _render_page(tmp_path, monkeypatch)
    assert tvw.transcript_text_differences(html_file, formatted_file) == []


def test_webpage_transcript_text_change_detected(tmp_path, monkeypatch):
    import transcript_validate_webpage as tvw
    html_file, formatted_file = _render_page(tmp_path, monkeypatch)
    page = html_file.read_text(encoding="utf-8")
    cut = page.index('class="transcript"')
    page = page[:cut] + page[cut:].replace("heliocentric", "geocentric", 1)
    html_file.write_text(page, encoding="utf-8")
    diffs = tvw.transcript_text_differences(html_file, formatted_file)
    assert diffs and "heliocentric" in diffs[0]
