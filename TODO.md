# TODO — open bugs & tech debt

Tracked so we don't lose them. Items surfaced during the **2026-07-13 run-log
review** sessions unless marked *pre-existing* (not introduced by that work).
Fixed items live in CHANGELOG.md; recurring lessons in LEARNINGS.md.

---

## 2026-10-13 — End-to-end run findings (E2E)

**Rerun after E2E6 (commit 2efc602, $6.10):** scored emphasis passed on all three talks
(largest emphasis call 4,874 output tokens on Why Families). Why Families and Systems
Biology passed every stage and the gate allowed both. Beautiful Boy: Format dropped one
word ("that," in section 63); the word check stopped it for a person's review (the GUI
pauses there) and the gate blocked publication until it is reviewed — working as designed.

New from this run:
- ~~**Summary coverage messages contradict the verdict.**~~ Fixed E2E7 (2026-10-14). The stored verdict is PASS (the
  gate checks topic and closing items only) but its detail is the report's first line,
  "Validation: FAILED - missing: Q&A content (100%)", and the GUI logs "publication will
  be blocked until it does" when it is not (`validation_pipeline._write_summary_coverage_verdict`,
  `ts_gui._run_stage_structured_summary`). Make the detail and the message follow the
  gate status (P6).
- **Q&A share of Beautiful Boy varies: 100%, 18%, 100%** across runs 2–4 of the same talk.
  The detector depends on the formatter's headings and labels. Not gated, but it feeds
  the summary and abstract inputs.
- ~~**A theme used a new field label, "Summary"**~~ (Why Families interpretive themes). Sent
  to the judge as evidence and reported (TE, as designed). Another case of the model's
  free-form layout drifting. Fixed for new runs 2026-10-14 (ST): the theme stages return
  JSON and the pipeline writes the layout (`docs/plan_structured_themes_2026-10-14.md`).
  Old files keep the TE/TD handling.

**Run 9 (2026-10-14, commit 59d64c8, $6.62):** all 39 stages passed; the gate allowed all
three talks. Remaining noise, none of it failing a run:
- **The name check flags headings the model invents** in the overview and blog
  ("Patterns Identified", "Multigenerational Roots", "Closing Advice", "On June",
  "Swapping One Culprit") as names that do not appear in the source. Each costs a
  revision (all converged in run 9). Possible fix: judge a generated heading as a name
  only when it looks like a person's name. Needs the author's choice (it loosens a
  blocker's backstop).
- **Header validation** still logs 12–20 "problematic terms" warnings per talk.

**Run 8 (2026-10-14, commit 73168f1, $6.27):** Beautiful Boy and Systems Biology passed every
stage; the gate allowed both with warnings. Why Families: the overview failed faithfulness
on all three tries, one different claim each time (a made-up Bowen quote, "webinar-style",
a line addressed to the reader), so the gate blocked publication. Near misses: Beautiful
Boy summary 516 words (retried), Systems Biology abstract 274 and 266 words (retried twice).
The abstracts' Q&A sentences now come from the transcript, but the check still lists them
for review. Fixes for these and for the Format stops in runs 4, 6 and 7 are planned in
`docs/plan_run_safe_2026-10-14.md` (RS, approved and built 2026-10-14; see CHANGELOG).

Adjacent, found while building RS (not fixed):
- **The abstract has its own copy of the faithfulness retry loop**
  (`generate_structured_abstract`) instead of `_generate_until_faithful`. RS.6 added the
  revise step to both; the copy still lacks the shared loop's check that rejects a draft
  repeating a flagged claim (the judge then flags it again, one extra judge call).
- **The abstract prompt makes "webinar" the default event type**; the Why Families
  overview turned that into "a webinar-style conversation", which the judge flagged
  (the talk is an interview). The judge accepted "webinar" everywhere else in run 8.
  Author's choice in the prompt; noted, not changed.

**Runs 6 and 7 (2026-10-14, ST end-to-end, $6.26 and $6.08)** — theme stages all passed;
found outside them:
- ~~**Structured summary fails when every attempt is short.**~~ Fixed 2026-10-14 (SL3,
  `docs/calibration_summary_floor_2026-10-14.md`): 553 words accepted, 585 still asked. Run 7: Beautiful Boy 580
  words and Systems Biology 562, under the 585 floor on all three attempts, so the stage
  failed. Run 6: 584 and 581 on a first attempt, then passed. The model writes about
  560–600 words when asked for 650 (585–780 accepted). Options: ask for the middle of
  the band (about 680) while accepting 585–780, or retry with the draft and its word
  count. Needs the author's choice (it changes what the model is asked for).
- ~~**Abstract Q&A sentence built from pattern fragments.**~~ Fixed 2026-10-14 (AQ, same
  doc). `calculate_qa_percentage` still extracts the fragments for the abstract-input
  record (`to_contract_dict`); nothing reads them now (cleanup, not fixed). When the Q&A note is on,
  `AbstractInput.to_json` sends `qa_topics`: words after "about/on/regarding" with
  small words removed ("exploration reading book written"), and the prompt says to
  mention them. Run 7 Beautiful Boy: the judge flagged the Q&A sentence on all three
  attempts and the gate blocked. Beautiful Boy's Q&A share swings (100% / 18% / 100%),
  so this comes and goes. Fix: stop sending `qa_topics`; have the model describe the
  Q&A from the transcript, which the judge can check (same rule as E2E1).
- **Summary input still carries pattern-made Q&A fragments** (found in the AQ review, not
  fixed). `summary_pipeline.SummaryInput.to_json` sends `qa` with `question_types` (raw
  phrases after "about/on/regarding") and `percentage`, and the summary's Q&A coverage
  item is built from them. Lower risk than the abstract (the prompt does not name the
  field; the item does not gate), but the same rule applies (E2E1/AQ).
- **A first-attempt abstract failure leaves the earlier run's abstract on disk** (AQ
  review, existed before). If attempt 1 cannot be generated, the stage fails without
  writing, so the previous `abstract-generated.md` stays. (The word limit no longer
  raises: RS.1 keeps the shortest draft with a warning.)
