# Faithfulness judge flags: WRONG vs NOT QUITE RIGHT — review of the 2026-10-18 runs

Date: 2026-10-19. Judge: `faithfulness_judge` on claude-sonnet-5-5 with majority-of-3
confirmation (`config.FAITHFULNESS_CONFIRM_MODE = "majority3"`), `JUDGE_LOGIC_VERSION`
2026-10-13b, as run by the summary stage's own check (`_faithfulness_precheck`). No judge
code or prompt was changed for this review, and no API calls were made.

**Why.** The user's rule (2026-10-18): "The only fail is if something WRONG vs. not quite
right." This review counts how many of the judge's flags are wrong content and how many
are only not quite right, before any judge change is planned. The plan that follows from
it is `docs/plan_judge_severity_2026-10-19.md`.

## Result

43 flagged claims could be classified. **9 are WRONG (21%) and 34 are NOT QUITE RIGHT
(79%).** 20 of the 43 are borderline (marked in the table); counting every borderline
claim against the summary gives 26 WRONG and 17 NOT QUITE RIGHT (40%). Under every
reading, NOT QUITE RIGHT is a real share of the flags.

| Case | Flags | WRONG | NQR | NQR: supported (N1) | NQR: interpretation (N2) | NQR: wrong point (N3) | NQR: speaker credentials (N4) | Borderline (WRONG / NQR) |
|---|---|---|---|---|---|---|---|---|
| Holt (drafts, stage, live run) | 20 | 3 | 17 | 4 | 12 | 1 | 0 | 1 / 10 |
| 2021 Webcast Sep Part 1 | 8 | 2 | 6 | 0 | 3 | 2 | 1 | 0 / 3 |
| Societal Emotional Process | 2 | 0 | 2 | 0 | 1 | 0 | 1 | 0 / 1 |
| Systems Biology | 13 | 4 | 9 | 2 | 5 | 0 | 2 | 2 / 3 |
| **Total** | **43** | **9** | **34** | **6** | **21** | **3** | **4** | **3 / 17** |

One more claim (L3, below) was lost from the log and could not be classified.

WRONG flags by type: contradicts the source (W2) 4, wrong person (W3) 3, invented
conclusion or plan (W4) 2. None was an invented name, date, number or study (W1); names
are caught separately by the entity check.

By prompt: old summary prompt (commit 714a344, and the live run, which predates f62cb87)
22 flags, 4 WRONG; new prompt 21 flags, 5 WRONG.

**What would have passed if only WRONG claims failed (central reading):**

- First drafts: 2 of 16 passed. With NOT QUITE RIGHT passing and speaker credentials
  (N4) still failing, 8 of 16 would pass; with N4 passing too, 9 of 16. If every
  borderline claim counts as WRONG, the number stays at 2 (3 with N4), because each of the
  six extra drafts has at least one borderline flag. How borderline cases are worded in a
  policy decides most of the gain.
- The 2026-10-18 live run (`logs/gui_20261018_173321.log`) stopped on L5, a real remark
  placed under "closes by" (N3). With only WRONG failing, attempt 3 passes and the run
  finishes.

## Findings

1. **Most flags are not quite right.** 34 of 43. The judge's prompt already calls
   interpretation, framing and connection of grounded material "entailed", but the judge
   still fails it when the sentence reads as a causal claim or a stance ("frames these
   events as amplifiers … rather than independent causes").
2. **The judge also catches real errors, and they are the kind the user named.** A
   participant's story credited to Kerr (R35, and the same story leaking into Kerr's
   registry study in R34, R37); the stepdaughter placed in the wrong marriage (R22); a hedge
   turned into a claim the speaker declines (R25, same as gold case sa5); "closes without a
   formal conclusion" when Kerr says "I'm going to conclude by…" (R3); an invented future
   plan (R18); a wrong number of generations (R11). A change must keep failing these.
3. **Six flags are fully supported** (N1: R1, R7, R12, S1, R26, R30). Confirmation
   (majority of 3) did not overturn them, so these are steady judge errors, not random
   ones.
