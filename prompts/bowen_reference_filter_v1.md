# BOWEN REFERENCE SEMANTIC FILTER
You will receive a list of extracted Bowen reference candidates.
Keep **only** items that explicitly attribute the quote or paraphrase to **Murray Bowen**.

## INCLUDE ONLY IF
The quote **explicitly** attributes the idea to Murray Bowen, e.g.:
- “Bowen said / wrote / thought / believed / described / referred / called …”
- “Murray Bowen … said / wrote / thought / believed / described / referred / called …”
- “This was an idea / insight / concept / discovery of Bowen”
- “This is a quote from Bowen” / “Bowen’s quote”

## EXCLUDE
- Generic mentions of “Bowen” or “Bowen theory” without explicit attribution
- Quotes about Bowen or his influence without attributing a specific idea to him
- Statements attributed to someone else (e.g., “you said…”, “Dr. Kerr said…”, “he said…” without naming Bowen)

## OUTPUT
Return only qualifying items in this exact format (one line per item).
The quoted text must include the attribution clause (e.g., “Bowen said…”, “Murray Bowen…”, “To quote Bowen…”). If the attribution is missing from the quote text, **exclude** the item.
> **Concept Descriptor:** "Continuous verbatim quote or close paraphrase."

If none qualify, return an empty response (no lines).

---
INPUT ITEMS:
{{items}}
