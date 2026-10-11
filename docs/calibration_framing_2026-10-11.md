# Calibration — narrowed framing rule (TF.3–TF.5, 2026-10-11)

Plan: `docs/plan_judge_framing_2026-10-11.md`. Model: claude-sonnet-5-5, default effort.
**Outcome: not shipped (decision 2026-10-11).** Main keeps the prompt from before this
work (sha 96e5ab257296, `JUDGE_LOGIC_VERSION` 2026-10-10). Four versions were built on the
local branch `judge-framing` (archive); every version scored well on the gold set, but the
general version (v4) caused more false failures on real overviews and summaries than the
current prompt. The evidence files were copied to main.

## Versions

| | Rule (1) — unsupported framing | Prompt examples | Gold set |
|---|---|---|---|
| v1 | claims about a theory, field or world the speaker does not make | paraphrased k6 and tf_u1 (sweep finding) | 51 cases |
| v2 | same | unrelated subject (treaty, historians); tests enforce it | 51 (k4 relabelled entailed) |
| v3 (B) | the **writer's own** such claims; a claim attributed to the speaker is judged by the ordinary rules — worded around "an answer to an interviewer's question that names something as important or best" (sweep: fitted to the Kerr sentence it was measured on) | as v2 | 50 (k4 removed: ambiguous) |
| v4 | as v3, attribution rule general ("entailed" when a fair paraphrase, "unsupported" when the speaker did not say it) | entailed example also moved to an unrelated subject; tests cover every example | 53 (+ tf_u5–u7: attributed importance claims the speaker never makes) |

## Gold set (3 runs each)

| | Recall | Precision | Notes | Cost | File |
|---|---|---|---|---|---|
| Before (2026-10-10, 43 cases) | 0.91–0.95 | 1.00 | k6 missed 3/3 | — | `2026-10-10_sonnet55_default.json` |
| v1 (labels as of the run) | 0.96 ×3 | 0.96, 1.00, 1.00 | k4 missed 3/3; e13 flagged once | $1.52 | `2026-10-11_sonnet55_framing.json` |
| v1, k4 relabelled (post-hoc, same verdicts) | 1.00 ×3 | 0.96, 1.00, 1.00 | recomputed, no new run | — | — |
| v2 (k4 entailed) | 1.00 ×3 | 0.96 ×3 | k4 flagged 3/3 (verdict depends on prompt wording) | $1.49 | `2026-10-11_sonnet55_framing_v2.json` |
| v3 (B), k4 removed | 1.00 ×3 | 1.00, 1.00, 0.96 | e13 flagged once | $1.53 | `2026-10-11_sonnet55_framing_v3.json` |
| v4, 53 cases | 1.00 ×3 | 1.00 ×3 | no flips; tf_u5–u7 caught 3/3 | $0.67 | `2026-10-11_sonnet55_framing_v4.json` (records prompt sha) |

v3: k6, tf_u1–tf_u4, k5 and us7 ("Kerr concludes … definitively proven", attributed but
overstated) caught 3/3; tf_e1–tf_e4, ef1, ef2 accepted 3/3; real abstracts 3/3
(roots_bowen PASS, where_roots FAIL naming Malorni, dave_g FAIL naming nubbin); injected
fabrication caught; themes 1.00/1.00.

## Real project — Kerr 2026-09-13, the files that passed on 2026-10-10

`release_gate.check_faithfulness` (transcript + filename metadata, as in a real run), fresh
cache per check. Files and sha256 in `2026-10-11_framing_tf5_topicterm/k10_*.json`.

| Prompt | Failed checks | Flagged sentences (all supported by the source) |
|---|---|---|
| Before (current main) | **5 of 10** | "Michael Kerr calls a multigenerational perspective the best entry point." ×5 (the interviewer asks for the best entry point; Kerr answers "extremely important") |
| v3 (B) | 2 of 10 | "…societal regression, a concept Bowen introduced in 1975." ×2 (the interviewer: "in 1975 he said … He called it societal regression") — the drop from 5/10 came from wording fitted to the "best entry point" sentence |
| **v4** | **7 of 10** | "best entry point" ×3; "It links chronic anxiety to chronic inflammation and physical illness." ×2; "Years later he stood at Billy's grave and said, 'Billy, thank you for allowing me to grow up.'" ×2 (verbatim in the transcript) |

