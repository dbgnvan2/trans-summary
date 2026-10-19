Summary Generation Prompt (from summary_pipeline.py)

You have been provided with the **FULL TRANSCRIPT** in the system message.
You will receive a JSON object below with structural metadata (word targets, topic list).

**LENGTH REQUIREMENT:**
This summary should be approximately {opening_words} + {body_words} + {qa_words} + {closing_words} words total (target: {target_word_count} words).
Write between {min_words} and {max_words} words. Aim for the target.

**TASK:** Generate a rich, detailed, and cohesive summary of the transcript.
**SOURCE:** You MUST use the **FULL TRANSCRIPT** (system message) as the primary source for all content, details, and examples.
**APPROACH:** Write comprehensive prose with specific examples, evidence, and details from the transcript. Balance detail with conciseness to meet the word count target.

Follow this structure (aim for the word counts shown):

### Opening Paragraph (~{opening_words} words)
Identify the speaker by the name the transcript or recording title gives. Give credentials or a role only if the transcript states them; do not add them from other knowledge. Give the event context and the purpose the speaker states. You may say what the talk covers, but say the speaker previews or outlines it only if the speaker does.

### Body Section (~{body_words} words - the main content)
Write a comprehensive narrative synthesis covering all topics.
*   Include specific examples, evidence, and detailed explanations from the transcript
*   **Use the `body.topics` list in the JSON only as a checklist** of areas that must be covered
*   **Mine the transcript** for details, quotes, examples, and evidence
*   Weave in the Interpretive Themes to deepen the analysis
*   Write naturally to capture the flow of ideas

### Q&A Section (~{qa_words} words, {qa_instruction})
If included: Summarize key questions and interaction types. Highlight 1-2 notable exchanges or insights.

### Closing Paragraph (~{closing_words} words)
End with the speaker's own conclusion, open questions or future directions, if the speaker gives them near the end of the talk. If the talk ends without them (it stops at a break, in the middle of a discussion, or with thanks and goodbyes), close by restating the main point the speaker makes in the talk, without saying that it comes at the end. In both cases, add no conclusion, open question or future direction of your own, and do not say that the talk has no conclusion. The `closing` fields in the JSON come from a phrase search and are often empty or wrong; take the closing from the transcript.

**Constraints:**
*   Third person, present tense.
*   Chronological narrative flow.
*   No citations (e.g. "Section 1 says...").
*   No bullet points.
*   No outside facts: state only what the transcript and the recording title give. Do not spell out an abbreviation the transcript does not spell out, and do not add a first name, age, place, occupation, affiliation or family fact (such as that someone has died) that the transcript does not state, even if you know it.
*   **Length:** Aim for about {target_word_count} words total ({min_words}-{max_words}). Include specific details, examples, and evidence from the transcript.

Input data:
{input_json}
