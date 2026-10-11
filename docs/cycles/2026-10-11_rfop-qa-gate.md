# learning-qa QA gate — RF.O + RF.P web-check fixes

Range reviewed: `0da7469..HEAD`
Gate date: 2026-10-11
Reviewer: learning-qa failure-pattern sweep (skill preloaded)

## VERDICT: APPROVED

## RANGE / COMMITS

- `2973030` fix(webpage): Simple Web check reads the current simple-page layout (RF.O)
- `bd542a7` fix(webpage): web checks read topics, themes and key terms correctly (RF.P)
- `cec057e` docs: add the 2026-10-09 independent-reviewer specs, reviews and mutation-gate prompt

Code + tests live in the first two commits; `cec057e` is docs-only (specs, reviews,
CHANGELOG, TODO, mutation-gate prompt). No production code in `cec057e`.

Files in the code/test diff:
- `transcript_validate_webpage.py` (+160 / -343)
- `tests/test_simple_web_validation.py` (+224, new)

## TEST RESULT

`.venv/bin/python -m pytest -q` → **1222 passed, 23 skipped, 3 xfailed** (0 failed).
Working tree clean after the run (no leaked artifacts; `git status` empty).

## APPLICABLE PATTERNS

- P19 (producer/consumer format-contract drift) — the central pattern: source side
  must read the format the pipeline *writes*, via the shared parser, not a second regex.
- P7 (misaligned/lenient proxy) — substring match direction.
- P2 (silent drop) — source file that parses to nothing.
- P28/P34 (test reaches production data) — checked, no issue.
- P29 (floor assertion) — checked, no issue.
- P10 (test effort / fix-to-test map) — checked, mapped.

## FINDINGS

None of medium or higher severity. Two low-severity notes, neither blocking.

### 1. LOW — P7 — `transcript_validate_webpage.py:75` (`missing_names`)

`missing_names` matches a source name when its normalized form is a *substring* of
any page name (`n in h`). A source name that is a substring of a *different* page
item is counted present. E.g. source term "Self" would be counted present if the
page still carries "Differentiation of Self" — so a genuinely dropped short/generic
term is silently skipped.

- Risk: low. The mismatch path is a *warning*, not an issue (spec RF.P.3 "a mismatch
  stays a warning"); topic/theme/term names in this domain are long distinctive
  phrases; and this is strictly stricter than the old bidirectional
  (`src in html or html in src`) matching it replaces.
- The adversarial test `test_rfp3_missing_names_needs_the_whole_source_name` pins the
  reverse direction (shorter page name inside longer source name is a miss) but not
  this substring-of-a-different-item case.
- Fix (if desired): match on token-boundary or require the page name to be a
  prefix/suffix extension of the source name rather than any-substring.

### 2. LOW (informational) — P19 — `transcript_validate_webpage.py:834`

A *partial* item miss (some of N topics/themes/terms absent) is recorded as a
`warnings.append`, so `validate_webpage` returns `True` while items are missing.
Only a *fully empty* section is an `issue` (the `has_*` checks at :661–690). This is
explicitly spec-approved (RF.P.3: "a mismatch stays a warning"), so it is a recorded
decision, not a defect. Noted for completeness: the CLI exit code / stage failure is
driven by `len(issues) == 0`, so a page missing 1 of 10 themes "passes" with a printed
warning.

## CHECKED (per pattern checklist)

- Single-source-of-truth (pitfall 2): confirmed. `extract_topics_themes_metadata`
  reads topics/themes/key-terms through `artifact_contracts.codec(key).parse_markdown`
  — the same parsers the producers write through (`topics_from_markdown`,
  `themes_from_markdown`, `key_terms_from_markdown`). Field names verified against the
  codec item shapes (`name` for topics/themes, `term` for key_terms; themes take a
  `kind` arg). No parallel hand-copied regex remains on the source side.
- Fail-closed on unparseable source (P2): a file with a body that parses to zero items
  raises `SchemaError` (via `Codec.parse_markdown`), surfaced in `source_meta["source_errors"]`
  and appended to `issues` (:603–605) → `validate_webpage` returns False. Test:
  `test_rfp1_unreadable_source_artifact_fails`.
- Legend marks excluded from highlight counts (RF.O.1): `_metadata_from_sections` counts
  `mark`s only inside `transcript_root`; the legend `<mark>`s (no `title` attr) are also
  ignored by `find_missing_*` because `_title_label` returns `""` for title-less marks.
  Verified against `templates/simple_webpage.html` legend (lines 72–78) and
  `templates/webpage.html` legend (lines 44–49).
- Return-contract stability (P22): no changed return type/shape. `extract_html_metadata`,
  `extract_html_simple_metadata`, `extract_topics_themes_metadata` all return the same
  dict keys as before, plus one new `source_errors` key read via `.get("source_errors", [])`.
  All callers of these functions are inside `transcript_validate_webpage.py` itself
  (grep confirmed) — no stale external call sites.
- Test isolation (P28/P34): `test_simple_web_validation.py` monkeypatches
  `config.PROJECTS_DIR` and `config.LOGS_DIR` to `tmp_path`, and `html_generator` reads
  `config.PROJECTS_DIR` dynamically at call time (no frozen module-level copy — grep for
  `PROJECTS_DIR = config.` returned nothing). Tests generate real pages with the real
  templates, only `release_gate.publish_allowed` patched. No production-data writes.
- Exact assertions, not floors (P29): source-item lists asserted with `==` exact lists
  (`test_rfp1`, `test_rfp2`), section count asserted `== n_md`, `find_missing_bowen_items`
  asserted `== []`. The single `> 0` floor (`bowen_highlights`/`emphasis_highlights` in
  `test_rfo1`) is a smoke check on a generated page, and highlight-count correctness is
  pinned separately by `== 0` assertions in the legend test.
- Test validity (P27/P10): every new test contains a real `assert` on behaviour (real
  generator + real templates for RF.O/RF.P, adversarial broken-page tests asserting
  `validate_webpage(...) is False`). No vacuous tests, no return-a-bool, no assert-on-mock.
- No stochastic/LLM surface in this diff (P20/P23 not applicable): the code under review
  is deterministic HTML/markdown parsing.

## NOT COVERED

- Real-artifact run against the Kerr 2026-09-13 files (7/7 topics, 10/10 themes, 10/10
  key terms) is a *manual* claim in the spec, not an automated test. The tests use a
  reduced fixture (2 topics / 2 themes) through the real parser path, which pins the
  mechanism but not the full-real-scale count.
- `find_missing_emphasis_items` / `find_missing_bowen_items` still scan the whole
  document (pre-existing scope, unchanged by this diff); they are display-only (the
  issue/warning decisions use the transcript-scoped `html_meta["*_labels"]`), and legend
  marks carry no `title` so they are unaffected.
- Adjacent issues the spec itself flags as unfixed (themes file title / `---` rules /
  "Structural Themes (N total)" sub-headings render as page headings) — acknowledged,
  out of this diff's scope.
