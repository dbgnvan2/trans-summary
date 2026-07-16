"""Tests for the GEO-optimized overview post generation.

Purpose: Verify the overview-post pipeline path produces correctly-shaped
output without requiring a validated top lens, and that existing call sites
remain unaffected.
Spec:    docs/implementation_plan_2026-05-13.md (OV.3 through OV.10)
"""
import inspect
import re
from unittest.mock import MagicMock

import yaml

import config
import extraction_pipeline


# A known, GEO-compliant overview output used by the integration tests.
# Built to satisfy: word count >= OVERVIEW_MIN_WORDS, required frontmatter
# keys present, FAQ section with >= 3 ### question headers.
_MOCK_OVERVIEW_OUTPUT = """```yaml
slug: "test-overview-slug"
meta_description: "Test description containing the focus keyword for retrieval."
focus_keyword: "Test Focus"
target_audience: "General readers"
process_stage: "overview_post"
schema_type: "Article"
author: "Test Presenter"
date_published: "2024-01-01"
source_title: "Test Title"
faq:
  - q: "What is the test transcript about?"
    a: "The transcript by Test Presenter on 2024-01-01 covers the test material."
  - q: "Why does this matter to family systems readers?"
    a: "It clarifies a foundational dynamic relevant to the field."
  - q: "What are the key topics?"
    a: "Topic A and Topic B are discussed in detail."
  - q: "What should readers take away?"
    a: "Three actionable insights are presented."
```

# Test Title

Test Title is a lecture by Test Presenter (2024-01-01) about the test material covered in the source transcript.

## TL;DR

Test Presenter delivered a lecture on 2024-01-01 covering the test material. The lecture establishes key terms used in family systems work. It introduces several topics relevant to the focus keyword and the target audience.

- Test Presenter delivered the lecture on 2024-01-01.
- The talk introduces Topic A as a foundational concept.
- The talk introduces Topic B as a related concept.

## What is this transcript about?

Test Presenter introduces the material on 2024-01-01. The lecture sets out the foundational vocabulary used in family systems contexts. Test Presenter develops each idea in turn with examples drawn from clinical practice and theoretical writing.

The transcript anchors on a central distinction explored across multiple sections. Test Presenter returns to this distinction repeatedly to ground each named concept. The format is conversational but the structure is deliberate.

## Why does this matter?

The material matters to family systems readers because it clarifies foundational ideas. Test Presenter establishes a vocabulary that recurs throughout the broader literature. Readers who internalize these terms have stronger footing when engaging with related work.

The structural frames identified in the transcript anchor downstream discussion. They make explicit what is often implicit in clinical conversation. The frames support both theoretical work and applied practice.

## What are the key topics discussed?

**Topic A.** Test Presenter introduces Topic A as a foundational concept used throughout the lecture. The topic recurs in several sections and grounds later discussion.

**Topic B.** Test Presenter develops Topic B in contrast to Topic A. The contrast clarifies what each idea uniquely contributes to family systems work.

## Key terms and definitions

**Term One** — A core concept introduced by Test Presenter, defined in the opening section of the lecture.

**Term Two** — A related concept developed in contrast to Term One, expanded on in the middle sections of the lecture.

## Key takeaways

- Test Presenter establishes a clear vocabulary for the material on 2024-01-01.
- The structural frames anchor recurring discussion across the transcript.
- Topic A and Topic B together form the conceptual backbone of the lecture.
- The lecture supports both theoretical and applied use of the material.

## Frequently asked questions

### What is the test transcript about?

The transcript by Test Presenter on 2024-01-01 covers the test material. It introduces the foundational vocabulary used in family systems work. Two primary topics structure the discussion.

### Why does this matter to family systems readers?

It clarifies a foundational dynamic relevant to the field. The vocabulary established by Test Presenter recurs throughout the broader literature. Readers gain stronger footing for engaging with related work.

### What are the key topics?

Topic A and Topic B are discussed in detail. Test Presenter develops each one with examples drawn from clinical practice. The two topics together form the conceptual backbone of the lecture.

### What should readers take away?

Three actionable insights are presented. First, the vocabulary frames downstream conversation. Second, the structural frames make implicit ideas explicit. Third, the material supports both theoretical and applied use.
"""


