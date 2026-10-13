# Speaker attribution without labels (SA) and FAQ answers (FQ) — 2026-10-12

Plan: `docs/plan_speaker_attribution_2026-10-12.md`. Judge: claude-sonnet-5-5 with
confirmation (CF). Data and scripts: `docs/calibration/2026-10-12_speaker_attribution/`.

## What changed

- **SA.** A transcript with no speaker labels gets a note in the judge's source
  (`config.UNLABELED_SPEAKERS_NOTE`). For such a source only, the judge prompt gains a
  SPEAKER ATTRIBUTION rule (`faithfulness_judge._SPEAKER_RULE`, added by
  `instructions_for`). The rule accepts a claim that a participant in the conversation
  said grounded content, when the source does not show who said it. It does not
  accept:
  - a role the recording doesn't have;
  - content that is not in the source;
  - a reversed stance.

  A labelled transcript is judged with exactly the old prompt.
- **FQ.** The first sentence under a question heading (FAQ entries, question-style
  section titles) is judged with its question attached
  ("According to Michael Kerr, it does not. [in answer to: Does moving away from my
  family solve the problem?]"). Before, the question heading was removed as layout, so
  the judge saw the sentence alone.

`JUDGE_LOGIC_VERSION` is 2026-10-12e.

## Arms (same day, same harness)

- **old:** the HEAD prompt, HEAD claim extraction, and metadata without the note. This is
  the gate before this change.
- **always-on rule** (`always_on_rule/`, not shipped): every source got the rule. No FQ.
- **rule in windows** (`rule_in_windows/`, not shipped): the rule only with the note,
  plus the first FQ version; chunk windows also got the rule.
- **final** (top-level files): the rule only with the note, and only on full-source
  calls (chunk windows use the base prompt); FQ with in-text markers and the name-check
  fix.

The harness now builds gold sources the way the gate does, with metadata and the note
(`judge_recalibration.gold_sources`). Five SA gold cases were added (48 cases):
- sa1, sa2: interviewer remarks in the unlabeled Kerr transcript, entailed;
- sa3: a reversed stance (Kerr said to hold the "schizophrenogenic mother" view the
  source says Bowen rejected), contradicted;
- sa4: "the interviewer" in a lecture with no interviewer, unsupported;
- sa5: a reversed causal stance, contradicted.

## Results

| | old | always-on rule | rule in windows | final |
|---|---|---|---|---|
| Gold recall (3 runs) | 0.88, 0.96, 0.96 | 0.96 ×3 | 0.96 ×3 | 0.96 ×3 |
| Gold precision | 1.00, 0.96, 1.00 | 1.00 ×3 | 1.00 ×3 | 1.00 ×3 |
| SA cases sa1–sa5 | all correct ×3 | all correct ×3 | all correct ×3 | all correct ×3 |
| Themes precision (recall 1.00 in all) | 1.00, 0.87, 0.93 | 1.00, 1.00, 0.93 | 1.00 ×3 | 0.93, 1.00, 1.00 |
| Real abstracts / injected fabrication | 3/3, caught ×3 | same | same | same |
| Real prose not entailed, of 602 (3 runs) | 39, 49, 47 (mean 45) | 48, 48, 54 (50) | 50, 41, 43 (44.7) | 52, 47, 44 (47.7) |
| Where Roots blog (labelled) not entailed | 12, 21, 14 | 22, 21, 19 | 18, 18, 17 | 19, 19, 19 |
| Kerr 2026-09-13 summary, 10 whole-artifact checks | 10 PASS | 10 PASS | 9 PASS, 1 FAIL | 7 PASS, 3 FAIL |
| Kerr overview, 10 checks | 9 PASS, 1 FAIL | 9 PASS, 1 FAIL | 10 PASS | 10 PASS |
| "According to Michael Kerr, it does not." first-pass flags | 8/10 | 9/10 | 0/10 | 0/10 |

Notes:
- **The remaining gold miss is k6 in every arm.** It is the known framing gap (TODO, k6).
- **Real prose is within run-to-run variance.**
  - The Where Roots blog gets exactly the old prompt and the same claims in the final
    arm (labelled transcript, no question headings tagged), yet it ranged from 12 to 21
    across arms. So the always-on arm's 19–22 can't be separated from noise either.
  - The conditional rule was kept because it leaves labelled transcripts unchanged by
    construction.
  - FQ tags 36 claims per run in real prose. 1 is flagged, a Systems Biology overview
    sentence about Mena Bissell, which the old arm also flagged.
- **The overview block is fixed by FQ.** The first-pass flag on "it does not" went
  from 17 of 20 runs to 0 of 20.
- **The final arm's 3 Kerr summary FAILs are a real error.** All three were on "Years
  earlier, when his mother told him, 'I love you, but I love Billy the most,' he
  answered, 'Thank you.'"
  - The source says "Years later, she said to me…", after the graveside passage that
    the summary's sentence follows. "Years earlier" contradicts it.
  - The other arms missed it in all 30 checks. The summary was regenerated tonight and
    needs regenerating again.
- **Kerr's interviewer sentences were never flagged.** None of the three "The
  interviewer …" sentences was flagged in 40 whole-artifact checks, in any arm.
  Judged one by one (`targeted.json`), the old prompt also entailed all five role
  sentences 5/5. The publish-time FAIL on such a sentence (17:44) was a rare event. SA
  makes the accepted behaviour explicit, but this sample can't show a lower failure
  rate.
- **Labelled-copy control (`targeted.json`, run with the first always-on wording).**
  The older, labelled copy of the same talk marks U1 and U5 as said by Kerr; U2 is in
  unlabelled narration. With that source:
  - both prompts flag U1 and U5 as contradicted 5/5;
  - U2 was flagged 5/5 by the old prompt and 1/5 by the rule.

  The labels themselves are not always right: line 161 is marked "Michael Kerr" but
  reads as the interviewer speaking.
- **Watch item: the boat sentence.** "She handed the helm to him … though he says he
  deserved it" is faithful.
  - In the rule-in-windows arm it was a first-pass flag in 4 of 20 runs (1 confirmed).
  - In the final arm it was a first-pass flag in 1 of 10 runs (0 confirmed).
- **Cost:** about $35 for all arms.

## Conclusion

Shipped (final arm):
- no loss on gold, themes or real abstracts;
- real prose within the variance seen;
- the FAQ false flag is gone;
- the user's rule for unlabeled transcripts is now explicit, with adversarial gold cases
  for the ways it could be abused;
- the rule never applies to a labelled transcript or to a part-source chunk window.