- **Format variance, again:** run 6 Systems Biology (one malformed heading, one dropped
  word), run 7 Beautiful Boy (two differences). Format at high effort passed 8 of 9 in
  the 2026-10-14 measurement; these runs give 4 of 6. Since RS.3/RS.4 (2026-10-14) these
  no longer stop the run: dropped or changed words in ordinary text are set back to the
  source's words, and the extra-`00:` heading timestamp is corrected. The variance
  itself is unchanged; a difference at a heading or speaker label still needs review.
- **Shared thinking estimate is high for short calls.** `THINKING_TOKENS_ESTIMATE`
  adds 3,000 per call at high effort; the theme calls measured 375–2,036. Calibrate per
  stage if tighter estimates matter (see "Cost estimator still ~20% low").

- **The first abstract can describe interpretive themes that were later replaced**
  (found in the ST review, 2026-10-14; not fixed). PART 5 builds `abstract-initial` from
  the first interpretive set; if the theme/lens validation loop regenerates the themes,
  the saved abstract and theme file disagree. Before ST this happened when the
  validator rejected the interpretive themes; now also when it rejects the structural
  ones. The structured-abstract stage reads the saved files, so it is not affected.

**Rerun after E2E1–E2E5 (commit cbbf54e, $5.78):** all three talks pass the release gate
(ALLOW_WITH_WARNINGS). Systems Biology is no longer blocked (abstract: one flag on attempt
1, passed on attempt 2; theme judged grounded). Scored emphasis failed on the two long talks
(see below). Why Families passed every stage.

Run with `scripts/e2e_run.py` (all 16 GUI stages, headless, separate folder) on three
public talks at commit 6b712d9, main model claude-sonnet-5-5. Cost $6.18 in total.
Why Families: all stages pass, gate ALLOW_WITH_WARNINGS. Beautiful Boy: all stages
pass. Systems Biology: blocked.

### ⏸ Open — found by the run
- ~~**Abstract is given numbers the transcript does not contain (blocks Systems Biology).**~~ Fixed E2E1.
  The abstract prompt receives topic coverage ("~15% of transcript") and a Q&A
  percentage. The model wrote "The question-and-answer session, which accounted for
  roughly fifteen percent of the presentation…"; the judge, reading only the
  transcript, correctly finds it unsupported. Regeneration produced a different flag
  each time (3 attempts). Fix the inputs: do not give the generator figures it must
  not state, or tell it not to state them.
