# Plan: structured theme output (ST) — 2026-10-14

Status: **built 2026-10-14 (commit 24e0a3f); ST.1–ST.8 tested; ST.9 end-to-end rounds
done (runs 6 and 7, below); the author's side-by-side read of the themes is pending.**
Approved by the author 2026-10-14. See "Built" at the end for what differs from the plan.

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
  call writes its own cache entry instead of reading the shared one. The later calls
  (Topics, Key Terms) still read the shared cache. Measured in runs 6 and 7: 8.5k–28k
  tokens written per theme call, $0.04–0.12 per talk for the two calls, less the
  smaller output ($0.01–0.03): about $0.04–0.11 more per talk.
- **Quotes.** In JSON the model quotes with single quotes ('…') where the old files used
  double quotes. No check reads quotes from theme files (the verbatim check reads Bowen
  and emphasis quotes only).

Live smoke test (Why Families, public, claude-sonnet-5-5, about $0.15): both calls
passed on the first attempt, 3 structural and 8 interpretive themes. Output 2,061 and
3,957 tokens (run 5: 2,539 and 4,544).

## ST.8 — estimate rows (2026-10-14)

The old rows (structural `max(0.12T, 1100)`, interpretive `max(0.20T, 2000)`, plus the
Effort setting's thinking, priced as cache reads) were about 2x high for structural and
1.4x high for interpretive, before and after ST. The theme calls follow the Effort
setting, so the rows now hold the visible output (the JSON reply) and the thinking is
added as for other rows:

| Talk (transcript tokens) | Structural visible, runs 6 / 7 | Interpretive visible, runs 6 / 7 |
|---|---|---|
| Beautiful Boy (18,753) | 1,481 / 1,417 | 2,455 / 2,602 |
| Systems Biology (17,416) | 1,587 / 1,432 | 3,037 / 2,724 |
| Why Families (5,660) | 1,212 / 1,393 | 2,160 / 2,455 |

New rows: `config.THEME_OUTPUT_PCT` / `THEME_OUTPUT_FLOOR`, structural `max(0.08T, 1600)`,
interpretive `max(0.16T, 3100)`, priced as cache writes of prompt + transcript (+ the
structural themes for interpretive). Thinking measured at high effort was 375–1,168
(structural) and 1,355–2,036 (interpretive) per call; the shared estimate adds 3,000 per
call at high, so these rows' totals stay high (TODO). Test: `::test_st8_estimate_rows`.

## ST.9 — end-to-end rounds (2026-10-14)

Runs 6 and 7, all 16 stages on Beautiful Boy, Systems Biology and Why Families
(public talks), claude-sonnet-5-5. Run 6 cost $6.26, run 7 $6.08 (run 5: $6.05).

| | Run 5 (old) | Run 6 | Run 7 |
|---|---|---|---|
| Theme calls passed on the first attempt | n/a | 6 of 6 | 6 of 6 |
| Theme judge (`theme_grounding`) | PASS 3 of 3 talks | PASS 3 of 3 | PASS 3 of 3 |
| Unclassified theme fields reported | 1 (Beautiful Boy) | 0 | 0 |
| Trimmed theme notes | 0 | 0 | 0 |
| `.md` equal to the rendering of the `.json` | n/a | 6 of 6 | 6 of 6 |
| Validator rejected a theme set | 0 | 0 | 0 |
| Gate | 3 allowed | 2 allowed, 1 blocked (Format) | 2 allowed, 1 blocked (Format, abstract) |

The criterion is met: every theme stage passed, the theme judge passed every talk, and
no unclassified field or trimmed note was reported. The blocks were not theme stages:

- Run 6, Systems Biology: Format wrote one malformed heading (section 48, timestamp
  `[00:01:02:04]` and a trailing period) and dropped "the,".
- Run 7, Beautiful Boy: Format had two differences from the source; the abstract kept
  one unfaithful Q&A sentence after three attempts (from the pattern-made `qa_topics`,
  TODO).
- Run 7: the structured summary failed on two talks (580 and 562 words, under the
  585-word floor on all three attempts; TODO).

Theme length (average words): structural descriptions 72–97 (run 5: 78–89);
interpretive descriptions 57–74 (run 5: 78–99), so about 25% shorter; whole themes
slightly longer, since the evidence lists hold more items. Systems Biology got 3
structural themes in runs 6 and 7 (run 5: 4).

Human review: `docs/calibration/2026-10-14_structured_themes/side_by_side.html` (made
by `side_by_side.py` in the same folder) puts runs 5, 6 and 7 next to each other.
