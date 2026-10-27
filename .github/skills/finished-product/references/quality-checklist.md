# Finished Product Quality Checklist

Use this checklist before reporting that a finished product is ready.

## Discovery
- The request has been translated into a concrete deliverable shape.
- Ambiguities that materially affect the product were clarified.
- Existing workspace patterns or conventions were inspected before writing new code.

## Implementation
- The change is concise and scoped to the request.
- The right files and artifacts were created or updated.
- Imports, naming, module boundaries, and cross-file references remain consistent.
- Tests, docs, or validation artifacts were included where the repo expects them.

## Verification
- A command or test run proves the artifact works in the selected environment.
- The verification command was executed after the implementation was written.
- If a test failed, the failure was inspected before claiming completion.

## Reporting
- The summary states exactly what changed and why.
- Any remaining uncertainty, environment dependency, or follow-up risk is disclosed.
- Evidence from the verification command is included, not just a confident inference.
