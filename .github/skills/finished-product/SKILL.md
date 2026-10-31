---
name: finished-product
description: 'Create a finished product from a user request by inspecting the workspace, following local project conventions, producing the needed files or changes, and verifying that the delivered artifact is coherent and usable. Use for turning an idea, feature request, or patch into a complete, testable workspace output.'
---

# Finished Product

## When to Use
- A request needs a concrete deliverable rather than a speculative answer.
- You need to prepare code, documentation, tests, config, templates, or project artifacts.
- The workspace already has conventions and the task should follow them.

## Goal
Produce a working finished product that is specific, minimal, consistent with the repository, and supported by fresh verification evidence.

## Procedure

1. Clarify the target outcome.
   - Inspect the request and identify the deliverable shape: code, docs, tests, UI, config, dependency file, or a combination.
   - If the outcome is under-specified, ask only the questions needed to remove ambiguity.
   - Capture the acceptance signal in a way the workspace can verify later.

2. Read the workspace context.
   - Check the repository structure, existing guidance, and nearby files that define the project’s conventions.
   - Prefer project files already present over inventing a new pattern.
   - If a reusable skill, prompt, instruction, or agent template already describes the workflow, adapt it rather than starting from scratch.
   - Review the package metadata and test entrypoints, including whether the selected environment must install dependencies or the project itself in editable mode.

3. Choose the smallest useful implementation.
   - Make the fewest files and edits that satisfy the request.
   - Add tests or validation where the repository already expects them.
   - Keep changes focused on the required finished product and avoid unrelated churn.
   - Favor repository-compatible names, modules, and dependency declarations.

4. Create or update the artifact.
   - Write the implementation in the correct workspace location.
   - Follow the project’s naming, structure, and formatting conventions.
   - Preserve cross-file consistency, especially imports, references, test expectations, and documentation.
   - Preserve safety defaults when the repository has a paper-first or secure-by-default design.

5. Verify before claiming completion.
   - Run the relevant command or test that proves the product works.
   - Check syntax, diagnostics, and failing tests when applicable.
   - Prefer the workspace-selected interpreter or project’s documented command when verification depends on environment setup.
   - Report actual evidence rather than a confident guess.

6. Close with a product-quality review.
   - Compare the result against the checklist in [quality-checklist](./references/quality-checklist.md).
   - Confirm the user-facing deliverable is usable, consistent, and test-supported.

## Decision Points

- If the user request is vague, ask clarifying questions before editing files.
- If the repository already contains the right conventions, reuse them.
- If the deliverable is mostly a single-file change, keep the scope narrow and avoid speculative architecture.
- If the deliverable must be broader or multi-file, make a coherent plan and keep all edits aligned with that plan.

## Quality Criteria

A finished product is ready when:
- It addresses the original request directly.
- It respects the workspace structure and conventions.
- It includes or updates relevant tests, docs, or validation artifacts when needed.
- It has fresh evidence from a command, diagnostic, or test run showing the result satisfies the request.

## Typical Completion Pattern

1. Understand the requirement.
2. Inspect the workspace and relevant files.
3. Implement the minimal correct solution.
4. Validate with an execution or test command.
5. Report what changed and the verification evidence.

## Companion Assets

- [quality-checklist](./references/quality-checklist.md)
- [check_finished_product.py](./scripts/check_finished_product.py)
