# PIKI PISRS staging master

Owner mandate, 2026-11-16. Build a new permanent staging ingest on PIKI for test users and keep Medo as independent legacy production. Archive all documented, authorized and retrievable PISRS records, legal texts and observable history in PostgreSQL. Publish the separately approved derived Qdrant index and verify scheduled source→PG and PG→Qdrant parity independently.

**Status: review candidate. G0–G2 remain unaccepted. G3–G5 remain NOT_RUN.** The public OpenAPI bytes and operation/property inventory are independently verified. The bounded authorized GET evidence is recorded. Complete enumeration, source-wide history and exact legal linkage rules remain open. See [Audit](PIKI-PISRS-AUDIT.md).

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
| G0 Environment and entitlement | Confirm effective Docker root, volumes and no collisions, issuer-approved PIKI use and cadence, owner-approved role and ingress plans and independent backup destination. Schedule target-dependent role tests for first G3 preflight. | NOT ACCEPTED. Host PASS for bounded readout. Privileged inventory, grant, service scopes and recovery destination open. |
| G1 Source contract | Verified official OpenAPI and record of bounded authorized observations, reviewed coverage/terminal method, tested ID/relationship scope, legal/format limitations clearly dispositioned. | NOT ACCEPTED. Spec 27/27 documented, 26/26 GET samples on record; full terminal and lineage semantics unresolved. |
| G2 Data and release design | Reviewed field and storage matrix, exact sync/acceptance plan, accepted index history/version policy, verified release strategy and approved G3 sequence. | PROPOSED. Await G0/G1 readiness and owner approval. |
| G3 Permanent staging and source→PG | Owner-approved setup, role/privilege and recovery preflight, authorized full read, byte-level/projection/history parity and tested resume. | NOT_RUN. |
| G4 Cost and PG→Qdrant | Local tokenizer over actual chunks, frozen plan and rate, separate paid approval then exact manifest parity. | NOT_RUN. |
| G5 Nightly and user acceptance | Actual timer-run evidence, approved alerts, security, isolation and backup restore, read-only user acceptance. | NOT_RUN. |

Use distinct denominator and verification time for each catalogue, source text, normalized text, history and index claim. Report unresolved required cases; only audited exceptions with reasons are eligible for coverage. Before G3 the allowed activities are bounded authorized reads, evidence and design. G3 requires explicit owner acceptance. G4 paid requests require separate explicit owner approval after measured PG token cost.

## Next action

Review this candidate with the owner and record one OLC-91 decision identifying the approved source envelope, scope decisions and the evidence required to sign G0–G2. The issuer's PIKI use/rate and enumeration boundary, the protected host operator's Docker/backup proof, and the index history policy are the outstanding inputs.
