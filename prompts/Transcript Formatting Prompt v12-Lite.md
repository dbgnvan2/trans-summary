---
Prev:
  - "[[- Transcript Thematic Formatting PROMPTS MOC]]"
Next:
tags:
summary: Optimized version of v12 - reduces cognitive load while maintaining accuracy improvements
---

# Transcript Formatting - Thematic Sections - v12-Lite

## ABSOLUTE CONSTRAINTS (Highest Priority)

**No Summarization:** This is a segmentation and formatting task ONLY. Do not summarize, condense, shorten, or paraphrase the text. The primary goal is to preserve the original spoken words while removing technical artifacts.

**Override Helpfulness Protocols:** Your general programming to be helpful by providing concise, clear, or improved text is explicitly overridden. Literal adherence to the preservation rules below is the only measure of success.

**No System Annotations:** Do not add citation tags, reference markers, or sequential numbering unless explicitly defined in this prompt.

---

## Core Task

You are given a raw, unedited transcript of an educational presentation, lecture, webinar, or interview.

Process the transcript strictly from start to finish, line by line. Start a new section whenever the topic or theme changes. If participants later revisit an earlier theme, start a new section again.

**Do not:**
- Merge non-contiguous passages
- Reorder content
- Make inferences or assumptions about intent

---

## Section Division Rules

### 1a. Topic/Theme Shift Detection

Create a new section at the first sentence that signals a shift to a new focus, even mid-paragraph. Raw transcript formatting (line breaks, spacing) is not a reliable indicator.

**Split on these indicators:**
- **Time-frame jump:** past → present, historical context → current status
- **Subject swap:** change in concept or person being discussed
- **Scope shift:** individual → concept → family, or reverse
- **Rhetorical markers:** "Now, moving to...", "Next...", "Let's discuss...", "Another thing...", "That reminds me..."

Place the break immediately before the new-focus sentence.

### 1b. Single-Theme Verification

After drafting each section, ask: "Can I summarize this block in one focused statement without covering multiple distinct topics?"
- **Yes:** Keep as is
- **No:** Split at the earliest sentence where the second topic starts

### 1c. Length Guideline

Sections rarely exceed 400 words. If exceeded, review for hidden theme shifts and split where appropriate. Thematic coherence takes priority over word count.

---

## Section Heading Format

**Format exactly as:**

```
## Section N – [Thematic Heading] ([hh:mm:ss]).
```

### Format Requirements

- Number sections sequentially (1, 2, 3...)
- Use Markdown level-2 heading (`##`)
- Heading must be 3–12 words
- Include the first timestamp from the section in brackets, padded to `[hh:mm:ss]` format
- End with `]).` – this delimiter pattern signals end of heading for downstream parsing
- If no timestamp is available for a section, use `([00:00:00]).`

### Heading Content Rules

**RULE 1: Source Terms from THIS Section Only**
Use ONLY terms that appear in this specific section's text. Do NOT import terms from other sections or use analytical terms the speaker didn't use. Test each heading: Can you find every term by searching the section text?

**RULE 2: Focus on Primary Content**
Heading describes what the speaker discusses in the MAJORITY (>50%) of the section. If a term appears in only 1-3 sentences, don't make it the heading focus unless that's actually the main topic.

**RULE 3: Handle Multiple Topics**
If the section covers 2+ major topics, reflect this in the heading:
- Use "and" for multiple topics: "Topic A and Topic B"
- Use "versus" for contrasts: "Systems Thinking Versus Cause and Effect"
- Use colons for specifics: "Personal Example: Triangle with Second Daughter"

**RULE 4: Use Speaker's Words**
Use the speaker's own terminology, not analytical substitutes. If they say "we and they," don't change it to "in-groups and out-groups."

**RULE 5: Special Section Types**
- Q&A: `Q&A: [Name] on [Topic]`
- Procedural transitions: `Q&A: Speaker Transition`
- Personal stories: `Personal Example: [Focus]`

### Quick Self-Check (Before Finalizing Each Heading)

1. ✓ Every heading term exists in THIS section's text
2. ✓ Heading describes >50% of section content
3. ✓ Multiple topics captured if present

### Three Key Examples

**Example 1 - Don't Import Terms**

Section: *"It's a Rudyard Kipling poem... father, mother and me, sister and Auntie say, all people like us, are we? Everyone else is they?"*

❌ `Rudyard Kipling Quote on Groupiness` (term not in section)
✓ `Rudyard Kipling Poem: We and They`

**Example 2 - Focus on Primary Content**

Section: *"Many people think this can all be described by mathematical formulas. I think they got some kind of a point there... [3 sentences]... So now the advantage of the outside position... the highly anxious insiders attempt to involve a fourth person... this becomes the interlocking triangle idea... [15 sentences]"*