Earlier 3-check samples (`tt_*.json`): before 1/3, v2 2/3, v3 2/3 — too small to separate.
The flags under both prompts are random false positives; `docs/plan_judge_confirm_flags_2026-10-11.md`
addresses them. Cost of the 20 checks: ~$1.70.

## Held-out talks (did not shape the prompt) — v4 vs current, 3 runs each

Overviews and summaries of the Societal, Systems Biology and Where Roots fixture talks,
judged as the gate does (transcript + filename metadata), no cache
(`2026-10-11_framing_tf5_topicterm/ho_old.json`, `ho_v4.json`; $0.81 + $0.83). These are
older drafts that fail under both prompts; the comparison is the number of flags.
- Systems Biology overview: flags per run 5, 1, 3 (current) → **7, 9, 8 (v4)**. New in
  every v4 run: "Michael Kerr argues that systems biology is independently arriving at
  principles long central to Bowen Family Systems theory…" (the talk's own thesis) and
  "Both fields are arriving at the same core insight independently."; in 2 of 3 runs the
  reader-benefit sentence "For readers familiar with Bowen Family Systems theory, this
  lecture offers evidence…", which the rule is meant to accept.
- The other three artifacts: similar counts under both prompts.

## Real prose (prose_real, all 4 talks; harness = transcript only)

`judge_recalibration.py --prose-real` gives the judge the transcript without the filename
metadata, so claims naming the talk's date or year are over-reported; the real gate adds the
metadata, and re-judged that way those flags disappear (`2026-10-11_framing_gate_path.json`).
v1 vs before: 30 entailed → unsupported, 2 unsupported/contradicted → entailed (one
Societal abstract claim, now accepted; one Systems Biology blog claim). Examples the rule is
meant to catch, from summaries: "Understanding this dynamic requires grasping the
distinction between acute and chronic anxiety."; "This paradox—that freedom runs through
the source of constraint—defines the difficulty of genuine change."

## Topic / key-term check (advisory) — 3 checks each

| Prompt | Societal | Systems Biology | Where Roots |
|---|---|---|---|
| Before | PASS 3/3 | PASS 3/3 | FAIL 3/3 |
| v2 | FAIL 3/3 | PASS 3/3 | FAIL 3/3 |
| v3 (B) | FAIL 2/3 | PASS 3/3 | FAIL 3/3 |

The Societal flags are topic descriptions and key-term definitions; the check is advisory
(not in `GATE_BLOCKING_CHECKS`), so this is more warnings, not blocks.

## Decisions (2026-10-11)

TD1 both, refined (reader-benefit statements stay entailed); TD2 yes; TD3 8 labels approved;
TD4 keep → option B → v4 (3 more labels approved) → **don't ship**: v4 is the version
without fitted wording, and on real writing it fails more good text than the current
prompt (Kerr 7/10 vs 5/10; held-out Systems Biology overview 8 flags per run vs 3). k6
stays a known gap.

## Lesson
The gold set rewards strictness, so every version scored 0.96–1.00 there; only repeated
fresh checks on real writing that did not shape the prompt showed the precision cost.
Twice the prompt's wording was fitted to the cases it was measured on (examples mirroring
gold cases; a carve-out describing the one failing Kerr sentence). See LEARNINGS.md.

## Adjacent issues found, not fixed
- `judge_recalibration.py --prose-real` omits the filename metadata the gate includes.
- The prompt example "attributes recovery to medication" (since 2026-07-15) paraphrases
  gold us6; below the new overlap threshold (3 of 7 words) but worth replacing.
- A cached false FAIL is replayed on gate re-runs of unchanged files (see the CF plan).

Total cost of the framing work: about $14.70.
