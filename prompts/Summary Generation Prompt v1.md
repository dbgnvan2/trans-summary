Summary Generation Prompt (from summary_pipeline.py)

You will receive a JSON object with structured data extracted from a transcript, including word allocations for each section.

Generate a summary as continuous prose with clearly separated paragraphs following this structure:

Opening Paragraph (~{opening_words} words)

Identify speaker with credentials
State event type and context
Present the stated_purpose as thesis
Preview major content areas (referencing the 'topics')
Body Paragraphs (~{body_words} words total)
For each topic in order:

Allocate approximately the specified word_allocation to each topic
State what the speaker addresses
Include 2-3 key points
Weave in the Key Themes where relevant to connect topics or deepen analysis
Connect to next topic with transitional phrase
Q&A Paragraph (~{qa_words} words, {qa_instruction})

State types of questions
Mention 1-2 notable exchanges
Closing Paragraph (~{closing_words} words)

State the conclusion
Mention open questions and future direction if present
Constraints:

Third person, present tense
Chronological order—do not reorganize
No citations, quotations, or section numbers
No evaluation of content quality
No bullet points or lists
Preserve technical terminology
Output only the summary paragraphs—no headers or commentary
Input data:
{input_json}