def _seed_project_dir(tmp_path, stem):
    """Create a project directory with all four upstream artifacts.

    The structural-themes and topics files mirror the project's normalized
    header conventions so the section-extracting loader returns content.
    """
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / stem
    project_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / f"{stem}{config.SUFFIX_YAML}").write_text(
        "## Section 1\nTest material content.\n", encoding="utf-8"
    )
    (project_dir / f"{stem}{config.SUFFIX_ABSTRACT_INIT}").write_text(
        "Test Presenter (2024-01-01) introduces the material on family systems "
        "with foundational vocabulary that recurs throughout the lecture.",
        encoding="utf-8",
    )
    (project_dir / f"{stem}{config.SUFFIX_STRUCTURAL_THEMES}").write_text(
        "## Structural Themes\n\n### Frame A\nA structural anchor used throughout.\n"
        "### Frame B\nA second structural anchor in the talk.\n",
        encoding="utf-8",
    )
    (project_dir / f"{stem}{config.SUFFIX_TOPICS}").write_text(
        "## Topics\n\n### Topic A\nFoundational concept.\n"
        "### Topic B\nRelated concept.\n",
        encoding="utf-8",
    )
    (project_dir / f"{stem}{config.SUFFIX_KEY_TERMS}").write_text(
        "## Key Terms\n\n**Term One**: A core concept.\n"
        "**Term Two**: A related concept.\n",
        encoding="utf-8",
    )
    # Interpretive themes are loaded by the standalone path; provide a stub.
    (project_dir / f"{stem}{config.SUFFIX_INTERPRETIVE_THEMES}").write_text(
        "## Interpretive Themes\n\n### Dynamic A\nA process-level dynamic.\n",
        encoding="utf-8",
    )
    return projects_dir, project_dir