- ~~**Systems Biology structural theme judged ungrounded again**~~ Cause found (E2E2): the theme named the
  chapter author ("Pellikainen"), whom the speaker never names; the judge was right. Prompt rule added;
  its effect is not shown yet (6 of 6 test generations passed, old and new prompt). Was: ("Cancer as Dysregulated
  Niche and System, Not Rogue Cell"), on freshly generated themes. It fails on every
  run of this talk. Needs one look: is the theme wrong (names such as "Bertoloso",
  "Weinberg", "Popper") or is the judge wrong?
- ~~**Scored emphasis truncated**~~ Fixed E2E6 (thinking level "medium"); confirmed by the run after it
  (3 of 3 talks). Was: NOT fixed by E2E3. Rerun (cbbf54e): it failed on Beautiful Boy and
  Systems Biology at the new 24,000-token ceiling. The saved answer is ~3–4k tokens; successful calls
  used 11–14.5k output tokens, so the rest is thinking, and it varies run to run (Beautiful Boy: 14,540
  in one run, over 24,000 in the next). Raising the ceiling only moves the line. Next: set the thinking
  level (effort) for this call, measured against current item quality, or split long transcripts. In
  the GUI the run stops here on long talks. Was: (11k words): the reply used the full
  16,192 output tokens (8,192 + thinking headroom) and was rejected; the Bowen +
  Emphasis stage failed. Beautiful Boy (12k words) fit, so it depends on the run.
  `config.MAX_TOKENS_EXTRACTION` (8192) predates the thinking models.
- **Structured summary minimum length:** band fixed 2026-10-14 (SL, then SL3: the prompt
  asks for 585–780 words for the 650 target and 553–780 is accepted). Still open: the
  target is a fixed 650 whatever the talk length, so a short talk's summary may still
  run under 553 words; since RS.1 it is kept with a warning instead of failing. Was: a 569-word summary was rejected (minimum 600 words) and
  regenerated.
- **Meta-claims about the talk get flagged:** "The talk states no explicit
  conclusion" (overview, Why Families) and "though no explicit closing conclusion is
  stated" (abstract, Systems Biology). The prompts ask for a conclusion; when there is
  none the model says so, and the judge flags it. Retries fixed it here.
- **Init Val holds "abit" -> "a bit"** as not a mishearing fix (Why Families).
- **Header validation is slow and noisy:** 2–6 minutes per talk; 13–20 warnings per
  talk that a heading "contains problematic terms" such as "anxiety",
  "differentiation", "emotional system" (the talk's own subject).
- **The release gate runs 4 times per publish step** (web, PDF, simple, bundle);
  cached, so cheap, but the log repeats each verdict 4 times.

### ⏸ Open (adjacent, found in the E2E review, not fixed)
- **Output critic reads no real themes** (found in the TP review, 2026-10-14):
  `skills/trans-summary-output-critic/scripts/review_outputs.py` `extract_candidate_items`
  (~line 135) does not know the `**N. Title**` format; on the structural fixtures it returns
  only the heading "Structural Themes (3 total)", so its semantic review checks no theme.
  Fix: use `transcript_utils.theme_display_blocks`.
- **Open risk (TP/TD):** a theme the published-theme parser rejects (a title like
  "Summary", or a list item with no Description) is left out of the page, the judge and
  now the prompts, with no log line. None on disk today (55 files checked). New runs
  cannot produce one: ST rejects such a title and requires a description. Old files
  still can.
- **Summary and overview are also given figures their judge cannot check.**
  `summary_pipeline.SummaryInput.to_json` sends topic `percentage`, `sections` and the
  Q&A percentage. The overview gets the raw topics text ("~XX% of transcript;
  Sections X-Y") and the structural themes, whose prompt asks for "spans ~40% of
  content". Both are judged. Same fix as E2E1 if they start to block.
- `summary_pipeline.py` (~line 546) has its own "No explicit conclusion stated" text
  and conclusion patterns hardcoded in code (rule 9: editorial content belongs in
  config).
- `pattern_sets.patterns_dir()` builds its folder from the transcripts base, so with a
  source folder chosen directly it is `~/patterns`: the same parent-folder problem
  E2E4 fixed for the terms file.
- Choosing a new source folder replaces a saved custom terms path in memory, and a
  restart brings the saved one back (existing behaviour, tested).
- **Your real `logs/runtime_settings.json` still has test values:**
  `validation_approved_terms_path` (a deleted pytest folder) and `default_source_dir`
  / a favorite "/path/to/my/default/source". The saved terms path wins at startup, so
  E2E4 does not apply until it is reset (GUI: Terms File reset). The GUI now warns at
  startup.

### ⏸ Open — found while setting up the run
- ~~**The GUI's Init Val runs without your approved terms.**~~ Fixed E2E4. Choosing
  `/Users/davemini2/transcripts` as the source folder sets the base to its parent, so
  the terms file becomes `/Users/davemini2/approve_terms.txt`, which does not exist.
  `validation_learning.load_approved_terms` returns an empty set for a missing file
  with no warning (P2). Your file is `/Users/davemini2/transcripts/approve_terms.txt`.
- ~~**The test suite writes into the real `logs/runtime_settings.json`.**~~ Fixed E2E5 (the leaking tests were in
  `tests/test_ts_gui_run_all.py`; `set_transcripts_base` reset `LOGS_DIR`). The bad entries already in your file are not removed yet. After a full
  run, `validation_approved_terms_path` points to a pytest temp folder and
  `default_source_dir` is "/path/to/my/default/source". `tests/test_folder_defaults.py`
  alone does not do it; it depends on test order. Not yet traced.

---

## 2026-10-13 — Init Val (IV)

### ✅ Fixed 2026-10-13
- ~~Init Val stopped when a chunk had nothing to fix~~ — the fenced empty list was under
  the 50-character minimum reply length. See CHANGELOG (IV).

### ⏸ Open (adjacent, IV, not fixed)
- `transcript_initial_validation.py` (v1) `validate`: when the reply has no fenced list,
  the `raw_decode` fallback returns its findings directly, without
  `filter_validation_findings`. The fenced path filters. The GUI's default is v2, so this
  affects only the v1 mode.
- **Bowen semantic filter (same kind as IV, fails open):** `prompts/bowen_reference_filter_v1.md`
  says "If none qualify, return an empty response", but `validate_api_response` always
  rejects empty text. The call (`extraction_pipeline.py` ~line 475, `min_length=20`) is
  retried 3 times and then the `except` keeps **all** the original references. Fix: a
  fixed empty answer (e.g. `NONE`) in the prompt, accepted by the code; a filter failure
  should not keep everything.
- **Bowen extraction (same kind as IV):** `prompts/bowen_reference_extraction_v1.md` gives
  no answer for a talk with no Bowen references; a short reply ("None found.") is under
  the `min_length=50` at `extraction_pipeline.py` ~line 878 and the stage fails.
- The IV caller test sees only direct `call_claude_with_retry` calls on the default, not
  wrappers (`_generate_summary_with_claude`) or explicit minimums.

---

## 2026-10-11 — Web page checks (RF.O / RF.P)

### ✅ Fixed 2026-10-11 (`docs/plan_todo_triage_2026-10-11.md`)
- ~~Published Themes section shows file scaffolding~~ — D1: themes are rendered from the
  parsed items (`transcript_utils.theme_display_blocks`).
- ~~Stale worktree `hungry-wilbur`~~ — D3: removed (its one uncommitted change was
  already on main), with 5 fully merged branches.

### ⏸ Open — faithfulness judge (2026-10-11)
- **Watch (SA, 2026-10-12):** the Kerr summary sentence "She handed the helm to him… She
  did not react, though he says he deserved it." is faithful but was a first-pass flag
  in 5 of 30 checks with the SA rule (1 confirmed), against 0 of 10 before. Possibly noise;
  re-check if it blocks a real run (`docs/calibration_speaker_attribution_2026-10-12.md`).
- **Open (adjacent, SA):** any change to the judge's inputs or version re-judges every
  saved artifact. A borderline claim that passed at generation can then block at
  publish (how the 2026-10-12 Kerr run was blocked). By design (a logic change must
  re-verify). Flags now survive it (D2 + SA6); PASSes do not carry over.
- ~~Random false flags~~ — fixed 2026-10-11 (CF): a flag fails a run only when a fresh
  judgement agrees; Kerr false fails 5/10 → 0/10 (`docs/calibration_confirm_2026-10-11.md`).
  Still open: first-pass misses on the borderline policy cases k4/k5/k6 (gold recall
  0.86–0.91 per run). Accepted (decision CD2): the theme and key-terms judges have no
  confirmation.
- ~~**Sticky cached FAIL**~~ — fixed 2026-10-11 (D2): only PASS verdicts are kept in the
  disk cache; a FAIL is re-judged on the next gate run. A file judged FAIL before needs
  two PASSes in a row to pass a run, and its PASS is not stored. Limits: the "flagged"
  marker can be evicted by the 2000-entry cache cap (then a later PASS is stored); the
  blog-grounding check (advisory) has no two-PASS rule.
- **k6 gap (known, accepted)**: the judge accepts the writer's own claims about a theory
  ("…central to Bowen theory's explanation…"). A narrower framing rule was tried and not
  shipped (`docs/calibration_framing_2026-10-11.md`).
- ~~`judge_recalibration.py --prose-real` omits the filename metadata~~ — fixed 2026-10-11
  (Q5, shared `release_gate.with_recording_metadata`); the prompt sha is recorded since CF.
- ~~Prompt example "attributes recovery to medication" paraphrases gold us6~~ — fixed
  2026-10-12 (Q6/C1, `docs/calibration_q6_prompt_2026-10-12.md`); also "definitively
  proven" (us7). No loss: gold recall 0.95 vs 0.91 (the difference is ambiguous k4), Kerr 0/10.
- ~~**Open (Q6 review):** the prompt's "entailed" examples come from measured material~~ —
  fixed 2026-10-12 (FX, `docs/calibration_fx_examples_2026-10-12.md`): all four framing
  examples and the DOS example now use unrelated subjects; no loss on gold, real
  abstracts, Kerr (0/10); real prose flagged at a similar rate (final 46 vs current 48 of
  602; 14 sentences changed status, 1 run each). The calibration's real-abstract checks
  now include the gate's recording metadata.
- ~~**Judge reply format:** invalid JSON → ERROR → gate block~~ — fixed 2026-10-12: the
  cause was unescaped quotes inside a rationale; the parser now reads verdict objects
  directly when the reply isn't valid JSON (still fail closed). Native structured output
  remains the fuller fix (M2 follow-ups).
- ~~**Open risk (D2 × version bumps)**~~ — fixed 2026-10-12: a FAIL under any logic version
  marks the content as flagged (`release_gate._flagged_any_version`); the 35 flagged entries
  in the live cache still count after the Q6 bump.

### ⏸ Open — from the Hermes QA gate (`docs/cycles/2026-10-11_rfop-qa-gate.md`, APPROVED)
- ~~**LOW (P7)** `missing_names` substring match~~ — fixed 2026-10-11 (Q1): the page
  name must start with the source name.
- **LOW (decision)** a page missing some (not all) topics/themes/key terms is a
  warning, so the stage passes (RF.P.3 as approved). Revisit if partial misses should block.
- The "7/7, 10/10, 10/10" Kerr result is a manual run, not an automated test (the
  tests use a 2-item fixture through the same parsers).

## 2026-10-04 — Full-repo review (`REVIEW-trans-summary-2026-10-04.md`)

Plan: `docs/plan_review_fixes_2026-10-04.md` (R1–R18). Fixed on branch
`validation-hardening` 2026-10-04/05 — see CHANGELOG.

### ✅ Fixed
G1 (GUI BLOCK side effects), G11 (cleanup deletes sibling `_vN`), B-05 (placeholder
re-append), D-09 (escaped CSS), F12/F14/B-11 (client factory, retries, timeouts,
max_tokens), F2 (names in headings/labels/`---`), F3 (theme evidence judged), A-08
(zero claims → ERROR), F4 (judge cache key), F6 (drift monitor `--model` for themes),
G6 (speaker item), F13 (summary LLM rescue), C-07 (unverified ≠ missing), G14 (shipped
judge flags pinned), Q6 (Gen Abstract fails when unfaithful), emphasis / topics /
summary-coverage gates (R15).

### ⏸ Open — needs a decision
- **Key-terms gate — decided 2026-10-05: stays advisory.** After alternative-label
  grounding, `dave_g_test2` still FAILs two paraphrased labels ("Verbal and Physical
  Abuse", "Foster Care / Adoption Agency Work"); the author chose to keep key terms as a
  report-only check. Revisit only with a calibrated semantic check
  (`KEY_TERMS_JUDGE_ENABLED`).
- **Topics gate is lenient (review G9).** A topic FAILs only when title < 0.25 AND
  description < 0.20 against the whole transcript; the gate catches nonsense topics,
  not mis-sectioned or partly-fabricated ones.
- **Stated-purpose extraction** picked "I'm going to be presenting from PowerPoints."
  on a real run; summary/abstract coverage reports it as missing (advisory under 3a).
- ~~**Emphasis "verbatim" threshold is fuzzy.**~~ ✅ Measured 2026-10-12 (D6, 752 real
  quotes, 33 projects): the gate also requires full word coverage, so the example below
  is rejected. The gate's 0.80 is kept (0.95 would reject 4 real near-verbatim quotes to
  catch 2). The Emphasis validator now uses the gate's test (it passed 24 quotes as
  "partial" that the gate blocks). ~~**Still open (P7):** a quote with a swapped word passed when the
  quote's words also occur in order nearby~~ — fixed 2026-10-12 (SW,
  `docs/plan_swapped_word_quotes_2026-10-12.md`): a changed lead or tail of up to 4
  words now fails; 5 of 782 real passing quotes fail, each a real changed word. Still
  open (accepted): a substitute within 2 words of the rest of the quote, a changed edge
  the quote marks with "...", and a changed edge of 5+ words are not caught; an unmarked
  omission right after a quote's first words is rejected (no real case; 6 of 835 real
  quotes have an ellipsis).
  **Re-run Bowen/emphasis** for the 5 affected projects before republishing them:
  2021 Webcast Feb, Jun, Oct; 2021 Webinar Dec (KCFC); Monika Baege / Michael Kerr.
  The standalone CLI `transcript_validate_emphasis.py` crashed on scored files (2- vs
  3-tuples) and matched 15 words only; it now uses the gate's test and exits non-zero.
  Was: **Emphasis "verbatim" threshold is fuzzy (sweep note, pre-existing).** A quote passes
  at `EMPHASIS_QUOTE_PARTIAL_RATIO` 0.80, so "the family is a rational unit" against
  "…an emotional unit" scores 0.919. Now that emphasis gates publication, consider a
  stricter threshold — check it against the real fixtures first.
