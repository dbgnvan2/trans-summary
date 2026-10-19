# Summary closing instruction — live check (SC1.d), 2026-10-18

Plan: `docs/plan_summary_closing_2026-10-18.md#SC1.d`. Script:
`docs/calibration/2026-10-18_summary_closing/measure_closing.py`. Results:
`results.json` next to it. The full run log (`results.log`) is gitignored and stays local.

## What was measured

Four real transcripts. For each one, the old summary prompt (commit 714a344) and the new
one each made two first drafts. Each draft was made by the stage itself
(`generate_structured_summary` with one attempt): production model claude-sonnet-4-6,
judged by the stage's own check (`_faithfulness_precheck`: claude-sonnet-5-5 with
majority-of-3 confirmation, plus the name check). Then the real stage (three attempts,
with revision) ran once on Holt with the new prompt. Project files were copied to a scratch
folder, and the logs folder (judge cache, token log) was redirected there, so no real
project or log file was written. **Cost: $1.77** (scratch token log).

A flagged claim counts as a **closing flag** when its text is in the Closing Paragraph.
A **"no conclusion" sentence** is a closing that matches the script's `META_CLAIM`
pattern ("closes without a formal conclusion", "ends without…"). I checked every match by
hand, and all of them were correct.

## Results

| Case (how the talk ends) | Closing flags, old | Closing flags, new | "No conclusion" sentence, old | "No conclusion" sentence, new | All flags, old | All flags, new |
|---|---|---|---|---|---|---|
| Holt (recording stops in a panel discussion) | 1, 1 | 0, 0 | 2 of 2 | 0 of 2 | 3, 3 | 4, 4 |
| 2021 Webcast Sep Part 1 (stops mid-sentence) | 0, 1 | 1, 0 | 2 of 2 | 0 of 2 | 1, 3 | 3, 1 |
| Societal Emotional Process (speaker's closing point, then goodbyes) | 0, 0 | 0, 0 | 2 of 2 | 0 of 2 | 1, 0 | 0, 1 |
| Systems Biology (ends in Q&A) | 2, 1 | 1\*, 0 | 1 of 2 | 0 of 2 | 4, 3 | 4, 2 |
| **Total** | **6** | **2** | **7 of 8** | **0 of 8** | **18** | **19** |

\* Both new-prompt Systems Biology drafts were written with no headings, so the script
found no Closing Paragraph and counted every flag there as a body flag. The saved
Systems Biology summary from an earlier real run (old prompt) also has no headings, so
missing headings are not caused by this change, and nothing downstream checks for them.
For draft 1, I classified the flag by hand. The flagged sentence is the closing one and
starts "Kerr closes by underscoring the importance of patient agency… citing a surgeon's
advice". The flag is correct: a participant (Kathy) tells the surgeon story in the last
section, not Kerr. Draft 2's flags are both earlier in the text (I checked its last
paragraph on disk).

**Holt stage run (new prompt, three attempts):** try 1 had two flagged claims, both in
the body; try 2 (revision) passed. The stage returned True. Neither try had a closing
flag. Kept closing:

> Kerr closes by noting that Murray Bowen insisted his theory remain open to new
> knowledge rather than harden into unexamined assumption, and that the radical conceptual
> shift the theory offers is seeing Joe's long trajectory as reflecting changes in
> functional level of differentiation—emotional process—rather than the natural history
> of a disease.

The Bowen remark is in the last section (33), so "closes by" is accurate here.

## Against the plan's pass criteria

