# PIKI PISRS staging master

Owner mandate, 2026-11-16. Build a new permanent staging ingest on PIKI for test users and keep Medo as independent legacy production. Archive all documented, authorized and retrievable PISRS records, legal texts and observable history in PostgreSQL. Publish the separately approved derived Qdrant index and verify scheduled source→PG and PG→Qdrant parity independently.

**Status 2026-11-16.** The owner approved the [minimal topology](PIKI-PISRS-ARCHITECTURE.md) and [historical index policy](PIKI-PISRS-DATA.md#qdrant-contract). G0 and G1 remain open. Final G2 and G3 authorization remain open. G3–G5 are NOT_RUN. Full enumeration, parity and source-wide history are G3 tests.

## Canonical documents

| Document | Authority |
|---|---|
| [API](PIKI-PISRS-API.md) | Official operations, parameters, schemas and observed source behavior |
| [Environment](PIKI-PISRS-ENV.md) | PIKI measurements, access and credential evidence |
| [Architecture](PIKI-PISRS-ARCHITECTURE.md) | Proposed runtime, service topology, paths and network |
| [Data](PIKI-PISRS-DATA.md) | Proposed PG schema, OpenAPI field matrix and Qdrant contract |
| [Synchronization](PIKI-PISRS-SYNC.md) | Initial capture, resume, nightly, embeddings and publication rules |
| [Operations](PIKI-PISRS-OPERATIONS.md) | Future release, runtime, backup, restore and incident work |
| [Acceptance](PIKI-PISRS-ACCEPTANCE.md) | Evidence and closure conditions |
| [Audit](PIKI-PISRS-AUDIT.md) | Independent source/Git findings and review rationale |

[Linear project](https://linear.app/openlegalcore/project/pisrs-complete-source-to-index-synchronization-b47e7deb7c78) and [OLC-91](https://linear.app/openlegalcore/issue/OLC-91/pisrs-piki-g0-g2-credentials-uradni-openapi-in-ciljna-postgresql) record active decisions and evidence. OLC-85 belongs to the legacy record.

## Scope and gates

Integrate the official authorized catalogue, projection, code-list and state text scope. Record accessible state base and NPB versions with original bytes and independent legal-date/identity fields. Archive local and EU metadata, record any unsupported text by scope and seek owner approval separately before adding another source. Project installation, persistence, temporary work and backup on PIKI belong under `/data`, with only source checkout and essential OS configuration eligible for the system disk. Build no frontend, Engine/case-law changes, or parallel deployment.

| Gate | Output and prerequisite | Status |
|---|---|---|
| G0 Environment and entitlement | Confirm effective Docker root, volumes and no collisions, issuer-approved PIKI use and cadence, owner-approved role and ingress plans and independent backup destination. Schedule target-dependent role tests for first G3 preflight. | NOT ACCEPTED. /data host readback PASS. Effective store roots/binds, allowed source envelope, and independent recovery target/rights open. |
| G1 Source contract | Verified official OpenAPI, bounded early and terminal paging controls or equivalent issuer evidence, bounded required text identity and relation rules, and documented scope/unknowns. | NOT ACCEPTED. Prior spec and 26 GET samples on record. New targeted controls NOT_RUN, 0/21; secure operator credential context unavailable in this session. No full scan is required for G1. |
| G2 Data and release design | Reviewed minimality and preserved field/storage matrix, exact sync/acceptance plan, accepted index legal-date, history and maintenance policy, and approved G3 sequence. | OWNER DECISIONS APPROVED. Await G0/G1 evidence, recovery target and RPO/RTO agreement, final G2 acceptance and separate G3 authorization. |
| G3 Permanent staging and source→PG | Owner-approved setup, role/privilege and recovery preflight, authorized full read, byte-level/projection/history parity and tested resume. | NOT_RUN. |
| G4 Cost and PG→Qdrant | Local tokenizer over actual chunks, frozen plan and rate, separate paid approval then exact manifest parity. | NOT_RUN. |
| G5 Nightly and user acceptance | Actual timer-run evidence, approved alerts, security, isolation and backup restore, read-only user acceptance. | NOT_RUN. |

Use distinct denominator and verification time for each catalogue, source text, normalized text, history and index claim. Report unresolved required cases; only audited exceptions with reasons are eligible for coverage. Before G3 the allowed activities are bounded authorized reads, evidence and design. G3 requires explicit owner acceptance. G4 paid requests require separate explicit owner approval after measured PG token cost.

## Next action

Run the [single operator handoff](PIKI-PISRS-ENV.md#operator-terminal-handoff) and append its sanitized statuses, the issuer-grant finding and the recovery decision to OLC-91. The owner can then review the remaining gate evidence. Stop before G3 until explicitly authorized.
