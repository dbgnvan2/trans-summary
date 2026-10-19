# Plan and record: faithfulness flags warn, never block (WO0–WO7) — 2026-10-19

Status: **built 2026-10-19.** Supersedes `docs/plan_severity_downgrade_2026-10-19.md`
(NQ, not built).

## Decision (WO0)

The user, 2026-10-19, after the JS6 calibration (`docs/calibration_judge_severity_2026-10-19.md`)
showed that most flags are minor and that the severity step downgraded almost none of
them:

> "Warn only, never block. Add the no-outside-facts rule to all prose prompts, show the
> % score with the flagged claims as warnings, and drop the pending plan. Build it here."

What the 29 hand-labelled JS6 flags were: 17 wording, framing or order; 6 outside facts
the summary added (an abbreviation spelled out, an age, a first name, "late
grandmother"); 4 credited the wrong person; 1 called a conversation a webinar; 1
reversed what happened (C4).

What still blocks: every other check in `config.GATE_BLOCKING_CHECKS`, among them the
entity check (a name not in the source) and the theme judge (`theme_grounding`).

## Criteria

| ID | Criterion | Test |
|---|---|---|
| WO1 | The summary, abstract, overview and blog prompts carry a no-outside-facts rule: no abbreviation spelled out that the transcript does not spell out; no first name, age, place, occupation, affiliation or family fact the transcript does not state. The rule is in the summary prompt sent to the model. | `tests/test_faithfulness_warn_only_wo.py::test_wo1_prose_prompts_forbid_outside_facts`, `::test_wo1_rule_is_in_the_summary_prompt_sent` |
| WO2 | `faithfulness` is not in `config.GATE_BLOCKING_CHECKS`. `release_gate.check_faithfulness` returns WARN for any flagged claim (WRONG or NOT QUITE RIGHT), with the claims in `items`; a judge ERROR does not block. The entity check still blocks. | `::test_wo2_wrong_claim_warns_and_gate_allows`, `::test_wo2_judge_error_does_not_block`, `::test_wo2_error_detail_does_not_state_the_policy`, `::test_wo2_entity_check_still_blocks`; updated `tests/test_release_gate.py::test_wo2_m2_faithfulness_flag_warns_and_publishes`, `::test_r8d_zero_claims_artifact_is_unverified`, `tests/test_validator_gating_r15.py::test_r15d_blocking_checks_and_judges_armed` |
| WO3 | The verdict detail gives each judged artifact's score, "summary 90% (27 of 30 claims supported)", where a supported claim is one with no confirmed flag; `items` holds the numbers. A cached PASS keeps its claim count (`claims_judged`); `JUDGE_LOGIC_VERSION` is bumped so older entries without it are not served. An unknown count is never shown as a %. | `::test_wo3_score_in_detail_and_items`, `::test_wo3_pass_shows_score`, `::test_wo3_unknown_count_is_not_shown_as_a_score`, `::test_wo3_cached_pass_keeps_its_claim_count`, `::test_wo3_logic_version_bumped` |
| WO4 | Generation still revises flagged claims up to `GENERATION_FAITHFULNESS_ATTEMPTS` (summary, overview) or `ABSTRACT_MAX_ATTEMPTS` (abstract). When no attempt is clean it keeps the best draft, logs a warning and the stage succeeds, unless the kept draft has a name the gate's entity check would block on (or that check cannot run): then the stage fails as before. | `::test_wo4_summary_kept_with_flags_stage_succeeds`, `::test_wo4_summary_kept_with_name_stage_fails`, `::test_wo4_entity_check_error_still_fails_stage`; abstract: `tests/test_abstract_faithful_retry.py::test_wo4_abstract_kept_with_flags_stage_succeeds`, `::test_wo4_abstract_kept_with_name_stage_fails`, `::test_wo4_abstract_precheck_names_scoped_to_abstract` (the abstract's name check covers the abstract only, as its faithfulness check does) |
| WO5 | `release_gate.run_gate` logs every verdict that is not a PASS and does not block (a WARN; a FAIL of a check that does not block; an ERROR, tagged UNVERIFIED), and under the faithfulness one each flagged claim, marked wrong or not quite right. Every caller gets the lines: the GUI (through its logger, once each), html_generator, packaging, bundle export and the CLI. Before, run_gate logged only blockers and advisory ERRORs, so a faithfulness WARN and its claims reached only the run manifest. | `::test_wo5_gui_lists_flagged_claims_on_allow`, `::test_wo5_run_gate_logs_flagged_claims_for_every_caller`, `::test_wo5_gui_log_shows_flagged_claims_once`, `::test_wo5_blockers_are_not_listed_as_warnings`; `tests/test_run_fixes_rf.py::test_it3h_gate_warnings_logged_on_allow`, `tests/test_gate_observability.py::test_m8_gate_surfaces_nonblocking_error` |
| WO6 | Live check, not in CI: the 12 JS6 summary drafts (6 talks × 2, part d of `docs/calibration/2026-10-19_judge_severity/measure_severity.py`) made again with the new summary prompt, judged as in JS6. Results under `docs/calibration/2026-10-19_outside_facts/`. | Script + the section below |
| WO7 | Documents updated in the same commit. | Review of the diff |