- **Mutation gate not re-run** after `_emphasis_quote_found_ratio` changed (R15).

### Not fixed (minor findings in the report)
All other minor findings in the report remain open (e.g. F5 mutation-harness baseline,
F11 manifest model provenance, G2/G13 other discarded return values, G8/G9, STRUCT-*).

---


## 2026-09-23 — Source fidelity, review and pattern sets (open items)

- **Unify Terms File and pattern sets.** Initial Validation still uses the single global Terms File (`VALIDATION_APPROVED_TERMS_PATH`); pattern sets feed formatting. Approved-term lines in a pattern set currently have no effect. Decide whether Initial Validation should read the project's pattern set.
- **Calibrate the new judge checks on real runs.** `topic_term_faithfulness` ✅ measured 2026-10-12 (C2, `docs/calibration_topic_term_2026-10-12.md`): 5 real projects × 2 runs, one real misattribution caught every run, one borderline definition, no clear false flags; still advisory (decision pending: make the topics half blocking?). Heading claims (faithfulness, blocking) were never run against real outputs (no API key in the implementing session). Run 3–5 known-good projects; demote to WARN if they false-block.
- **Calibrate the gross limits.** `VALIDATION_MISMATCH_RATIO` (1.5%) and `VALIDATION_MAX_CONTIGUOUS_RUN` (10) rest on one real transcript (where_roots). Also `QUOTE_MIN_WORD_COVERAGE = 1.0`.
- ~~**Formatting model retirement.**~~ ✅ DONE 2026-10-12: `FORMATTING_MODEL` = Sonnet 5.5,
  `AUX_MODEL` = Haiku 5.5 (`docs/calibration_formatting_model_2026-10-11.md`). Was: `FORMATTING_MODEL` is Haiku 4.5; Anthropic lists its retirement as not sooner than 2026-10-15. **Measured 2026-10-11** (`docs/calibration_formatting_model_2026-10-11.md`): Haiku 5.5 passed 2 of 6 runs vs 3 of 6, and edits the speaker's words more (grammar, a name, a repeated passage); cheaper and faster on long talks. Not switched — decision pending (switch anyway / measure low effort and Sonnet 5.5 / wait). `VALIDATION_MODEL` and `AUX_MODEL` are also Haiku 4.5. `DEFAULT_MODEL` (Sonnet 4.6) is a legacy model.
