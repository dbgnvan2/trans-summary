Abstract Generation Prompt (from abstract_pipeline.py)

You will receive a JSON object with structured data extracted from a transcript.

Generate an abstract of about {target_word_count} words — and never more than 249 words — as a single paragraph containing these components in sequence:

Context (1-2 sentences): Speaker, event type, subject domain
Central Argument (1-2 sentences): The opening_purpose restated as thesis. Unless provided the event type is always "webinar"; or "conference" if indicated in the transcript. 
Key Content (2-3 sentences): Cover the topics in order, stating what the speaker does with each
Conclusions (1-2 sentences): The closing_conclusion restated
Q&A note (1 sentence, only if qa_percentage > 20): Mention qa_topics
Constraints:

Third person, present tense
No citations, quotations, or section numbers
No evaluation of content quality
No bullet points or lists
Preserve technical terminology from input
Hard length limit: the abstract must be under 250 words
Output only the abstract paragraph—no headers, labels, or commentary
Input data:
{input_json}