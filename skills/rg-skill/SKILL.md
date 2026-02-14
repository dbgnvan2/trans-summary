---
name: rg-skill
description: Fast trigger for Python regression hardening workflows. Use when the user says "Run RG skill" or wants quick failing-test-first regression coverage for a Python repository, including targeted pytest updates, focused verification, and risk reporting.
---

# RG Skill

## Goal
Provide a short, easy invocation alias for regression-focused testing work.

## Invocation Pattern
- Preferred user command: `Run $rg-skill on <repo-path> for <bug/regression>`
- If details are missing, infer practical defaults and proceed.

## Workflow
1. Reproduce the bug first
- Add or update a failing pytest that captures the regression.

2. Add regression protection
- Implement focused tests for nearby edge cases.
- Reuse existing fixtures and project test style.

3. Verify quickly
- Run targeted pytest scope first.
- Run broader tests only when needed.

4. Report
- Return PASS/FAIL test outcomes.
- List touched tests/files.
- Note remaining risk gaps.

## Scope
- Designed for Python repositories.
- For `trans-summary`, align with existing markers/tooling (`live_api`, `integration`, `ruff`) and default to offline-safe checks.