- **Packaging can ship stale pages.** `package_transcript` zips existing webpage/PDF even if an artifact changed after they were built; regenerate or compare against the run-manifest hashes.
- **PDF transcript text is not checked** word-for-word (the webpage is).
- **Review keys and `skip_words_file`.** Approval keys use raw word positions after skip-word filtering; validating with a different skip-words file makes approvals not match (fails closed, but forces re-review).
- **Review window only verified on a Linux virtual display.** Check layout on macOS; the dialog test is skipped without a display (CI).
- **Chunked formatting** for transcripts beyond the single-pass limit (~45k words on Haiku 4.5); currently fails early with a message.

## 2026-07-18 — Adversarial code-review findings

Full report: `docs/CODE_REVIEW_2026-07-18.md` (45-agent adversarial review, refute-first verified). Being worked through in `/csdp` batches of 5. `verify:` is the independent verification verdict (`→X` = re-rated severity).

### ✅ Fixed (37) — see CHANGELOG 2026-07-18

- **[C1]** Non-dict runtime_settings.json crashes config import app-wide (corrupt-state not handled) — `config.py:64`
- **[H1]** Faithfulness/theme judges re-send the full transcript per artifact with NO shared cached prefix — the single biggest waste — `faithfulness_judge.py:228`
- **[H2]** Process-lifetime judge memo is defeated by the CLI orchestrator's subprocess-per-publish-step model — gate + armed judges run 4x/publish — `release_gate.py:354`
- **[H3]** Non-atomic write + silent {} reset loses ALL persisted settings on a partial write — `config.py:89`
- **[H4]** pyproject.toml under-declares runtime deps: only jsonschema listed, so `pip install .` yields a broken install — `pyproject.toml:7`
- **[H5]** CI build matrix (3.8/3.9/3.10) contradicts requires-python>=3.11 AND the code's real >=3.10 floor; failures masked by `|| true` so it can never fail — `.github/workflows/ci.yml:56`
- **[H6]** README lists all three default model IDs, none of which match config.py — `README.md:211`
- **[H7]** README says abstract-coverage failure halts 'Run All' — code made it advisory (contradicts README line 23 too) — `README.md:126`
- **[H8]** Default 'V2 (Safe)' initial validator swallows transient API/parse failures and silently drops a chunk's findings (fail-open) — `transcript_initial_validation_v2.py:233`
- **[H10]** O(items × transcript) fuzzy grounding scan blows up to minutes on a long transcript with ungrounded quotes — `extraction_pipeline.py:828`
- **[H11]** Claim-extraction label-strip regex silently deletes a fabricated pre-colon specific before the armed faithfulness judge ever sees it (gate bypass) — `faithfulness_judge.py:136`
- **[H12]** Faithfulness and theme judge models are floating aliases, NOT date-pinned snapshots — comment claims 'PINNED' but the value has no date suffix (P20/P6) — `config.py:548`
- **[H13]** Stored XSS: untrusted transcript + LLM fields flow unescaped into the HTML/PDF bundle — `transcript_utils.py:1642`
- **[M2]** Abstract regeneration loop blames/regenerates the abstract for unfaithful claims in OTHER narrative artifacts (summary/overview/blog) — `extraction_pipeline.py:1118`
- **[M3]** Emphasis score is miscomputed and timestamp silently dropped when a rank header omits the '%' sign — `transcript_utils.py:1499`
- **[M4]** ARCHITECTURE_DESIGN.md omits the entire release-gate / faithfulness-judge / theme-judge layer that now governs publishing — `ARCHITECTURE_DESIGN.md:82`
- **[M5]** config.py inline 'Defaults' comment states FORMATTING_MODEL = claude-sonnet-4-6, but the actual default is Haiku — `config.py:645`
- **[M6]** Retry/backoff policy hard-coded at use sites, not in config.py — `transcript_utils.py:560`
- **[M8]** A non-blocking ERROR ("couldn't verify") ships as ALLOW_WITH_WARNINGS with no distinct signal in the one-line log, exit code, or a marker file — `release_gate.py:554`
- **[M9]** Run manifest omits a code-version / gate-policy stamp, so a decision can't be traced to the code or policy that produced it — `release_gate.py:600`
- **[M10]** token_usage.csv column headers mislabel the data they carry ('Items' holds the model, 'Status' holds the stop_reason) — `transcript_utils.py:399`
- **[M11]** Whole transcript is re-normalized on every find_text_in_content call (re-normalize-per-item) — `transcript_utils.py:1729`
- **[L1]** check_entity_consistency name regex uses \s+ and joins proper names across newlines, corrupting the near-duplicate clash detector — `release_gate.py:290`
- **[L2]** Split/inconsistent dev-dependency and specifier management across the three files — `requirements.txt:10`
- **[L3]** README claims html_generator.py is 650 lines; the file is 822 — `README.md:363`
- **[L4]** Stale doc comment: FORMATTING_MODEL comment says Sonnet, code sets Haiku — `config.py:645`
- **[L5]** VALIDATION_MODEL lacks a setter and is not refreshed like its siblings — `config.py:47`
- **[L6]** Prompt-caching beta header string duplicated as a magic literal — `transcript_utils.py:624`
- **[L7]** Editorial stopword list embedded in Python source — `extraction_pipeline.py:1276`
- **[L8]** Cost rows fall back to 'unknown_script' when no logger is passed, losing per-stage cost attribution — `transcript_utils.py:711`
- **[L9]** Git revision is cached as 'unknown' for the whole session after a single git failure — `ts_gui.py:186`
- **[L10]** Abstract prompt hard-codes '249'/'under 250 words' as literal text, duplicating config.ABSTRACT_HARD_MAX_WORDS (P4 drift) — `prompts/Abstract Generation Prompt v1.md:5`
- **[L11]** `_fill_prompt_template` copy-pasted identically in extraction_pipeline and validation_pipeline — `validation_pipeline.py:75`
- **[L12]** Two orphaned top-level unittest files are dead code (superseded by tests/) — `legacy_initial_validation_logic.py:13`
- **[L14]** Five near-identical `load_prompt()` functions differing only by a config filename constant — `summary_pipeline.py:736`
- **[L16]** base_name used to build filesystem paths without sanitize_filename (defense-in-depth gap) — `html_generator.py:679`
- **[L18]** check_theme_grounding 'no theme artifacts -> PASS' is an untested pass-on-empty branch, asymmetric with faithfulness's 'no artifact -> ERROR' — `release_gate.py:500`

