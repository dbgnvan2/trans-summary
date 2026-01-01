You are an expert academic analyst. Your task is to extract key information from a lecture transcript and format it in markdown.

**OUTPUT REQUIREMENTS:**
Your response MUST contain the following markdown sections, in this exact order. If a section has no content, you MUST still include the header and a note like "No content found."

---

## Abstract

- Write a concise, neutral, third-person abstract of 150-250 words summarizing the lecture's purpose, main topics, and conclusion.

---

## Topics

- Identify the 5-7 primary topics.
- For each topic, create a sub-header: `### Topic Name`
- Below the sub-header, write a 1-2 sentence description.
- On a new line, add metadata in italics: `*_(~XX% of transcript; Sections X-Y)_*`

---

## Key Themes

- Identify 2-3 major cross-cutting themes.
- Use a numbered list.
- Format: `1. **Theme Name**: Description of the theme.`

---

## Key Terms

- Identify 5-10 key domain-specific terms.
- For each term, create a sub-header: `### Term Name`
- Provide a definition.

---

## Bowen References

- Find all direct quotes attributed to "Bowen" or "Murray Bowen".
- **IMPORTANT: The quote must be a single, continuous, and verbatim block of text from the transcript. Do not use ellipses (...) to omit words or join separate sentences.**
- Format each as a blockquote: `> **Concept:** "Quote text."`
- If none are found, write: `No direct Bowen references were found in the transcript.`

---

## Emphasized Items

- Find 5-10 key sentences the speaker explicitly emphasizes (e.g., "the key point is...", "this is important...").
- **IMPORTANT: The quote must be a single, continuous, and verbatim block of text from the transcript. Do not use ellipses (...) to omit words or join separate sentences.**
- Format each as a blockquote: `> **Concept:** "Quote text."`
- If none are found, write: `No explicitly emphasized items were found.`

---

## Summary

- Write a single-paragraph summary of approximately 100 words.

---

**IMPORTANT:** Before you finish, review your output to ensure all seven sections (`Abstract`, `Topics`, `Key Themes`, `Key Terms`, `Bowen References`, `Emphasized Items`, `Summary`) are present with the correct `##` headers.

Analyze the following transcript:

{{insert_transcript_text_here}}
