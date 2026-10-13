# Plan: changed first or last word in a quote (SW) — 2026-10-12

Status: **built 2026-10-12.** The user asked me to continue with my own
recommendations overnight. It changes the blocking `verbatim_quotes` check, so it was
measured on every real quote on disk before it shipped. The measurement is offline,
with no API calls.

## Problem (D6 open item)

`_quote_word_coverage` aligns a quote to the source and allows skipped source words
anywhere, because quotes omit words without an ellipsis. In 60 of the 73 real quotes
that pass and are not word-for-word, the skipped spans are 1–37 words of
interjections, section headings or asides. So "every quote word found, in order" can
pass a quote whose first word was changed, if that word also occurs a little earlier
in the source. Known cases:
- "I think the future…" where the speaker said "…to me the future…";
- "My mother" where the source says "her mother".

## Rule (SW1)

The quote's **lead** (and, mirrored, its **tail**) is the run of matched blocks from
the start of the quote up to the first skip of at least
`config.QUOTE_STRAY_BLOCK_MIN_GAP` (3) source words. It is stray, and its words don't
count as found, when all of these hold:
- it has at most `config.QUOTE_STRAY_BLOCK_MAX_WORDS` (4) words;
- its words are not among the source words just before (or after) the rest of the
  quote, which are `config.QUOTE_STRAY_NEAR_WORDS` (3) plus its own length. Those
  words being there means an omission ("And she also described" quoted as "She
  described");
- the quote doesn't mark the omission there with "..." or "…".

Only the ends are checked. The alignment keeps order, so a changed word inside a
quote is already a mismatch, and a short block between two omissions inside a quote
is the speaker's word in its place.

**Known limit (accepted).** An omission right after a quote's first words (or before
its last words) that isn't marked with an ellipsis looks the same as a swap, and
fails. For example, "The family is an emotional unit" for "the family, as I have said
many times before, is an emotional unit". No real passing quote has this shape.
Pinned by `test_sw3_known_limit_unmarked_edge_omission_fails`.

**Not caught (accepted):**
- A substitute within 2 words of the rest of the quote. A skip of fewer than 3 words
  is a normal omission everywhere.
- A changed lead or tail that the quote marks with "..." or "…" at that edge. The
  marker is read as the speaker's own omission. Only 6 of the 835 real quotes contain
  an ellipsis, so the exemption is tested mainly on synthetic text.
- A changed lead or tail of 5 or more words. It isn't checked.

**One-gap quotes.** When a quote has a single large skip, its lead and tail are each
other's "rest of the quote". Only the shorter side is counted as changed, so the
reported coverage stays meaningful (0.5, not 0.0).

## Measurement (SW4)

- **Corpus:** every Bowen and emphasis quote, read as the gate reads it, from 35 real
  projects: local projects, "2020 Videos", the KCFC and BTA drives, and the test
  fixtures. That is 835 quotes, of which 782 pass today. This covers more than D6's
  752 quotes from 33 projects. The first SW draft missed the 11 "2020 Videos"
  projects, whose folder names differ from their file names.
- **Result:** 5 newly fail and none newly pass. Each was checked against its source,
  and each is a real one-word change:
  - "I think the future" for "to me the future";
  - "My mother" for "her mother";
  - "I took a physicist" for "It took a physicist";
  - "And at the end of that" for "So, anyway, at the end of that";
  - "The kinds of experiences" for "the kind of experiences" (two of the speaker's
    attempts joined).
- **Drafts rejected:**
  - The first draft checked only the outermost block with a 2-word cap and ignored
    ellipses. It missed changed leads aligned as two blocks or three words, and
    rejected ellipsis-marked omissions.
  - Two drafts rejected faithful real quotes: "She described…", fixed by the
    near-word check, and "…I realized…", fixed by checking ends only.
  - The first tests passed with the rule switched off. Every adversarial test now
    checks both states.
- **Kerr:** the Kerr 2026-09-13 project has none of the 5.
- **Not committed:** the corpus. The quotes include client material.

## Criteria and tests (`tests/test_swapped_word_quotes_sw.py`)

| ID | Criterion | Test | Status |
|---|---|---|---|
| SW1 | A changed lead or tail (one block, two short blocks, or three words) that also occurs nearby fails, and passed before SW. | `test_sw1_changed_first_words_fail`, `test_sw1_changed_lead_as_one_block_fails`, `test_sw1_changed_three_word_lead_fails`, `test_sw1_changed_last_word_fails` | done |
| SW2 | A true quote, an omission beside the quote's first word, an ellipsis-marked omission, an inner word between omissions, and a quote starting mid-sentence all keep full coverage. | `test_sw2_true_quote_passes`, `test_sw2_omitted_word_next_to_the_quote_passes`, `test_sw2_marked_omission_passes`, `test_sw2_inner_word_between_omissions_passes`, `test_sw2_quote_starting_mid_sentence_passes` | done |
| SW3 | Thresholds live in config; the known limit is pinned. | `test_sw3_thresholds_are_config`, `test_sw3_known_limit_unmarked_edge_omission_fails` | done |
| SW5 | A one-gap quote is not counted twice; ellipsis positions survive a repeated word. | `test_sw4_one_gap_quote_is_not_counted_twice`, `test_sw4_word_repeated_across_an_ellipsis_keeps_positions` | done |
| SW4 | No faithful real quote is rejected. | Not code-testable: the corpus measurement above (client material, not committed). | done |

## Effect on existing projects

The 5 projects with these quotes will be blocked at their next publish until their
Bowen or emphasis step is re-run:
- 2021 Webcast Feb, Jun and Oct;
- 2021 Webinar Dec (KCFC);
- the Monika Baege / Michael Kerr talk.

Extraction now drops such quotes at the verbatim check, because it shares the
predicate.
