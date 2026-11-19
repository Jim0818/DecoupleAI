---
name: issue-fixer
description: |
  Implement verified TextPicOS issues in dependency-ordered batches. Use when
  the user asks to fix TODO items, drain the issue queue, or execute an approved
  system plan. Do not trigger for status questions or retrospective discovery.
---

# Issue Fixer

Treat every TODO statement as a hypothesis until the repository confirms it.

## Workflow

1. Read `sources.issue_queue` from `config/system/source-registry.yaml`,
   which points to `docs/issues/TODO.md`, or use the user-provided issue file. Fail if the selected source is missing.
2. Run `PYTHONPATH=src python -m textpicos.maintenance.todo_queue lint`.
3. Verify each claim against current schemas, scripts, prompts, and artifacts.
4. Merge issues that share one protocol-level root cause.
5. Order implementation by dependency:
   canonical contract, deterministic runtime, consumers, documentation, audit.
6. Persist a plan using the task/plan capability available in the current host.
   If no task tool exists, maintain a short checklist in the response or an
   explicitly requested plan file.
7. Execute when the user requested implementation. Pause for approval only when
   the user requested planning or the change is destructive/irreversible.
8. After every batch, run focused tests, residual-keyword searches, and
   `bash scripts/audit.sh --scope system`; update the TODO progress immediately.

## Rules

- Do not implement a stale TODO literally.
- State machines, counters, validation, routing, and registries belong in code.
- Do not hand-edit `.claude` governance Skill host links.
- Preserve unrelated user changes.
- Historical documents may retain old terms when clearly archived.
- A batch is complete only when its mechanism, tests, docs, and queue status
  agree.

## Output

Summarize verified root causes, implemented batches, tests, remaining failures,
and exact canonical files. Avoid host-specific tool names in persisted plans.
