# TODO — open bugs & tech debt

Tracked so we don't lose them. Items surfaced during the **2026-07-13 run-log
review** sessions unless marked *pre-existing* (not introduced by that work).
Fixed items live in CHANGELOG.md; recurring lessons in LEARNINGS.md.

---

## 2026-07-18 — Adversarial code-review findings

Full report: `docs/CODE_REVIEW_2026-07-18.md` (45-agent adversarial review, refute-first verified). Being worked through in `/csdp` batches of 5. `verify:` is the independent verification verdict (`→X` = re-rated severity).

### ✅ Fixed (10) — see CHANGELOG 2026-07-18

- **[C1]** Non-dict runtime_settings.json crashes config import app-wide (corrupt-state not handled) — `config.py:64`
- **[H3]** Non-atomic write + silent {} reset loses ALL persisted settings on a partial write — `config.py:89`
- **[H4]** pyproject.toml under-declares runtime deps: only jsonschema listed, so `pip install .` yields a broken install — `pyproject.toml:7`
- **[H5]** CI build matrix (3.8/3.9/3.10) contradicts requires-python>=3.11 AND the code's real >=3.10 floor; failures masked by `|| true` so it can never fail — `.github/workflows/ci.yml:56`
- **[H6]** README lists all three default model IDs, none of which match config.py — `README.md:211`
- **[H7]** README says abstract-coverage failure halts 'Run All' — code made it advisory (contradicts README line 23 too) — `README.md:126`
- **[H8]** Default 'V2 (Safe)' initial validator swallows transient API/parse failures and silently drops a chunk's findings (fail-open) — `transcript_initial_validation_v2.py:233`
- **[H10]** O(items × transcript) fuzzy grounding scan blows up to minutes on a long transcript with ungrounded quotes — `extraction_pipeline.py:828`
- **[H11]** Claim-extraction label-strip regex silently deletes a fabricated pre-colon specific before the armed faithfulness judge ever sees it (gate bypass) — `faithfulness_judge.py:136`
- **[H13]** Stored XSS: untrusted transcript + LLM fields flow unescaped into the HTML/PDF bundle — `transcript_utils.py:1642`

### ⏸ Deferred (8) — need a human/API decision, NOT done overnight

- **[H1]** Faithfulness/theme judges re-send the full transcript per artifact with NO shared cached prefix — the single biggest waste — `faithfulness_judge.py:228`
  - Why deferred: judge prompt-caching restructures the ARMED judge's input → needs P20 re-calibration (API key)
- **[H2]** Process-lifetime judge memo is defeated by the CLI orchestrator's subprocess-per-publish-step model — gate + armed judges run 4x/publish — `release_gate.py:354`
  - Why deferred: persist the judge memo across subprocesses — architectural; needs a design decision
- **[H9]** God-function: summarize_transcript is 462 lines, 11 params, one try/except -> bool — `extraction_pipeline.py:1354`
  - Why deferred: refactor the 462-line summarize_transcript — large structural change; wants human review
- **[H12]** Faithfulness and theme judge models are floating aliases, NOT date-pinned snapshots — comment claims 'PINNED' but the value has no date suffix (P20/P6) — `config.py:548`
  - Why deferred: pin judge models to a dated snapshot — needs the real snapshot ID; a wrong pin breaks the judge
- **[M1]** Cross-process last-writer-wins read-modify-write on runtime_settings.json — `config.py:85`
  - Why deferred: cross-process settings lock (flock) — portability + design; low impact (lost update, not corruption; H3 already prevents corruption)
- **[M7]** God-function: validate_configuration is 414 lines of linear validation — `config.py:890`
  - Why deferred: refactor the 414-line validate_configuration — large, same class as H9
- **[M11]** Whole transcript is re-normalized on every find_text_in_content call (re-normalize-per-item) — `transcript_utils.py:1729`
  - Why deferred: pre-normalize the transcript once per stage — matcher signature change touches all callers
- **[L15]** Standalone CLI extraction pipeline (transcript_process.py + transcript_summarize.py + transcript_extract_*) appears superseded by extraction_pipeline.py — `transcript_process.py:32`
  - Why deferred: confirm/remove the standalone CLI pipeline — needs a decision on whether it's still supported
- **PyYAML / google deps (sweep #2):** `GoogleDocSummary.py` / `ListModels.py` import `google*`, undeclared in deps — peripheral scripts, don't break CI; add `google-api-python-client`/`google-auth-oauthlib` only if they're still used.

### Remaining (25) — by severity

#### Medium

- **[M2] Abstract regeneration loop blames/regenerates the abstract for unfaithful claims in OTHER narrative artifacts (summary/overview/blog)** — `extraction_pipeline.py:1118` (CONFIRMED, verify:CONFIRMED, dim=correctness)
  - Scenario: generate_structured_abstract() runs AFTER generate_structured_summary() (see legacy_pipeline_integration.py steps 4 vs 6, and summarize_transcript writes summary/blog/overview earlier). Its regeneration loop calls _abstract_gate_precheck …
  - Fix: Scope the generation-time precheck to the abstract only. Add an artifact-suffix filter argument to check_faithfulness (or a dedicated single-artifact judge call) and pass [config.SUFFIX_ABSTRACT_GEN] from _abstract_gate_precheck, mirroring how entity_grounding is already abstract-scoped. The full multi-artifact …
- **[M3] Emphasis score is miscomputed and timestamp silently dropped when a rank header omits the '%' sign** — `transcript_utils.py:1499` (CONFIRMED, verify:CONFIRMED→low, dim=correctness)
  - Scenario: parse_scored_emphasis_output header pattern 1 captures the score with the class [^\]%\n]+, which INCLUDES the pipe character, and the '%' is optional (%?). For the real, %-terminated format ([Explicit - A2 - Rank: 92% | 00:04:09]) the '%' …
  - Fix: Exclude '|' from the score character class (e.g. (?P<score>[^\]%|\n]+)) in both header_patterns, or parse/strip the optional '| HH:MM:SS' timestamp before the score. Add a round-trip test with a %-less, timestamped header asserting the correct score and preserved timestamp.
- **[M4] ARCHITECTURE_DESIGN.md omits the entire release-gate / faithfulness-judge / theme-judge layer that now governs publishing** — `ARCHITECTURE_DESIGN.md:82` (CONFIRMED, verify:CONFIRMED, dim=docs-accuracy)
  - Scenario: The architecture doc (last touched Apr 10, 112 lines) describes the pipeline as formatting → summarization/extraction → validation → output and never mentions the fail-closed release gate or the two armed Sonnet judges. But release_gate.py …
  - Fix: Add a section to ARCHITECTURE_DESIGN.md documenting release_gate.py and the faithfulness/theme judges (armed status, pinned FAITHFULNESS_JUDGE_MODEL/THEME_JUDGE_MODEL, fail-closed Hard-BLOCK posture, recall/precision bars in config.py:584-585 / 605-606).
- **[M5] config.py inline 'Defaults' comment states FORMATTING_MODEL = claude-sonnet-4-6, but the actual default is Haiku** — `config.py:645` (CONFIRMED, verify:CONFIRMED→low, dim=docs-accuracy)
  - Scenario: config.py:643-645 documents the model defaults inline: '# Defaults: DEFAULT_MODEL = claude-sonnet-4-6 / AUX_MODEL = claude-haiku-4-5-20251001 / FORMATTING_MODEL = claude-sonnet-4-6'. The FORMATTING line is wrong — config.py:46 sets …
  - Fix: Change config.py:645 to 'FORMATTING_MODEL = claude-haiku-4-5-20251001' to match config.py:46.
