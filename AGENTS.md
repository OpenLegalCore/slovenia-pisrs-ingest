# AGENTS.md — PISRS ingest

These instructions apply to all work in **this repository only**:
`OpenLegalCore/slovenia-pisrs-ingest`. They do not govern any other repository.

## Current authorization: HOLD

The owner has paused product development. The present documentation consolidation is an
explicit exception. Do not resume implementation, deployment, source collection, or
production operations until the owner explicitly authorizes that activity. A green
build, a prior approval for a different task, or a Linear status is not authorization.

## One product, one objective

Deliver and maintain a **small, reliable, understandable production PISRS ingestion
program**, not a platform. The required result is legally accessible PISRS source
catalogs and historical versions, their available text in PostgreSQL
(`appdb`, schema `pisrs`), all eligible text vectors in Qdrant
(`pisrs_current`), and verified ongoing nightly synchronization. For missing
source text, preserve a reason rather than inventing content.

Required source investigation includes the 13 documented PISRS API catalogs,
available history, and the legitimately accessible Official Gazette. Case law,
`lexai-engine`, Engine/LWS, their infrastructure, and unrelated systems are out
of scope.

## Sources of authority (do not duplicate them)

- **Product scope, acceptance, and permissions:** [PISRS project contract](https://linear.app/openlegalcore/document/pisrs-projektna-pogodba-source-to-index-completeness-9d8c57fb5c81).
- **Only backlog and historical evidence:** [Linear PISRS project](https://linear.app/openlegalcore/project/pisrs-complete-source-to-index-synchronization-b47e7deb7c78), including existing OLC-77 through OLC-85 issues.
- **Only code/PR/CI authority:** this GitHub repository and its protected `main`.
- **External source contract:** [official PISRS API documentation](https://pisrs.si/swagger/navodila).

Read the applicable existing Linear issue and evidence before doing work. Keep dated
measurements and incident details in that issue, **not in AGENTS.md or README.md**.

## Mandatory anti-drift workflow

1. Identify **one measured product gap** in the existing Linear backlog. State
   how closing it improves source -> PostgreSQL -> Qdrant -> nightly correctness.
2. Take the **shortest safe path** using the existing code. Prefer a focused fix
   to new modules, schemas, services, abstractions, or infrastructure. Investigate
   only unknowns that directly block that fix.
3. Reuse passing evidence. Run only the smallest tests needed for the change and
   the existing required CI. Never launch a new generic audit or repeat a completed
   one without a specific invalidating change.
4. After an authorized activation, verify its **effect on actual source/PG/Qdrant
   data and nightly behavior**. Do not stop at a successful patch, PR, merge, tag,
   wheel, test suite, or staging artifact.
5. Report concisely: **what works, what is missing, one next action**. Use
   `PASS`, `FAIL`, `UNKNOWN` with evidence and timestamps. A code PASS is
   never a production-completeness PASS.

No subagents, speculative security projects, broader refactors, platform-building,
unnecessary packaging, or unrelated reviews. Do not turn an operator-specific
obstacle into a cross-project networking/firewall exercise. The owner confirms
that the PISRS ingest is the only writer to `pisrs_current`; do not investigate
Engine/LWS as hypothetical competing writers without new evidence and a request.

Codex work on the owner's host should use one bounded, directly executable
`/goal` when actually needed; this chat has no access to that host's terminal.
Do not waste the Codex weekly budget on work achievable through connected tools.

## Approval boundary

Require specific owner authorization before authenticated bulk PISRS API reads,
production PostgreSQL/Qdrant writes, paid embeddings, `nightly`, backfill,
`reconcile --apply`, checkpoint/timer/service changes, deployment, or Git
merges/releases. Approval is scoped to the named action; do not add artificial
confirmation rounds inside that scope. Codex security prompts may require direct
owner approval. Never rewrite public Git history or existing release tags.

Apply only necessary protections for the approved operation (a suitable backup,
rollback/readback, lock/preflight where relevant). Do not launch independent
infrastructure work. Represent secret presence only as `SET`/`UNSET`;
never expose credentials, private DSNs, or raw sensitive evidence.

Public documentation and code: **English**. Owner-facing communication:
**Slovenian**. Prefer the smallest suitable model (Luna for routine inspection,
Sol High for API/code/integrity; Astra only with demonstrated need).
