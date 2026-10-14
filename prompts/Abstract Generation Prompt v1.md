Abstract Generation Prompt (from abstract_pipeline.py)

You will receive a JSON object with structured data extracted from a transcript.

Generate an abstract of about {target_word_count} words — and never more than {hard_max_words_minus_one} words — as a single paragraph containing these components in sequence:

Context (1-2 sentences): Speaker, event type, subject domain
Central Argument (1-2 sentences): The opening_purpose restated as thesis; if opening_purpose is empty, state the talk's main subject instead. Unless provided the event type is always "webinar"; or "conference" if indicated in the transcript. 
Key Content (2-3 sentences): Cover the topics in the order given, stating what the speaker does with each
Conclusions (1-2 sentences): The closing_conclusion restated. If closing_conclusion is empty, leave this component out; do not say that the talk has no conclusion.
Q&A note (1 sentence, only if include_qa_note is true): What the audience asked about or discussed in the question period, as the transcript shows it
Constraints:

Third person, present tense
No citations, quotations, or section numbers
No percentages or proportions: do not say how much of the talk any part took
No evaluation of content quality
No bullet points or lists
Preserve technical terminology from input
Hard length limit: the abstract must be under {hard_max_words} words
Output only the abstract paragraph—no headers, labels, or commentary
Input data:
{input_json}