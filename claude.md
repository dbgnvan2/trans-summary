# trans-summary — Claude Code instructions

Python LLM pipeline for summarizing transcripts and documents. Multi-stage pipeline
with extraction, enrichment, and validation phases.

## Global standards

Read the relevant file from `~/.claude/standards/` before starting work:

| Standard | When |
|---|---|
| `learnings.md` | P2 (silent drops between pipeline stages), P5 (harden all sibling LLM calls), P9 (token/size caps in summarization) |
| `llm-integration.md` | Any prompt change, model selection, or output parsing/validation |
| `external-api.md` | Any LLM API call — timeouts, `.json()` guarding, retry logic |
| `file-maintainability.md` | Large number of doc files suggests complexity — read before adding another module |
| `security.md` | API keys in config, never in source |

## Key rules

- Pipeline stages must be independently runnable and testable.
- `config.py` is the single source for model IDs, token limits, and thresholds.
- Multiple `*_FIXES_APPLIED.md` and `CODE_REVIEW*.md` files indicate past churn — read `AGENTS.md` and `ARCHITECTURE_DESIGN.md` before making structural changes.
