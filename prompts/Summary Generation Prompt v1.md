Summary Generation Prompt (from summary_pipeline.py)

You have been provided with the **FULL TRANSCRIPT** in the system message.
You will receive a JSON object below with structural metadata (word targets, topic list).

**LENGTH REQUIREMENT:**
This summary should be approximately {opening_words} + {body_words} + {qa_words} + {closing_words} words total (aim for 650-750 words).
Summaries under 600 words will be rejected. Aim to be thorough but stay reasonably close to the target.

**TASK:** Generate a rich, detailed, and cohesive summary of the transcript.
**SOURCE:** You MUST use the **FULL TRANSCRIPT** (system message) as the primary source for all content, details, and examples.
**APPROACH:** Write comprehensive prose with specific examples, evidence, and details from the transcript. Balance detail with conciseness to meet the word count target.

Follow this structure (aim for the word counts shown):

### Opening Paragraph (~{opening_words} words)
Identify speaker with credentials, event context, stated purpose, and preview of content areas.

### Body Section (~{body_words} words - the main content)
Write a comprehensive narrative synthesis covering all topics.
*   Include specific examples, evidence, and detailed explanations from the transcript
*   **Use the `body.topics` list in the JSON only as a checklist** of areas that must be covered
*   **Mine the transcript** for details, quotes, examples, and evidence
*   Weave in the Key Themes to deepen the analysis
*   Write naturally to capture the flow of ideas

### Q&A Section (~{qa_words} words, {qa_instruction})
If included: Summarize key questions and interaction types. Highlight 1-2 notable exchanges or insights.

### Closing Paragraph (~{closing_words} words)
State the conclusion, open questions, and future directions.

**Constraints:**
*   Third person, present tense.
*   Chronological narrative flow.
*   No citations (e.g. "Section 1 says...").
*   No bullet points.
*   **Length:** Aim for 650-750 words total. Include specific details, examples, and evidence from the transcript. Summaries under 600 words will be rejected, but avoid significantly exceeding 800 words.

Input data:
{input_json}