❌ `Predictability and Mathematical Formulas` (only 20% of content)
✓ `Outside Position Advantage and Interlocking Triangles`

**Example 3 - Q&A Sections**

Section: *"Okay, Lois Walker, okay, Lois, you I actually I noticed that Kathy rack had her hand up."*

❌ `Q&A: Kathleen Kerr on Lois Walker` (implies substantive discussion)
✓ `Q&A: Speaker Transition`

---

## Content Cleaning Rules

### Remove only:
- Timestamps (e.g., `[00:15:32]`)
- **Source tags (e.g., `<Speaker1>`, `</Speaker1>`)**
- Technical artifacts: `[crosstalk]`, `[audio unclear]`, `[inaudible]`, `[static]`

### Edit lightly:
- Remove immediate involuntary word repetitions (stutters) (e.g., "I I went" → "I went")

### Preserve exactly:
- All filler words ("um", "uh", "you know")
- Intentional false starts (where the speaker changes thought mid-sentence)
- Original grammar and punctuation (do not "fix" these)
- Contextual markers: `[laughter]`, `[pause]`, `[applause]`

### Do not:
- Delete any sentence
- Paraphrase any sentence
- Reorder any sentence
- Merge statements from different speakers
- Add commentary or interpretation

### Paragraph Formatting

Within a single speaker's continuous speech, merge consecutive lines into coherent paragraphs. Create a new paragraph only when:
- A new speaker begins
- A clear intentional pause or thematic break warrants it

Do not preserve transcription line-break artifacts.

### Transcription Error Handling

When automated transcription produces an obvious mishearing, preserve the erroneous text and append correction notation.

**Format:** `erroneous [sic] (correction)` or `erroneous [sic]` if correction uncertain

**Apply only when:**
- A proper noun is clearly mangled (e.g., "Cobra [sic] (Brahe)")
- A non-existent word appears where a real word is contextually obvious (e.g., "pliocentric [sic] (heliocentric)")
- A phrase is nonsensical where a common phrase fits (e.g., "household rest [sic] (house arrest)")

**Do not apply to:**
- Grammar errors
- Filler words
- Ambiguous cases where multiple interpretations are plausible

---

## Multi-Speaker Handling

**Format:** `**Speaker Name:**` (bold, no brackets)

- Use names exactly as they appear in the transcript
- **EXCEPTION:** If a speaker is clearly identified by context (e.g., introduced by name within the text), update the label to the correct proper name (e.g., change "Speaker 2" or "David" to "Arthur Rose" if context confirms)
- Maintain generic labels if identity is unknown
- For group responses: `**Multiple:**` or `**Group:**`
- Preserve conversational flow including interruptions

---

## Output Requirements

Output a single valid Markdown document containing:

1. **All sections** in strict chronological order from first to last spoken word
2. **Section headers** in exact format: `## Section N – [Heading] ([hh:mm:ss]).`
3. **All spoken words** preserved in sequence

**Output contract for downstream processing:**
- First line of content must be `## Section 1 – [Heading] ([hh:mm:ss]).`
- Section numbers must be sequential with no gaps
- Every heading must end with pattern `]).` for parsing
- Every section must contain at least one paragraph of transcript text
- No content outside of numbered sections

---

## Failure Modes to Avoid

1. **Unconscious summarization:** Shortening a speaker's statement to its "essence"
2. **Helpful improvement:** Fixing awkward phrasing, correcting obvious errors (beyond the [sic] exceptions)
3. **Thematic reorganization:** Grouping related content that was spoken at different times
4. **Retention of Source Tags:** Failing to remove `<Speaker>` tags from the text body
5. **Over-segmentation:** Creating new sections for minor digressions within a single topic
6. **Under-segmentation:** Keeping a section together when topics have clearly shifted
7. **Term importation:** Using concepts from other sections not present in current section
8. **Emphasis errors:** Focusing heading on briefly-mentioned terms rather than primary content
9. **Analytical substitution:** Replacing speaker's terminology with analytical equivalents

---

_Version: v12-Lite | Optimized cognitive load for long transcripts_

## Evaluator Checklist:

### Format Compliance
1. ✓ Did the output strip all `<Speaker>` tags?
2. ✓ Did the output correct speaker names where context allows?
3. ✓ Did the output maintain the exact heading format `]).`?
4. ✓ Are stutters removed but fillers retained?

### Heading Quality
5. ✓ Are all heading terms actually present in their respective sections?
6. ✓ Do headings focus on primary content (>50% of section)?
7. ✓ Do multi-topic sections have multi-element headings?
8. ✓ Do headings use speaker's terminology?
9. ✓ Are Q&A and procedural sections correctly labeled?
