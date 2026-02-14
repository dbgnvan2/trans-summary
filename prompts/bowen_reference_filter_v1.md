# BOWEN REFERENCE SEMANTIC FILTER
You will receive a list of extracted Bowen reference candidates.
Keep only items where the quote text itself attributes the statement to Murray Bowen / Dr. Bowen / Bowen.

## INCLUDE ONLY IF
- The quote itself includes attribution wording, for example:
- "Bowen said / wrote / thought / believed / described / referred / called ..."
- "Murray Bowen ... said / wrote / thought / believed / described / referred / called ..."
- "I remember Murray saying ..."
- "I remember talking to Murray ... He said ..."
- "To quote Bowen ..." / "This is a quote from Bowen" / "Bowen's quote" / "Bowen's comment"
- "Bowen was very clear about ..."

## EXCLUDE
- Theory-only framing: "Bowen theory says ...", "in Bowen theory terms ...", "the theory says ..."
- Mentions of "Bowen theorists" (not Murray Bowen attribution)
- Generic mentions of Bowen that do not attribute the statement to Bowen as source
- Statements attributed to someone else (e.g., "you said...", "Dr. Kerr said...")

## OUTPUT
Return only qualifying items in this exact format (one line per item).
> **Concept Descriptor:** "Continuous verbatim quote or close paraphrase."

If none qualify, return an empty response (no lines).

---
INPUT ITEMS:
{{items}}
