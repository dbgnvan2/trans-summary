# Plan: who-said-what in transcripts without speaker labels (SA) — 2026-10-12

Status: **built 2026-10-12.** Approved, then revised by the user's note. Results:
`docs/calibration_speaker_attribution_2026-10-12.md`.

## Problem

The source for "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13" has
no speaker labels, so the formatted transcript has none either. The summary writes "The
interviewer observes…", "The interviewer cites…". Without labels the transcript can't
show who said what, and the judge sometimes marks these sentences "contradicted". It
passes or fails them by chance:
- 16:18 run: the summary passed at generation (attempt 2/3).
- 17:44 run: the same file was re-judged at publish and failed ("contradicted"), which
  blocked publication.
- 20:02 re-run: attempt 2 failed on "The interviewer describes self-differentiation as a
  scale…". Attempt 3 passed, and the saved summary still has three "The interviewer …"
  sentences.

Why the publish step re-judged a file that had passed: commit 1c0e98f added `_theme_body`
and `_is_theme_block` to the judge input functions. That changed the judge cache key, so
every claim was judged again.

## Decision (user, 2026-10-12)

"The interviewer" is a neutral term. Without speaker labels, saying that the interviewer
(or the speaker / interviewee) said something should not fail. The first version of this
plan stopped the writers from using these roles. That version is withdrawn. The writers
are not changed; the judge is.

## Approach (as built)

1. **Detect the missing labels.** `transcript_utils.has_speaker_labels(text)` is True
   when at least `config.SPEAKER_LABEL_MIN_TURNS` (2) lines start with a speaker label.
   - Accepted shapes: `**Name:**`, `**Name**:`, `__Name:__`, `*Name:*`, `_Name:_`, or a
     plain `Name:` of up to four capitalised words.
   - The label may be indented or follow `> ` or `- `.
2. **Tell the judge.** `release_gate.with_recording_metadata` adds
   `config.UNLABELED_SPEAKERS_NOTE` to the judge's source when there are no labels.
   This also happens when the file name gives no metadata.
3. **Rule only with the note.** `faithfulness_judge.instructions_for(source)` adds
   `_SPEAKER_RULE` before the reply format only when the source has the note.
   - A labelled transcript gets exactly the old prompt. An always-on first version
     judged a labelled blog more strictly.
   - The rule covers a claim that a participant in the conversation said grounded
     content, when the source does not show who said it.
   - The participant must exist in the recording.
   - The content must be in the source.
   - The stance must be kept: a view the source shows being questioned or rejected
     can't be presented as that participant's own.
   - Context that does show the speaker is still used.
   - Attribution to people outside the conversation is judged as before.
4. **FQ (found during measurement).** The first sentence under a question heading (FAQ
   entries, question-style section titles) is judged with its question attached. A
   marker is put on the answer line before the layout strip
   (`faithfulness_judge._mark_question_answers`), so no line is matched by content. The
   ungrounded-name check ignores the attached question (`_claim_body`). The overview
   sentence "According to Michael Kerr, it does not." was flagged on first pass in
   17 of 20 runs and blocked 2 of them, because the question heading was stripped.
5. **Review fixes.**
   - D2 flags now match on the artifact and model, not the source text
     (`release_gate._flag_identity`).
   - A PASS that relied on the note says so in its verdict detail
     (`_speaker_note_suffix`).
   - The gold harness, the drift monitor and the live calibration test build sources
     as the gate does (`judge_recalibration.gold_sources`).
6. **Cache key.** `JUDGE_LOGIC_VERSION` is 2026-10-12e. The following are hashed into
   the key:
   - the rule text, the label pattern, the threshold and the note;
   - `has_speaker_labels`, `with_recording_metadata`, `instructions_for`,
     `_mark_question_answers`, `_claim_body` and `_clean_claim_line`, and the two
     marker patterns.
7. **Chunk windows use the base prompt** (second review). A window sees part of the
   recording and its "entailed" is final, while the rule's role and stance tests need
   the whole source. A claim a window does not entail is judged again on the full
   source, with the rule.

## Acceptance criteria and tests (`tests/test_speaker_attribution_sa.py`)

| ID | Criterion | Test | Status |
|---|---|---|---|
| SA1 | Labels detected in labelled fixtures (Where Roots, older Why Families), not in unlabeled ones (Societal, Systems Biology). | `test_sa1_detects_labels_in_fixtures` | done |
| SA1.a | Adversarial: one `**Note:**` line or inline bold is not a label set. | `test_sa1a_single_or_inline_bold_is_not_labels` | done |
| SA1.b | Other label shapes count as labels; lower-case prose before a colon does not. | `test_sa1b_other_label_shapes_count_as_labels` | done |
| SA2 | Note added only without labels, also without filename metadata; PASS detail records it. | `test_sa2_note_added_only_without_labels`, `test_sa2_note_without_filename_metadata`, `test_sa2_pass_detail_records_note` | done |
| SA3 | Rule only with the note; it requires a real role, content in the source and the same stance. | `test_sa3_rule_only_with_note`, `test_sa3_prompt_rule_present` | done |
| SA4 | Cache key covers version, functions, threshold, note and rule text. | `test_sa4_cache_key_covers_label_logic`, `test_sa4_threshold_and_note_change_the_key`, `test_sa4_rule_text_changes_the_key` | done |
| SA5 | Gold sources built as the gate builds them; SA gold cases sa1–sa5; a source without a base name is an error. | `test_sa5_gold_sources_built_as_the_gate_builds_them`, `test_sa5_gold_source_without_base_is_an_error` | done |
| SA6 | Dirty state: a flag set before the note still needs two PASSes after it. | `test_sa6_flag_survives_source_note` | done |
| FQ | Answer openers carry their question; non-question headings don't; the answer's words are kept; an earlier identical sentence doesn't take the tag; bold-label, numbered and list answers are tagged; a name in the question is still judged on its own. | `test_fq_answer_opener_carries_question`, `test_fq_non_question_heading_and_empty_answer_do_not_tag`, `test_fq_tag_goes_to_the_answer_not_an_earlier_twin`, `test_fq_answer_with_bold_label_or_number_is_tagged`, `test_fq_name_in_question_heading_is_still_judged`, `test_fq_tag_keeps_the_answer_content`, `test_fq_functions_in_cache_key` | done |
| SA8 | Chunk windows use the base prompt; the full-source re-judge gets the rule. | `test_sa_chunk_windows_use_base_prompt` | done |
| SA7 | Real measurement, old vs new, same day. | not code-testable; `docs/calibration_speaker_attribution_2026-10-12.md` | done |

## Adjacent issues found, not fixed

- **Any change to the judge's input functions re-judges every saved artifact.** So a
  borderline claim that passed can later block an artifact that hasn't changed. This is
  by design: a logic change must re-verify. Logged in TODO.
- **Only the first chunk window carries the note.**
  - `chunk_source` splits the full source into word windows. The first window
    starts with the metadata and the note; the later windows don't.
  - A claim a window does not entail is judged again on the full source, which has
    the note. So the final verdict always sees it; only cost is affected.
- **Q&A-only labels.** A lecture whose labels appear only in its Q&A (Where Roots: 3
  labels) counts as labelled, so its lecture part gets no note. That is the stricter
  side.
