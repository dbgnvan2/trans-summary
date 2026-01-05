Your task is to identify and correct transcription errors in the provided text.
The text is a transcript of a spoken presentation or conversation.

Focus on:

1.  **Phonetic errors**: Words that sound similar but are wrong in context (e.g., "their" vs "there", "system" vs "cistern").
2.  **Typos/Spelling**: Obvious misspellings.
3.  **Punctuation**: Only if it significantly alters meaning or makes the text unreadable.
4.  **Missing words**: Where the sentence is clearly broken.

**Do NOT correct:**

- Colloquialisms or informal speech patterns (e.g., "gonna", "kinda") unless they obscure meaning.
- Grammar that reflects the speaker's actual voice, even if technically incorrect.
- Speaker labels or timestamps.

**Output Format:**
You must output the result as a **valid JSON list** of objects. Do not include any markdown formatting (like `json ... `) or preamble/postscript text. Just the raw JSON array.

Each object in the list must have:

- `error_type`: One of "spelling", "phonetic", "punctuation", "grammar", "other".
- `original_text`: The **exact** text segment from the transcript that contains the error. This must match character-for-character so it can be programmatically replaced. Keep it short (3-10 words) to ensure uniqueness if possible, but long enough to be unique.
- `suggested_correction`: The corrected text.
- `reasoning`: Brief explanation of why this is an error.

**Example Output:**
[
{
"error_type": "phonetic",
"original_text": "the affect of the system",
"suggested_correction": "the effect of the system",
"reasoning": "'Effect' is the noun required here."
}
]

If no errors are found, output an empty list: `[]`.
