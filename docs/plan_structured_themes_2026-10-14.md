# Plan: structured theme output (ST) — 2026-10-14

Status: **built 2026-10-14; ST.1–ST.7 tested; ST.8 and ST.9 wait on the end-to-end
rounds.** Approved by the author 2026-10-14. See "Built" at the end for what differs
from the plan.

## Problem

The structural and interpretive theme stages return free-form markdown, and every later
step reads it back with patterns. The model's layout drifts, and each drift has needed a
fix:

| Date | Drift | Fix |
|---|---|---|
| 2026-10-12 | a third theme layout (list items) | T1 parser |
| 2026-10-13 | "Nested under structural theme(s)" read as evidence | TM |
| 2026-10-13 | closing notes read as the last theme's evidence | TE |
| 2026-10-13 | closing notes shown on the page | TD |
| 2026-10-14 | closing notes sent to the overview and lens prompts | TP |
| 2026-10-14 | a new label "Summary" inside a theme (E2E run 4) | reported, not fixed |
| 2026-10-14 | a new label "Closing paragraph:" (E2E run 5) | reported, not fixed |

One cause stands out: both theme prompts ask for "one short paragraph summarizing…"
after the list, so a closing note is requested every time, and the model labels it
differently each run.

## Goal

The model returns the themes as JSON that must match a schema. The pipeline then writes
the markdown file itself, in one fixed layout. Notes the model wants to add go in a JSON
field that is never shown or judged. Layout drift becomes impossible for new runs.

## Design

1. **Schema.** `schemas/themes.schema.json` goes to version 2 with every field the
   prompts ask for.
   - Structural theme: `number`, `title`, `description`, `key_evidence` (list of
     strings), `coverage_role`.
   - Interpretive theme: `number`, `title`, `description`, `nested_under` (list of
     structural theme numbers), `key_evidence`, `lens_fuel_value`.
   - Both kinds: an optional top-level `rationale` string. This is the closing paragraph
     the prompts ask for; it is kept in the JSON only.
   - A version-1 file (number, name, description, derived from markdown) still validates
     as a legacy shape.
2. **Generation.** The theme stages call the model with structured output
   (`output_config.format` = JSON schema). This works on claude-sonnet-5-5, with
   thinking and streaming. Forced tool use is rejected on Sonnet 5.5, so tool use is not
   used.
   - `call_claude_with_retry` gets an `output_format` argument. It is merged into the same
     `output_config` that already carries the thinking level, sent through `extra_body` as
     effort is today.
   - The API ignores `minLength` and number limits, so the full schema is checked locally
     afterwards (`artifact_contracts`), along with:
     - numbers run 1..N;
     - every `nested_under` number exists among the structural themes;
     - required strings are not empty.
   - A reply that fails these checks is retried, and the stage fails closed after the
     retries, as now.
3. **Rendering.** `artifact_contracts.themes_to_markdown` writes the canonical layout from
   the JSON: `**N. Title**` then `**Description:**`, `**Key evidence:**`, and so on, with
   fixed labels. The `rationale` field is never rendered. Both files are saved:
   - `*-themes.json`, the source of truth (version 2);
   - `*-themes.md`, rendered from it.
4. **Prompts.** Both theme prompts describe the fields instead of a layout. The closing
   paragraph request becomes the `rationale` field. The naming rule (E2E2) stays.
5. **Consumers unchanged in this phase.** The page, judge, lens prompts, overview, abstract,
   summary, bundle and webpage checks keep reading the `.md` file. A rendered file has one
   known layout, so the existing parsers read it exactly. This keeps the change small and
   leaves the judge's input format unchanged. Switching consumers to the JSON is phase 2.
6. **Every theme producer uses it:**
   - core generation (PART 1 and 2);
   - the regeneration inside the theme/lens validation loop;
   - the interpretive prompt's input. It gets the rendered structural themes through
     `themes_for_prompt`, unchanged.
7. **Existing projects.** Old `.md` files keep working through today's parsers (T1, TM,
   TE, TD, TP stay for them). Nothing is converted. Re-running Core on a project produces
   the new format.

## Acceptance criteria and tests

| ID | Criterion | Test |
|---|---|---|
| ST.1 | Schema v2 accepts a full structural and interpretive object, rejects a missing required field, an extra field, an empty title, numbers out of order, and an interpretive `nested_under` number with no structural theme | `tests/test_structured_themes_st.py::test_st1_*` |
| ST.2 | `call_claude_with_retry(output_format=…)` sends `output_config.format` with the schema and keeps `effort` in the same object | `::test_st2_request_has_format_and_effort` (fake client, real request builder) |
| ST.3 | Generation retries a reply that is not valid JSON or fails the local checks, and fails closed after the retries | `::test_st3_invalid_reply_retried_then_fails` |
| ST.4 | Rendered markdown re-parses, with today's parsers (`theme_display_blocks`, `parse_theme_blocks_with_evidence`), to exactly the JSON's titles, descriptions and evidence; `rationale` never appears in the markdown, page, judge input or prompt text | `::test_st4_round_trip_*` (property test over generated objects plus the real fixtures converted to JSON) |
| ST.5 | Every theme producer (core PART 1/2, validation-loop regeneration) writes both files; the `.md` is the rendering of the `.json` | `::test_st5_all_producers_write_json_and_md` |
| ST.6 | The prompts contain no layout or closing-paragraph instruction and describe each field | `::test_st6_prompts_describe_fields` |
| ST.7 | Old `.md` files (all real fixtures) still parse as before: same theme list, same judge input | existing TD/TE/TM/TP tests plus `::test_st7_legacy_fixtures_unchanged` |
| ST.8 | Cost estimate rows for the theme stages still match measured output | `::test_st8_estimate_rows` |
| ST.9 | End-to-end: three public talks, two rounds; every theme stage passes, theme judge PASS rate not lower than runs 3–5, no unclassified field and no trimmed note reported | human-reviewed run report (below) |

