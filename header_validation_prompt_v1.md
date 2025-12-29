You are validating section headings for an academic lecture transcript.

TASK: Evaluate whether the headings accurately represent their section content.

EVALUATION CRITERIA:

1. TERM ACCURACY

   - Are all terms in the heading explicitly present in the transcript?
   - FAIL if: Heading uses terms not present in section

2. TOPIC COVERAGE

   - Does the heading represent the primary topic(s)?
   - FAIL if: Heading focuses on <30% of content

3. COMPLETENESS

   - If section has multiple distinct topics, does heading reflect this?
   - FAIL if: Section has 2+ major topics but heading only mentions one

4. INTERPRETIVE NEUTRALITY

   - Does heading use speaker's own language vs. interpretive/analytical terms?
   - WARN if: Heading adds analytical framework not in speaker's words

5. EMPHASIS ACCURACY
   - Does heading emphasis match content emphasis?
   - FAIL if: Heading emphasizes minor mentions over primary content

OUTPUT FORMAT:
For each section provided, output the following block:

SECTION [Number]:
STATUS: [PASS / WARN / FAIL]

TERM ACCURACY: [Assessment]

- List each heading term
- Confirm presence in text or note absence

TOPIC COVERAGE: [Assessment]

- Identify primary topic(s)
- Compare to heading focus

COMPLETENESS: [Assessment]

- Count distinct topics
- Note if heading captures all major topics

INTERPRETIVE NEUTRALITY: [Assessment]

- Identify analytical vs. direct terms

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