### ⏸ Deferred (6) — need a human/API decision, NOT done overnight

- **[H9]** God-function: summarize_transcript is 462 lines, 11 params, one try/except -> bool — `extraction_pipeline.py:1354`
  - Why deferred: refactor the 462-line summarize_transcript — large structural change; wants human review
- **[M1]** Cross-process last-writer-wins read-modify-write on runtime_settings.json — `config.py:85`
  - Why deferred: cross-process settings lock (flock) — portability + design; low impact (lost update, not corruption; H3 already prevents corruption)
- **[M7]** God-function: validate_configuration is 414 lines of linear validation — `config.py:890`
  - Why deferred: refactor the 414-line validate_configuration — large, same class as H9
- **[L13]** Validator-dispatch (v1/v2 select + get_latest_version + validate + apply) copy-pasted across three ts_gui methods — `ts_gui.py:2533`
  - Why deferred: GUI validator-dispatch dedup across 3 ts_gui methods — CONSIDERED, deferred: the 3 methods genuinely differ (interactive vs auto flow), the change can't be verified headlessly (needs launching the GUI), and the review flagged it for human review. Best done at the app.
- **[L15]** Standalone CLI extraction pipeline (transcript_process.py + transcript_summarize.py + transcript_extract_*) appears superseded by extraction_pipeline.py — `transcript_process.py:32`
  - Why deferred: RESOLVED — KEEP. The CLI (transcript_process / transcript_extract_* / transcript_summarize) is cross-referenced across those modules AND covered by tests/test_validator_gate_hardening.py, so it's a supported, tested entry point, not dead code. No removal.
- **[L17]** mut_harness scores a suite TIMEOUT as 'killed', inflating the very mutation score the M6.A validity gate trusts — `mut_harness.py:160`
  - Why deferred: mut_harness scores a suite TIMEOUT as 'killed' — changing kill/survive semantics affects the M6.A CI mutation gate; debatable (a hung mutant arguably IS caught)
