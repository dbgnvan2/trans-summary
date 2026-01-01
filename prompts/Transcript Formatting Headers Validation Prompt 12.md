You are validating section headings for an academic lecture transcript.

TASK: Evaluate whether the heading accurately represents the section content.

EVALUATION CRITERIA:

1. TERM ACCURACY

   - Are all terms in the heading explicitly present in the transcript?
   - Check: Do a word/phrase search - is each heading term findable in the text?
   - FAIL if: Heading uses terms not present in section

2. TOPIC COVERAGE

   - Does the heading represent the primary topic(s)?
   - Check: What percentage of the section discusses the heading topic?
   - FAIL if: Heading focuses on <30% of content

3. COMPLETENESS

   - If section has multiple distinct topics, does heading reflect this?
   - Check: Count distinct topics; does heading mention all major ones?
   - FAIL if: Section has 2+ major topics but heading only mentions one

4. INTERPRETIVE NEUTRALITY

   - Does heading use speaker's own language vs. interpretive/analytical terms?
   - Check: Are terms direct quotes or paraphrases vs. analytical concepts?
   - WARN if: Heading adds analytical framework not in speaker's words

5. EMPHASIS ACCURACY
   - Does heading emphasis match content emphasis?
   - Check: If term mentioned once briefly, is it the heading focus?
   - FAIL if: Heading emphasizes minor mentions over primary content

OUTPUT FORMAT:
For each section provided, output the following block:

SECTION [Number]:
STATUS: [PASS / WARN / FAIL]

TERM ACCURACY: [Assessment]

- List each heading term
- Confirm presence in text or note absence
- Quote relevant excerpts (max 10 words per quote)

TOPIC COVERAGE: [Assessment]

- Identify primary topic(s) in section
- Estimate % of content for each topic
- Compare to heading focus

COMPLETENESS: [Assessment]

- Count distinct topics
- Note if heading captures all major topics

INTERPRETIVE NEUTRALITY: [Assessment]

- Identify analytical vs. direct terms
- Note any interpretive leaps

EMPHASIS ACCURACY: [Assessment]

- Note if emphasis is balanced or skewed

RECOMMENDATION:
[If PASS: "Heading is accurate"]
[If WARN: "Heading is acceptable but consider: [suggestions]"]
[If FAIL: "Heading should be revised. Suggested alternatives:

- Alternative 1
- Alternative 2"]

---

Validate the following sections in batch.

{batch_content}
