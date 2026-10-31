# Development mandate

Improve the existing PISRS ingest; keep PostgreSQL authoritative and Qdrant derived.
The latest explicit owner instruction takes precedence over these project notes.
Read PROJECT_GOALS.md, ARCHITECTURE.md, OPERATIONS.md and ACCEPTANCE_TESTS.md as needed.

## Execution

- Before each execution batch, verify the repository remote, branch and target environment.
  A cloud checkout is not evidence of access to the production host.
- Work on a named development branch. Do not modify public main without owner approval.
- Perform ordinary inspection, isolated tests, branch edits, commits and review preparation
  autonomously within the approved task. Ask only for a missing decision or a protected action.
- Use available execution tools. If host execution is unavailable, continue repository work
  and prepare an exact handoff for a dedicated host Codex session; do not default to manual commands.
- Reuse the existing Linear records linked in PROJECT_GOALS.md. Keep their current scope,
  evidence, completion criteria and status accurate. Preserve historical findings as dated evidence.
- Make the smallest change supported by a reproduced fault or a verified source contract.
  Do not add applications, unrelated services or work in other repositories.

## Verification and protection

- Run the relevant regressions, the existing suite and required lint/build checks.
  Use the locked environment; do not regenerate uv.lock incidentally.
- Distinguish offline tests, integration tests, upstream coverage and production acceptance.
  Exit zero, matching database counts or CI success alone do not prove source completeness.
- Do not expose credentials, source documents, private endpoints or raw production logs publicly.
- Production writes, deployment/switch-over, paid embedding runs and destructive operations
  require explicit approval of a concrete reviewed action. Never reset history or force-push
  without approval. Do not replace or stop the existing nightly during preparation.
- Report what changed, the exact checks performed, unresolved findings and the next action.
  Do not describe an unexecuted test or an older supplied audit as a fresh successful run.