- **PyYAML / google deps (sweep #2):** `GoogleDocSummary.py` / `ListModels.py` import `google*`, undeclared in deps — peripheral scripts, don't break CI; add `google-api-python-client`/`google-auth-oauthlib` only if they're still used.

### Remaining (0) — by severity


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

## 2026-07-17 — faithfulness judge: re-calibrate after metadata-in-source change ✅ DONE
Re-calibrated since on 2026-07-19, 2026-10-04, 2026-10-09, 2026-10-10 and 2026-10-11.

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

## 2026-07-17 — Init Val fuzzy matcher (follow-up) ✅ FIXED 2026-08-22

The span-match guard (`transcript_utils.span_matches_original`) now makes Init Val
auto-apply *safe* against mis-located spans, but it does so by **skipping** them —
so the fuzzy-auto-apply path is largely neutralized whenever normalization changes
offsets (double spaces, timestamps, punctuation inside the phrase). Root cause:
`transcript_utils.find_text_in_content` computes its returned `(start, end)` from
normalized-word indices / first-prefix occurrence, so its offsets don't map back
to the raw text when normalization changed lengths.

- **Follow-up:** ✅ **FIXED 2026-08-22.** `find_text_in_content` now re-locates the
  matched window in the RAW haystack via `_locate_raw_span` (a case-insensitive,
  whitespace-flexible `\b…\b` regex) in both the exact and fuzzy branches, so a
  whitespace/case-only difference returns correct raw offsets and a legitimate
  fuzzy correction applies again — while the span guard still blocks a true
  mis-location (a typo/timestamp-split word, where `_locate_raw_span` returns None
  and the prior heuristic + guard keep the safe skip). Tests: `find_text_in_content`
  raw-offset cases in `test_fuzzy_grounding_prefilter.py`; the v1/v2 span-guard
  tests now assert the correction APPLIES for a double-space difference.
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

- ~~**⚠️ Themes migration shim must handle TWO real formats.**~~ ✅ Stale:
  `parse_bold_numbered_theme_blocks` reads both (AC M3.D.1). A P6 sweep of the
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
- ~~**Emphasis all-items-content-rejected raw fallback.**~~ ✅ FIXED 2026-10-11 (Q3):
  nothing is saved, the step fails, an earlier run's emphasis file is renamed `.stale`,
  and the main pipeline logs a warning.
- ~~**Adjacent (Q3 sweep):** a response of 500 characters or less that parses
  to 0 emphasis items is still saved raw and reported as success~~ — fixed 2026-10-12 (N1,
  `docs/plan_small_fixes_2026-10-12.md`): nothing saved, step fails
  (`extraction_pipeline.extract_scored_emphasis`, the `else response` fallback). The
  release gate then returns ERROR on that file, so it is loud at publish time.
- ~~**Adjacent (U5 sweep):**~~ fixed 2026-10-12 (N3: defaults are `None`, resolved per call). Was: `validate_headers`, the abstract helpers in
  `abstract_validation.py` and `generate_structured_abstract` take `model=config.AUX_MODEL`
  as a default bound at import, so a CLI call without a model ignores the model chosen in
  the GUI. `validate_summary_coverage` was fixed (its gate key depends on the model).
- **Adjacent (T1–T5 review, not fixed):**
  - ~~fixed 2026-10-12 (N2)~~ `extraction_pipeline._is_valid_section_content` (~line 183) accepts `1. **Title**`
    themes when the shared parser finds none, so Core can report valid themes while the
    format check reports drift. It should use the shared parser only.
  - (N5, 2026-10-12: the report now lists what it leaves out; pricing them is still open.) The cost estimate has no rows for the faithfulness/theme judges (majority of 3),
    the overview, summary-coverage validation, abstract-initial, or regeneration loops,
    so it is low by an amount it does not state.
  - ~~fixed 2026-10-12 (N3)~~ Function defaults `model=config.DEFAULT_MODEL` / `config.AUX_MODEL` are bound when
    the program starts. They matter only for a caller that passes no model; the GUI
    passes one.
- ~~**Theme evidence picks up document-level fields (found 2026-10-13, TM review):**~~
  judge side fixed 2026-10-13 (TE, `docs/calibration_theme_evidence_2026-10-13.md`).
  ~~**Still open (display):** the published page shows the trailing paragraph inside the
  last theme~~ — fixed 2026-10-13 (TD, `docs/plan_theme_display_2026-10-13.md`; labelled and
  unlabeled closing notes); rebuild the Why Families, Beautiful Boy and "This is a test"
  pages to pick it up. Adjacent: the overview/blog prompts got the raw themes
  files, notes included — fixed 2026-10-14 (TP). Was: the
  last theme in a file runs to the end of the text, so a trailing bold paragraph ("Summary
  paragraph", "Rationale and coverage summary") becomes that theme's evidence for the
  judge and is published with it (`transcript_utils._extract_theme_evidence`,
  `theme_display_blocks`). Seen in the Why Families and Beautiful Boy structural files.
  Fix: an allowlist of evidence labels in config (e.g. "key evidence") plus a contract
  test over every real fixture. It changes what the theme judge sees, so it needs a theme
  calibration run.
- **Systems Biology structural themes (found 2026-10-13, TM):** the theme "Convergence
  Between Systems Biology and Bowen Family Systems Theory" is judged ungrounded in 6 of 6
  checks (overreaching description, wrong section citation). Regenerate that project's
  structural themes before publishing it (`docs/calibration_theme_meta_label_2026-10-13.md`).
- ~~**Theme judge meta label (decision):**~~ fixed 2026-10-13 (TM, user approved; no
  change on gold or 36 real checks, `docs/calibration_theme_meta_label_2026-10-13.md`;
  21 of 25 interpretive files on disk use the label — the "126 of 161" below counted a
  wider set, scope not recorded). Was: `config.THEME_JUDGE_META_LABELS` has "nested under
  structural themes" but not "nested under structural theme(s)", the label 126 of 161 real
  interpretive files use and the prompt now names. That field is sent to the theme judge
  as evidence, not skipped. This was already the case; adding the label changes what the
  judge sees and needs a theme calibration run.
- ~~**Adjacent (Q4):** `parse_topics_from_extraction` strategy 2 treats text
  before the first `###` header as a topic~~ — fixed 2026-10-12 (N4): skipped and logged.
  `extract_scored_emphasis` (`extraction_pipeline.py:727`) does
  `final_content = "\n\n".join(lines) if validated_items else response` — when
  items parse but ALL fail `validate_emphasis_item` (content grounding), it saves
  the RAW model response, so content-rejected items get written (and now pass the
  M3 *format* self-check → a sidecar of rejected items). This is a pre-existing
  *content*-validation gap orthogonal to M3's format contract (the codec judges
  shape, not grounding); flagged per rule 10, not fixed here. Fix: on zero
  validated items, write a header-only/empty artifact (or fail) rather than the
  raw response.
- ~~**Abstract-input strategy-1 topic name edge.**~~ ✅ FIXED 2026-10-11 (Q4): a
  header that strips to "" was reproducible; such topics are skipped and logged. `parse_topics_from_extraction`
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
- ~~**Institutionalize:** mutation-score gate in CI~~ ✅ Stale: the nightly
  `mutation-gate` job runs `quality_gates.py mutation`.

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
- ~~**Dead duplicate `_generate_simple_html_page`.**~~ ✅ Stale: one definition remains. `html_generator.py` defines it
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

- ~~**Universal `MAX_TOKENS_SUMMARY=4096` output ceiling.**~~ ✅ FIXED 2026-10-11 (D5):
  `cap_max_tokens_for_model` now caps at the model's own max output
  (`config.MODEL_OUTPUT_TOKEN_LIMITS`, else `model_specs.capabilities`); the 2 tests
  were rewritten and un-xfailed. In practice this changes only the abstract LLM check
  with more than ~50 items. Header validation: ✅ FIXED 2026-10-12 (HV) — the
  whole-transcript call that was cut off now uses the batched validator; per-batch
  ceiling 8192 as margin (largest measured batch 6,525 tokens incl. thinking; the
  batched path fit at 4096 too). Was: the cap floored every model to 4096 (2 xfail tests).
- **Config settings don't reload across `ProjectSettings` instances.** A new
  instance does not pick up a persisted `default_source_dir`. Real gap; fixing it
  is a config-wide change. xfail: `test_config_validation.py::test_runtime_settings_persistence`.
- ~~**Bowen integration tests certify the abandoned `> **Label:**` format.**~~
  ✅ FIXED 2026-07-15: repointed to the real consumer `parse_bowen_references_text`
  (the saved `### Concept\n> "quote"` format), un-xfailed, now passing; removed from
  `test_code_health.py::KNOWN_REDS`.
- ~~**6 vacuous (assertion-free) tests still on the allowlist.**~~ ✅ Stale: fixed
  2026-07-15 (see Test-validity audit); `KNOWN_VACUOUS` no longer exists. `test_exception_fix.py`
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

### ~~Emphasis saver doesn't sanitize `"`~~ ✅ FIXED 2026-10-11 (Q2)
The cause was the parser, not the saver: a quote with a quotation inside was cut short
when first read, and a quoted concept name was taken as the quote (one real case in 44
files). `parse_scored_emphasis_output` now reads to the line-ending closing mark.
Unlike `_format_bowen_refs` (which maps `"`→`'`), the emphasis save block writes
quotes raw, so a nested `"` inside a quote would truncate on re-parse (a P19
round-trip hazard). Ref: `extraction_pipeline.py` `extract_scored_emphasis` save block.

### ~~`_load_runtime_settings` AttributeError on valid non-dict JSON~~ ✅ Stale: fixed by review C1
Corrupt JSON resets to `{}`, but a *valid* non-dict top-level (hand-edited `[]`
or a string) would `AttributeError` on the first `.get`. Ref: `config.py` `_load_runtime_settings`.

---

## Pre-existing test failures (9 — red before the run-log work, still red)
Worth a dedicated pass; none related to the validator/estimator/Bowen fixes.

- `test_config_validation.py::test_runtime_settings_persistence` — config singleton doesn't reload across instances (SOURCE_DIR).
- ~~`test_html_generation.py::test_highlighting_logic` — highlight tuple unpack (`expected 3, got 2`).~~ ✅ FIXED 2026-07-15 (Step 2).
- ~~`tests/test_html_generator.py::` `test_generate_simple_html_page_structure`, `test_highlight_html_content_basic`, `test_highlight_html_content_exact_word_match` — HTML highlighting.~~ ✅ FIXED 2026-07-15 (Step 2): both `_highlight_html_content` and `format_ref_list` now tolerate 2-/3-tuples.
- ~~token-cap tests~~ ✅ rewritten for D5 2026-10-11.
- ~~Bowen integration (2)~~ ✅ repointed and un-xfailed 2026-07-15.

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

### Redundant Emphasis+Bowen double-run ✅ FIXED 2026-08-22
Selecting **Core** (with Include Emphasis/Bowen) *and* the standalone
**Bowen + Emphasis** stage runs both twice (wasted cost + overwrite). A workflow
choice, not a bug — a heads-up warning when both are selected would help.
Ref: `ts_gui.py` `_run_selected_stages`.
✅ `_run_selected_stages` now logs a heads-up warning (via the unit-tested
`_duplicate_bowen_emphasis` predicate) when both are selected and at least one of
Bowen/Emphasis is included in Core.

---

## ~~Step 3 — multi-agent contract audit (P19)~~ ✅ DONE 2026-07-14
Ran: 11 finders (one per LLM pipeline step) + 20 adversarial verifiers, all checked
against the real KCFC artifacts. 12 findings confirmed (see **P19 contract-audit
findings** at the top of this file, A1–A12), 8 refuted. No new API spend.
Next actionable work: the **theme-parsing cluster A1–A3** (highest impact — silently
corrupts both the abstract and summary inputs on every real transcript).