1. **New-prompt drafts have no more closing flags than old: met** (2 vs 6).
2. **No new-prompt draft says the talk has no conclusion: met** (0 of 8; old 7 of 8).
3. **Societal Emotional Process: the new closing still gives the speaker's closing point
   (identity as the key issue): partly met.** Draft 1 gives it ("identity, not nutrition
   or stress management, was the primary driver"). Draft 2 gives a different point, which
   the check accepted. Neither old-prompt draft gave it, so nothing was lost. Accepted
   under the user's rule of 2026-10-18: fail only when something is wrong, not when it is
   not quite right.
4. **The real stage on Holt has no closing flag: met.** It passed on try 2.

## Things this check found that the change does not fix

- **Body flags: 12 old vs 17 new** (all flags minus closing flags), mostly Holt (4 vs 8).
  The flagged claims are the same kinds under both prompts: framing such as "frames these
  events as amplifiers of an already chronically stressed system", "The exchange
  reinforces the presentation's core argument", and small invented details ("genogram
  spanning two generations"). Two drafts per case can't separate a prompt effect from
  judge and generation variance (the same Where Roots blog, judged three times with the same
  prompt, got 12, 21 and 14 flags: `docs/calibration_speaker_attribution_2026-10-12.md`). The
  revision loop handles body flags: the Holt stage passed on try 2. Worth watching in the
  next end-to-end runs (TODO).
- **"Closes by" is still used for points not made at the end** in some new closings. Holt
  new draft 2: "Kerr closes by emphasizing that emotional programming… is more important
  than diagnosis". That is Kerr's argument from the body, and the check accepted it. Sep
  Part 1 new draft 1: "Kerr's email to Chris closes with the observation…", which was
  flagged. The instruction "without saying that it comes at the end" is followed only
  some of the time.
- **Old-prompt closings invent open questions and future directions** in 8 of 8 drafts
  ("Future sessions are implied but unspecified", "a paper in progress and the
  expectation that future research…"). That is the behaviour the change removes. The
  check flagged only some of these sentences, so the old prompt's closing-flag count
  understates the problem.

## Every closing paragraph

### Holt
- **old 1:** Kerr closes without a formal conclusion, noting that a systems framework will likely require more than his lifetime to fully integrate these ideas. He expresses hope that interdisciplinary dialogue will eventually bring them together, leaving open questions about the relative weight of biological and relational variables in severe psychiatric illness.
- **old 2:** Kerr closes without a formal conclusion, noting that Bowen himself wanted his theory kept open to new knowledge rather than treated as settled assumption. The case raises unresolved questions about how biological vulnerability, multigenerational emotional process, and individual agency interact across a lifetime of psychiatric illness.
- **new 1:** Joe's own counsel to others with psychiatric diagnoses captures the talk's central tension: know the facts honestly, understand how the family system has shaped you, learn to nurture yourself and those around you, and above everything else, do not accept the diagnosis as a death sentence, because recovery is a process that took him twenty years.
- **new 2:** Kerr closes by emphasizing that emotional programming within the multigenerational relationship system is more important than diagnosis or genetics in explaining what happens to individuals like Joe, and that people and families exist on a continuum of interdependence that shapes symptom development and recovery alike.

### 2021 Webcast Sep Part 1
- **old 1:** The session ends without a formal conclusion, leaving open how Chris will respond to the email reframe and whether the shift from individual blame to systemic thinking will translate into the action move Kerr identifies as essential for genuine differentiation of self.
- **old 2:** The session ends without a formal conclusion, leaving open the question of whether Chris can translate this systemic reframe into sustained action. Future sessions will test whether insight into triangular co-creation, combined with deliberate behavioral moves, can produce measurable change in differentiation of self.
- **new 1 (flagged):** Kerr's email to Chris closes with the observation that the ability to think about the triangle and act accordingly can have an amazing impact — underscoring that seeing the system clearly, and then moving from that seeing, is the essential double requirement Bowen theory places on anyone seeking real change.
- **new 2:** Kerr emphasizes that seeing the situation as a triangle — with no one person elevated to a position of causality — and acting on that insight can have an amazing impact, representing a foundational step that Bowen theory makes possible through a change in perspective followed by deliberate, differentiated action.

### Societal Emotional Process
- **old 1:** The session closes without a formal conclusion, with Dr. Kerr expressing regret that Linda could not participate live in the discussion. Open questions remain about the family as an emotional system and the mechanisms by which experiential faith supports differentiation. Future sessions are implied but unspecified.
- **old 2:** Kerr closes without a formal conclusion, expressing gratitude for Linda's candor and noting the privilege of hearing people describe themselves directly. Open questions about the family as an emotional system — including the husband's own 2010 spiritual experience — remain for future exploration.
- **new 1:** Kerr observes that the interviewee's case illustrates how identity, not nutrition or stress management, was the primary driver of her physical decline, and that her willingness to look honestly at herself — rather than deny what was being revealed — was the central choice that made everything else possible.
- **new 2:** Kerr observes that the interviewee is "unquestionably functioning on a higher level" and that this is something she has accomplished herself. He frames the privilege of clinical work as hearing people describe who they really are, uninterpreted — and learning from that in return.

### Systems Biology
- **old 1 (flagged, both sentences):** Kerr leaves open the question of how fully Bowen theory can be integrated with systems biology's emerging frameworks. The multi-scale parallel — from cell to organism to family to society — is named but not yet theorized, pointing toward future work that could formalize these connections.
- **old 2 (flagged):** Kerr closes without a formal conclusion, leaving open the question of how fully Bowen theory and systems biology can be integrated. The convergence he describes is framed as generative and ongoing, with a paper in progress and the expectation that future research will continue drawing these frameworks closer together.
- **new 1 (no headings; flagged closing sentence, full paragraph not saved):** Kerr closes by underscoring the importance of patient agency in cancer treatment, citing a surgeon's advice that patients either fully trust a chosen physician or become their own informed decision-maker — but that mixing the two…
- **new 2 (no headings; last paragraph):** Kerr's central claim is that the biological sciences, through systems biology and niche theory, are converging on the same insight Bowen theory has long held: that individual pathology cannot be separated from the larger relational and environmental system in which it arises, and that restoring the system, rather than eliminating the symptom, is the more promising path forward.

## Limits of this check

- Two drafts per case and one stage run. This shows the direction of the change, not a rate.
- The script as run saved each draft's closing, not the whole draft, and found the closing
  by its heading. A draft with no headings needed the hand classification above.
