# Implementation Plan: Overview Blog Post (parallel to Lens-based Blog)

Date: 2026-05-13
Author: Claude (planning step per global workflow rule #1)
Scope: Add a second, optional "Overview Post" generator that runs alongside
the existing Lens-#1 blog post. The user selects which post to produce.

---

## 1. Background

Today, `summarize_transcript()` in `extraction_pipeline.py` produces one blog
post from one input: the validated top-ranked lens (`top_lens`).
- Prompt: `prompts/Transcript Summary Blog Post v1.md`
- Output suffix: `config.SUFFIX_BLOG` (` - blog.md`)
- GUI entry: button "7. Blog (Lens #1)" at `ts_gui.py:649` → `do_generate_blog()`
  at `ts_gui.py:1480`
- CLI entry: `summarize_transcript(..., skip_blog=False, ...)`
- The blog generation block is gated by `if not skip_blog:` at
  `extraction_pipeline.py:1334`, and requires a validated `top_lens` to exist.

The user wants a second post type with a different intent:
"what this transcript is, why it matters, key topics discussed, takeaways."
This post does not need lenses; it needs the upstream artifacts (abstract,
topics, key terms, structural themes).

Per the user: the two posts are parallel artifacts — the lens-based post
re-surfaces source material through a specific angle; the overview post
orients a new reader. Keep both.

---

## 2. Acceptance Criteria

Each criterion has an ID (OV.N) and a specific verification method.

| ID | Criterion | Verification |
|----|-----------|--------------|
| OV.1 | A new prompt file `prompts/Transcript Summary Overview Post v1.md` exists with the template variables `{{focus_keyword}}`, `{{target_audience}}`, `{{title}}`, `{{presenter}}`, `{{date}}`, `{{abstract}}`, `{{structural_themes}}`, `{{topics}}`, `{{key_terms}}`. | File existence + `grep -c '{{...}}'` for each placeholder. |
| OV.2 | `config.py` defines `SUFFIX_OVERVIEW = " - overview.md"`, `PROMPT_OVERVIEW_FILENAME = "Transcript Summary Overview Post v1.md"`, and `OVERVIEW_MIN_WORDS = 800` (matches the unit pattern of existing `BLOG_MIN_WORDS = 800`, not `MIN_BLOG_CHARS`). | `grep -n "SUFFIX_OVERVIEW\|PROMPT_OVERVIEW_FILENAME\|OVERVIEW_MIN_WORDS" config.py`. |
| OV.3 | `summarize_transcript()` accepts a new keyword-only `skip_overview: bool = True` parameter without breaking existing positional callers. | pytest: `test_summarize_transcript_signature_accepts_skip_overview`. |
| OV.4 | When `skip_overview=False` and required artifacts are present, an overview post is generated and saved with `SUFFIX_OVERVIEW`. | pytest with mocked Anthropic client: assert `<base> - overview.md` exists in the project dir and `len(content.split()) >= OVERVIEW_MIN_WORDS`. |
| OV.5 | Overview generation does NOT require a validated `top_lens`. | pytest: `test_overview_runs_without_top_lens` — invoke standalone overview path with no lenses on disk; assert success and file existence. |
| OV.6 | When invoked standalone (`skip_extracts_summary=True`), the overview path loads `abstract`, `topics`, `key_terms`, `structural_themes` from existing project files. | pytest: pre-seed a project dir with the four files; assert the prompt received contains substrings from each. |
| OV.7 | The GUI exposes a new control "7b. Overview Post" that calls `summarize_transcript` with `skip_extracts_summary=True, skip_emphasis=True, skip_bowen=True, skip_blog=True, skip_overview=False`. | String match in `ts_gui.py`: button text "7b. Overview Post" + handler `do_generate_overview` + the exact skip-flag tuple in its call. |
| OV.8 | GUI file-listing in `ts_gui.py:1028` includes an `("Overview", ...)` entry pointing at `<base>{SUFFIX_OVERVIEW}`. | `grep -n '"Overview"' ts_gui.py` + line content match. |
| OV.9 | Existing call sites pass `skip_overview=True` by default and existing behavior (lens-based blog) is unchanged. | pytest: rerun current `test_extraction_*` suite; assert no diff in output files for a lens-blog-only run. |
| OV.10 | An end-to-end smoke test (mocked Claude responses) exercises overview generation and asserts the saved file's frontmatter contains the required GEO keys: `slug`, `meta_description`, `focus_keyword`, `process_stage`, `schema_type`, `author`, `date_published`, `faq`. The body contains the H2 "Frequently asked questions" section and at least three `### ` Q-headers under it. | pytest: parse YAML frontmatter; assert keys present and `faq` is a non-empty list. Body regex: `^### .+$` count ≥ 3 inside FAQ section. |
| OV.11 | The "Do All Steps" path is NOT changed in this work (overview is opt-in only). | Manual: confirm that `do_all_steps` in `ts_gui.py:1795` still produces only the lens blog, not the overview. (Human-verify by reading the diff; this is the "no silent expansion" check.) |

OV.11 is the only human-verified criterion; everything else is automated.

---

## 3. Order of Implementation

Dependencies are linear; each step depends on the prior.

1. **Prompt content (OV.1) — GEO-optimized.** Author
   `prompts/Transcript Summary Overview Post v1.md`. The post is designed
   for **Generative Engine Optimization** (Perplexity, ChatGPT search,
   Google AI Overviews, Claude). Design principles, each tied to a known
   AI-search retrieval signal:

   | GEO principle | What it produces in the post |
   |---|---|
   | Definitional opener (entity-first) | First sentence is `<Title> is a <type> by <Presenter> (<date>) about <subject>.` Pure declarative, no hook. |
   | TL;DR block above the fold | 40–60 word abstract-of-the-abstract immediately after H1, plus a 3-bullet "Key facts" list. Citable atoms. |
   | Question-shaped H2s | Section headings phrased as natural-language queries (e.g. "What is this transcript about?", "Why does this matter?", "What are the key topics?"). Matches how AI search rewrites user queries. |
   | Atomic, citable statements | Body uses short declarative sentences with named entities (people, concepts, dates) on the same line as the claim. Avoid pronoun-chained paragraphs. |
   | Explicit attribution | Author/presenter, date, source title repeated at least once in body prose so a snippet retrieval includes provenance. |
   | Named-entity surfacing | Key terms appear as **bold** on first mention, then in a dedicated "Key terms" definition list (term → 1-sentence definition). |
   | FAQ block | Trailing "Frequently asked questions" section: 4–6 Q/A pairs the post answers. Drives AI-search FAQ extraction. |
   | Schema hint | YAML frontmatter includes `schema_type: "Article"` and a `faq:` list (mirrors the FAQ section). Downstream HTML generator can convert to JSON-LD later; for now it's a machine-readable hint. |
   | Stable canonical structure | Section order is fixed (see below) so retrieval signatures are predictable. |

   **Section structure (fixed order):**

   ```
   <YAML frontmatter: slug, meta_description, focus_keyword,
    target_audience, process_stage="overview_post",
    schema_type="Article", author, date_published,
    faq: [{q, a}, ...]>
   # <Title>
   <Definitional opening sentence.>

   ## TL;DR
   <40–60 words.>
   - <Key fact 1>
   - <Key fact 2>
   - <Key fact 3>

   ## What is this transcript about?
   <Anchored on abstract. 2–3 short paragraphs.>

   ## Why does this matter?
   <Anchored on structural themes + abstract. Atomic statements.>

   ## What are the key topics discussed?
   <Rendered from topics. Each topic = bold lede + 1–2 sentences.>

   ## Key terms and definitions
   <Definition list from key_terms.>

   ## Key takeaways
   - <3–5 atomic, citable takeaways>

   ## Frequently asked questions
   ### <Q1>
   <A1, 2–4 sentences>
   ### <Q2>
   <A2>
   ...
   ```

   **Constraints in the prompt:**
   - Target word count: `{{target_word_count}}` (passed in from config).
   - Stay grounded in source material; no invented claims.
   - Include focus keyword in title, opening sentence, and one H2.
   - No lens, no hooks, no rationale.

   The blog prompt remains untouched.

2. **Config (OV.2).** Add the three constants. Wire them into the
   `config.settings`/`config.show_config` machinery if those files enumerate
   constants (check `config.py:745–811`). No env-var exposure for now.

3. **Pipeline plumbing (OV.3, OV.5, OV.6, OV.9).**
   - Add `skip_overview: bool = True` to `summarize_transcript`.
   - After the existing `if not skip_blog:` block (`extraction_pipeline.py:1334`),
     add `if not skip_overview:` block that:
     - Does NOT require `top_lens`.
     - Loads `abstract_output` from `<stem>{SUFFIX_ABSTRACT_INIT}` (or the
       generated/validated abstract if present) via the same
       `_load_section_from_project_file` helper already used at line 1248–1259
       for the standalone-blog path.
     - Calls `_load_summary_prompt(config.PROMPT_OVERVIEW_FILENAME)`,
       `_fill_prompt_template(...)` (passing `target_word_count=config.OVERVIEW_MIN_WORDS`),
       and `_generate_summary_with_claude(...)`.
     - Enforcement: `_generate_summary_with_claude` natively accepts a
       `min_words` parameter (verified at `extraction_pipeline.py:86`).
       Pass `min_words=config.OVERVIEW_MIN_WORDS` directly. This is cleaner
       than the blog's char-only enforcement and is the native word-count
       guard in the existing helper.
     - Saves with `_save_summary(output, formatted_filename, "overview")`.
   - Decision: the prompt is invoked with `transcript_system_message` as the
     cached system message (same as blog) so prompt caching is preserved.

4. **GUI (OV.7, OV.8).**
   - Add button "7b. Overview Post" next to "7. Blog (Lens #1)" at
     `ts_gui.py:649`. Pick a free grid slot (row 2, col after blog) without
     disturbing the existing layout.
   - Add `do_generate_overview()` mirroring `do_generate_blog()` at
     `ts_gui.py:1480` with the skip flags tuple in OV.7.
   - Add the "Overview" entry to the file-listing block at `ts_gui.py:1028`.
   - Add a state-enable line to the button-state updater at `ts_gui.py:1903`.

5. **Tests (OV.4, OV.10, plus regression).**
   - New file `tests/test_overview_post.py` with the three pytest tests
     described in OV.4–OV.6 and OV.10. Use the same mocking style as the
     existing extraction tests under `tests/`.
   - Run full `pytest` to verify OV.9.

6. **Status report.** Generate `docs/spec_coverage_2026-05-13.md` with the
   OV.N table per global rule #6 once implementation completes.

---

## 4. Variables Available to the Overview Prompt

Confirmed from the pipeline state at point of overview generation:

| Variable | Source | Standalone-path source |
|----------|--------|------------------------|
| `{{focus_keyword}}` | function arg | function arg |
| `{{target_audience}}` | function arg | function arg |
| `{{title}}` | `metadata["title"]` (parse_filename_metadata) | same |
| `{{presenter}}` | `metadata.get("presenter", metadata.get("author",""))` | same |
| `{{date}}` | `metadata.get("date","")` | same |
| `{{abstract}}` | `abstract_output` from PART 5 | load `<stem>{SUFFIX_ABSTRACT_INIT}` |
| `{{structural_themes}}` | `structural_output` from PART 1 | load `<stem>{SUFFIX_STRUCTURAL_THEMES}` |
| `{{topics}}` | `topics_output` from PART 3 | load `<stem>{SUFFIX_TOPICS}` |
| `{{key_terms}}` | `key_terms_output` from PART 4 | load `<stem>{SUFFIX_KEY_TERMS}` |

The standalone-path loader at `extraction_pipeline.py:1248–1259` already
loads three of the four. Abstract loading is the only new helper invocation
needed.

---

## 5. Out of Scope

- CLI flag wiring — `main.py` is a stub and is not used as an entry point.
- "Do All Steps" inclusion of the overview — explicitly excluded (OV.11) so
  the new artifact is opt-in.
- Validation of overview output — no back-validator for the overview post
  yet. A future increment may add one once the prompt stabilizes.
- Changes to the lens-based blog prompt or its pipeline.
- HTML/PDF rendering of the overview — packaging pipeline is not touched.

---

## 6. Adjacent Issues Found (Not Fixed)

Per global rule #8, flagged but not fixed in this change:

1. **`PROMPT_BLOG_FILENAME` magic string in the prompt-loader** —
   `_fill_prompt_template` does not currently validate that all `{{...}}`
   placeholders in the template are supplied. Missing keys may render as
   literal `{{key}}` in the output. Worth a follow-up to add strict-mode
   validation in the templating helper. (file: `extraction_pipeline.py`,
   the `_fill_prompt_template` definition near the top of the file)

2. **`SUFFIX_ABSTRACT_INIT` vs `SUFFIX_ABSTRACT_GEN`** — the project stores
   both an initial abstract and a generated/validated abstract. The standalone
   path's choice between them is currently ad-hoc. For the overview, this
   plan defaults to `SUFFIX_ABSTRACT_INIT` since it's always written
   (validation is optional). Worth a follow-up to add a single canonical
   "best available abstract" resolver. (file: `extraction_pipeline.py`,
   abstract loading area)

3. **GUI button-row layout** — the button grid is hand-laid; adding "7b"
   is fine for one button but the row is getting dense. A follow-up to
   group the post-extraction buttons into a sub-frame would help readability.
   (file: `ts_gui.py:649–680`)

These are not addressed here. They are listed so the user can decide
whether to schedule follow-ups.

---

## 7. Open Questions for the User

None blocking. Soft questions the user can override during review:

- Q1: `OVERVIEW_MIN_WORDS = 800` (mirrors `BLOG_MIN_WORDS = 800`). Adjust
  if you want shorter/longer overviews.
- Q2: Section order is fixed by GEO-retrieval logic (definitional opener →
  TL;DR → what/why/topics → terms → takeaways → FAQ). Reordering reduces
  GEO effectiveness; flag if you have a strong reason to swap.
- Q3: `schema_type: "Article"` in frontmatter — appropriate now; could be
  upgraded to `"FAQPage"` or `"Course"` later. Default to Article unless
  you say otherwise.
- Q4: FAQ count: 4–6 pairs. Reasonable, but say if you want a hard number.

---

## 8. What I Will NOT Do Until You Approve

- Write the prompt.
- Touch `config.py`, `extraction_pipeline.py`, or `ts_gui.py`.
- Create the test file.

I will wait for your sign-off on this plan (or your requested edits) before
proceeding to step 1.
