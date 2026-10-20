# Independent review: approach and code (2026-10-19)

**Reviewed:** `main` at `28d37dd`, on Mac mini1, at the request of the davemini2 session.
**Scope:** (A) the run-blocking failure history, (B) whether the design fits Dave's quality bar,
(C) whether the code implements it correctly. Review only; no code was changed.
**Method:** six read-only reviewers ran in parallel (failure history; approach; Format code;
extraction code; gate and judge code; GUI, orchestration and config), each told to verify every
finding by reading the code path end to end. The coordinator re-checked the top findings against
the source (heading regex, topics regex, gate call sites, `GATE_BLOCKING_CHECKS`, faithfulness
warn-only, header-batch failure, emphasis drift save, speaker-prefix regex, judge settings). No
LLM/API calls were made and the pipeline was not run.

**Test suite:** `python -m pytest -q` on Python 3.11 with `requirements.txt` installed:
1835 passed, 23 skipped, 1 xfailed, 3 failed. The 3 failures are the PDF tests in
`tests/test_bundle_export.py`; WeasyPrint could not load its system libraries (Pango) on this
Mac. They are an environment gap here, not a code fault.

**Quality bar used throughout** (Dave's words): "the run doesn't fail, especially on
warnings … very good, not perfect"; "the only fail is if something WRONG vs. not quite right."
WRONG = invented facts, names, events, quotes or conclusions; content that contradicts the
source; a claim credited to the wrong person. NOT QUITE RIGHT (NQR) = fair paraphrase, real
content at the wrong point, a different but supported choice of main point.

---

## Verdict

The design is right in one part and wrong in most of the rest. The cheap deterministic checks
(an invented multi-word name, an altered quote, a broken artifact file, a formatted transcript
whose words differ from the source) catch WRONG content and broken output, and they should keep
blocking. Almost everything else treats a cosmetically or editorially different output as a
failure: one strict regex per output shape (headings, topics metadata, emphasis headers, Bowen
quotes), JSON-shape contracts, keyword-ratio scores, an LLM that validates another LLM's themes,
a coverage checklist, and a single-vote theme judge, eight of them wired into
`GATE_BLOCKING_CHECKS` with `GATE_ERROR_BLOCKS = True` and the gate re-run up to seven times per
run. The history bears this out. Of 35 run-blocking causes on record, 6 were real faults, 11 were
checks stricter than Dave's bar and 18 were bugs in the checking code itself. Runs started
failing on 2026-07-15, when a "fail closed: absence of proof of correctness blocks publication"
gate was introduced and the faithfulness judge was armed as a hard block on the day it was built.
Each later blocking rule was followed within days by runs stopping on it, and each model output
slip has been answered with one more normalizer, plan doc and test file. The fix is to remove and
simplify, not to add: keep four deterministic blockers, repair Format output instead of rejecting
it, run the gate once per run, never let an advisory stage halt a run, and stop the
normalizer-per-slip habit.

**One decision needs Dave before any of this is built (see B.0):** since today's WO change, a
WRONG prose claim (an invented quote, a reversed story, words credited to the wrong person) only
warns unless it contains an invented multi-word name. That conflicts with "the only fail is
WRONG", but the judge as built cannot tell WRONG from NQR, so making it block again would bring
back the false stops.

---

## A. Failure history

### A.1 Counts

| Class | Meaning | Count | Of which since 2026-10-08 |
|---|---|---|---|
| 1 | Real fault caught: WRONG content or a broken artifact | 6 | 5 |
| 2 | Check stricter than Dave's bar (blocked on NQR output) | 11 | 9 |
| 3 | Bug in the pipeline or in the check itself | 18 | 11 |
| | **Total blocking causes** | **35** | **25** |

By era: 3 causes before July 2026 (none about content), 7 in July–August, 25 between
2026-10-08 and 2026-10-19. Part of the October density is volume: the E2E runner did 11
three-talk runs between 10-13 and 10-15. Of the judge-flagged claims quoted in the records,
4 were WRONG and 7 were NQR (including 2 supported claims sent to the wrong chunk).

### A.2 Classified failures

| # | Date / run | Stopped at | Cause | Class | Evidence |
|---|---|---|---|---|---|
| 1 | 2026-01-11 | Structured Summary | 460 words, hard floor 600 | 2 | ADDITIONAL_FIXES_APPLIED.md:182; CHANGELOG 2026-01-11 |
| 2 | 2026-03 | Format preflight | Input size compared with the output-token cap | 3 | CHANGELOG 2026-03-10 |
| 3 | 2026-03-15 | Format validation | False mismatch explosion on TRX/Whisper-wrapped input | 3 | 25e05e1, 731f26d |
| 4 | 2026-07-17 | entity_grounding | `# Abstract\n\nIn` matched as a proper name | 3 | 5a38261 |
| 5 | same | entity_grounding | Presenter name from the filename flagged | 3 | 2959e03 |
| 6 | same | faithfulness | "In this 2021 webinar" year flagged (metadata not in judge source) | 3 | 643ad9a |
| 7 | 2026-08-22 Systems Biology | gate | YAML metadata and bold labels judged as claims | 3 | 186aa32 |
| 8 | same | faithfulness | "The environment is not incidental." (editorial framing) | 2 | 4be1271 |
| 9 | same | entity check | Presenter name flagged in abstract | 3 | 9213e93 |
| 10 | same | GUI stage 8 | Both generators re-ran the gate and failed silently | 3 | 5704526 |
| 11a | 2026-10-08 Why Families | gate faithfulness | Supported claims routed to the wrong chunk | 3 | plan_judge_routing_fix_2026-10-09 |
| 11b | same | same | Reversed Navy story; invented Georgetown claim | 1 | CHANGELOG 2026-10-09 |
| 12 | 2026-10-09 Why Families | source_fidelity | `0:33` read as `[00:33:00]` on all 21 headings (value 60× wrong) | 1 | plan_run_fixes_2026-10-09 RF.A |
| 13 | same | verbatim_quotes | Inner `"…"` written `'…'`; normalizer bug | 3 | RF.B |
| 14 | same | Blog | Blog-only stage wrote no blog | 3 | RF.C |
| 15 | 2026-10-09 | Gen Abstract ×3 | Interviewer turns counted as Q&A; prompt forced a Q&A sentence | 3 | RF.F |
| 16a | 2026-10-09 | Format | 108 of 119 differences were curly vs straight apostrophes | 3 | RF.G |
| 16b | same | Format | 7 dropped YouTube chapter-title lines | 2 | RF.H |
| 16c | same | Format | "contributor" → "perpetrator", written by Init Val auto mode | 1 | RF.G/RF.I, bc205ae |
| 17 | 2026-10-09 | Full Web/PDF | A spliced emphasis quote | 1 | RF.K, b36867a |
| 18 | 2026-10-10 | Blog faithfulness | Metaphors and the lens's own reading flagged | 2 | RF.N, c3dff3b |
| 19 | 2026-10-12 | artifact_contracts | Themes parsed to zero (model copied the prompt's list layout) | 3 | 1c0e98f |
| 20 | 2026-10-12 Kerr | faithfulness | "The interviewer observes…" on an unlabeled transcript | 2 | plan_speaker_attribution_2026-10-12 |
| 21 | 2026-10-13 | Init Val | Valid empty reply ` ```json [] ``` ` under the 50-char minimum | 3 | 6b712d9 |
| 22a | E2E run 1 | Gen Abstract ×3 | Q&A share figure the pipeline itself fed in | 3 | TODO E2E; CHANGELOG E2E1 |
| 22b | same | theme judge | Chapter author never named by the speaker | 1 | CHANGELOG E2E2 |
| 23 | E2E runs 2–3 | Bowen + Emphasis | Reply cut off at the token ceiling | 3 | E2E3, E2E6 |
| 24 | E2E run 7 | Gen Abstract ×3 | Q&A sentence built from pattern fragments | 3 | CHANGELOG AQ |
| 25 | E2E run 4 | Format + 4 publish stages | One dropped "that," in ~12,000 words | 2 | plan_run_safe_2026-10-14 |
| 26 | E2E run 6 | Format + 4 publish | Dropped "the,"; one heading `[00:01:02:04]` | 2 | same (RS.3, RS.4) |
| 27 | E2E run 7 | Format + 4 publish | Dropped "I just remember, I just" and "that" | 2 | same |
| 28 | E2E run 7 | Structured Summary | 580 and 562 words, floor 585, all 3 tries | 2 | same; SL3 |
| 29 | E2E run 8 Why Families | Overview ×3 + 4 publish | One invented Bowen quote (WRONG); "webinar-style" and a reader line (NQR); each retry rewrote the draft | 1 (+2, +3) | same (RS.6) |
| 30 | 2026-10-18 Holt interview | Structured Summary ×3 | Real remarks placed under "closes by" (NQR); prompt demanded a conclusion | 2 | judge_flag_review_2026-10-18 L4/L5 |
| 31 | 2026-10-19 Holt panel | Format (41 errors) | 40 headings `(00:00:19).` instead of `([00:00:19]).` | 2 | plan_heading_brackets_2026-10-19 |

Not counted: the "Luciano Malorni" fabrication that **shipped** in July (found by audit, never
caught by a run; the gate was built because of it); a July run that passed on 5 of 12
transcribed chunks; heading-name flags in runs 9–10 that cost revisions only.

### A.3 When checks became blocking

| Date | Commit | Decision |
|---|---|---|
| 2025-12-26 | 4f92cda | Word floors raise after retries (hard from the start) |
| 2026-03-18 | 651f16c | Run All halts on format validation, header validation, abstract generation, abstract coverage |
| 2026-04 → 06 | — | No gate work (9 commits in three months) |
| 2026-07-15 | e8f233d, d454278 | "Trust Unattended": fail closed; `release_gate.py`; entity_grounding blocking; ERROR blocks by default |
| 2026-07-15 | dadf8b1, 902a59c | `artifact_contracts.py` + `schemas/`: schema drift blocks |
| 2026-07-15 | 96449df → a8a761f | Faithfulness judge built, then armed as a hard block the same day; theme judge armed (4e7b063) |
| 2026-07-17 | 5a38261, 2959e03, 643ad9a | First three false blocks, two days later |
| 2026-08-21/22 | 5f9ac05, 64e5843, 82cdf6c | Chunked judge; `consistency` made blocking; entity check widened |
| 2026-09-23 | 6d75875, 5cabfc3 | `source_fidelity` and `verbatim_quotes` (100% coverage) blocking; heading contract checks; every raw-vs-formatted difference must be explained or reviewed |
| 2026-10-04/05 | a41a2c5, 1146599, 4eb95e4, 0a0d15a | Gen Abstract fails when no attempt is faithful; names checked in headings; topics_grounding and summary_coverage blocking |
| 2026-10-09 | 9a21c9f, 189a1d3 | Summary, blog, overview judged at generation, 3 attempts, stage fails |
| 2026-10-11 | 71e6bd5 | Majority-of-3 confirmation for a flag |
| 2026-10-14 | 59d64c8 | Soft word limits; Format restores dropped words (RS.3); revise-only-flagged retries |
| 2026-10-19 | 5122d27, 28d37dd | Faithfulness out of `GATE_BLOCKING_CHECKS` (warn only); heading brackets normalizer |

The July–October surge (277 commits) added the whole verification layer: `release_gate.py`,
`artifact_contracts.py`/`schemas/`, `faithfulness_judge.py`, theme and key-term judges,
`judge_drift_monitor.py`, `judge_recalibration.py`, `transcript_validate_consistency.py`,
`format_review.py`, `pattern_sets.py`, `quality_gates.py`, `source_completeness.py`.
`GATE_BLOCKING_CHECKS` went from one check (2026-07-15) to eight (`config.py:612`). Since
2026-10-01: 123 commits and 21 plan docs. Test files: 35 in April, 131 now.

**Answer to "it never used to have this":** correct. Before July the pipeline could stop in
three ways, none about content, and three stops are on record in six months. The stops began on
2026-07-15 with the fail-closed gate, and each new blocking rule added more. The gate has caught
real faults (an invented quote, an invented name, a spliced quote, a reversed story, a word Init
Val itself changed), but in every multi-cause run the real fault sat beside a stricter-than-bar
or buggy one, and 29 of 35 causes were not real faults.

---

## B. Approach

### B.0 Decision for Dave: what happens to a WRONG prose claim?

Built today (`release_gate.py:1293-1305`, `config.py:612`): a faithfulness flag of either
severity is a warning and publication goes on. The only automatic blocks on invented content are
`entity_grounding` (a multi-word proper name not in the source) and `verbatim_quotes` (a quote
whose words are not in the source). So an invented Bowen quote in prose, a reversed story, a
wrong number or words credited to the wrong person now publish with a warning.

The judge cannot tell WRONG from NQR well enough to block on it. The severity step (prompt ends
"If you are unsure, answer WRONG"; a first WRONG vote is final, an NQR label needs two votes)
downgraded 0 of 12 NQR flags in the authors' own calibration (`docs/calibration_judge_severity_2026-10-19.md`).
Blocking on it would bring back the stops in A.2 rows 8, 18, 20, 29 and 30.

Options:
1. **Recommended: keep warn-only, and make the warnings readable.** End each run with a short
   list of flagged claims per artifact (sentence, why, source passage) at the top of the run log
   and in the bundle, and have Dave read it before publishing. That is a human doing the one
   judgement the model cannot yet do, at the point where it costs a minute rather than a run.
2. Keep warn-only and switch the severity step off (`FAITHFULNESS_SEVERITY_MODE = "off"`); it
   only decides which sentences get revised now, and it labels nearly all of them WRONG.
3. Re-arm blocking for WRONG only after the severity step is fixed (invert the tie-break, give a
   WRONG vote the same second vote an NQR vote gets) and re-calibrated on real NQR flags, not on
   injected fabrications. This is more checking work, which is the opposite of what this review
   recommends elsewhere.

### B.1 Ranked recommendations

Ranked by how many run stops each removes, weighed against effort. Every item removes or
simplifies; none adds a check.

**1. Format: repair the output instead of rejecting it.** (Removes A.2 rows 16b, 25–27, 31 and
the next variants; code findings S2–S5.)
- Parse `## ` heading lines loosely (any dash or colon after `Section N`, `Section 01`, any
  bracket form, optional period, 1- or 2-digit hour, two-group times resolved against the raw),
  rewrite each to the canonical form, renumber 1..N.
- Take the heading time from the alignment `check_heading_timestamp_positions` already computes
  (`formatting_pipeline.py:1183`, the `allowed` set) instead of erroring.
- Restore every plain-text deletion with `format_review.restore_source_words`, regardless of
  length (drop `VALIDATION_MAX_CONTIGUOUS_RUN` for deletions; keep it for changed/inserted
  blocks, which mean paraphrase).
- Restore a word dropped at a section heading boundary to the end of the previous section; keep
  pausing only at a speaker-label boundary (the wrong side of a label is a wrong attribution).
- Left as hard stops: no headings, a section with no text, a cut-off reply, the mismatch ratio.
- Retire RF.A, RS.4 and HB1 as separate code paths; they become one function.
- Effort: about a day. Largest payoff.

**2. Shrink `GATE_BLOCKING_CHECKS` to the four deterministic checks**: `source_fidelity`,
`entity_grounding`, `artifact_contracts`, `verbatim_quotes` (`config.py:612`). Demote to WARN:
- `theme_grounding`: one LLM vote on interpretive content blocks; once flagged, two clean votes
  are needed to clear (S10).
- `summary_coverage`: blocks on bullets or two paragraphs, and on "a different but supported
  choice of main point" (S9).
- `topics_grounding`: a keyword-ratio proxy that fails a paraphrased title.
- `consistency`: blocks on an empty Bowen extraction (an omission, not a wrong statement).

With no LLM check left blocking, `GATE_ERROR_BLOCKS` can no longer turn an API outage into a
blocked, quarantined bundle (S11). Effort: one line plus test updates; WO is the template.

**3. Run the gate once per run.** Today it runs from `ts_gui.py:2399`, then again inside
`generate_webpage`, `generate_simple_webpage`, `generate_pdf` (`html_generator.py:696, 754,
801`), `package_transcript` (`packaging_pipeline.py:23`) and `export_bundle`
(`bundle_export.py:216`). Each run can call an LLM judge, so the runs can disagree, and a BLOCK on
a later run quarantines HTML written seconds earlier (S1). Run it once in the orchestrator and
pass the decision down; keep a check in the standalone CLI entry points only. Effort: small.

**4. No advisory or optional stage may halt a run.**
- `val_headers` halts on one failed API batch although its verdicts are advisory (S12).
- A PDF failure skips `simple_web`, `package` and `bundle`, which already tolerate a missing PDF (S13).
- The standalone Bowen + Emphasis stage halts where Core only warns.
- Generation stages halt on an entity flag the gate will block anyway (`extraction_pipeline.py:1519-1521, 1726-1729`).
- The theme/lens back-validation regenerates three artifacts per round and halts Core after 3 rounds, including when the validator's own reply fails to parse (S16).
- Take `val_headers` and the theme/lens back-validation out of the default run (keep the buttons). Effort: small.

**5. Structured artifacts: one lenient parser or JSON per artifact, not one strict regex.**
Topics metadata (`summary_pipeline.py:172`, duplicated at `abstract_pipeline.py:130`), emphasis
headers and Bowen quotes each have one regex, no generation-time retry, and a failure that shows
up later as a gate block (S6–S8). Themes already use JSON plus `check_reply` retry
(`extraction_pipeline.py:334-347`). Either move the other three to the same pattern, or loosen
the regexes to accept the separators the models actually produce. Stop saving an unparseable
emphasis reply under the canonical name "so the release gate will BLOCK"
(`extraction_pipeline.py:780-794`); save it as a debug file and continue without emphasis, as the
short-reply path already does. Repair the theme JSON (drop unknown keys, renumber, clamp
`nested_under`) instead of rejecting it (S20). Effort: small to medium.

**6. Cut judge spend at generation.** Since WO, the generation-time revise loop can no longer
change the publication decision. Set `GENERATION_FAITHFULNESS_ATTEMPTS` and
`ABSTRACT_MAX_ATTEMPTS` to 1 (`config.py:1205, 1208`) and the severity mode to `off`
(`config.py:712`), unless option B.0-3 is chosen. Each attempt is a chunked judge pass, three
confirmation votes per flag and one to three severity votes, across three or four artifacts.
Effort: trivial.

**7. Pre-flight checks freshness, not existence.** Re-running Format (or a review that changes
text) leaves a stale YAML. Pre-flight only checks that files exist (`ts_gui.py:2534, 2621`), so
every LLM stage runs and is paid for, then the gate blocks on "stale YAML"
(`release_gate.py:311-320`). Compare the format record's `formatted_sha256` with the YAML body and
re-run the YAML step automatically. Same for Init Val refusing to run when `_vN` files exist
(`ts_gui.py:3213-3222`): pick the latest version, as the manual path does (S14, S15). Effort: small.

**8. Stop the normalizer-per-slip habit.** Each model output variant has produced a plan doc, a
regex, tests and a CHANGELOG entry (HB1: 5 files, 324 lines, for a missing pair of brackets).
With items 1 and 5 in place, a new cosmetic variant is a one-line change to a lenient parser, not
a plan. The repo is 35k lines of Python and 131 test files for a single-user tool; most of the
recent growth is checks on checks.

### B.2 Check inventory (what can stop a run today)

| Check | Where | Effect | NQR can trigger? | Recommendation |
|---|---|---|---|---|
| Heading contract (regex, numbering, time in raw, order) | `formatting_pipeline.py:904, 1020-1106` | Halt Format, no review | Yes | Repair (B.1-1) |
| Heading time vs alignment | `formatting_pipeline.py:1128-1200` | Halt Format | Yes | Repair (B.1-1) |
| Gross limits (>10 consecutive words, >1.5%) | `formatting_pipeline.py:1288-1302` | Halt, no restore | Yes | Restore deletions; keep ratio (B.1-1) |
| Difference at heading/label boundary | `format_review.py:108-119` | Pause for a person | Yes (heading) | Restore at heading; keep pause at label |
| Format reply short / cut off / refusal | `formatting_pipeline.py:192-205` | Retry, then halt | No | Keep |
| Init Val with existing `_vN` files | `ts_gui.py:3213-3223` | Halt | No (state) | Use latest version |
| Header validation API batch failure | `transcript_validate_headers.py:277-283` | Halt run | No (transport) | Remove from default run |
| Theme JSON contract | `artifact_contracts.py:319-376` | Retry ×3, halt Core | Yes | Repair |
| Theme/lens back-validation | `extraction_pipeline.py:1787-1816, 2020-2103` | 3 rounds, halt Core | Yes | Remove from default run |
| Entity flag at generation | `extraction_pipeline.py:1519-1521, 1726-1729` | Halt stage | Rarely (fuzzy matches) | Warn; gate blocks |
| Faithfulness at generation | `extraction_pipeline.py:1431-1525, 1660-1731` | Never halts (WO) | — | 1 attempt, severity off |
| Word floors beyond ±25% | `transcript_utils.py:791-796, 972-975` | Halt stage | Rarely | Keep the reply, warn |
| Summary structure (bullets, <3 paragraphs) | `summary_validation.py:727-736` | Gate block | Yes | Repair or warn |
| Summary coverage | `release_gate.py:606-632` | Gate block | Yes | Warn |
| Topics grounding (keyword ratio) | `validation_pipeline.py:420-451` | Gate block | Yes | Warn |
| Consistency (empty Bowen refs) | `transcript_validate_consistency.py:225-229` | Gate block | Yes | Warn |
| Theme grounding (one LLM vote) | `faithfulness_judge.py:1348-1380` | Gate block | Yes | Warn |
| Entity grounding at gate | `release_gate.py:198-238` | Gate block | Mostly WRONG | **Keep** |
| Source fidelity at gate | `release_gate.py:301-335` | Gate block | No, if Format passed | **Keep**; auto-rerun YAML when stale |
| Artifact contracts at gate | `release_gate.py:717-751` | Gate block | No | **Keep** |
| Verbatim quotes | `release_gate.py:385-418` | Gate block | No (an altered quote is WRONG) | **Keep**, or drop the bad item |
| Any blocking check returning ERROR | `release_gate.py:72-83` | Gate block | No (outage) | Resolved by B.1-2 |
| Webpage validator (text differs, sections) | `transcript_validate_webpage.py` | Halt stage | No (generator bug) | Keep |

---

## C. Code findings

Impact classes: **WRONG-THROUGH** = lets WRONG content through; **STOPS-RUN** = halts a run or
blocks publication on acceptable output; **OTHER**. Confidence is about the code path; frequency
could not be measured (no real transcripts on this machine).

### C.1 Lets WRONG content through

| ID | Where | Finding and failure scenario | Conf. |
|---|---|---|---|
| W1 | `formatting_pipeline.py:841-847`, `:81-88` | Speaker labels are never compared with the source: every `**X:**` is masked in the formatted text and every speaker prefix is stripped from the raw. The prompt invites the model to name speakers from context. A label on the wrong paragraph, or the wrong name, passes Format, and the YAML states the word-level comparison passed. That is "a claim credited to the wrong person", passing with a clean record (P33). Minimum fix: warn when the raw has no labels and the output has more than one; compare the label sequence when the raw has labels. | high |
| W2 | `formatting_pipeline.py:83-87`, `format_review.py:256-263` | `strip_raw_speaker_prefixes` treats any line-leading phrase of up to 41 characters ending in a colon as a speaker label (`[A-Za-z][\w .'-]{0,40}:`). A raw line `Here is the point: the family…` loses "Here is the point"; the formatted text keeps it, so it shows up as an inserted block, and RS.3 then **deletes the speaker's real words** from the formatted transcript and records a pass. Restrict to `Speaker N`, `Unknown Speaker`, or names in the TRX `Speakers:` header (P3). | high (mechanism) |
| W3 | `extraction_pipeline.py:1551-1552`, `:1698-1702` | The abstract pre-check returns "unavailable" when either check errors, even if the entity check found an invented name; the stage then reports success without the entity re-check the summary/overview path does (`:1328-1330`, `:1515-1521`). The gate still blocks at publish, so this is a P6 status mismatch rather than a leak to publication. | high |
| W4 | `release_gate.py:1293-1305`; `config.py:612` | Policy, not a bug: WRONG prose claims without a multi-word name warn only (B.0). | high |
| W5 | `release_gate.py:432-434, 498-515` | Blog grounding adds generated lens titles to the source and drops any claim that is a substring of a lens title, so a fact invented in the lens stage and reused in the blog is excused (P7). The check is advisory, so the effect is a missing warning. Not verified: whether lenses are judged themselves. | medium |
| W6 | `format_review.py:79-88` | `review_counts` counts every log entry ever, not those for the current source and formatted text, so the YAML "N difference(s) reviewed and approved by a person" can report decisions made on an earlier version (P6). | medium |
| W7 | `extraction_pipeline.py:1561, 1695` | With the judge disabled, the abstract logs "passed faithfulness + grounding" (the summary path correctly says "unavailable"). | high, low impact |

### C.2 Stops a run on acceptable output

| ID | Where | Finding and failure scenario | Conf. |
|---|---|---|---|
| S1 | `ts_gui.py:2399`; `html_generator.py:696, 754, 801`; `packaging_pipeline.py:23`; `bundle_export.py:216`; `release_gate.py:845-878, 1759-1775` | The gate runs up to 7 times per run. `theme_grounding` re-judges with an LLM each time (a FAIL is never cached; once flagged, a PASS is not cached). The `publish_allowed` docstring calls the gate deterministic; it is not. Gate 3 (inside `generate_pdf`) can BLOCK after gate 2 allowed, and `_quarantine_stale_bundle` renames the HTML written seconds earlier to `.blocked-stale`. The GUI shows only "PDF generation failed." because those gate runs log to their own file loggers. | high |
| S2 | `formatting_pipeline.py:904-918` | `_HEADING_RE`, `_EXTRA_ZERO_TS_RE` and `_LOOSE_HEADING_TS_RE` all require the literal en dash and `\d{2}` hours. `## Section 3 - Title (00:00:19).` (hyphen), an em dash, a colon, `Section 01`, `[0:05:20]` or `(05:20)` each produce one error per heading; with more than one error RS.3 is skipped and the run halts. 28d37dd fixed brackets only; its own test `test_hb1d` pins several of these variants as "left for the validator". | high (mechanism) |
| S3 | `formatting_pipeline.py:1086, 1093-1094, 1193-1199` | A heading time a few seconds off the caption, earlier than the previous heading, or not in the raw is an error, though the code already knows the allowed values. Heading metadata, NQR. | high |
| S4 | `format_review.py:108-116`; `ts_gui.py:1866-1867` | A word dropped at the start of a new section ("So,", "And", "Now,", the very markers the prompt splits on) has a heading in the gap, so it is not restorable and the run pauses for a person. Only a speaker-label boundary needs a person. | high (mechanism) |
| S5 | `formatting_pipeline.py:1294-1301`; `config.py:1147` | A plain-text deletion over 10 words sets the gross flag, so RS.3 is never tried and the run halts asking for a paid re-run, although `apply_decisions` can restore any length. The limit predates RS.3 (P22). | high (mechanism) |
| S6 | `summary_pipeline.py:172`; `abstract_pipeline.py:130` | The topics metadata regex needs a literal `;` with text before it. Verified: `(~25% of transcript, Sections 1-5)` and `(~25%; Sections 1-5)` parse to zero topics; `Sections 1–5` (en dash) parses as `1`. Topics generation has no `check_reply`, the stage reports success, and the gate later blocks on `artifact_contracts` and `summary_coverage`. Same class as the 2026-10-19 Format halt. | high |
| S7 | `extraction_pipeline.py:780-794` | An emphasis reply over 500 characters that parses to zero items is saved under the canonical name "so the release gate will BLOCK publish". A short unparseable reply saves nothing and does not block. The same model slip costs nothing or blocks publication depending on reply length. The header regex rejects en dashes, pipes and a bold label. | high |
| S8 | `transcript_utils.py` (Bowen bold pattern, ~1500); `extraction_pipeline.py:361-387, 1042-1050` | A Bowen quote wrapped over two `> ` lines, or `**Concept** "quote"` without a colon, parses to nothing; an empty `## Bowen References` file is written and the blocking `consistency` check fails when the transcript names Bowen. No retry. | medium-high |
| S9 | `summary_validation.py:727-736, 784-788` | A summary with a bullet list, a "Section N" reference, or fewer than three paragraphs is a stored FAIL that blocks publication. | high |
| S10 | `faithfulness_judge.py:1348-1380`; `release_gate.py:861-878, 1515-1525` | The theme judge makes one call; one "ungrounded" label blocks publication, with no confirmation or severity step. Once a theme is flagged, two consecutive PASS votes are needed to clear it. Any theme field not in the label lists is judged as a claim. | high |
| S11 | `release_gate.py:81, 96-105, 620-626`; `config.py:615` | Any blocking check that returns ERROR blocks: no API key, an outage longer than the retry window, two unparseable judge replies, or a stale summary verdict whose in-gate re-validation raises. On BLOCK the previously allowed bundle is quarantined (P1). | high |
| S12 | `transcript_validate_headers.py:277-283`; `ts_gui.py:2069-2077` | One failed API batch makes header validation return False and the run halts, skipping 12 stages, though the verdicts are advisory (P1). | high |
| S13 | `ts_gui.py:2365-2371` | A PDF failure (WeasyPrint missing or crashing) halts the run, so simple web, package and bundle never run; `package_transcript` already handles a missing PDF (`packaging_pipeline.py:54`). | high |
| S14 | `ts_gui.py:2534, 2621`; `release_gate.py:311-320`; `ts_gui.py:2019` | Pre-flight checks that files exist, not that they are current. After a Format re-run or a review that changes text, every LLM stage runs, then the gate blocks on a stale YAML (P8). | high |
| S15 | `ts_gui.py:3213-3222, 2267-2276` | Init Val auto mode refuses to run if `_vN` files exist; Format refuses a file without `_validated` in its name. A full re-run with the default selection halts at step 0 after any earlier failure (P8). | high |
| S16 | `extraction_pipeline.py:1806-1815, 2053-2103` | An unparseable theme/lens validator reply marks both theme sets invalid; three rounds regenerate them and then fail Core, abandoning themes, topics, key terms and abstract already paid for (P1). | medium |
| S17 | `transcript_utils.py:791-796, 972-975`; `extraction_pipeline.py:1463-1465, 1685-1686` | Soft word limits become hard beyond ±25% (an overview under 600 words three times); a hard miss on attempt 1 fails the stage. | high (path), low (frequency) |
| S18 | `transcript_utils.py:962-965` | `TruncatedResponseError` and `RefusalError` are never retried, on the ground that the request is deterministic; with sampling it is not. | medium (path), low (frequency) |
| S19 | `release_gate.py:321-326` | No raw-source copy and no matching `.txt` in source/processed is an ERROR that blocks; an older project whose source file moved cannot publish. | high |
| S20 | `artifact_contracts.py:319-376`; `extraction_pipeline.py:338-347` | Theme JSON with an extra field or numbering 0..N-1 is retried, then halts Core, instead of being repaired. | high |

### C.3 Other

| ID | Where | Finding | Conf. |
|---|---|---|---|
| O1 | `ts_gui.py:2779` | Stage success is the runner's return value; `STAGE_OUTPUTS` (`:187`) is never checked after a stage, so a stage that returns True without its output file is reported complete (P6). About six lines to fix. | medium |
| O2 | `html_generator.py:692, 750, 797` | Gate warnings and block reasons from the in-generator gate runs go to `logs/generate_*.log`, not the GUI log (P2). | high |
| O3 | `formatting_pipeline.py:1515-1518` | When `validate_format` raises, it returns False without writing a record; the review-only check then reads the previous run's record (P8). | medium |
| O4 | `faithfulness_judge.py:12`, `:1064` | Docstrings still say a judge error blocks publication and that the step fails a run on WRONG content; both are false since WO (rule 13). | high |
| O5 | `config.py` | 22 settings no non-test module reads (e.g. `KEY_TERMS_JUDGE_ENABLED`, `VALIDATION_MODEL`, `THEME_ARTIFACT_SUFFIXES`, which duplicates `release_gate._THEME_KIND`). Editorial lists kept in Python rather than data files: `EVALUATIVE_TERMS`, `SCAFFOLDING_HEADING_PHRASES`, `BOWEN_CONCEPT_LABELS`, `THEME_SCAFFOLDING_LABELS`, `FAITHFULNESS_GENERIC_HEADINGS`, `LENS_STOPWORDS`, `QUOTE_FILLER_WORDS`, `STUTTER_ALWAYS_REVIEW`, `ABSTRACT_CONCLUSION_PATTERNS`, `REVISE_PREAMBLE_STARTS`, `ABSTRACT_QA_NOTE_MARKERS` and others. The name lists already live in `data/`. | high |
| O6 | `uv.lock`; `tests/test_client_factory_r5.py:14` | The committed `uv.lock` (last changed 2026-01-03) pins only `ruff`, so `uv sync` installs the newest versions of every runtime dependency (anthropic 1.15.0 here) instead of the pins in `requirements.txt`. Under that install, `tests/test_client_factory_r5.py` fails to import `httpx`, which it imports directly but no dependency file declares. CI uses `requirements.txt`, so CI is not affected. Regenerate the lock or delete it; declare `httpx` if tests import it. | high |
| O7 | `summary_pipeline.py:811-825`; `abstract_pipeline.py:529-541` | These two LLM callers pass no timeout (600 s fallback); their siblings use 900 s (P5). | high, low impact |
| O8 | `transcript_utils.py:2671` | `delete_logs` calls `unlink()` unguarded; one locked file aborts the rest. `archive_logs` handles the same case. | high, low impact |
| O9 | `extraction_pipeline.py:2245, 2312`; `summary_pipeline.py:803-804` | With `revise` supplied by every caller, the "regenerate with feedback" branch never runs; docstrings still describe it. | high, low impact |

### C.4 Checked and found sound

- RS.3 restore checks both SHA-256 hashes before writing (`format_review.py:146-151`).
- Fuzzy "corrections" are not auto-accepted; RS.3 restores them.
- A held near-miss reply is kept when a later try fails outright (`transcript_utils.py:1116-1126`).
- Revisions are judged whole from the file on disk; an echoing draft can never become "best".
- No transcript truncation before the LLM; output caps follow the model's own limit.
- The judge disk cache serves only PASS verdicts and keys on artifact, source, model, prompt and
  the code of ~50 routing functions; no stale-PASS replay was found.
- Judge reply parsing fails closed and never defaults to a pass label.

---

## Not covered

- No end-to-end run and no API calls. Frequencies are inferred from code and from the repo's
  own run records, not measured. Cost figures are counts of call sites, not spend.
- Init Val correction logic (`transcript_initial_validation*.py`), blog lens selection, PDF and
  DOCX generation internals, `pattern_sets.py` internals, `quality_gates.py`/`mut_harness.py`
  (test-suite gates, not runtime gates), schema JSON contents, calibration scripts and gold sets
  (their reported numbers were taken as the authors' claims and checked only against the code
  paths they describe).
- Whether the webpage validator's "text differs" check has its own false positives.
- `logs/` from real runs (not on this machine).
- The 3 PDF tests that need WeasyPrint's system libraries were not run successfully here.