4. **Eight Holt flags are the summary restating an interpretive theme.** The "amplifier"
   sentence (R2, R4, R8, R9, R13, R14, S2, L2) is interpretive theme 3 of the Holt run,
   nearly word for word: "The presenter does not dismiss these biological events but frames
   them as amplifiers of an already-stressed system rather than independent causes." L1 is
   theme 2. The summary prompt says "Weave in the Interpretive Themes to deepen the
   analysis" (`prompts/Summary Generation Prompt v1.md`), and the theme judge is built to
   accept grounded interpretation, but the summary's judge fails the same sentence.
5. **Speaker credentials and previews come from the summary prompt.** Line 17 asks the
   opening to "Identify speaker with credentials, event context, stated purpose, and
   preview of content areas." When the transcript has no credentials, the model supplies
   them ("psychiatrist and longtime exponent of Bowen family systems theory": R16, R24,
   R32, R36), and when the speaker gives no preview it writes one (R17). The credentials
   are true (Kerr says "we're both psychiatrists" in the Holt talk, §1), but no source the
   judge sees contains them, so the judge cannot tell a true one from an invented one.
6. **Correction to the brief's example.** The brief said Kerr "did say people with
   already-stressed systems are more vulnerable". The Holt transcript has, in §31: "people
   can take excessive doses of various other drugs that affect the mind, and I think
   they're vulnerable too." It does not say "already-stressed systems". The amplifier
   framing is Kerr's general model (§25–§30) applied to surgeries he says he put on his
   graph ("I put surgery in here in both instances"), after he says "I certainly don't
   know". That is interpretation, not invention, but it is borderline.

## Classes used

**WRONG** (fail):
- W1 a fact, name, date, number, place, event, quote or study that is not in the source;
- W2 something the source contradicts: a changed number or relationship, a meta-claim
  about the talk the source contradicts, or a hedged statement made definite against an
  explicit hedge;
- W3 content credited to the wrong person (one participant's story or remark presented as
  another's or as the presenter's);
- W4 a conclusion, stance, plan or future event the speaker never states and that does not
  follow from what he says, or that runs against a position he states.

**NOT QUITE RIGHT** (pass, at most warn):
- N1 supported: a fair paraphrase or summary; the flag is a judge error;
- N2 interpretation: the writer frames, connects or emphasizes what the speaker says,
  including applying the speaker's own stated ideas to material he discusses, without a new
  fact;
- N3 wrong point: real content placed at the wrong point ("closes by" for an opening
  remark), or the talk's structure described loosely;
- N4 speaker credentials: a true description of the speaker that is not in the transcript
  or the recording title. Listed apart because the judge cannot verify it (see the plan).

**Borderline** marks a claim where a careful reader could put it in the other class. The
note says which way and why.

## Sources and method

Each claim was checked against the formatted transcript the judge saw (plus the recording
title, which the gate adds as metadata). Section numbers (§) are the transcript's own.

| Case | Source read | Words |
|---|---|---|
| Holt | Scratch copy made by the 2026-10-18 measurement (`…/fff590dd-…/scratchpad/sc1d/1 A and B Heartland Conference 2007 joe Holt interview - Michael Kerrr - 2026-01-26/… - formatted.md`). `/Volumes/davemini` is not mounted, so the original could not be opened; the Sep Part 1 scratch copy is byte-identical (sha1 2d0624d9…) to its original, which supports that the copies are faithful. | 7,401 |
| 2021 Webcast Sep Part 1 | `/Volumes/CrucialX9/1 MY DISK/KCFC ALL/projects/2021 Webcast Sep Part 1 - Michael Kerr - 2021-09-/… - formatted.md` | 2,128 |
| Societal Emotional Process | `tests/fixtures/prose_real/Societal Emotional Process - Michael Kerr - 2021-12-12_v-valid/… - formatted.md` | 11,784 |
| Systems Biology | `tests/fixtures/prose_real/Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25_20260718_155038/… - formatted.md` | 4,929 |

Claims: every `issues` entry in `docs/calibration/2026-10-18_summary_closing/results.json`
(37 from 16 first drafts, 2 from the Holt stage run) and the claims in
`logs/gui_20261018_173321.log` lines 359–375 (live run, old prompt). None of the four
transcripts has speaker labels, so the judge used the speaker-attribution rule (SA).

## Claims

ID key: R = `results.json` draft issue, in file order (case, prompt, draft); S = Holt
stage run, try 1; L = live-run log. "(closing)" = the claim is in the Closing Paragraph.

### Holt (20)

