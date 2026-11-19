---
name: retro-optimizer
description: |
  Review a completed TextPicOS task or supervisor run, identify reproducible
  friction, and triage findings into NOW, QUEUE, or DROP. Trigger only when the
  user explicitly asks for a retrospective. Do not implement queued changes
  unless the user separately authorizes implementation.
---

# Retro Optimizer

The skill observes and triages. Deterministic queue hygiene belongs to scripts.

## Workflow

1. State the completed task and review scope: content, visual work, research,
   documentation, bug fix, or configuration change.
2. Anchor the run, account, assigned tasks, modes, delivered versions, and actual results.
3. Run `PYTHONPATH=src python -m textpicos.maintenance.todo_queue lint`.
4. Read only prior retrospective records explicitly selected for this task;
   verify previous fixes with current source or contract evidence. The issue queue
   is `docs/issues/TODO.md`, registered in `config/system/source-registry.yaml`.
5. Review only dimensions relevant to the selected scope:
   contract conflict, account/mode coverage, ambiguity, persistence,
   context/load, and checkpoint effectiveness.
6. Classify findings:
   - NOW: blocks the next run or risks data loss;
   - QUEUE: important cross-file work;
   - DROP: isolated observation whose fix costs more than its value.
7. Before proposing a new queue entry, run
   `PYTHONPATH=src python -m textpicos.maintenance.todo_queue similar --title "<title>"`.
   Merge evidence into an existing root issue when a match exists.
8. Present the triage. Do not modify system files during a retrospective unless
   the user explicitly authorizes the NOW items.
9. When a persisted report is requested, use the project output path declared
   by the task and return its reference; otherwise keep the triage in the task result.
10. For explicitly authorized external feedback, follow `skills/kb-bridge/SKILL.md`
    and select `op: write-retro` through its current dispatch protocol. Read the
    parameter documentation in `skills/kb-bridge/handlers/write_retro.py` when needed.
    A bridge failure is reported and does not erase the local result.

## Scope References

- Content and visual tasks: current task goals, input references, selected methods,
  acceptance criteria, delivered versions, actual review results, and tool receipts.
- Load account or method details only when they affected the reviewed task.
- External projects, including the separate video system, are outside the default scope.

## Output

Use four short sections: NOW, QUEUE, DROP, prior-retro regression. Every finding
must include evidence and affected canonical files. Do not report aggregate
AI-flavor or weighted title scores as quality gates.
