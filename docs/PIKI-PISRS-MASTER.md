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

## Implementation-ready specification: scope, authority and handoff

**Purpose:** build one new permanent PIKI staging ingest, not a general legal-data platform. This canonical document set describes the full intended path through G5: authorized PISRS API discovery, exact raw archive in PostgreSQL, independently verifiable source manifests and history, resumable nightly, then a separately approved dated historical vector index in Qdrant and tested backup/recovery. The old Medo service is an immutable read-only reference in this mandate. Do not create new products, services, databases or alternative acquisition sources.

**Source boundary**: include **all authorized records actually retrievable from the pinned PISRS integration API**: 13 paged catalogs, ten full list projections, dictionary list and per-ID values, state base/NPB text and its retrievable versions. Operation 27 is a credential-request POST and is never dispatched by ingest. Preserve local/EU metadata but **do not promise local or EU full texts** absent an explicitly authorized documented integration route. Preserve excluded/unsupported scopes and their counts; no invented portals or screen scraping. “Complete” applies only to an explicitly evidenced source scope, cutoff and denominator, not unqualified entirety of the PISRS website.

**Authority precedence for implementers**: owner approvals and hard restrictions in OLC-91 → AGENTS.md → this MASTER (scope/gates) → official pinned [API](PIKI-PISRS-API.md) (wire format) → [DATA](PIKI-PISRS-DATA.md) (storage, identity, provenance, legal dates) → [SYNC](PIKI-PISRS-SYNC.md) (transactional algorithm and promotion) → [ARCHITECTURE](PIKI-PISRS-ARCHITECTURE.md) (deployment) → [OPERATIONS](PIKI-PISRS-OPERATIONS.md) (run/restore) → [ACCEPTANCE](PIKI-PISRS-ACCEPTANCE.md) (pass/fail evidence). ENV records measured host and external authorizations; AUDIT is dated historical evidence, **not** a source for overriding later owner approvals. On genuine conflict: fail closed, cite exact conflicting clauses, resolve once in these documents before executing destructive work. No agent may silently replace a required owner decision with a new design.

| Full delivery milestone | Design source | Acceptance evidence |
|---|---|---|
| G0 permissions and PIKI readiness | ENV + ARCHITECTURE + OPERATIONS | Effective Docker/containerd on /data, source grant/rate, isolated reserved storage, independent recovery destination/owner/retention and agreed recovery objectives. |
| G1 source identity and access | API + DATA | Official OpenAPI hash 27/27, 26 documented GET, 15 DTO/125 fields, bounded paging/source-ID controls, explicit allowable exclusions and known unresolved links. |
| G2 frozen engineering specification | MASTER + ARCHITECTURE + DATA + SYNC + OPERATIONS + ACCEPTANCE | Coherent table/invariant, source-run, index/legal-time, safety/restore and nightly contracts with no missing material architecture choice. Sign off a **single exact Git commit**; design signoff is not deployment authorization. |
| G3 PostgreSQL source ingest | DATA + SYNC + OPERATIONS | Approved fresh PG and 15 archive tables, real permitted full sweep, raw bytes/versions, independent source→PG manifest parity, resume/idempotence and backup proof. |
| G4 dated current/history Qdrant | DATA + SYNC + OPERATIONS | Five index tables, owner-approved token tariff/amount, full cached vector and Qdrant parity, QA downtime fence and zero-cost restore route. |
| G5 automatic readiness | ARCHITECTURE + SYNC + OPERATIONS + ACCEPTANCE | Actual nightly timer, retry/monitor, approved QA access, off-host encrypted restore drill and measured RPO/RTO. |

**Design versus execution boundary:** a completed architectural description does **not** prove source-wide completeness, the availability of a backup provider, PostgreSQL schema correctness in a deployed instance or a nightly run. Those are runtime evidence gates G3–G5. Conversely, do not demand an already installed database, all-source scan or Qdrant rebuild as prerequisites to writing a technically complete specification. The specification must name each runtime stop/preflight and proof.