## WO6 — live check of the summary prompt

Run 2026-10-19: the 12 JS6 drafts (6 talks × 2) made again with the new summary prompt
and judged as in JS6 (judge, confirmation, severity step). Same transcripts in both runs
(sha checked). Cost $1.83. Files in `docs/calibration/2026-10-19_outside_facts/`:
`results.json` and `results.log` (the run), `blind_flags.md` (the flags),
`compare.py` → `compare.json` (the counts below), `outside_fact_hits.py` →
`outside_fact_hits.txt` (each outside-fact text hit, checked against the transcript).

| | Old prompt (JS6) | New prompt |
|---|---|---|
| Confirmed flags | 22 in 333 claims | 9 in 347 claims |
| Claims supported | 93% | 97% |
| Drafts with a flag | 9 of 12 | 5 of 12 |

Per draft, the score ranged from 84% to 100% before and from 89% to 100% after.
Each run made one draft per slot, so part of the drop can be run-to-run variation.

**The 9 new flags, checked by hand against the transcripts:**

| Flag | Talk | What the claim does | Kind |
|---|---|---|---|
| D1 | Jan #1 | Says Bertoloso draws on Waddington. The transcript shows a Waddington quote on one slide and her idea ("organized … organizers of molecular systems") on another, with no link between them. | Linked to the wrong person |
| D2 | Jan #2 | "Marta Bertoloso". The transcript has "Bertoloso", "Bartoloso" and, from a participant, "Maria Bertoloso". | Outside fact (first name) |
| D3 | Mar #2 | Says the session "centers on" the question of what threats generate anxiety. The speaker raises it once ("the search was, what are the threats that generate anxiety?"). | Framing |
| D4 | Mar #2 | "Several times" and "visibly registers". The transcript: "I repeated it a couple of times" and "she heard herself saying that". | Wording |
| D5 | Mar #2 | Gives the presenter a remark made by a participant, Randy ("people who haven't been trained up … in the individual model"). | Credited the wrong person |
| D6 | April #1 | Says the presenter "closes by" saying Bowen's point on unmarried couples "may ultimately determine the outcome for this pair". He quotes Bowen in the Q&A ("it's easier to leave than stay") and makes no prediction. | Framing, inference added |
| D7 | April #2 | "In her late thirties". No age is given; Vermont, counselor and the sister 13 years older are in the transcript. | Outside fact (age) |
| D8 | April #2 | "Parents' anxious focus … likely amplified the family projection process". The transcript: being born with no stomach "probably accentuated the family projection process". | Wording |
| D9 | April #2 | "Neither partner is motivated" to engage the extended family. The transcript: "if either one would be motivated to deal with a larger family, that could make a difference". | A condition stated as a fact |

So 2 of the 9 are outside facts, 2 credit or link the wrong person, and 5 are wording,
framing or a condition stated as a fact. None says the opposite of what happened.

**Outside facts by text search** (`outside_fact_hits.txt`; a hit counts only when the
text is not in that talk's transcript):

| Outside fact | Old drafts | New drafts |
|---|---|---|
| "KCFC" spelled out as "Kansas City Family Center" | 3 | 0 |
| An age not in the transcript ("late thirties") | 2 | 1 |
| "late grandmother" | 1 | 0 |
| The first name "Marta" (not in the Roots or Jan transcripts) | 4 | 3 |

The rule cut these from 10 to 4 but did not remove them. The judge did not flag "Marta
Bertolaso" in either Roots draft, in either run; it flagged 1 of the 4 old and 1 of the
3 new.

Not measured: the abstract, overview and blog prompts got the same rule.

## Not changed

- The severity step (JS) still runs (`FAITHFULNESS_SEVERITY_MODE = "majority3"`). It now
  only labels each flag wrong or not quite right in the warnings and decides which
  claims generation revises. In JS6 it labelled nearly every flag wrong.
