# Lean abstract path: standalone Topics stage + Topics-only abstract

## Context

Today a good abstract requires running the entire monolithic Core stage
(Structural Themes + Interpretive Themes + Topics + Key Terms + Lenses in one
`summarize_transcript` call), then `generate_structured_abstract`, which
*hard-requires* both the Topics and Interpretive-Themes artifacts
(extraction_pipeline.py:934-938). But the abstract prompt
(`prompts/Abstract Generation Prompt v1.md`) only ever uses metadata,
`opening_purpose` (from transcript), **topics**, `closing_conclusion` (from
transcript) and Q&A (from transcript) — **Interpretive Themes are passed in the
JSON but never referenced by the prompt.** So the themes requirement is
vestigial, and the minimum needed for a good abstract is **Topics + the
formatted transcript**.

Goal: let a user produce an abstract (and, independently, Emphasis + Bowen)
without generating Structural/Interpretive Themes, Key Terms or Lenses:

```
formatted text ──> Topics ──> Abstract          (Topics-only)
formatted text ──> Scored Emphasis              (already standalone today)
formatted text ──> Bowen References             (already standalone today)
```

Only two changes are needed (Emphasis/Bowen are already transcript-only and
already have a no-prerequisite stage).

## Acceptance criteria

**LA.1 — Standalone Topics generator.** A new `generate_topics(formatted_filename,
model=config.DEFAULT_MODEL, logger=None, transcript_system_message=None) -> bool`
in `extraction_pipeline.py` produces the `SUFFIX_TOPICS` artifact from the cached
transcript alone, reusing the *exact* PART-3 logic in `summarize_transcript`
(same `PROMPT_TOPICS_FILENAME`, `min_length=220`, the "## Topics" header-normalising
regex at extraction_pipeline.py:1101-1106, and `_save_summary(..., "topics")`).
Re-exported from `pipeline.py`. Test: `tests/test_lean_abstract.py::test_la1_generate_topics_writes_topics_artifact` (LLM mocked).

**LA.2 — Topics-only abstract.** `generate_structured_abstract` requires only the
Topics artifact; a missing Interpretive-Themes artifact is tolerated (themes passed
as `""`, which `parse_themes_from_extraction` already maps to `[]`). The
guard at extraction_pipeline.py:934 changes from "topics AND themes" to "topics
only". Behaviour with themes present is unchanged. Tests:
`test_la2_abstract_succeeds_without_interpretive_themes`,
`test_la2_abstract_still_fails_without_topics`.

**LA.3 — Topics stage in the GUI.** `ts_gui.py` gains a `topics` stage in
`STAGE_DEFINITIONS` (label "T. Topics"), placed after `yaml` and before `core`,
with a `_run_stage_topics` wrapper (`pipeline.generate_topics(f"{base_name}{SUFFIX_YAML}",
config.settings.DEFAULT_MODEL, logger)`) registered in `stage_runners`. Test:
`test_la3_topics_stage_registered` (asserts key present in STAGE_DEFINITIONS + stage_runners).

**LA.4 — Topics stage dependency.** `STAGE_DEPENDENCIES["topics"]` requires the
transcript, satisfiable by the `yaml` stage or an existing `SUFFIX_YAML` artifact
(mirrors `core`). Test: `test_la4_topics_depends_on_yaml`.

**LA.5 — Abstract dependency relaxed to Topics-only.** `STAGE_DEPENDENCIES["gen_abstract"]`
changes from two AND-groups (`core`→Topics **and** `core`→Interpretive Themes) to a
single OR-group satisfiable by **either** the new `topics` stage **or** `core`
(both write `SUFFIX_TOPICS`): `[(("topics", "SUFFIX_TOPICS"), ("core", "SUFFIX_TOPICS"))]`.
Interpretive Themes is no longer a prerequisite. Tests:
`test_la5_gen_abstract_depends_on_topics_only`,
`test_la5_preflight_allows_topics_then_abstract` (pre-flight passes for
`{topics, gen_abstract}` with a yaml artifact present, and for `{gen_abstract}`
with only a topics artifact on disk),
`test_la5_preflight_blocks_abstract_without_topics` (neither topics/core selected
nor topics artifact on disk → blocked, message names "Topics").

## Out of scope

- Per-item selectability of the other Core artifacts (Structural/Interpretive/Key
  Terms/Lenses) — Core stays monolithic; only Topics gets a standalone path.
- Changing the abstract-initial produced *inside* Core (it still runs with themes,
  which Core generates anyway).
- Any change to Emphasis/Bowen — already transcript-only with a no-prerequisite stage.

## Verification

- `pytest tests/test_lean_abstract.py tests/test_stage_dependencies.py -q` (headless, LLM mocked).
- Real-file smoke: extend the existing scratch smoke script to select `{topics, gen_abstract}`
  against `test1/`, confirm pre-flight passes; and `{gen_abstract}` with no topics → blocked.