**Approved decisions** (owner, 2026-11-16): 20 tables (15 source, five index), existing Docker with PG in G3 and Qdrant in G4, three host service accounts and one timer, one Qdrant collection with a bounded read fence during publication, PG vector cache for no-paid-call restore, and dated semantic search across current and evidence-qualified historical state texts. All project installations/data and their scratch, WAL and backups on /data, off-host encrypted copy separately approved. No paid G4 API requests without measured explicit owner authorization.

**Completion predicate for the documentation itself:** (1) every intended phase and required source class has exactly one canonical contract and acceptance test, (2) repository file/anchor links and source field matrix are internally consistent, (3) no stale historical NOT_RUN/NOT_VERIFIED note is presented as current state, (4) no additional technical architecture decision is necessary to implement the documented design, and (5) all nontechnical/external decisions are explicitly enumerated as gates with responsible actor. An immutable Git publication alone is **not** a formal owner signoff. Until the final owner decision on the exact reviewed commit, report DOCUMENTATION_FINAL_ACCEPTED=NO.

## Scope and gates

Integrate the official authorized catalogue, projection, code-list and state text scope. Record accessible state base and NPB versions with original bytes and independent legal-date/identity fields. Archive local and EU metadata, record any unsupported text by scope and seek owner approval separately before adding another source. Project installation, persistence, temporary work and backup on PIKI belong under `/data`, with only source checkout and essential OS configuration eligible for the system disk. Build no frontend, Engine/case-law changes, or parallel deployment.

| Gate | Output and prerequisite | Status |
|---|---|---|
| G0 Environment and entitlement | Confirm effective Docker root, volumes and no collisions, issuer-approved PIKI use and cadence, owner-approved role and ingress plans and independent backup destination. Schedule target-dependent role tests for first G3 preflight. | **PARTIAL / NOT ACCEPTED.** Owner-run sudo readback: Docker effective `/data/docker` overlayfs, no current Docker containers, `/data` 402 GiB free. Reserved /data paths conflict-free in the targeted filesystem read. **Effective containerd root PASS** via owner live process descriptor on `/data/containerd`. Issuer PIKI long-running usage/rate and independent backup/recovery decision remain open; actual roles are G3/G4 preflight. |
| G1 Source contract | Verified official OpenAPI, bounded early and terminal paging controls or equivalent issuer evidence, bounded required text identity and relation rules, and documented scope/unknowns. | **PARTIAL / NOT ACCEPTED.** Spec/26 GET previously verified; owner-run 17/21 plus **24/24 new GETs, all HTTP 200**. **All three local catalogue endpoint stop-boundary pilots PASS_BOUNDED** (op17 last 1997/19 rows, op19 last 3/36 rows, op21 last 507/11 rows; repeated controls stable). Full source membership/parity is G3. Official references now identify the ZDR-1 version markers, the real ZVPot-1 CELEX edge and code 13022. Subsequent identity handoff made **1/3 bounded protected GET (HTTP 200)** for ZVPot-1, but returned `CELEX_API NOT_VERIFIED`; conditional EU GET was not sent. Saved base HTML unavailable (`ZDR_BASE NOT_RUN`), dictionary ID unknown (`DICTIONARY_API NOT_RUN`). Do not count successful HTTP as a proven edge. |
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

## Consolidated documentation review — 2026-11-16

The canonical candidate was reconciled end to end **without changing architecture or starting code**. The source inventory is defined in API, typed persistence and identity rules in DATA, exact staging topology in ARCHITECTURE, operational transactions and recovery in SYNC/OPERATIONS, and the 18 tests in ACCEPTANCE. AGENTS and README point to this master. AUDIT remains immutable dated evidence, not a current approval certificate.