| ID | Claim | Class | Source evidence | Note |
|---|---|---|---|---|
| R1 (old 1) | A later appendix surgery in 2000 triggers a second severe episode, with intensified hallucinations and suicidality, managed through a day program rather than inpatient care. | NQR · N1 | §17: "my appendix … I was on anesthetics. And this was in 2000 … after the anesthetics, I woke up more depressed than I had been"; "More suicidal like that in the early days. I would hear people saying things, and they weren't"; "No, I didn't go to the hospital. I went to a day-out patient." Kerr calls it his "second worst". | Every element is in §17. |
| R2 (old 1) | Kerr acknowledges he cannot fully explain the mechanism but notes that people can emerge from anesthesia in frankly psychotic states, and frames these biological events as amplifiers of an already chronically stressed system rather than independent causes, reinforcing the feedback loop between relational anxiety and biological vulnerability. | NQR · N2 · borderline | §31: "I certainly don't know. I put surgery in here in both instances … I've seen people come out of anesthesia quite psychotic … I think they're vulnerable too." §25: "remissions and relapses are part of an anxiety-driven, larger system, process". §30: "more important than the diagnosis, more important than the genes". | Amplifier family (finding 4). First half is §31. The framing is Kerr's general model applied to surgery; he does not say it about surgery. Borderline W4 because §31 opens "I certainly don't know". |
| R3 (old 1, closing) | Kerr closes without a formal conclusion, noting that a systems framework will likely require more than his lifetime to fully integrate these ideas. | **WRONG · W2** | §23: "Okay, I'm going to conclude by contrasting Bowen family systems theory with what I would call conventional theory". §30: "The last slide." The lifetime remark is §1 (opening): "eventually a systems way of thinking will bring these ideas together, probably not over my lifetime." | "Without a formal conclusion" is contradicted by §23. The lifetime half alone would be N3. Old prompt; f62cb87 removed "no conclusion" sentences. |
| R4 (old 2) | Kerr acknowledges the biological reality while framing these events as amplifiers of an already-stressed system rather than independent causes—noting that he has observed anesthesia producing acute psychosis in other patients. | NQR · N2 · borderline | §31, as R2. | Amplifier family. |
| R5 (old 2) | The exchange reinforces the presentation's core argument that biological and relational stressors interact rather than operate separately. | NQR · N2 | §31: "I put surgery in here in both instances". §26: "it's putting equal weight on both". | Writer framing. "Core argument" is loose: Kerr's stated core point is that emotional process matters more than diagnosis or genes (§30). No new fact. |
| R6 (old 2, closing) | The case raises unresolved questions about how biological vulnerability, multigenerational emotional process, and individual agency interact across a lifetime of psychiatric illness. | NQR · N2 · borderline | §31: "I certainly don't know". §1: "probably not over my lifetime". §19: "something inside of you, some spirit". | The writer's own open question, the kind f62cb87 removes from closings. All three elements are in the talk, and Kerr says the integration is unfinished (§1); he does not pose this question. Borderline W4. |
| R7 (new 1) | In the children's home, Joe describes feeling invisible—not remembered by peers or staff, told by his house mother Christine that his parents did not love him, and watching his brother Jack rebel repeatedly while he remained compliant. | NQR · N1 | §9: "She would say my parents didn't love me and no one loved me … I also believed that I was invisible … most of the people in the children's home didn't remember me … Jack ran away several times. I was really compliant … My brother Jack was very rebellious". §10: "I think Christine stood out." | Supported. The transcript spells the house mother "Christina" (§7) and "Christine" (§10). |
| R8 (new 1) | Kerr notes that anesthesia can precipitate psychosis and frames these medical events as amplifiers of an already chronically stressed system rather than independent causes. | NQR · N2 · borderline | §31, as R2. | Amplifier family. |
| R9 (new 1) | Kerr acknowledges the observation, confirms he has seen patients emerge from anesthesia in psychotic states, and reiterates that biological stressors interact with an already-stressed system rather than acting as isolated causes. | NQR · N2 · borderline | §31, as R2. | Amplifier family. "Reiterates" holds only for his general model. |
| R10 (new 1) | The exchange reinforces the conference's interdisciplinary framing and the presenter's argument that biological and relational variables must be held together. | NQR · N2 | §1: "this is the whole point of having an interdisciplinary". §31. | Writer framing; no new fact. |
| R11 (new 2) | Joe Holt's family history is presented through a complex genogram spanning two generations. | **WRONG · W2** | §2: "It's a complex diagram". §4: "the grandfather … died quite young … at the age of 49"; "Sophie, the grandmother". §5: "Joe's grandfather's first wife". | The diagram has three generations (Joe and siblings, parents, grandparents). A small wrong number. |
| R12 (new 2) | His house mother Christine told him his parents did not love him, and when he returned to the home as an adult, staff did not remember him. | NQR · N1 | §9: "She would say my parents didn't love me … when I went back to visit the children's home in my late teens, and as an adult, you know, people don't remember I was there." | Supported. |
| R13 (new 2) | A later appendix surgery with anesthetics produced a second severe episode, which Kerr frames not as an independent cause but as a biological amplifier of an already chronically anxious system. | NQR · N2 · borderline | §17 (first half); §31, as R2. | Amplifier family. |
| R14 (new 2) | He frames these events as amplifiers rather than primary causes, consistent with his systems argument. | NQR · N2 · borderline | §31, as R2. | Amplifier family. |
| S1 (stage, new) | His clearest positive memory is of an unidentified man who held him in the night during a brief foster placement—a moment he describes as the best memory from those years. | NQR · N1 | §10: "I went to live with the family, and it was for a short period … the man came in the room and picked me up in the middle of the night and held him. And it's probably the best memory I have, and I have no idea who he was … It's the only memory I have … that's good from those years." | Supported. |
| S2 (stage, new) | Kerr acknowledges the observation directly, noting that he has seen people emerge from anesthesia in psychotic states and that individuals with already-stressed systems are likely more biologically vulnerable to such events—framing medical stressors as amplifiers of existing system anxiety rather than independent causes. | NQR · N2 · borderline | §31: "people can take excessive doses of various other drugs that affect the mind, and I think they're vulnerable too." | Amplifier family. The source does not say "already-stressed systems"; the vulnerability reading is interpretive theme 3's (finding 6). |
| L1 (live, attempt 1) | He contrasts his own compliance with brother Jack's repeated runaways, framing these as distinct adaptive postures within the same anxious system. | NQR · N2 · borderline | §9 (Joe): "Jack ran away several times. I was really compliant". §28 (Kerr): "the siblings rapidly assume their parts. Nobody has a choice." | The contrast is Joe's; the "postures within the same anxious system" framing is Kerr's (§28) and interpretive theme 2. Crediting the framing to Joe is borderline W3. |
| L2 (live, attempt 1) | Kerr acknowledges that anesthesia can precipitate psychosis and frames these medical events as biological amplifiers of an already chronically stressed … *(cut off in the log)* | NQR · N2 · borderline | §31, as R2. | Amplifier family. |
| L4 (live, attempt 2, closing) | Kerr closes by expressing hope that Bowen theory remains open to new knowledge rather than hardening into unexamined assumption, leaving the relationship between emotional process and psychiatric diagnosis as a productive open question. | **WRONG · W4 · borderline** | §33: "Murray Bowen thought that keep his theory open to new knowledge so that it wouldn't just become, everybody assumes it's accurate". §30: "I consider that programming more important than the eventual diagnosis in explaining what goes on." | First half: Bowen's wish, reported by Kerr at the end (fair). The "open question" runs against the position Kerr states in §30. Borderline: it could be read as Kerr's general openness to new knowledge. |
| L5 (live, attempt 3, closing) | Kerr closes by noting that Murray Bowen wanted to keep his theory open to new knowledge so that it would not harden into unexamined assumptions, and expresses his own view that an interdisciplinary, systems way of thinking will eventually bring these ideas together. | NQR · N3 | §33 (end), as L4. §1 (opening): "My view is that eventually a systems way of thinking will bring these ideas together". | Both halves are Kerr's; the second is his opening remark placed under "closes by". This flag stopped the run. |

