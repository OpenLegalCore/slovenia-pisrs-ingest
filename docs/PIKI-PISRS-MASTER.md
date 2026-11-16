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
| G0 Environment and entitlement | Confirm effective Docker root, volumes and no collisions, issuer-approved PIKI use and cadence, owner-approved role and ingress plans and independent backup destination. Schedule target-dependent role tests for first G3 preflight. | **PARTIAL / NOT ACCEPTED.** Owner-run sudo readback: Docker effective `/data/docker` overlayfs, no current Docker containers, `/data` 402 GiB free. Reserved /data paths conflict-free in the targeted filesystem read. Effective containerd root, issuer grant and owner recovery decision remain open; actual roles are G3/G4 preflight. |
| G1 Source contract | Verified official OpenAPI, bounded early and terminal paging controls or equivalent issuer evidence, bounded required text identity and relation rules, and documented scope/unknowns. | **PARTIAL / NOT ACCEPTED.** Spec/26 GET previously verified; owner-run 17/21 plus **24/24 new GETs, all HTTP 200**. **All three local catalogue endpoint stop-boundary pilots PASS_BOUNDED** (op17 last 1997/19 rows, op19 last 3/36 rows, op21 last 507/11 rows; repeated controls stable). Full source membership/parity is G3. Official references now identify the ZDR-1 version markers, the real ZVPot-1 CELEX edge and code 13022. Archived HTML attribution and exact CELEX/dictionary API controls still await evidence; new protected calls 0/3. |
| G2 Data and release design | Reviewed minimality and preserved field/storage matrix, exact sync/acceptance plan, accepted index legal-date, history and maintenance policy, and approved G3 sequence. | OWNER DECISIONS APPROVED. No additional design blocker identified beyond the targeted G0/G1 evidence and proposed recovery agreement. Final G2 acceptance and explicit G3 authorization remain separate. |
| G3 Permanent staging and source→PG | Owner-approved setup, role/privilege and recovery preflight, authorized full read, byte-level/projection/history parity and tested resume. | NOT_RUN. |
| G4 Cost and PG→Qdrant | Local tokenizer over actual chunks, frozen plan and rate, separate paid approval then exact manifest parity. | NOT_RUN. |
| G5 Nightly and user acceptance | Actual timer-run evidence, approved alerts, security, isolation and backup restore, read-only user acceptance. | NOT_RUN. |

Use distinct denominator and verification time for each catalogue, source text, normalized text, history and index claim. Report unresolved required cases; only audited exceptions with reasons are eligible for coverage. Before G3 the allowed activities are bounded authorized reads, evidence and design. G3 requires explicit owner acceptance. G4 paid requests require separate explicit owner approval after measured PG token cost.

## G3 transition checklist

| When | Required proof or action |
|---|---|
| Before G3 authorization | Confirm effective containerd root and fit of the reserved PIKI paths; accept the independently recoverable destination, access/custodian and RPO/RTO proposal; clarify issuer-approved staging/initial/ongoing source scope and use; resolve remaining G1 identity controls or explicitly accept a bounded scope with exclusions. Record final G0–G2 acceptance and explicit G3 authority in OLC-91. |
| During G3 preflight before writes | Verify pinned release/digest, effective PostgreSQL role and privileges, least-privileged source/service route, mount and WAL ownership, negative access tests, and backup destination rights. Set up only approved PostgreSQL/source prerequisites. No Qdrant dependency for G3. |
| During G4 preflight before Qdrant writes | Prove Qdrant service roles, scoped collection, QA fence and recovery from verified PG vectors. Any paid embeddings need separately approved measured token costs. |
| Acceptance with running staging | G3 tests full source enumeration, raw/history and source-to-PG parity, resume and isolation. G4 tests exact index parity. G5 tests real nightly, read-only access and timed independent recovery. |

## Next action

Use the [one terminal handoff](PIKI-PISRS-API.md#remaining-source-identity-controls), obtain the [issuer scope and recovery decisions](PIKI-PISRS-ENV.md#source-grant-and-use-conditions), then record one owner signoff. The 17+24 completed GETs and the three local bounded terminal pairs remain established. Stop before G3 until explicitly authorized.