| Required specification area | Canonical binding source | Documentation check |
|---|---|---|
| All authorized PISRS operation classes and explicit exclusions | API operations and implementation envelope | 27 documented operations = 26 ingest GET + one out-of-scope credential-request POST; 13 paged + ten unpaged + state text + two code operations |
| Parameters, DTOs, identity keys and nullable source behavior | API parameter groups + DATA field matrix and identity contract | 15 schemas and 125 field rows; numeric/SOP/CELEX/dictionary namespaces distinct |
| PostgreSQL raw-byte history and consistency | DATA 20-table inventory and migration rules | 15 G3 archive/source + five G4 index/paid tables, migrations and audit constraints defined |
| First full sweep, independent source-to-PG parity | SYNC deterministic contract + ACCEPTANCE A01–A11 | stop conditions, two-manifest comparison and honest NOT_VERIFIED boundary described |
| Daily renewal, pause/resume, failures and checkpoint | SYNC + OPERATIONS daily chain + ACCEPTANCE A10–A15 | no silent advancement on cap/partial source; one scheduled pipeline |
| State legal versions and dated search | DATA legal eligibility + API source identity + ACCEPTANCE A06/A18 | no invented legality/retroactivity, no unsupported local/EU full-text claims |
| Qdrant vector cache, paid cost and source/index separation | DATA Qdrant contract + SYNC G4 + ACCEPTANCE A12/A13 | exact cached-vector/point parity, guarded in-place one-collection update |
| PIKI paths, process identities and privilege gates | ENV + ARCHITECTURE + OPERATIONS | /data, existing Docker/containerd proven; not-yet-created roles are G3/G4 tests |
| Confidentiality, backup, restoration and continuity | ENV credential register + OPERATIONS recovery + ACCEPTANCE A16/A17 | off-host destination and custodian **unapproved external input**; actual RPO/RTO measured in G5 |
| Final release/read-only test-user acceptance | OPERATIONS + ACCEPTANCE A14–A18 | true timer run, negative access, backup restore and dated legal QA required in G5 |

**Static candidate checks:** 11 existing project documents traversed; 73 internal relative links and anchors resolvable; 20 declared tables; 15 DTO/125 mapped fields; 27 official operations (26 GET, one POST); A01–A18 all present; no obvious long API-token patterns in inspected document contents. These checks validate internal consistency of the **documentation**, not actual PostgreSQL migrations, source completeness, Qdrant vector correctness, real nightly performance or legal/source entitlement.

**Remaining material external/owner inputs** (do not hide behind a green documentation check): (1) confirm with issuer whether current credential/grant permits a scheduled PIKI bulk initial/daily run, rate, retention/reuse; (2) name/approve real independent off-host backup/recovery destination and custodian, retention and RPO <=24h / proposed RTO <=8h; (3) decide whether residual G1 proof gaps (base ZDR-1 HTML attribution, selected CELEX/code-list edges) may be explicit archived exceptions or require additional verified positive fixtures before G3. In either case, a required unknown locator cannot be silently treated as available. These are approval/empirical evidence dependencies, **not permissions to redesign the application**.

**Status: CONSOLIDATED_SPECIFICATION_CANDIDATE, NOT OWNER ACCEPTED.** No implementation code or runnable SQL migration exists on this review branch. Static consistency is not runtime verification; final owner acceptance on the exact reviewed commit and a separate G3 authorization are required before installation or bulk ingestion. Record these decisions in the existing OLC-91 without creating new projects.

## Next action

**Do not rerun the completed 17+24 GET pilots or the latest generic 1-GET identity handoff.** Preserve the [owner terminal identity results](PIKI-PISRS-API.md#owner-run-final-identity-handoff-2026-11-16) and use only the necessary targeted source-shape/reference analysis before further API reads. Obtain the [issuer scope](PIKI-PISRS-ENV.md#source-grant-and-use-conditions) and choose the independent recovery destination/custodian and RPO/RTO, then record one G0–G2 owner signoff. G3 requires explicit separate authorization; full enumeration/parity are its tests.