Not counted:
- **L3** (live, attempt 1): the log line is cut at 300 characters
  (`extraction_pipeline.py:1471`, `"; ".join(issues)[:300]`), so the third claim's text is
  lost.
- Attempt 2's first-pass flag "Kerr structures the presentation in three segments, using
  Joe's own words alongs…" was overturned by confirmation (log line 367), so it was not a
  flag.

### 2021 Webcast Sep Part 1 (8)

| ID | Claim | Class | Source evidence | Note |
|---|---|---|---|---|
| R15 (old 1) | He mentions that the upcoming Bowen Theory Academy conference will feature a speaker who champions the view that meaningful parallels exist between systems thinking in physics and in human emotional process, signaling that this theme will receive fuller treatment in future sessions. | NQR · N2 · borderline | §2: "looking at possible links between Bowen theory and all life on the planet, even the physical world. Are there parallels? And when Bowen Theory Academy has its meeting next October, one of the speakers who's been championing of that view is going to be with us". | The meeting and speaker are in §2. "Fuller treatment in future sessions" is the writer's inference; borderline W4 if "sessions" means future webcasts, which the source does not mention. |
| R16 (old 2) | Michael Kerr, a prominent Bowen theory clinician and educator, opens the first webcast of the 2021 academic year by grounding the session in a live clinical case that prompted him to examine a broader question: what must a person actually accomplish to gain traction in a relationship system and improve their level of differentiation of self? | NQR · N4 | §1: "welcome to the first webcast of this academic year … what is it that people have to accomplish to get some traction in a relationship system and improve their level of differentiation of self." "2021" and the name are in the recording title, which the judge sees. | Only "a prominent Bowen theory clinician and educator" is outside the source (finding 5). |
| R17 (old 2) | He previews three interrelated content areas—the stepfather-stepdaughter-mother triangle, the systemic rather than individual nature of triangular tension, and the coaching strategy he employed through a follow-up email intervention. | NQR · N3 · borderline | §1: "I've got two things to talk about today". The three areas are §5, §16 and §14–§18. | All three areas are in the talk, but Kerr does not preview them; the prompt asks for a "preview of content areas" (finding 5). Borderline W2 ("three" against "two things"). |
| R18 (old 2, closing) | Future sessions will test whether insight into triangular co-creation, combined with deliberate behavioral moves, can produce measurable change in differentiation of self. | **WRONG · W4** | Nothing. The transcript stops mid-sentence in §18: "So your ability to think about what I'm suggesting and act accordingly can". | An invented future plan. Old prompt; f62cb87 targets this. |
| R19 (new 1) | His mother, who lives abroad and remains in close contact with him, made the referral to Kerr after Chris told her the situation at home had become untenable. | NQR · N2 | §7: "his mother's in pretty good contact with him, even though they live far away … said, I think I need some help with this"; "that kind of pushed him over the edge of doing something". §4: "He's originally from Bristol, England"; "she made the referral". | "Abroad" is inferred; "untenable" is stronger than "I need some help". Mild strengthening, no new fact. |
| R20 (new 1) | Both spouses acknowledged that their busy schedules left little time to sit down and work through the conflict together. | NQR · N2 · borderline | §10: "he said, my wife and I don't have a lot of time to sit down together and try to talk this through". | Chris says it for both of them, in the first session, which he attended alone. "Both spouses acknowledged" credits the wife too; borderline W3. |
| R21 (new 1, closing) | Kerr's email to Chris closes with the observation that the ability to think about the triangle and act accordingly can have an amazing impact — underscoring that seeing the system clearly, and then moving from that seeing, is the essential double requirement Bowen theory places on anyone seeking real change. | NQR · N3 | §17: "seeing it as a triangle with no one person to blame and acting on that insight can have an amazing impact". §18 (last words): "So your ability to think about what I'm suggesting and act accordingly can". §3: "it takes an action move to get the job done". | The "amazing impact" line is earlier in the same email; the email's own close is cut off. Real content at the wrong point. |
| R22 (new 2) | The central tension involves Chris's sixteen-year-old stepdaughter, Sage, from his first marriage. | **WRONG · W2** | §4: "a daughter by the first marriage. That ended in divorce. And she is now 16". §13 (the wife, about Chris): "This is his first marriage." | Sage is from the wife's first marriage; this marriage is Chris's first. Wrong relationship. |

