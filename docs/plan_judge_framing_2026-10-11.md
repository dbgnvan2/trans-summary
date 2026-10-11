# Plan: tighten the faithfulness judge on the writer's own framing (TF.1–TF.6)

Status: **TF.1 + TF.2 built on local branch `judge-framing` (`99568fd`, not on main);
awaiting TD3 (gold labels) before the live runs.** TD1 = both, refined (below); TD2 = yes.
Request 2026-10-11: option 3 of the independent-reviewer result ("put the effort on the
Claude side").

## Why

- Sonnet 5.5 consistently accepts one class of gold case: k6, "This distinction is
  central to Bowen theory's explanation of how family dysfunction persists." (gold label
  unsupported, D1 2026-10-10). It also accepts k4 in 1 of 3 runs ("Kerr, anxious about
  her speed, took over"; she handed him the helm).
- This is not a model failure. The prompt (`faithfulness_judge._JUDGE_INSTRUCTIONS`,
  "EDITORIAL / RHETORICAL FRAMING IS 'entailed'") tells the judge that framing which adds
  no new specific is entailed, and one of its own examples, "That kind of reckoning is
  rare in science.", is the same kind of sentence as k6. The prompt and the D1 labels
  disagree.
- The rule was added on 2026-08-22 (`4be1271`) because the judge false-BLOCKED blog and
  overview rhetoric. Since RF.N the blog has its own advisory check (stage 2 accepts
  grounded interpretation), so the blocking cost of a stricter rule now falls on the
  **overview, summary and abstract** (the faithfulness check blocks).
- The 2026-10-10 calibration lists 45 real-prose claims that 4.6 rejected and 5.5 accepts
  (30 blog, 12 overview, 2 summary, 1 abstract). These are the sentences this change will
  move, and the check in TF.4 is built on them.

## The change (prompt only; no code path, model, threshold or blocking status changes)

Narrow the framing exemption instead of removing it:

- **Still entailed** — emphasis or restatement of a point the speaker makes:
  "The environment is not incidental."; "It was a logical approach, and it produced
  genuine discoveries."; "They are looking at the parts when the explanation lives in
  the pattern."
- **Still entailed (TD1 refine, 2026-10-11)** — a sentence about what the material
  offers the reader (who it helps, what a reader who understands it sees or does
  differently) when it follows from content the speaker gave. The overview prompt
  requires this in "Why does this matter?" (`prompts/Transcript Summary Overview Post
  v1.md:114`); rejecting it would fail every overview.
- **Unsupported (new, TD1a)** — a sentence that states the *status, importance or role*
  of an idea within a theory or field ("central to Bowen theory's explanation of …",
  "the key mechanism", "Bowen's most important insight"), or a generalization about a
  field or the world beyond the talk, when the speaker does not say it.
- **Unsupported (new, TD1b)** — a sentence that changes *who did what*, or adds a motive
  or feeling the source does not give (k4: "anxious about her speed, took over" when she
  handed him the helm).
- The example "That kind of reckoning is rare in science." leaves the entailed list
  (TD2); it is gold case tf_u1, so it is not used as a prompt example.
- Prompt examples are never gold cases (test `test_tf1_prompt_does_not_quote_gold_claims`),
  so calibration measures the rule, not recall of the examples.

## Acceptance criteria → tests

- **TF.1 Prompt states the narrowed rule** — the instructions contain the three bullets
  above and no longer list "That kind of reckoning is rare in science." as entailed; the
  judge cache does not reuse old verdicts (`_judge_logic_version` hashes the prompt;
  `JUDGE_LOGIC_VERSION` bumped to 2026-10-11).
  - Tests (offline): `tests/test_judge_framing_tf.py::test_tf1_prompt_has_narrowed_rule`,
    `test_tf1_logic_version_changes`.
- **TF.2 Gold cases for the rule** — add 8 cases from the public prose_real talks, taken
  from the 45-claim list: 4 status/importance/generalization sentences (unsupported) and
  4 emphasis/restatement sentences (entailed). Labels proposed by me, approved by you
  before the live run (TD3), as with D1.
  - Test (offline): `test_tf2_gold_has_framing_cases` (cases present, sources public,
    both labels represented).
- **TF.3 Calibration on Sonnet 5.5 (live, 3 runs)** — `judge_recalibration.py` as on
  2026-10-10: gold recall ≥ 0.90 / precision ≥ 0.70; k6 and the 4 new unsupported
  framing cases caught in 3/3 runs; ef1, ef2 and the 4 new entailed cases accepted in
  3/3 runs; real abstracts unchanged (roots_bowen PASS, where_roots FAIL naming Malorni,
  dave_g FAIL naming nubbin); injected fabrication caught; theme gold unchanged
  (the theme prompt does not change).
  - Output: `docs/calibration/2026-10-11_sonnet55_framing.json`.
- **TF.4 Real prose: what would now block** — every claim in the 12 prose_real
  abstracts, summaries and overviews (and the 3 blogs, for information; the blog is
  advisory) is judged with the new prompt. The report lists every verdict that changes,
  and every artifact whose status changes PASS → FAIL. You review the list (TD4); this
  is the human-review criterion and is not code-testable.
  - Output: `docs/calibration_framing_2026-10-11.md`.
- **TF.5 Kerr check** — the current Kerr 2026-09-13 summary and overview judged with the
  new prompt; result reported (would the run still publish).
- **TF.6 Record** — CHANGELOG; `docs/calibration_framing_2026-10-11.md` with numbers,
  changed verdicts and cost; memory note updated; full suite green; learning-qa sweep
  before landing.

## Decisions for you

- **TD1** — which framing becomes unsupported: (a) status/importance/role claims and
  generalizations beyond the talk; (b) changed actor or added motive (k4). Proposed:
  both.
- **TD2** — "That kind of reckoning is rare in science." becomes unsupported. Proposed:
  yes (it is the k6 kind of sentence).
- **TD3** — you approve the 8 new gold labels before the live run.
- **TD4** — stop rule: if TF.4 shows overviews/summaries you consider fine now failing,
  we keep the current prompt (revert) or narrow further. You decide on the list.

## Order

TF.1 + TF.2 offline tests first → write prompt change → propose 8 gold labels → **your
approval of labels** → TF.3 live (3 runs, ~$2) → TF.4/TF.5 live (~$1–2) → report to you
→ **your decision (TD4)** → TF.6, sweep, commit, push. Nothing reaches main before TD4.

## Risks

- More overview/summary claims flagged → more regeneration attempts (RF.J loop, up to 3)
  and possible blocks on runs that publish today. TF.4/TF.5 measure this before it lands.
- The blog's stage 1 uses the same judge: more blog claims go to stage 2 (theme judge),
  so a little more cost; the blog stays advisory.
- Sonnet 5.5 takes no temperature, so verdicts vary between runs; TF.3 uses 3 runs.

## Adjacent issues found, not fixed

- The judge prompt is one text for every artifact type; it cannot be stricter on the
  summary than on the blog. A per-artifact rule would need a code change (not proposed).
