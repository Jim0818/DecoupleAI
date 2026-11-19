---
name: doc-sync
description: |
  Audit TextPicOS documentation after structural changes. Use when agents,
  roles, methods, contracts, routing, or system facts changed.
  Runs deterministic drift checks first and reports semantic conflicts for
  review. Do not use it as a bulk documentation rewriter.
---

# Doc Sync

`.agents/skills/doc-sync/` is the canonical skill. `.claude/skills/doc-sync/`
is a same-source host link managed by `textpicos.maintenance.sync_governance_skills`.

## Workflow

1. Run `PYTHONPATH=src python -m textpicos.maintenance.doc_sync_audit --json`.
2. Run `PYTHONPATH=src python -m textpicos.maintenance.sync_governance_skills check`.
3. Read only the files named by findings and the canonical source registered in
   `config/system/source-registry.yaml`.
4. Classify each difference:
   - mechanical drift: fix the generated pointer or stale reference;
   - semantic conflict: report both claims and recommend the canonical one;
   - historical text: leave unchanged when it is inside an archive.
5. Never guess counts, paths, or task dependencies. Derive them from the filesystem,
   schema, or registry.
6. After authorized edits, rerun both commands and `bash scripts/audit.sh --scope system`.

## Output

Report changed files, unresolved semantic conflicts, command results, and any
remaining audit failures. This skill does not edit external session memory and
does not automatically rewrite every documentation layer.

## Boundaries

- Canonical TODO: `docs/issues/TODO.md`, registered as `sources.issue_queue` in `config/system/source-registry.yaml`.
- Retrospective material: use the records explicitly selected by the current task; do not scan historical directories.
- Canonical project methods: `skills/`; optional host tool bundles: `.agents/skills/`. Host links follow `config/system/capabilities.json`.
- Do not edit `.claude/skills/{doc-sync,issue-fixer,retro-optimizer}` directly.