### Societal Emotional Process (2)

| ID | Claim | Class | Source evidence | Note |
|---|---|---|---|---|
| R23 (old 1) | Dr. Kerr is explicit that no single event caused the deterioration — rather, the cluster unmasked a self-deficit accumulating since at least 2004, with hormonal symptoms traceable to age fifteen. | NQR · N2 · borderline | §7 (Linda): "I had symptoms since 2004 … as I talked with Dr. Kerr the first time, I understood that it wasn't really any one of those things in particular, but it certainly unmasked the story." §16: "all the hormonal symptoms since I was age 15". §5: "lost self". | The facts are there. Linda reports the point as what she understood from Kerr; "Kerr is explicit" overstates who said it (borderline W3). "Self-deficit" is the writer's word for "lost self". |
| R24 (new 2) | Dr. Michael Kerr, psychiatrist and longtime exponent of Bowen family systems theory, presents a recorded Skype interview with a woman living in France who experienced a stage-one uterine cancer diagnosis alongside a cluster of major life stressors. | NQR · N4 | §2: "we did it on Skype and recorded it". §3: "She lives in France". §8: "I had stage one uterine cancer". §7: the 2015 events. | Only the credentials are outside the source (finding 5). |

### Systems Biology (13)

| ID | Claim | Class | Source evidence | Note |
|---|---|---|---|---|
| R25 (old 1) | He proposes that chronic anxiety, as understood in Bowen theory, is precisely the variable that explains individual variability in cancer risk and progression — why similar exposures produce different outcomes across people and families. | **WRONG · W2** | §15: "I think that's something that Bowen theory can contribute to with its concept of chronic anxiety". §20: "the stress factor may affect cancer progression, but it doesn't necessarily mean that that's why the cancer has occurred". | A hedge ("can contribute", "may affect progression") becomes "precisely the variable that explains … risk", which §20 declines. Same as gold case sa5 (contradicted). |
| R26 (old 1) | A cancer registry study Kerr cites found that patients who genuinely believed in their chosen treatment course — whether conventional or unconventional — fared better than those who were ambivalent or passive. | NQR · N1 | §29: "the individuals who truly believed that what they were doing was the best thing they could be doing … If I let you guys give me this drug … it's going to kill me. I'm leaving. That person could live. Whereas the opposite was there, too. Give me everything you got, doc … That can be eroded if you put the doctor on too much of a pedestal." | Supported; "ambivalent or passive" is a fair reading of the contrast. |
| R27 (old 1, closing) | Kerr leaves open the question of how fully Bowen theory can be integrated with systems biology's emerging frameworks. | NQR · N2 · borderline | §1: "the biological sciences, at least, are moving toward many familiar things to Bowen theorists … I think it's a real positive thing for the future of Bowen theory". | The writer's own open question. Kerr does not raise it, and does not take the opposite position. Borderline W4. |
| R28 (old 1, closing) | The multi-scale parallel — from cell to organism to family to society — is named but not yet theorized, pointing toward future work that could formalize these connections. | NQR · N2 · borderline | §27 (Cynthia): "that is a perfect description of societal regression". §25: "we could take this from what's going on in the identified patient … in a family, all the way down to how is that playing out inside". §11: "a paper I'm beginning to work on … It will have that kind of theme". | The writer's assessment; the future work has a basis in §11. Borderline W4. |
| R29 (old 2) | Patient variability surfaces repeatedly as the explanatory gap that cell-focused models cannot close. | NQR · N2 | §21: "being able to explain variation in levels of chronic anxiety among people". §28 (Janice): "the variability in people's ability to adapt". §5: "very limited progress in finding cancer cures". §20: the prostate example. | A synthesis across sections; no new fact. |
| R30 (old 2) | A cancer registry study Kerr cites found that patients who held firm confidence in their chosen treatment course — regardless of which course — showed better outcomes than those who were ambivalent or deferential. | NQR · N1 | §29, as R26. | Supported; "deferential" matches "put the doctor on too much of a pedestal". |
| R31 (old 2, closing) | Kerr closes without a formal conclusion, leaving open the question of how fully Bowen theory and systems biology can be integrated. | NQR · N2 · borderline | The transcript ends in Q&A (§26–§30) with no concluding statement; §3 promises "a few comments by me at the end", which are not in the transcript. | Unlike R3, nothing in this source contradicts "without a formal conclusion" (but the source is incomplete: see Limits). The open question is as R27. |
| R32 (new 1) | Michael Kerr, a psychiatrist and longtime exponent of Bowen Family Systems Theory, presents a lecture-format webcast exploring an unexpected convergence between systems biology and Bowen theory. | NQR · N4 | §1: "I like to divert off into a lecture type format … the biological sciences, at least, are moving toward many familiar things to Bowen theorists. And I didn't expect that". | Only the credentials are outside the source. |
| R33 (new 1) | Cynthia offers the lecture's sharpest conceptual synthesis, noting that the description of single cells trapped in self-promotion rather than cooperation is a precise description of societal regression — naming the multi-scale isomorphism that Kerr had assembled but not fully articulated. | NQR · N2 | §27: "when the single cell is trapped in a state of promoting the single cell rather than cooperation among cells … that is a perfect description of societal regression". | Cynthia's point is accurate. "Sharpest" and "not fully articulated" are the writer's evaluation. |
| R34 (new 1) | Janice Norton raises the clinical reality of variability in patient adaptation to cancer diagnosis, and Kerr responds with a cancer-registry study finding that patients who held confident, self-directed beliefs about their treatment — regardless of which course they chose — showed better outcomes than those who mixed approaches or ceded all agency. | **WRONG · W3 · borderline** | §29, as R26. §30 (Kathy): the surgeon said "don't mix up those two things. Those people die." | "Those who mixed approaches" comes from Kathy's surgeon story and is put into Kerr's study. Borderline: the study's "they weren't going to change" could be read as the opposite of mixing. |
| R35 (new 1) | Kerr closes by underscoring the importance of patient agency in cancer treatment, citing a surgeon's advice that patients either fully trust a chosen physician or become their own informed decision-maker — but that mixing the two approaches is associated with worse outcomes. | **WRONG · W3** | §30 (Kathy): "I had the good fortune to be with a good friend … the surgeon … said, there are two courses that I recommend … don't mix up those two things. Those people die." | Kathy tells the story, not Kerr. The user's own example of WRONG. |
| R36 (new 2) | Michael Kerr, a psychiatrist and longtime exponent of Bowen Family Systems Theory, presents a lecture-format webcast exploring an unexpected convergence between systems biology and Bowen theory. | NQR · N4 | As R32. | As R32. |
| R37 (new 2) | Janice Norton raises the considerable variability in patients' ability to adapt to a cancer diagnosis, prompting Kerr to cite a cancer-registry study finding that patients who genuinely believed in their chosen course of treatment — and held to it — showed better long-term outcomes than those who deferred entirely to medical authority or mixed strategies. | **WRONG · W3 · borderline** | As R34. | As R34. |

