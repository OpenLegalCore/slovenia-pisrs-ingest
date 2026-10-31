# Acceptance tests

Each result records revision, environment, time/window, checks and evidence, and is PASS,
FAIL or UNKNOWN. Unknown coverage is not a successful completeness result.
Use the source contract verified for each collection; do not invent identities or exclusions.

| ID | Required evidence and success condition |
| --- | --- |
| A1 Source enumeration | Independent inventories for every required collection, verified pagination/export termination, unique IDs and totals, plus cross-collection overlap. Zero unexplained missing or duplicate identities. |
| A2 Source to PostgreSQL | Set comparison of source act/text/version IDs with stored identities. Every required item imported or individually reason-coded; source counts alone are insufficient. |
| A3 Text fidelity | Compare returned original text/HTML and independently expected content with stored versions, blocks and chunks: no unexplained omissions, duplicated text, reordered provisions or lost tables/annexes. Include nested HTML and real-source fixtures. |
| A4 Identity integrity | Correct stable act/text links, version/block/chunk relations, deterministic UUIDs and hashes. Ambiguous SOPs stay explicit until source evidence resolves them; never force a merge. |
| A5 PostgreSQL representations | Compare materialized JSON with canonical columns, including active/latest flags and act_id. Evaluate status semantics separately from legal validity and source completeness. |
| A6 PostgreSQL to Qdrant | Independent expected eligible chunk set plus full canonical ID/payload comparison. Zero unexplained missing/orphan/unsafe points or payload differences; verify vector existence/dimensions and model provenance. |
| A7 History | Record earliest/latest coverage and expected versions per act/source, not just the latest date. Demonstrate old text preservation, historical gaps/exclusions and the intended vector-history boundary. |
| A8 Repeat and failure | Same bounded input converges without duplicate identities or unnecessary embeddings. Failure/retry and concurrent-run tests preserve the checkpoint and recover partial PG/Qdrant work. |
| A9 Nightly and release | Approved immutable revision installed; actual schedule and observed timer-triggered run verified; checkpoint matches completed work; complete postflight and tested rollback. Old nightly/release retained until approved switch-over. |

## Test layers

1. Offline regressions, existing tests, lint and package build.
2. Isolated real PostgreSQL/Qdrant integration: transaction/schema contracts, payloads,
   failures and retry; simulated services are labelled as simulated.
3. Authorized upstream read-only checks: API contracts, real identities, pagination and text.
4. Approved production canary, exact readback and supervised nightly/postflight.

CI proves only the checks it executes. A reconcile PASS proves agreement with its PostgreSQL
input; it cannot discover records absent from that input. Do not claim all historical versions
must be present in pisrs_current without first defining the required archive/index behavior.