- **[M6] Retry/backoff policy hard-coded at use sites, not in config.py** — `transcript_utils.py:560` (CONFIRMED, verify:CONFIRMED→low, dim=maintainability-config)
  - Scenario: config.py centralizes timeouts, token caps, temperatures and thresholds, but the retry policy of call_claude_with_retry is entirely inline magic constants: max_retries=3 (L560), exponential backoff `2 ** attempt` (L776, L794, L823), …
  - Fix: Promote MAX_RETRIES, RETRY_BACKOFF_BASE, TIMEOUT_ESCALATION_FACTOR, RETRY_FALLBACK_TIMEOUT (referencing TIMEOUT_SUMMARY), and DEFAULT_MIN_RESPONSE_CHARS into config.py and reference them at these sites.
- **[M8] A non-blocking ERROR ("couldn't verify") ships as ALLOW_WITH_WARNINGS with no distinct signal in the one-line log, exit code, or a marker file** — `release_gate.py:554` (CONFIRMED, verify:CONFIRMED→low, dim=observability)
  - Scenario: An advisory check not in GATE_BLOCKING_CHECKS (required_artifacts / verbatim_quotes / timestamp_citations / entity_consistency — see DEFAULT_CHECKS at release_gate.py:536-545) raises. `_safe` (line 95-104) converts it to a Status.ERROR …
  - Fix: In run_gate's summary log line (release_gate.py:554) also emit counts of ERROR and WARN verdicts (e.g. '... N verdict(s), E error(s), W warn(s), B blocker(s)') and log each advisory ERROR verdict at WARNING level alongside the blocker loop at line 556-557. Consider a distinct Decision value (e.g. …
- **[M9] Run manifest omits a code-version / gate-policy stamp, so a decision can't be traced to the code or policy that produced it** — `release_gate.py:600` (CONFIRMED, verify:CONFIRMED, dim=observability)
  - Scenario: build_manifest's `provenance` block (release_gate.py:600-607) records only model IDs and the source transcript sha256. It does NOT record the git revision of the code that ran, nor which checks were treated as blocking …
  - Fix: Add to build_manifest provenance: the git short revision (reuse the subprocess pattern from ts_gui.py:_current_git_revision) and a snapshot of the effective gate policy (sorted GATE_BLOCKING_CHECKS and GATE_ERROR_BLOCKS). This makes the single manifest artifact self-describing for reproducibility.