## Limits

- **One reviewer.** I classified every claim; no second person checked the labels. The
  borderline marks show where the call could go the other way, and the counts are given
  both ways above.
- **L3 is lost** to the 300-character log cut.
- **No judge labels or rationales.** `results.json` stores the flagged sentences only, so
  this review cannot say whether the judge called each one "contradicted" or "unsupported".
- **Holt was read from the scratch copy** (see Sources).
- **The Systems Biology source is incomplete.** Its raw transcript's header says "Cloud
  transcription incomplete: transcribed 5 of 12 chunks". The five chunks cover about 40 of
  the recording's 88 minutes; the formatted transcript jumps from 00:23 to 00:48 and from
  00:54 to 01:20.
  The summary and the judge saw the same incomplete text, so the classes above hold against
  that text; R31's "without a formal conclusion" may be wrong about the actual talk.
- **Sample.** Four talks, mostly first drafts. This shows what kinds of flags the judge
  raises, not a rate for all talks.

## Adjacent issues found, not fixed

- `extraction_pipeline.py:1471` cuts the flagged-claim list at 300 characters in the
  warning log, so claims are dropped from the only record of a failed attempt (P2). The
  abstract loop's warning (`extraction_pipeline.py:1665`) should be checked for the same.
- Nothing in the pipeline reads the transcription tool's "incomplete" warning: a search of
  the repo for "transcription incomplete" / "missing time ranges" finds nothing. The
  Systems Biology project was summarised and judged from about 40 of its 88 minutes.
- `prompts/Summary Generation Prompt v1.md` line 17 asks for "credentials" and a "preview
  of content areas" whether or not the transcript has them (R16, R17, R24, R32, R36).
- The same prompt says "Weave in the Interpretive Themes", whose interpretation the
  summary's judge then fails (finding 4).
- `docs/calibration/2026-10-18_summary_closing/measure_closing.py` saves flagged sentences
  but not the judge's labels or rationales.