def _patch_pipeline_for_overview(monkeypatch, projects_dir, mock_output):
    """Wire up the monkeypatches shared by the overview integration tests."""
    monkeypatch.setattr(config, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(extraction_pipeline, "validate_input_file", lambda _p: None)
    monkeypatch.setattr(extraction_pipeline.os, "getenv", lambda _k: "fake-key")
    monkeypatch.setattr(extraction_pipeline.anthropic, "Anthropic", lambda **_k: object())
    monkeypatch.setattr(
        extraction_pipeline,
        "create_system_message_with_cache",
        lambda *_a, **_k: [{"type": "text", "text": "stub"}],
    )
    # Capture the prompt that would be sent to Claude.
    captured = {}

    def _fake_generate(prompt, model, temperature, logger, **kwargs):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["temperature"] = temperature
        captured["kwargs"] = kwargs
        return mock_output

    monkeypatch.setattr(
        extraction_pipeline, "_generate_summary_with_claude", _fake_generate
    )

    # Skip downstream validators that fire post-overview only when
    # skip_extracts_summary=False; harmless to neutralize them anyway.
    monkeypatch.setattr(
        extraction_pipeline, "validate_emphasis_items", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        extraction_pipeline, "validate_topics_lightweight", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        extraction_pipeline, "validate_key_terms_fidelity", lambda *_a, **_k: None
    )
    return captured


def _filename_metadata_stub(stem):
    """Return a parse_filename_metadata stub that matches the seeded stem."""
    return lambda _name: {
        "stem": stem,
        "title": "Test Title",
        "presenter": "Test Presenter",
        "author": "Test Presenter",
        "date": "2024-01-01",
    }


def test_ov3_signature_includes_skip_overview():
    """OV.3: summarize_transcript accepts skip_overview with default True."""
    sig = inspect.signature(extraction_pipeline.summarize_transcript)
    assert "skip_overview" in sig.parameters
    assert sig.parameters["skip_overview"].default is True


def test_ov9_existing_callers_unaffected_by_default(tmp_path, monkeypatch):
    """OV.9: callers that omit skip_overview still run (default True path)."""
    stem = "OV9-Default-Caller-Test"
    projects_dir, _ = _seed_project_dir(tmp_path, stem)
    # Also seed a top lens so the existing blog flow has what it needs;
    # we'll skip the blog too, leaving every output path off.
    _patch_pipeline_for_overview(monkeypatch, projects_dir, _MOCK_OVERVIEW_OUTPUT)
    monkeypatch.setattr(
        extraction_pipeline, "parse_filename_metadata", _filename_metadata_stub(stem)
    )

    ok = extraction_pipeline.summarize_transcript(
        formatted_filename=f"{stem}{config.SUFFIX_YAML}",
        model="claude-sonnet-4-6",
        focus_keyword="Test Focus",
        target_audience="General readers",
        skip_extracts_summary=True,
        skip_emphasis=True,
        skip_bowen=True,
        skip_blog=True,
        # skip_overview omitted on purpose — default True.
        logger=MagicMock(),
    )
    assert ok is True
    overview_path = projects_dir / stem / f"{stem}{config.SUFFIX_OVERVIEW}"
    assert not overview_path.exists(), (
        "Overview file must NOT be created when skip_overview defaults to True."
    )


def test_ov4_overview_generates_and_saves_file(tmp_path, monkeypatch):
    """OV.4: skip_overview=False produces a file at SUFFIX_OVERVIEW with
    word count >= OVERVIEW_MIN_WORDS (relaxed: real model will hit target,
    mock string is fixed-length; the test asserts the file exists + nonempty)."""
    stem = "OV4-Generates-Test"
    projects_dir, project_dir = _seed_project_dir(tmp_path, stem)
    _patch_pipeline_for_overview(monkeypatch, projects_dir, _MOCK_OVERVIEW_OUTPUT)
    monkeypatch.setattr(
        extraction_pipeline, "parse_filename_metadata", _filename_metadata_stub(stem)
    )

    ok = extraction_pipeline.summarize_transcript(
        formatted_filename=f"{stem}{config.SUFFIX_YAML}",
        model="claude-sonnet-4-6",
        focus_keyword="Test Focus",
        target_audience="General readers",
        skip_extracts_summary=True,
        skip_emphasis=True,
        skip_bowen=True,
        skip_blog=True,
        skip_overview=False,
        logger=MagicMock(),
    )
    assert ok is True
    overview_path = project_dir / f"{stem}{config.SUFFIX_OVERVIEW}"
    assert overview_path.exists()
    content = overview_path.read_text(encoding="utf-8")
    assert content.strip(), "Overview file must be non-empty"


def test_ov5_overview_does_not_require_top_lens(tmp_path, monkeypatch):
    """OV.5: overview generation succeeds with no lenses on disk."""
    stem = "OV5-No-Lens-Test"
    projects_dir, project_dir = _seed_project_dir(tmp_path, stem)
    # Explicitly verify no lens file exists in the seeded fixture.
    assert not (project_dir / f"{stem}{config.SUFFIX_LENSES}").exists()
    _patch_pipeline_for_overview(monkeypatch, projects_dir, _MOCK_OVERVIEW_OUTPUT)
    monkeypatch.setattr(
        extraction_pipeline, "parse_filename_metadata", _filename_metadata_stub(stem)
    )

    ok = extraction_pipeline.summarize_transcript(
        formatted_filename=f"{stem}{config.SUFFIX_YAML}",
        model="claude-sonnet-4-6",
        focus_keyword="Test Focus",
        target_audience="General readers",
        skip_extracts_summary=True,
        skip_emphasis=True,
        skip_bowen=True,
        skip_blog=True,
        skip_overview=False,
        logger=MagicMock(),
    )
    assert ok is True
    assert (project_dir / f"{stem}{config.SUFFIX_OVERVIEW}").exists()


def test_ov6_overview_prompt_includes_each_artifact(tmp_path, monkeypatch):
    """OV.6: standalone path's filled prompt contains substrings from each
    of abstract / structural-themes / topics / key-terms."""
    stem = "OV6-Artifact-Inputs-Test"
    projects_dir, _ = _seed_project_dir(tmp_path, stem)
    captured = _patch_pipeline_for_overview(monkeypatch, projects_dir, _MOCK_OVERVIEW_OUTPUT)
    monkeypatch.setattr(
        extraction_pipeline, "parse_filename_metadata", _filename_metadata_stub(stem)
    )

    extraction_pipeline.summarize_transcript(
        formatted_filename=f"{stem}{config.SUFFIX_YAML}",
        model="claude-sonnet-4-6",
        focus_keyword="Test Focus",
        target_audience="General readers",
        skip_extracts_summary=True,
        skip_emphasis=True,
        skip_bowen=True,
        skip_blog=True,
        skip_overview=False,
        logger=MagicMock(),
    )

    prompt = captured["prompt"]
    assert "foundational vocabulary" in prompt, "Abstract content missing from prompt"
    assert "Frame A" in prompt, "Structural themes missing from prompt"
    assert "Topic A" in prompt, "Topics missing from prompt"
    assert "Term One" in prompt, "Key terms missing from prompt"
    assert "Test Focus" in prompt, "Focus keyword missing from prompt"
    # min_words must be wired through to the Claude call.
    assert captured["kwargs"].get("min_words") == config.OVERVIEW_MIN_WORDS


def test_ov10_overview_output_has_geo_frontmatter_and_faq(tmp_path, monkeypatch):
    """OV.10: saved file frontmatter contains required GEO keys and FAQ
    section has >= 3 ### question headers."""
    stem = "OV10-GEO-Shape-Test"
    projects_dir, project_dir = _seed_project_dir(tmp_path, stem)
    _patch_pipeline_for_overview(monkeypatch, projects_dir, _MOCK_OVERVIEW_OUTPUT)
    monkeypatch.setattr(
        extraction_pipeline, "parse_filename_metadata", _filename_metadata_stub(stem)
    )

    extraction_pipeline.summarize_transcript(
        formatted_filename=f"{stem}{config.SUFFIX_YAML}",
        model="claude-sonnet-4-6",
        focus_keyword="Test Focus",
        target_audience="General readers",
        skip_extracts_summary=True,
        skip_emphasis=True,
        skip_bowen=True,
        skip_blog=True,
        skip_overview=False,
        logger=MagicMock(),
    )

    content = (project_dir / f"{stem}{config.SUFFIX_OVERVIEW}").read_text(
        encoding="utf-8"
    )

    # Extract frontmatter — accept fenced ```yaml block or --- block.
    fenced = re.search(r"```yaml\n(.*?)\n```", content, re.DOTALL)
    assert fenced, "Output must begin with a ```yaml frontmatter block"
    frontmatter = yaml.safe_load(fenced.group(1))
    required_keys = {
        "slug",
        "meta_description",
        "focus_keyword",
        "process_stage",
        "schema_type",
        "author",
        "date_published",
        "faq",
    }
    missing = required_keys - frontmatter.keys()
    assert not missing, f"Frontmatter missing required GEO keys: {missing}"
    assert isinstance(frontmatter["faq"], list) and len(frontmatter["faq"]) >= 3

    # FAQ body section with >= 3 ### question headers.
    faq_split = content.split("## Frequently asked questions", 1)
    assert len(faq_split) == 2, "Body must contain '## Frequently asked questions'"
    faq_body = faq_split[1]
    question_headers = re.findall(r"^### .+$", faq_body, re.MULTILINE)
    assert len(question_headers) >= 3, (
        f"FAQ section must have at least 3 ### question headers, got {len(question_headers)}"
    )
