Your task is to identify likely transcription mistakes in a domain-specific transcript corpus focused on Bowen family systems material.

Focus only on:

1. **Proper nouns**: names, places, organizations, or domain-specific named entities that are wrong in context.
2. **Homophones**: sound-alike words that are wrong in context.
3. **Spelling / non-words**: obvious malformed transcript output.
4. **Word-boundary errors**: words incorrectly split or merged.

Do not correct:

- grammar
- punctuation
- capitalization-only issues
- colloquialisms or informal speech
- stylistic awkwardness
- sentence smoothing or readability improvements

Preserve the speaker's voice. Do not add words that were probably not spoken.

Output Format:
You must output the result as a valid JSON list of objects. Do not include markdown or explanatory text. Return only the raw JSON array.

Each object must have:

- `error_type`: One of `proper_noun`, `homophone`, `spelling`, `word_boundary`
- `original_text`: The exact text segment from the transcript that contains the error. Keep it unique enough for programmatic replacement.
- `suggested_correction`: The corrected text.
- `reasoning`: Brief explanation of why this is likely a transcription error.

Example output:
[
  {
    "error_type": "proper_noun",
    "original_text": "We studied Merry Bowen in this lecture",
    "suggested_correction": "We studied Murray Bowen in this lecture",
    "reasoning": "Murray Bowen is the correct proper noun in this domain."
  }
]

If no errors are found, output an empty list: []
