# Summary length floor and abstract Q&A input — 2026-10-14 (SL3, AQ)

Author decisions (2026-10-14): keep the summary target at 650 words and lower the
floor; slightly shorter summaries are fine unless the validation needs more words. Stop
sending the pattern-made Q&A topics to the abstract.

## SL3 — summary floor

**Problem.** End-to-end run 7 failed the structured summary on two talks: every draft
was under the 585-word floor (Beautiful Boy 580, Systems Biology 562), so the stage
failed after three attempts. Run 6 had two first drafts under it (584, 581).

**Does the validation need more words?** No. The coverage gate checks topic and closing
items, not length. Every saved summary in runs 1–7 (589–837 words) passed it, and all 18
drafts measured below passed it, down to 490 words. One check that does not gate did
miss: the 490-word draft (Beautiful Boy) reported its Q&A content item missing; so did
saved summaries of 604 and 589 words in runs 4 and 6, so it is not only length.

**Measurement** (`docs/calibration/2026-10-14_summary_floor/measure_summary_length.py`,
three drafts per talk from run 7's files, claude-sonnet-5-5, the floor switched off so
each draft's own length shows, the real coverage validation on each draft):

| Talk | Prompt asks for 585–780 | Prompt gives only the target and the maximum |
|---|---|---|
| Beautiful Boy | 553, 561, 539 | 490, 608, 522 |
| Systems Biology | 572, 626, 636 | 572, 557, 552 |
| Why Families | 709, 637, 710 | 668, 594, 655 |
| Coverage gate | PASS 9 of 9 | PASS 9 of 9 |

I expected the stated minimum to pull drafts down toward it; it does the opposite.
Without it, the long talks' drafts were shorter (490–608 against 539–636).

**Change.** The prompt still asks for 90–120% of the target (585–780 for 650); a draft
from 85% up (553) is accepted, so a draft slightly under the asked minimum is not
regenerated. `config.SUMMARY_LENGTH_MIN_RATIO` (asked, 0.9),
`SUMMARY_LENGTH_ACCEPT_MIN_RATIO` (accepted, 0.85), `SUMMARY_LENGTH_MAX_RATIO` (1.2);
`config.summary_prompt_word_range` and `config.summary_word_bounds`. With the asked
minimum in the prompt, 1 of 9 drafts here (539) and 0 of 6 in runs 6–7 were under 553;
the stage fails only if all three attempts are.

Results: `docs/calibration/2026-10-14_summary_floor/results_minimum_in_prompt.txt`,
`results_no_minimum_in_prompt.txt`.

## AQ — abstract Q&A note

**Problem.** When the Q&A note is on, the abstract model was given `qa_topics`: words
after "about/on/regarding" with small words removed ("exploration reading book
written"), and told to mention them. Run 7, Beautiful Boy: the judge rejected the Q&A
sentence on all three attempts and the gate blocked.

**Change.** `AbstractInput.to_json` no longer sends `qa_topics`; the prompt asks for one
sentence on what the audience asked about or discussed, as the transcript shows it. The
abstract coverage check's Q&A item now looks for a Q&A note by Q&A-specific phrases
(`config.ABSTRACT_QA_NOTE_MARKERS`) instead of the fragments. Single words ("audience",
"question", "discussion") were tried first and dropped in review: a real abstract with
no Q&A note matched on "to an audience unfamiliar with the approach".

**Measurement** (`docs/calibration/2026-10-14_abstract_qa/measure_abstract_qa.py`,
Beautiful Boy from run 7, Q&A share 100%, the real stage with its faithfulness judge,
claude-haiku-5-5 as in the GUI): 3 of 3 passed. This was measured before the 250-word
limit was enforced at generation; the third abstract (265 words) would now be
regenerated. Each Q&A sentence named questions from
the talk (detachment versus differentiation, multigenerational sources of child focus,
trauma-informed versus systems formulations). One attempt was retried for an unrelated
claim (a date).

**Also found.** One of the three abstracts had 265 words; the 250-word limit was stated
in the prompt and only warned about in validation (runs 2–7: 153–248 words). It is now
enforced at generation (`max_words`) for the published abstract, and a later attempt
that fails outright keeps the best earlier draft, as the summary does (SL2). Core's
intermediate first abstract (PART 5) is generated without the limit.

Results: `docs/calibration/2026-10-14_abstract_qa/results.txt`.
