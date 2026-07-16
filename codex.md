# File Maintainability Policy

## Purpose
[Confirmed] This policy defines when a source file should be considered too large, too broad, or too complex, and how to prevent refactoring debt during ongoing development.

## Core Standard
[Confirmed] Judge a file by maintainability, not by line count alone.

[Confirmed] A file is acceptable when:
- it has one clear responsibility,
- its contents are cohesive,
- changes are localized,
- functions are understandable,
- and the file is easy to test and navigate.

[Confirmed] A file should be refactored when it becomes difficult to understand, risky to modify, or responsible for multiple distinct concerns.

## Required Rules
1. [Confirmed] Keep each source file focused on one clear responsibility.
2. [Confirmed] Do not mix unrelated concerns in the same file unless there is a strong architectural reason.
3. [Confirmed] Prefer separation of:
   - UI / presentation
   - business logic
   - persistence / database access
   - API / network calls
   - parsing / transformation
   - shared utilities
4. [Confirmed] Split files by responsibility and cohesion, not by arbitrary line ranges.
5. [Confirmed] Do not create tiny fragmented files merely to satisfy a line-count target.
6. [Confirmed] Keep functions and methods simpler than files; function complexity is often a stronger warning sign than total file length.
7. [Confirmed] When modifying a file, evaluate whether the new change increases responsibility creep, coupling, or complexity.
8. [Confirmed] Refactoring must preserve behavior and should maintain or improve test coverage.

## Review Criteria
For every file created or modified, evaluate these questions:

### 1. Responsibility
[Confirmed] Can the file's purpose be described accurately in one sentence?

- Good: one clear purpose
- Bad: multiple distinct reasons to change

### 2. Cohesion
[Confirmed] Do the functions, classes, and sections naturally belong together?

- Good: related parts support the same purpose
- Bad: unrelated helpers or mixed concerns accumulate in one file

### 3. Navigation
[Confirmed] Can a developer quickly find where to make a change?

- Good: structure is obvious
- Bad: heavy scrolling, jumping, or searching is required

### 4. Complexity
[Confirmed] Are the functions readable and locally understandable?

Watch for:
- deep nesting,
- excessive branching,
- large multi-step routines,
- too many parameters,
- hidden side effects.

### 5. Abstraction Level
[Confirmed] A file should operate at a reasonably consistent level of abstraction.

- Good: high-level orchestration separated from low-level implementation details
- Bad: UI event wiring beside parsing, storage, validation, and formatting internals

### 6. Change Coupling
[Confirmed] Do unrelated changes repeatedly touch the same file?

- Good: changes are localized
- Bad: file becomes a hotspot for unrelated edits or merge conflicts

### 7. Testability
[Confirmed] Can the file be tested without large setup or broad system coupling?

- Good: clear seams and isolated behavior
- Bad: testing requires full app state, network, DB, and UI together

### 8. Dependency Load
[Confirmed] Does the file import or know about too many unrelated dependencies?

- Good: limited dependencies relevant to purpose
- Bad: file becomes a central dependency hub

## Line Count Heuristic
[Confirmed] Line count is a secondary heuristic, not the main standard.

Use these thresholds as prompts for review, not hard rules:
- under 200 lines: usually fine
- 200-400 lines: review lightly
- 400-700 lines: review carefully
- over 700 lines: strong refactor candidate

[Requires Verification] These thresholds vary by language, framework, and file type.

[Confirmed] Exceptions may include:
- generated files,
- schema/type declaration files,
- large declarative configuration files,
- tightly cohesive lookup or mapping tables.

## Mandatory Refactor Triggers
Refactor or propose refactor when any of the following is true:

1. [Confirmed] The file has more than one clear reason to change.
2. [Confirmed] Multiple unrelated concerns are being added over time.
3. [Confirmed] One or more functions have become branch-heavy, deeply nested, or hard to reason about.
4. [Confirmed] The file is difficult to test in isolation.
5. [Confirmed] The file is a repeated merge-conflict hotspot.
6. [Confirmed] A developer cannot quickly identify where a change belongs.
7. [Confirmed] The file has become a dumping ground for helpers or edge-case logic.

## Refactoring Guidance
When refactoring:
1. [Confirmed] Split by responsibility, not by arbitrary size.
2. [Confirmed] Extract stable, coherent units with clear names.
3. [Confirmed] Preserve public behavior unless the change request explicitly includes behavior changes.
4. [Confirmed] Add or update tests before and after refactoring when practical.
5. [Confirmed] Avoid introducing indirection with no readability benefit.
6. [Confirmed] Prefer a slightly longer cohesive file over multiple confusing micro-files.

## Practical Agent Behavior
When creating or modifying code:
- [Confirmed] Check whether the target file already has one responsibility.
- [Confirmed] If the change introduces a second major concern, create or use a more appropriate file.
- [Confirmed] If the file is already too broad, refactor incrementally as part of the task when safe to do so.
- [Confirmed] If full refactoring would be too disruptive, isolate the new concern and note the remaining debt explicitly.
- [Confirmed] Do not defer obvious maintainability problems indefinitely if they materially increase future cost.

## Default Decision Rule
[Confirmed] A file is acceptable if it is cohesive, understandable, and locally modifiable, even if it is not small.

[Confirmed] A file is too large when its size increases cognitive load, blends responsibilities, or makes safe modification harder.

## Compact Checklist
Before finalizing a change, verify:

- [Confirmed] One clear purpose
- [Confirmed] Cohesive contents
- [Confirmed] Readable functions
- [Confirmed] Reasonable abstraction consistency
- [Confirmed] Easy navigation
- [Confirmed] Acceptable testability
- [Confirmed] No unnecessary dependency sprawl
- [Confirmed] No obvious need to split by responsibility

## Instruction to Follow
[Confirmed] Apply this policy continuously during development, not only after a file becomes oversized.