## Cannot be fully tested in code (human review proposed)

Theme quality. Structured output might change what the model writes: longer or shorter
descriptions, evidence as fragments. For the three talks, I would put the new themes
next to the ones from end-to-end run 5 and ask you to read them. That's about 10 minutes
of reading.

## Order

1. ST.1 schema and validation.
2. ST.2 request plumbing.
3. ST.4 renderer and round trip.
4. ST.3 generation with retries.
5. ST.6 prompts.
6. ST.5 wire all producers.
7. ST.7 and ST.8 regression checks.
8. learning-qa review.
9. ST.9 end-to-end runs and your side-by-side read.

## Cost

End-to-end measurement: two rounds on three talks, about $12. Theme generation itself
should cost about the same as now, since the output is the same content in JSON. The first
request with a new schema has a one-time compile delay, and the API caches the schema for
24 hours.

## Risks

- The SDK version in use may not accept `output_config` as an argument. It is already
  sent through `extra_body` for effort, and the format goes the same way. ST.2 tests it.
- `rationale` must never leak. ST.4 checks every reader.
- Quality change (see human review). If the themes are worse, the prompts are adjusted
  before the change goes live, not after.

## Phase 2 (not in this plan)

- Consumers read the JSON directly: page, judge, prompts. Then the pattern parsers are
  needed only for old files.
- The same approach for the other free-form outputs that are parsed: topics, key terms,
  ranked lenses, emphasis, Bowen references.

## Adjacent issues found, not fixed

- `skills/trans-summary-output-critic/scripts/review_outputs.py` cannot read the current
  theme layout (TODO, found in the TP review).
- The summary and overview prompts receive topic coverage percentages that the judge
  cannot check (TODO, E2E review).

## Built (2026-10-14)

Code: `schemas/themes.schema.json` (version 2), `artifact_contracts.py`
(`check_structured_themes`, `structured_themes_from_reply`, `themes_model_schema`,
`themes_to_markdown`), `transcript_utils.call_claude_with_retry` (`output_format`,
`check_reply`), `extraction_pipeline._generate_structured_themes` and `_save_themes`.
Tests: `tests/test_structured_themes_st.py`.

Differences from the plan:

- **Interpretive themes are regenerated when the structural themes are.** In the
  theme/lens validation loop, a rejected structural set used to be regenerated alone,
  and the kept interpretive themes still named the old structural themes. With numbers
  in `nested_under` that would point at the wrong theme or at none, so new structural
  themes now bring new interpretive themes. This adds one call only when the validator
  rejects the structural themes (none in end-to-end runs 1–5).
- **A parser fix found by the round-trip test.** When the last theme's last field
  started with "# ", the trimming code (`_theme_own_text_report`) took the start of the
  value for a line start and cut the field from the page. It now searches from the
  field's end, so only a real line start counts. No fixture changed (ST.7 snapshot).
- **Both theme sets are saved together.** PART 1 used to save the structural themes
  before PART 2 ran; if PART 2 failed, the new structural file sat next to the earlier
  run's interpretive file, which names the earlier structural themes (review finding).
  Both are now saved after both are generated.
- **Read-back before saving.** `_save_themes` checks that the rendered markdown reads
  back to the object's themes; if not (a renderer bug), it raises and writes nothing.
- **Models without structured output.** `model_specs` has a `structured_output` flag
  (Claude 4.5 and later). On another model the theme stage fails before any request,
  with the reason, instead of a "malformed request" from the API.
- **Title check.** A title the parsers skip as a heading ("Summary", "Conclusion",
  "… (3 total)", "# …") is rejected and retried, since it would vanish from the page.
- **Whitespace.** Every string in the reply is reduced to single spaces, so each field
  is one line in the markdown and reads back the same.
- **Old T2 tests replaced.** They checked that the prompts describe the markdown
  layout; the prompts no longer do (ST.6).
- **Cache.** The API puts the schema in front of the cached transcript, so each theme
  call writes its own cache entry instead of reading the shared one. Measured on Why
  Families: 8,263 and 8,315 tokens written where run 5 read 8,074. That is about $0.03
  per call on an 8k-token talk, more on longer ones.
- **Quotes.** In JSON the model quotes with single quotes ('…') where the old files used
  double quotes. No check reads quotes from theme files (the verbatim check reads Bowen
  and emphasis quotes only).

Live smoke test (Why Families, public, claude-sonnet-5-5, about $0.15): both calls
passed on the first attempt, 3 structural and 8 interpretive themes. Output 2,061 and
3,957 tokens (run 5: 2,539 and 4,544).