- **[M10] token_usage.csv column headers mislabel the data they carry ('Items' holds the model, 'Status' holds the stop_reason)** — `transcript_utils.py:399` (CONFIRMED, verify:CONFIRMED→low, dim=observability)
  - Scenario: log_token_usage writes the header row ['Timestamp','Script Name','Items','Status','Cache','Tokens Sent','Tokens Response','Cache Creation Tokens','Cache Read Tokens','Estimated Cost ($)'] (line 399-401) but the data row writes [timestamp, …
  - Fix: Rename the header cells to match the data: 'Items'->'Model', 'Status'->'Stop Reason' in transcript_utils.py:399, and update analyze_token_usage.py:83 to read row["Model"]. Add a round-trip test asserting DictReader keys map to the intended values.
#### Low

- **[L1] check_entity_consistency name regex uses \s+ and joins proper names across newlines, corrupting the near-duplicate clash detector** — `release_gate.py:290` (CONFIRMED, verify:PLAUSIBLE, dim=correctness)
  - Scenario: check_entity_consistency extracts names with re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", ...). Because \s+ matches newlines, two capitalized tokens on adjacent lines are fused into one bogus multi-word 'name'. Verified: input …
  - Fix: Use [ \t]+ instead of \s+ between name words in the regex at release_gate.py:290, matching the deliberate choice in abstract_validation.find_ungrounded_names (abstract_validation.py:73).
- **[L2] Split/inconsistent dev-dependency and specifier management across the three files** — `requirements.txt:10` (CONFIRMED, verify:PLAUSIBLE, dim=deps-build)
  - Scenario: pytest==8.3.3 (a test-only tool) is pinned in requirements.txt (the runtime deps file), while the other dev tool ruff lives in pyproject [dependency-groups].dev — two different homes for dev deps. pyproject uses a floating lower bound …
  - Fix: Consolidate dev deps (pytest + ruff) into pyproject [dependency-groups].dev, keep requirements.txt to runtime-only (or generate it), and add a ruff lint step to quality-gates so the declared dev tooling is actually run.
- **[L3] README claims html_generator.py is 650 lines; the file is 822** — `README.md:363` (CONFIRMED, verify:PLAUSIBLE, dim=docs-accuracy)
  - Scenario: README:363 labels the architecture box 'html_generator.py (650 lines)' and README:381 boasts '59% code reduction ... (1,584 → 650 lines)'. The file is now 822 lines (wc -l). The '650' figure and the derived 59%-reduction claim are stale — …
  - Fix: Update README.md:363 and :381 to the current line count (822) or drop the specific line-count claim, which will keep drifting.
- **[L4] Stale doc comment: FORMATTING_MODEL comment says Sonnet, code sets Haiku** — `config.py:645` (CONFIRMED, verify:PLAUSIBLE, dim=maintainability-config)
  - Scenario: The defaults comment block at L642-645 states `FORMATTING_MODEL = "claude-sonnet-4-6"`, but the actual assignment at L46 is `self.FORMATTING_MODEL = "claude-haiku-4-5-20251001"` (comment there correctly says Haiku suffices). A developer or …
  - Fix: Update the L645 comment to claude-haiku-4-5, or delete the redundant defaults comment block entirely since the assignments at L44-47 are the source of truth.
- **[L5] VALIDATION_MODEL lacks a setter and is not refreshed like its siblings** — `config.py:47` (CONFIRMED, verify:PLAUSIBLE, dim=maintainability-config)
  - Scenario: DEFAULT_MODEL, AUX_MODEL and FORMATTING_MODEL each have a set_* method (L234-253) and are re-exported/refreshed as module globals in set_transcripts_base (L302-311), but VALIDATION_MODEL (set at L47, validated at L1007/L1012) has neither: …
  - Fix: Add ProjectSettings.set_validation_model() mirroring the other three, and include VALIDATION_MODEL in the module-level refresh, or document explicitly that it is intentionally fixed.
- **[L6] Prompt-caching beta header string duplicated as a magic literal** — `transcript_utils.py:624` (CONFIRMED, verify:PLAUSIBLE, dim=maintainability-config)
  - Scenario: The literal `{"anthropic-beta": "prompt-caching-2024-07-31"}` is hard-coded at both the streaming (L624) and non-streaming (L634) call sites. When Anthropic graduates or renames the beta flag, an editor must find and change both copies; …
  - Fix: Define a single ANTHROPIC_BETA_HEADERS constant in config.py and reference it at both call sites.
- **[L7] Editorial stopword list embedded in Python source** — `extraction_pipeline.py:1276` (CONFIRMED, verify:PLAUSIBLE, dim=maintainability-config)
  - Scenario: _LENS_STOPWORDS (L1276-1281) is a hand-curated 40+ word vocabulary list — including content-specific additions 'keeps'/'keep' — used by lens-title grounding (_top_lens_is_grounded, L1284). Per project rule 9 (editorial content belongs in …
  - Fix: Move the stopword set to config.py (or a YAML vocab file) alongside the other editorial lists already centralized there (THEME_SCAFFOLDING_LABELS, FAITHFULNESS_SKIP_LINE_LABELS).
- **[L8] Cost rows fall back to 'unknown_script' when no logger is passed, losing per-stage cost attribution** — `transcript_utils.py:711` (CONFIRMED, verify:PLAUSIBLE, dim=observability)
  - Scenario: call_claude_with_retry derives the CSV 'Script Name' from `getattr(logger, 'name', 'unknown_script') if logger else 'unknown_script'` (transcript_utils.py:711-712). call_claude_with_retry defaults logger=None (line 561), and the coverage …
  - Fix: Either require a named logger on the cost-logging path, or have call_claude_with_retry accept an explicit `script_name` argument, or give verify_with_llm/validate_abstract_coverage a getLogger(__name__)-style fallback like the judges do, so no cost row is ever attributed to 'unknown_script'.
- **[L9] Git revision is cached as 'unknown' for the whole session after a single git failure** — `ts_gui.py:186` (CONFIRMED, verify:PLAUSIBLE, dim=observability)
  - Scenario: _current_git_revision caches into module-level _GIT_REVISION_CACHE on first call (ts_gui.py:177-188). If the first `git rev-parse` fails for any transient/environmental reason (git not on PATH at launch, cwd not yet a repo, permission …
  - Fix: Do not cache the failure sentinel: only memoize a successful revision, and re-attempt on 'unknown' (or drop the cache entirely — the subprocess is cheap and called rarely).
- **[L10] Abstract prompt hard-codes '249'/'under 250 words' as literal text, duplicating config.ABSTRACT_HARD_MAX_WORDS (P4 drift)** — `prompts/Abstract Generation Prompt v1.md:5` (CONFIRMED, verify:PLAUSIBLE, dim=prompts)
  - Scenario: The abstract prompt embeds the length ceiling as prose: 'never more than 249 words' (line 5) and 'the abstract must be under 250 words' (line 19). The same ceiling lives in config.py:727 (ABSTRACT_HARD_MAX_WORDS = 250) which validation …
  - Fix: Inject the hard ceiling into the prompt from config (e.g. a {hard_max_words} placeholder fed from ABSTRACT_HARD_MAX_WORDS) instead of the literal 249/250, so the prompt and the validation gate share one source of truth.
- **[L11] `_fill_prompt_template` copy-pasted identically in extraction_pipeline and validation_pipeline** — `validation_pipeline.py:75` (CONFIRMED, verify:PLAUSIBLE, dim=redundant-dead)
  - Scenario: The template-fill helper (regex placeholder substitution + `{{insert_transcript_text_here}}` replacement) is defined character-for-character identically in extraction_pipeline.py:67 and validation_pipeline.py:75. If the placeholder syntax …
  - Fix: Hoist `_fill_prompt_template` into transcript_utils (or one module) and import it in the other.
- **[L12] Two orphaned top-level unittest files are dead code (superseded by tests/)** — `legacy_initial_validation_logic.py:13` (CONFIRMED, verify:PLAUSIBLE, dim=redundant-dead)
  - Scenario: legacy_initial_validation_logic.py and legacy_pipeline_integration.py are full unittest.TestCase files sitting at repo root. They are imported by nothing (grep for both module names returns zero importers) and are NOT collected by default …
  - Fix: Delete both files (their coverage lives under tests/). If any case is unique, port it into the tests/ equivalent.
- **[L13] Validator-dispatch (v1/v2 select + get_latest_version + validate + apply) copy-pasted across three ts_gui methods** — `ts_gui.py:2533` (CONFIRMED, verify:PLAUSIBLE, dim=redundant-dead)
  - Scenario: The mode='v2' vs 'v1' branch that instantiates TranscriptValidatorV2/TranscriptValidator, calls get_latest_version, then validate/validate_chunked and apply_corrections(_safe) is duplicated in three methods: _run_initial_validation …
  - Fix: Extract one helper `_make_validator(mode)` / `_run_validation(mode, file, model)` and call it from all three sites so the model argument and dispatch stay consistent.
- **[L14] Five near-identical `load_prompt()` functions differing only by a config filename constant** — `summary_pipeline.py:736` (CONFIRMED, verify:PLAUSIBLE, dim=redundant-dead)
  - Scenario: `load_prompt()` is independently defined with an identical body (build PROMPTS_DIR/<CONST>, raise FileNotFoundError if missing, read_text) in summary_pipeline.py:736, abstract_pipeline.py:446, formatting_pipeline.py:86, …
  - Fix: Add `load_prompt(filename: str) -> str` to transcript_utils and pass the per-module constant.
- **[L16] base_name used to build filesystem paths without sanitize_filename (defense-in-depth gap)** — `html_generator.py:679` (SPECULATIVE, verify:PLAUSIBLE, dim=security)
  - Scenario: generate_webpage/generate_simple_webpage/generate_pdf (html_generator.py:678-680,733-735,786-788) and package_transcript (packaging_pipeline.py:25,61) build output paths as `config.PROJECTS_DIR / base_name / f"{base_name}{SUFFIX}"` using …
  - Fix: Run base_name through sanitize_filename() (or assert it equals its sanitized form) at the top of each generate_*/package_* entry point before constructing PROJECTS_DIR paths, so path safety does not depend on every caller remembering to pass a bare stem.
- **[L17] mut_harness scores a suite TIMEOUT as 'killed', inflating the very mutation score the M6.A validity gate trusts** — `mut_harness.py:160` (SPECULATIVE, verify:PLAUSIBLE, dim=tests)
  - Scenario: run_suite runs pytest with `-x` (stop at first failure) and `timeout=120`; on TimeoutExpired it returns False, and False is defined as 'killed'. Killing mutants stop early via `-x` (fast), but a SURVIVING mutant runs the full green …
  - Fix: Treat TimeoutExpired as an inconclusive/error outcome (re-run or report separately), not as a kill. At minimum distinguish returncode!=0 (a real test failure = killed) from a timeout (unknown), and surface timeouts in the campaign result so a slow survivor can't be laundered into the score.
- **[L18] check_theme_grounding 'no theme artifacts -> PASS' is an untested pass-on-empty branch, asymmetric with faithfulness's 'no artifact -> ERROR'** — `release_gate.py:500` (CONFIRMED, verify:PLAUSIBLE, dim=tests)
  - Scenario: With THEME_JUDGE_ENABLED=True and theme_grounding a hard blocker, a run that has a source and key but neither theme artifact on disk returns Verdict PASS ('no theme artifacts present') and clears the armed gate silently. Its sibling …
  - Fix: Add a test that runs check_theme_grounding on an enabled project with source+key but zero theme artifacts and asserts the intended verdict, and add a comment documenting why themes-absent is PASS while narrative-absent is ERROR (themes optional vs required). If themes-absent should be ERROR/WARN, align it with …

### Systemic risks (classes, not single instances)

1. **Fail-open: a transient/error outcome is recorded as an empty-but-benign result (P1/P2)** — The same 'return [] / PASS-on-empty' shape recurs across the fail-closed core: the V2 validator drops a chunk's findings on API failure, its JSON parser returns [] on truncation, check_theme_grounding treats 'no artifacts' as PASS while faithfulness treats it as ERROR, and a non-blocking ERROR ships as ALLOW_WITH_WARNINGS with no distinct log/exit-code/marker signal. In every case 'couldn't …
2. **Duplicated source-of-truth that drifts silently (P4/P19)** — Load-bearing values are copy-pasted instead of referenced, and the copies have already diverged: model IDs are wrong in README (all three) and in the config.py:645 'Defaults' comment; the abstract prompt hardcodes 249/250 vs config.ABSTRACT_HARD_MAX_WORDS; retry/backoff constants and a 900.0 timeout duplicate TIMEOUT_SUMMARY inline; token_usage.csv headers mislabel their columns; runtime deps …
3. **The LLM-judge fail-closed core has real-path and scoping holes (P20/P7)** — The armed judges are trusted as hard blockers but the plumbing around them is under-exercised on the production path: destructive claim extraction removes fabrications before judging (false PASS), the abstract regeneration precheck runs the full multi-artifact faithfulness sweep instead of abstract-only scope (false BLOCK + wasted attempts + misblame), the judge models are floating aliases rather …

### Refuted during verification (no action)

- The release-gate judges (and all extraction/generation prompts) embed untrusted transcript text with spoofable text delimiters and no prompt-injection guard (`faithfulness_judge.py:224`, filed medium) — The structural observation (no injection guard, spoofable text delimiters, no "SOURCE is data" clause) is factually accurate, but the concrete failure scenario does not occur. (1) …
- Generation-time faithfulness precheck re-judges ALL narrative artifacts, then the publish gate (separate process) judges them again (`extraction_pipeline.py:1118`, filed medium) — The finding's central mechanism does not hold up against the code. (1) There is NO "separate publish subprocess with an empty memo." Publishing runs through …
- Mutation gate excludes the two fail-closed safety modules it exists to protect (release_gate.py, faithfulness_judge.py) (`quality_gates.py:78`, filed medium) — No wrong behavior occurs. MUTATION_GATE (quality_gates.py:78) is by design a small, explicitly-curated list; the accompanying comment states verbatim "Kept small and fast: the …
- The gold-set calibration that is the sole basis for arming both judges as Hard BLOCKs is live-API-only; no offline test guards calibration-invalidating drift (P20) (`tests/test_faithfulness_calibration.py:29`, filed medium) — The finding's structural facts are correct (both judges ENABLED and in GATE_BLOCKING_CHECKS per config.py 542/597/487; the three precision/recall calibration tests are …
- Duplicated `_load_formatted_transcript` in two live pipeline modules (drift risk) (`validation_pipeline.py:51`, filed medium) — The finding's concrete failure scenario depends on the claim "validation calls its own" copy of _load_formatted_transcript, which is false. The copy at validation_pipeline.py:51 …
- No CI job exercises the declared runtime Python 3.12; gating job runs only 3.11 (`.github/workflows/ci.yml:18`, filed medium) — The CI facts are accurate (quality-gates line 23 and mutation-gate line 42 both pin python-version "3.11"; build matrix tops at 3.11 and swallows failures via `pytest -q || true`; …

---
## 2026-07-17 — entity_grounding OR-logic gap (widened by metadata grounding)

`find_ungrounded_names` grounds a multi-word name if **any** significant token
matches the source (OR-logic — a documented lexical-check limitation). Grounding
the presenter's name via filename metadata (so 'Michael Kerr' isn't false-BLOCKed)
means the presenter's **first name** ('michael') is now a grounded token, so a
fabricated surname riding on it ('Michael Bowen') passes the lexical check. The
faithfulness judge (M2) is the semantic backstop for this class. Pinned by
`tests/test_release_gate.py::test_entity_grounding_shared_token_name_is_a_known_lexical_gap`.
- **Follow-up (optional):** consider requiring the *surname* (last token) to be
  grounded, or ALL tokens, if false-negatives on presenter-token names prove real.

## 2026-07-17 — faithfulness judge: re-calibrate after metadata-in-source change

`release_gate.check_faithfulness` now prepends the recording metadata (title,
presenter, date, year from the filename) to the source, so a legitimate
metadata-derived abstract fact ("In this **2021** webinar…") is no longer judged
as a fabricated year (it was a false publish BLOCK). Per P20, the faithfulness
judge is ARMED and calibrated — **re-run the calibration eval** to confirm the
metadata-augmented source doesn't shift precision/recall on the gold set:
```
RUN_FAITHFULNESS_CALIBRATION=1 PYTHONPATH=$PWD .venv/bin/python \
  -m pytest tests/test_faithfulness_calibration.py -q -s
```
Low risk (only known catalogue facts become entailable; a fabricated name/stat
still won't match), but the gold set should be re-verified before relying on it.

---

## 2026-07-17 — Init Val fuzzy matcher (follow-up)

The span-match guard (`transcript_utils.span_matches_original`) now makes Init Val
auto-apply *safe* against mis-located spans, but it does so by **skipping** them —
so the fuzzy-auto-apply path is largely neutralized whenever normalization changes
offsets (double spaces, timestamps, punctuation inside the phrase). Root cause:
`transcript_utils.find_text_in_content` computes its returned `(start, end)` from
normalized-word indices / first-prefix occurrence, so its offsets don't map back
to the raw text when normalization changed lengths.

- **Follow-up:** fix `find_text_in_content` to return correct *raw-text* offsets
  (e.g. re-locate the matched window in the original string), so legitimate fuzzy
  corrections apply again while the span guard still blocks mis-locations.
  Verified empirically 2026-07-17: `find_text_in_content("beta gamma", "beta   gamma")`
  returns a misaligned slice, which the guard correctly skips.
- **Adjacent (not fixed):** the multi-match branch still applies a ≥7-word
  correction to *all* occurrences of its `original_text` — intended, but noted.

---

## 2026-07-16 — bundle export / GUI follow-ups (deferred, not blockers)

Flagged during the bundle-export + selective-re-run work (see CHANGELOG
2026-07-16). None block the shipped features.

1. **`package_transcript` doesn't include the bundle or the individual MD files.**
   The `.zip` packages the rendered webpage/PDF + transcript, not the new
   `- bundle.pdf` / `- bundle.docx` or the per-stage `.md` files. Decide whether
   the zip should include the bundle. (Adjacent issue, rule #10 — flagged, not
   changed.)
2. **Google Doc export deferred.** The plan was PDF + DOCX now, Google Doc later
   (upload the generated `.docx` to Drive, which auto-converts). Not built — needs
   Drive OAuth. See `docs/bundle_export_plan.md`.
3. **Live pandoc DOCX path is integration-only (untested in CI).** Unit tests mock
   `subprocess.run`; the real pandoc invocation was smoke-tested locally
   (pandoc 3.10) but has no automated coverage. The committed
   `templates/styles/bundle-reference.docx` can drift from
   `scripts/gen_bundle_reference_docx.py` after a pandoc upgrade — re-run the
   generator to refresh (BE.11).
4. **`webpdf` still fail-closes before `package`.** Bowen/Emphasis were moved
   ahead of the publish-gated stages, but a release-gate BLOCK on `webpdf` will
   still halt `package`/`bundle` if they're selected after it. Acceptable
   (those are publish artifacts), noted for awareness.

---

## M2 faithfulness judge — ARMED (2026-07-15), follow-ups

**ARMED** (`FAITHFULNESS_JUDGE_ENABLED = True`, Hard BLOCK, prose only). Calibrated
on REAL full artifacts after an isolated-gold calibration was caught as a P10 gap
(LEARNINGS.md). Re-run the calibration any time with:
```
RUN_FAITHFULNESS_CALIBRATION=1 \
  PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_faithfulness_calibration.py -q -s
```
(Key auto-resolves from the shared `~/.config/llm/keys.json` via
`transcript_utils.resolve_anthropic_key()`.)

Follow-ups (not blockers) — incl. learning-qa arming-review findings:
1. ~~**Themes coverage.**~~ ✅ DONE 2026-07-15 — a separate **theme GROUNDING judge**.
   The entailment judge is the wrong check for themes (they interpret by design);
   `faithfulness_judge.judge_themes_artifact` + `release_gate.check_theme_grounding`
   ask "is this theme grounded in real source content?" instead. ARMED (Hard BLOCK),
   calibrated on real theme artifacts (20 grounded / 8 fabricated, recall/precision
   1.0). Themes stay OUT of `FAITHFULNESS_ARTIFACT_SUFFIXES` (entailment) but ARE in
   `THEME_ARTIFACT_SUFFIXES` (grounding).
2. **Living gold set.** Add every escaped hallucination found in production to
   `tests/fixtures/faithfulness_gold/gold.json`; re-run the calibration on any prompt
   or threshold change (spec §M2 flags the judge's semantic quality as curated-eval,
   not a unit test). The set now includes adversarial invented-stance cases (us6/us7)
   — the "no proper noun" recall class that the prompt tightening now catches.
3. **Judge model is PINNED** (`FAITHFULNESS_JUDGE_MODEL = "claude-sonnet-4-6"`, not
   aliased to DEFAULT_MODEL) so a generation-model bump can't silently move the armed
   judge onto an un-recalibrated model (P6). Changing it requires a re-calibration.
4. **Key precondition (verify in the publish env).** Armed → every publish ERROR→BLOCKs
   if no Anthropic key resolves. The key is NOT in `.env`; it resolves from the shared
   `~/.config/llm/keys.json`. Confirm that file is present wherever the gate actually
   runs, or publishes block uniformly (correct fail-closed, but a hard runtime coupling).
5. **judged==0 → ERROR** is a correct pass-on-empty guard: a run with none of the
   prose artifacts blocks. Verified the abstract is always emitted (it's in
   `GATE_REQUIRED_ARTIFACT_SUFFIXES` + scanned by entity_grounding), so a real
   publishable run always has ≥1 prose artifact — no false-BLOCK class here.
6. **Test-guard hardening (F5) — DONE 2026-07-15.** The root-conftest offline fixture
   now also defaults `resolve_anthropic_key -> None` (unless `RUN_FAITHFULNESS_CALIBRATION`),
   so an enabled-path test that forgets to supply a key cannot reach a live API call —
   `check_faithfulness` ERRORs on the missing key instead. Enabled-path tests opt in
   explicitly by patching `resolve_anthropic_key` (loud opt-in). Residual: a test that
   provides a key but forgets to mock the judge could still call live — mock-discipline,
   documented here.
7. **Cost/latency.** When armed, each publish judges the prose artifacts via Sonnet
   (deduped per-content by the gate memo). If per-publish cost matters, consider a
   single orchestrator-level gate call instead of the per-entry-point `publish_allowed`.
8. **`summary_pipeline` proportionality WARN** and other pre-existing items below.
- **Consider native structured output (L4).** The judge parses a JSON array via
  robust regex + fail-closed guard. A tool-use / structured-output call would be
  more robust than free-text JSON; not required (unparseable → ERROR, never silent),
  but a future hardening.
- **Long-source token budget (P9).** The judge sends the full transcript + all
  claims in one call (no truncation, correct for grounding). A very long transcript
  could exceed context → API error → ERROR (fail closed). Fine for now; revisit if
  real runs hit it (batch by section, or a retrieval step).

---

## M3 schema contracts — staging follow-ups (2026-07-15)

Codec layer (`artifact_contracts.py`) + bowen boundary landed (M3a, M3b-bowen).
Remaining boundaries stage one at a time behind the migration shim.

- **⚠️ Themes migration shim must handle TWO real formats.** A P6 sweep of the
  codec over every real artifact on the drive found `parse_bold_numbered_theme_blocks`
  (consumer) returns **zero** on a real structural-themes file that uses
  `### N. Title` (H3-numbered) instead of the `**N. Title**` (bold-numbered) format
  the parser expects (`Monika Baege and Michael Kerr interview - 2010-09-23`,
  processed with the 2025-02 prompt). This is genuine pre-existing producer/consumer
  drift (P19). **Before wiring themes to the gate** (`_CONTRACT_ARTIFACTS`), the
  themes codec / `parse_bold_numbered_theme_blocks` must parse BOTH formats, or the
  first unattended re-publish of that (and any same-era) run will false-BLOCK
  (AC M3.D.1 requires legacy real artifacts to migrate). bowen/key-terms/topics/
  emphasis/interpretive-themes are all clean across the 6 real projects checked.
- **Emphasis all-items-content-rejected raw fallback (adjacent, not fixed).**
  `extract_scored_emphasis` (`extraction_pipeline.py:727`) does
  `final_content = "\n\n".join(lines) if validated_items else response` — when
  items parse but ALL fail `validate_emphasis_item` (content grounding), it saves
  the RAW model response, so content-rejected items get written (and now pass the
  M3 *format* self-check → a sidecar of rejected items). This is a pre-existing
  *content*-validation gap orthogonal to M3's format contract (the codec judges
  shape, not grounding); flagged per rule 10, not fixed here. Fix: on zero
  validated items, write a header-only/empty artifact (or fail) rather than the
  raw response.
- **Abstract-input strategy-1 topic name edge (very low prob).** `parse_topics_from_extraction`
  (`abstract_pipeline.py:108`) `name = match[0].strip()` on a `###\s+([^\n]+)`
  capture could strip to `""` on a whitespace-only header → `minLength:1` schema
  violation → fail-closed block. Real-data risk is negligible (names are non-empty
  in practice) but it's the one input-shaped path to a false block; a `name` filter
  in the parser would close it.
- **JSON sidecar is write-only so far.** `write_json_sidecar` emits `<base> -
  <artifact>.json` but no consumer reads it yet (gate + renderers still re-parse
  the `.md`). Durable provenance today; make a consumer prefer the validated
  `.json` (with an md↔json reconcile) in a later step to fully realize the
  structured-intermediate benefit.
- **Remaining boundaries to wire:** emphasis, key-terms, themes (see above),
  topics, abstract-input (JSON validate hook at `AbstractInput` assembly — no
  markdown wire format, so no round-trip; pinned by the producer/gate path).

---

## Test-validity audit (2026-07-15) — Step 1 done, follow-ups open

Mutation testing + fixture-provenance + vacuity scan of the whole suite. Full
report: `TEST_VALIDITY_REPORT.md`. Harness: `mut_harness.py`.

### ✅ FIXED 2026-07-15 (Step 1)
- Two broken tests in `test_validation_warnings.py`: `test_summary_proportionality_warning`
  (crashed — `unittest.mock` unimported; stale mock) and `test_summary_evaluative_warning`
  (mis-indented into the prior method, never collected). Both now run and pass.
- Added `tests/test_validator_logic_hardening.py` (15 tests) pinning validator decision
  logic. Mutation score: `summary_validation` 9%→28%, `abstract_validation` 36%→50%,
  `validation_pipeline` 24%→27%.

### Open follow-ups (test debt)
- ~~**`validate_key_terms_fidelity` tier thresholds still unpinned.**~~ ✅ FIXED
  2026-07-15 (Step 2). The `0.50 / 0.90 / 0.80 / 0.35` cutoffs are promoted to
  `config.KEY_TERMS_*` and pinned by a real-artifact disk-fixture test
  (`test_f1_keyterms_real_run_tiers_pinned`: EXACT==8 / FAIL==2 on the real run).
  A new LOCAL def-grounding floor (`KEY_TERMS_DEF_LOCAL_MIN`) closes the
  swapped-definition false-pass and is pinned by `test_f1_keyterms_swapped_definition_not_exact`.
- **Remaining low mutation scores — ✅ largely addressed 2026-07-15.**
  `summary_validation.check_keyword_coverage` + `check_proportionality` mutation score
  raised 44%→71% (on those two functions) by pinning the previously-untested logic:
  the medium tier (`match_count>=1`), the count-vs-ratio high boundary, the
  section-vs-total proportionality terms, the dynamic-tolerance tiers (Closing<50=2.5 /
  <100=0.5 / 100–200=0.4), and the per-section divide-by-zero guard
  (`tests/test_validator_logic_hardening.py`). Residual survivors are editorial
  tolerance-tier *constants* at exact integer boundaries (50/100/200) and redundant
  ratio alternatives masked by the count path — low correctness value. `validation_pipeline`
  key-term/topic validators were hardened in Step 2 (`test_validator_gate_hardening.py`,
  real-artifact tiers); a deeper mutation pass there is a slow follow-up (mut_harness runs
  the full suite per mutant).
- ~~**False-green synthetic format tests.**~~ ✅ FIXED 2026-07-15.
  `test_summary_pipeline_parsing.py` theme tests repointed to REAL fixtures
  (kcfc structural=3 / interpretive=7, scaffolding-only→0); the `### header`-as-theme
  test (certified the A1 bug) removed. `test_bowen_references_integration.py` (2
  formerly-xfail) repointed to the real consumer `parse_bowen_references_text` (the
  saved `### Concept\n> "quote"` format) — un-xfailed, now passing.
- ~~**Vacuous assertion-free tests.**~~ ✅ FIXED 2026-07-15. `test_exception_fix.py`
  (×4) now assert the swallow-not-raise contract of `log_token_usage` (row written /
  warning printed / stack trace logged); `test_validation_headless.py` (×2, live_api)
  now assert the findings list + schema keys and `pytest.skip` on missing preconditions.
  `KNOWN_VACUOUS` is now EMPTY (M6.B gate blocks any new vacuous test).
- **Institutionalize:** add a mutation-score gate on the seven core modules to CI so
  this cannot silently rot again (coverage % does not detect it).

---

## P19 contract-audit findings (2026-07-14, step 3)

Multi-agent producer→consumer (prompt → generation → save → parser/validator)
contract audit against the **real KCFC artifacts**. 12 confirmed, each verified
against real on-disk bytes + an adversarial refutation pass (8 candidate findings
were refuted). Ordered by corrected severity. IDs `A1`–`A12`.

### 🔴 HIGH — ✅ FIXED 2026-07-14 (A1–A3 + sibling)
Shared bold-numbered-first parser (`transcript_utils.parse_bold_numbered_theme_blocks`
+ `is_scaffolding_theme_name`), both consumers reordered, loud zero-from-non-empty
warning, round-trip tests on the real artifacts (`tests/test_theme_parsing_contract.py`).
Verified on real KCFC files: structural 1→3, interpretive 2→7. `learning-qa` review
also fixed a P19 sibling — `extraction_pipeline._is_valid_section_content` validated
all-scaffolding structural files as usable content (now routes through the parser) —
and hardened `is_scaffolding_theme_name` against false-positives (labels →
`config.THEME_SCAFFOLDING_LABELS`, rule #9). 284 tests pass, 7 pre-existing failures
unrelated. See CHANGELOG.md.

### ✅ FIXED 2026-07-14 — validator pass-on-empty cluster (A5, A9, A10, A11)
"Validators reporting success without verifying." A5: `count_header_verdicts`
(drift-tolerant) wired into both header producers — loud warning on FAIL>0 /
zero-from-non-empty + report `## Verdict Summary` (real KCFC: 1 FAIL/5 WARN/44 PASS,
was silent pass); advisory by design. A9: empty required-items → fail-closed in
`summary_validation` + `abstract_validation` (P5 siblings). A10: distinct
`config.PURPOSE_EXTRACTION_FAILED` sentinel — transient failure keeps the purpose
check required + hard-uncovered (P1), not silently demoted. A11: empty-keyword item →
`(False,'low')` (LLM-rescue-eligible, not auto-'high', not hard-failed). `learning-qa`
2nd pass caught + fixed an LLM-rescue-bypass regression (F1/F2). 295 tests pass. See
CHANGELOG.md + `tests/test_validator_pass_on_empty_contract.py`.

- **A1 — Theme parser returns 1 bogus theme instead of 3 (abstract path).**
  `parse_themes_from_extraction` gates on `"###" in text`, so Strategy 1 captures
  the section header `### Structural Themes (3 total)` as the theme *name* and
  mashes the 3 real `**N. …**` themes into one description blob. The bold-numbered
  Strategy 2 that would parse them is dead-gated behind `if not themes:`. Live run
  on real `structural-themes.md` → **1 theme, the 3 real ones lost**, fed to the
  abstract with no error. Ref: `abstract_pipeline.py:149` (`_is_real_theme_name`
  `:134`, gate `:165`, bold regex `:167`).
- **A2 — Theme parser collapses 7 interpretive themes into 2 junk entries (summary path).**
  Same root cause, different consumer. Real 7-theme `interpretive-themes.md` parses
  to `['## Interpretive / Process Themes (7 total)' (12 002-char blob), 'Summary Paragraph']`;
  zero real themes reach `prepare_summary_input`. Ref: `summary_pipeline.py:300`
  (early `return themes` `:338`), consumed `:607`.
- **A3 — `summary_pipeline.parse_themes` has NO path that reads the real format.**
  Even with A2's `###` hijack fixed, both fallback regexes anchor on a bare
  `\d+.` line, but real headers start with `**`. The working bold-numbered handler
  exists only in `abstract_pipeline` (`:166`), never ported. Zero-from-non-empty is
  silent. Ref: `summary_pipeline.py:346-363`.

### 🟠 MEDIUM — ✅ FIXED 2026-07-14 (A4, A6, A7, A8) + 🟡 A12
A4: non-capturing alternation so the closing body is searched (patterns →
`config.ABSTRACT_CONCLUSION_PATTERNS`, rule #9; narrow-phrase recall gap tracked
below). A6: `parse_section_range` expands every comma segment (`re.search`/`findall`,
survives "Sections N" prefixes), deduped — real cause of the topics `section_mismatch`.
A7: `verify_highlights_bs4.load_source_quotes` reads all 3 real quote formats +
non-zero exit on drift (bowen 0→1, emphasis 0→22). A8: `_top_lens_is_grounded`
(content-token overlap) gates the loop and **fails closed after retries** (no ungrounded
lens ships). A12: `_strip_leading_scaffolding` excludes a leading `# Abstract` header
from word count + keyword matching. `learning-qa` 2nd pass caught + fixed 2 HIGH
regressions (A8 exhaustion fall-through, A6 anchored-match drop). 311 tests pass. See
CHANGELOG.md + `tests/test_audit_medians_contract.py`.

- **A4 — `extract_closing_conclusion` single-group `re.findall` drops the body.**
  `r"## Section (N|…)[^#]+"` has one capturing group, so `findall` returns section
  *numbers* (`"45 46 …50"`) and discards the closing text. Conclusion search always
  fails → returns `"No explicit conclusion stated"` → the abstract validator
  **silently skips the required conclusion-coverage check on 100 % of transcripts**.
  Ref: `abstract_pipeline.py:305-317`; gate `abstract_validation.py:253-256`.
- **A5 — Header-validation verdicts are never counted; a real FAIL passes.**
  `validate_headers` returns `True` on `len≥100` with zero parsing. Model format-drifts
  (`**STATUS:** FAIL` in some batches vs plain elsewhere); a declared-format counter
  sees 0 FAILs / 2 of 5 WARNs. Section 15 genuinely FAILs yet the step reports success.
  Ref: `validation_pipeline.py:594`; no STATUS counter in any consumer.
- **A6 — `parse_section_range` truncates multi-segment citations to the first range.**
  Anchored `re.match(r"(\d+)\s*-\s*(\d+)")` fires on the leading range and never
  reaches the `else` findall: `"7-8, 15, 33-35"` → `[7,8]`. Deflates section-grounding
  scores. **This is the real cause of the `section_mismatch: 7` mislabelled "cosmetic"
  below.** Ref: `summary_pipeline.py:274-288`; consumed `validation_pipeline.py:429-430`,
  `summary_pipeline.py:249`.
- **A7 — `verify_highlights_bs4.load_source_quotes` uses the abandoned bowen format.**
  Regex expects `> **Label:** "quote"`; real artifact is `### Concept\n> "quote"` →
  returns `[]` → "Loaded 0 bowen references" → highlight verifier reports a clean pass
  having **verified nothing** (a mis-highlighted/hallucinated bowen quote rides through).
  Ref: `verify_highlights_bs4.py:56`; reuse `transcript_utils.load_bowen_references`.
- **A8 — `top_lens` accepted on a truthy-dict gate, never reconciled to the ranked lenses.**
  `if structural_valid and interpretive_valid and top_lens: break` — nothing compares
  `top_lens.title` to the 12 lenses actually written, so a paraphrased/invented top lens
  is "✓ validated" and piped to the blog. Ref: `extraction_pipeline.py:1323,1344,1484-1490`.
- **A9 — `validate_summary_coverage` reports PASS on an empty checklist (`all([]) == True`).**
  When topics are missing/drifted the required-items list is empty → "Required coverage:
  0/0" → **any non-empty (even off-topic) summary validates**. Also `check_keyword_coverage`
  auto-returns `(True,'high')` when `total_keywords == 0`. Ref: `summary_validation.py:469,316-317`.
- **A10 — Abstract coverage denominator regenerated from a live LLM call at validation time.**
  `is_required = "manually insert" not in opening_purpose`, and `extract_opening_purpose`
  hits the API at read time. No key / a timeout demotes the purpose check required→optional
  — **a transient outage flips FAIL into reported PASS** (P1). Re-run now yields `3/3` vs the
  saved `4/4`. Ref: `abstract_validation.py:240`; `abstract_pipeline.py:259`; `validation_pipeline.py:650`.

### 🟡 LOW

- **A11 — Empty-keyword coverage item auto-marked covered `'high'`.** `if total_keywords
  == 0: return True, "high"` — latent on this artifact (all topic names >4 keywords), bites
  on all-stopword/short topic names. Ref: `summary_validation.py:316`.
- **A12 — Abstract word count includes the forbidden `# Abstract` header (+2 tokens).**
  Prompt says "no headers"; model emits one; `len(abstract.split())` counts it (331 vs 329),
  can tip a boundary-length abstract's min/max check. Ref: `abstract_validation.py:620`;
  save `extraction_pipeline.py:1102`.

### Refuted but real fragility (not strict P19 — keep on radar)
Emphasis raw-quote no-escaping (non-greedy regex tolerates it; = pre-existing item below);
`verify_with_llm` positional YES/NO zip (both abstract & summary — real fragility, no
format-drift trigger); `extract_section("Lenses (Ranked)")` regex miss (sibling path handles it).

---

## Real-run audit (2026-07-15) — Step 2: validator gate hardening ✅

Audited a full real run (`Where Roots Bowen Theory Reside in the Brain - Michael
Kerr - 2022-02-18`) against its source; re-ran the deterministic validators on the
real artifacts in both directions. See CHANGELOG.md (Step 2) + LEARNINGS.md.

**Fixed:** emphasis 15-word blindspot → head+tail match + real return bool (also
fixed a pre-existing false-negative); key-terms definition proxy → added local
grounding (`_best_local_grounding`) + downgrade-with-warning + thresholds promoted
to `config.*` and pinned; abstract fabricated-name detector (`find_ungrounded_names`,
advisory); Bowen within-file dedup; `html_generator` 2-vs-3 tuple crash (+ sibling
`format_ref_list`); `unknown_script` named loggers (5 sites). Tests:
`tests/test_validator_gate_hardening.py`, fixtures `tests/fixtures/where_roots/`.

**Adjacent issues (flagged by learning-qa review, not fixed — rule 10):**
- **Dead duplicate `_generate_simple_html_page`.** `html_generator.py` defines it
  twice (~line 266 dead-shadowed, ~line 642 live); the first is unreachable. Pre-existing.
- **`_best_local_grounding` re-normalizes the whole transcript per key term.**
  N terms × full-transcript `normalize_text` — fine at current scale (sub-second on
  ~11k words × 10 terms) but hoist `norm_tokens` out of the per-term path if it ever bites.

**Still open (generation-side, lower priority):**
- **Emphasis timestamps drift from the quote's real location.** Several items carry
  a timestamp for the wrong block (e.g. the mass-energy quote tagged `00:18:06`,
  actually ~`00:20:04`; a Rediger-book quote tagged `00:48:10`, actually ~`01:24`).
  Quotes are verbatim; the citation is wrong. This is in emphasis *generation*, not
  the validator. Consider deriving/validating the timestamp from the matched span.
- **Cross-artifact name inconsistency.** The same unnamed person is "Bertoloso"
  (topics, faithful to source ASR), "Bertolaso" (structural themes, corrected), and
  the now-flagged fabricated "Luciano Malorni" (abstract). F4's detector catches the
  fabrication; consistency across artifacts is not enforced.

## Phase 1 (unattended-robustness spec) — known limitations of the release gate

The fail-closed release gate (M1/M4/M7) is in. `learning-qa` reviewed the diff;
its findings were fixed except these two, kept as honest limitations:

- **F2 — the entity blocker only catches MULTI-WORD Latin names.** A single-word
  fabricated surname ("Malorni" alone), an ALL-CAPS acronym/org, initials
  ("J. Ewing"), or a non-Latin-script name slip through `find_ungrounded_names`
  (`abstract_validation.py`) and publish silently. It caught the actual shipped
  "Luciano Malorni" (multi-word). Broadening to single-word/acronym would flag
  every capitalized word — the real fix is the semantic judge (M2, deferred). U2
  is therefore only met for the multi-word subset (already stated in the spec).
- **F5 — manifest/publish-decision precision (largely addressed).** `publish_allowed`
  now writes the run manifest tied to THE decision that gated (fixed: a normal
  publish always leaves a manifest, no separate second gate run). Residual: each
  publish entry point (webpage/pdf/package) still runs the gate independently
  (deterministic, so the decision is identical) and the manifest is a gate-time
  snapshot — bundle files written *after* the guard aren't all captured. A single
  orchestrator-level `gate_and_report` call (once, after all artifacts exist,
  before publish) would make it exact + run the gate once; do it when the
  pipeline orchestration layer is next touched.

## Phase 0 (unattended-robustness spec) — product decisions surfaced

Raised while resolving the pre-existing red tests (M8.B). Each is xfail-annotated
with a reason; these need a product call, not a test edit.

- **Universal `MAX_TOKENS_SUMMARY=4096` output ceiling.** `cap_max_tokens_for_model`
  floors *every* model to `config.MAX_TOKENS_SUMMARY` (4096), so the haiku 8192
  entry in `MODEL_OUTPUT_TOKEN_LIMITS` and any higher per-model limit are always
  dominated. Header-validation batches and long summaries may be truncated (P9).
  **Decide:** is 4096 the intended global ceiling, or should the cap be the *model*
  limit (raising header-validation / summary headroom)? xfail:
  `test_header_validation_token_limits.py` (2 tests).
- **Config settings don't reload across `ProjectSettings` instances.** A new
  instance does not pick up a persisted `default_source_dir`. Real gap; fixing it
  is a config-wide change. xfail: `test_config_validation.py::test_runtime_settings_persistence`.
- ~~**Bowen integration tests certify the abandoned `> **Label:**` format.**~~
  ✅ FIXED 2026-07-15: repointed to the real consumer `parse_bowen_references_text`
  (the saved `### Concept\n> "quote"` format), un-xfailed, now passing; removed from
  `test_code_health.py::KNOWN_REDS`.
- **6 vacuous (assertion-free) tests still on the allowlist.** `test_exception_fix.py`
  (×4) and `test_validation_headless.py` (×2) verify nothing (TEST_VALIDITY_REPORT §3).
  The M6.B gate (`quality_gates.find_vacuous_tests`) now blocks *new* ones and
  allowlists these; give them real assertions and drop them from `KNOWN_VACUOUS`
  in `tests/test_quality_gates.py`.

## Bugs (unfixed)

### ~~`unknown_script` rows in the cost log on real runs~~ ✅ FIXED 2026-07-15 (Step 2)
Five API calls logged token usage with a nameless logger → `unknown_script` rows in
**real runs**. Fixed: `abstract_pipeline` (×2), `summary_pipeline`,
`transcript_extract_terms`, `transcript_audit_voice` now pass a named logger.
Tests: `test_validator_gate_hardening.py::test_extract_terms_passes_named_logger`,
`::test_audit_voice_passes_named_logger`. (Abstract/summary sites pass the module
logger directly.)

### Emphasis saver doesn't sanitize `"` inside quote/concept text *(pre-existing)*
Unlike `_format_bowen_refs` (which maps `"`→`'`), the emphasis save block writes
quotes raw, so a nested `"` inside a quote would truncate on re-parse (a P19
round-trip hazard). Ref: `extraction_pipeline.py` `extract_scored_emphasis` save block.

### `_load_runtime_settings` AttributeError on valid non-dict JSON *(pre-existing)*
Corrupt JSON resets to `{}`, but a *valid* non-dict top-level (hand-edited `[]`
or a string) would `AttributeError` on the first `.get`. Ref: `config.py` `_load_runtime_settings`.

---

## Pre-existing test failures (9 — red before the run-log work, still red)
Worth a dedicated pass; none related to the validator/estimator/Bowen fixes.

- `test_config_validation.py::test_runtime_settings_persistence` — config singleton doesn't reload across instances (SOURCE_DIR).
- ~~`test_html_generation.py::test_highlighting_logic` — highlight tuple unpack (`expected 3, got 2`).~~ ✅ FIXED 2026-07-15 (Step 2).
- ~~`tests/test_html_generator.py::` `test_generate_simple_html_page_structure`, `test_highlight_html_content_basic`, `test_highlight_html_content_exact_word_match` — HTML highlighting.~~ ✅ FIXED 2026-07-15 (Step 2): both `_highlight_html_content` and `format_ref_list` now tolerate 2-/3-tuples.
- `tests/test_header_validation_token_limits.py::` `test_validate_batch_caps_tokens_for_haiku`, `test_cap_max_tokens_defaults_to_32000_when_model_limit_unknown` — token-cap logic.
- `tests/test_bowen_references_integration.py::` `test_bowen_references_generation_and_extraction`, `test_bowen_references_fallback_to_primary_when_filter_invalid` — Bowen integration (may now behave differently after the Bowen fixes — recheck when investigating).

---

## Improvements / tech debt

### Bowen extraction still concept-labels on some transcripts
Enriched prompt + fixed attribution filter + counter now capture genuine
attributions (e.g. "Bowen's basic ideas") and the drop-diagnostic makes 0-results
inspectable — but the *primary extraction* still surfaces concept applications and
can miss real attributions (e.g. "Bowen did at MCV" on the KCFC file). **Next:**
iterate the extraction prompt using `… - bowen-references-debug.md` as evidence.

### Cost estimator still ~20% low
Improved 3.6× → ~1.3× low. Remaining gap: Ranked Lenses output under-modeled
(~2171 est vs ~4850 actual) and the Theme/Lens validation loop can run up to 3×
(modeled as 1 pass). Calibrate against more real runs if tighter estimates matter.
Ref: `transcript_cost_estimator.py`.

### Topics validation `section_mismatch` — ✅ parser bug FIXED (A6)
Topics cite section ranges that don't line up with actual sections
(`section_mismatch` 6–7 on real runs). ~~Cosmetic; the topics themselves validate.~~
**2026-07-14:** the P19 audit (**A6**) traced most of this to `parse_section_range`
truncating multi-segment citations to the first range — **fixed** (see the MEDIUM
banner above). Re-run a real transcript to confirm the residual mismatch count drops;
any remainder is genuine topic/section drift, not the parser.
Ref: `validation_pipeline.py` `validate_topics_lightweight`, `summary_pipeline.py` `parse_section_range`.

### Abstract conclusion detection has narrow phrase recall *(from A4 fix)*
`extract_closing_conclusion` now searches the closing body correctly, but
`config.ABSTRACT_CONCLUSION_PATTERNS` is a short hardcoded phrase list — a real
closing using none of them (e.g. the KCFC "witching hour…" sign-off) still returns
"No explicit conclusion stated", dropping the conclusion-coverage check. Broaden the
phrase set (editorial) or add a fallback (e.g. last 1–2 sentences of the final
section). Ref: `abstract_pipeline.py` `extract_closing_conclusion`, `config.ABSTRACT_CONCLUSION_PATTERNS`.

### `_validated` filename gate broader than needed
`do_run_selected` blocks any selection whose source lacks `_validated`, including
late-only stages (package/webpdf/bowen_emphasis) that don't read the raw source.
Matches prior `do_all` behaviour (spec SS.10) — not a regression. Revisit if it
causes spurious "run Init Val first" blocks. Ref: `ts_gui.py` `do_run_selected`.

### Redundant Emphasis+Bowen double-run
Selecting **Core** (with Include Emphasis/Bowen) *and* the standalone
**Bowen + Emphasis** stage runs both twice (wasted cost + overwrite). A workflow
choice, not a bug — a heads-up warning when both are selected would help.
Ref: `ts_gui.py` `_run_selected_stages`.

---

## ~~Step 3 — multi-agent contract audit (P19)~~ ✅ DONE 2026-07-14
Ran: 11 finders (one per LLM pipeline step) + 20 adversarial verifiers, all checked
against the real KCFC artifacts. 12 findings confirmed (see **P19 contract-audit
findings** at the top of this file, A1–A12), 8 refuted. No new API spend.
Next actionable work: the **theme-parsing cluster A1–A3** (highest impact — silently
corrupts both the abstract and summary inputs on every real transcript).
