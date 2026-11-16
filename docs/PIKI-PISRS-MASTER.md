# PIKI PISRS staging master

Owner mandate, 2026-11-16. Build a new permanent staging ingest on PIKI for test users and keep Medo as independent legacy production. Archive all documented, authorized and retrievable PISRS records, legal texts and observable history in PostgreSQL. Publish the separately approved derived Qdrant index and verify scheduled source→PG and PG→Qdrant parity independently.

**Status 2026-11-16 (final documentation review).** The owner has approved the [minimal topology](PIKI-PISRS-ARCHITECTURE.md) and [historical index policy](PIKI-PISRS-DATA.md#qdrant-contract). G0 host/permit checks and bounded G1 positive source samples are documented; their **formal owner acceptance** together with the final G2 documentation commit is still pending. No G3 installation authorization exists. Full enumeration, independent source→PG and PG→Qdrant parity, operational nightly and restorations are **NOT_RUN** and belong to G3–G5. The independent off-host backup remains deferred OLC-94.

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

**Purpose:** build one new permanent PIKI staging ingest, not a general legal-data platform. This canonical document set describes the full intended path through G5: authorized PISRS API discovery, exact raw archive in PostgreSQL, independently verifiable source manifests and history, resumable nightly, then a separately approved dated historical vector index in Qdrant and protected local recovery; independent off-host disaster recovery is later OLC-94. The old Medo service is an immutable read-only reference in this mandate. Do not create new products, services, databases or alternative acquisition sources.

**Source boundary**: include **all authorized records actually retrievable from the pinned PISRS integration API**: 13 paged catalogs, ten full list projections, dictionary list and per-ID values, state base/NPB text and its retrievable versions. Operation 27 is a credential-request POST and is never dispatched by ingest. Preserve local/EU metadata but **do not promise local or EU full texts** absent an explicitly authorized documented integration route. Preserve excluded/unsupported scopes and their counts; no invented portals or screen scraping. “Complete” applies only to an explicitly evidenced source scope, cutoff and denominator, not unqualified entirety of the PISRS website.

**Authority precedence for implementers**: owner approvals and hard restrictions in OLC-91 → AGENTS.md → this MASTER (scope/gates) → official pinned [API](PIKI-PISRS-API.md) (wire format) → [DATA](PIKI-PISRS-DATA.md) (storage, identity, provenance, legal dates) → [SYNC](PIKI-PISRS-SYNC.md) (transactional algorithm and promotion) → [ARCHITECTURE](PIKI-PISRS-ARCHITECTURE.md) (deployment) → [OPERATIONS](PIKI-PISRS-OPERATIONS.md) (run/restore) → [ACCEPTANCE](PIKI-PISRS-ACCEPTANCE.md) (pass/fail evidence). ENV records measured host and external authorizations; AUDIT is dated historical evidence, **not** a source for overriding later owner approvals. On genuine conflict: fail closed, cite exact conflicting clauses, resolve once in these documents before executing destructive work. No agent may silently replace a required owner decision with a new design.

| Full delivery milestone | Design source | Acceptance evidence |
|---|---|---|
| G0 source access and PIKI readiness | ENV + ARCHITECTURE + OPERATIONS | Owner-confirmed 2024 permit, working protected PIKI token, effective Docker/containerd /data roots, isolated available staging paths and conservative configurable rate/byte caps. The independent backup is OLC-94, not a G0 block. |
| G1 source identity and access | API + DATA | Official OpenAPI hash 27/27, 26 documented GET, 15 DTO/125 fields, bounded paging/source-ID controls, explicit allowable exclusions and known unresolved links. |
| G2 frozen engineering specification | MASTER + ARCHITECTURE + DATA + SYNC + OPERATIONS + ACCEPTANCE | Coherent table/invariant, source-run, index/legal-time, safety/restore and nightly contracts with no missing material architecture choice. Sign off a **single exact Git commit**; design signoff is not deployment authorization. |
| G3 PostgreSQL source ingest | DATA + SYNC + OPERATIONS | Approved fresh PG and 15 archive tables, real permitted full sweep, raw bytes/versions, independent source→PG manifest parity, resume/idempotence and backup proof. |
| G4 dated current/history Qdrant | DATA + SYNC + OPERATIONS | Five index tables, owner-approved token tariff/amount, full cached vector and Qdrant parity, QA downtime fence and zero-cost restore route. |
| G5 automatic readiness | ARCHITECTURE + SYNC + OPERATIONS + ACCEPTANCE | Genuine nightly source/index chain, restart and monitoring, read-only QA, independently readback-verified local fenced PG restore and Qdrant rebuild from PG vectors. Off-host disaster recovery is a later OLC-94 acceptance. |

**Design versus execution boundary:** a completed architectural description does **not** prove source-wide completeness, the availability of a backup provider, PostgreSQL schema correctness in a deployed instance or a nightly run. Those are runtime evidence gates G3–G5. Conversely, do not demand an already installed database, all-source scan or Qdrant rebuild as prerequisites to writing a technically complete specification. The specification must name each runtime stop/preflight and proof.

**Approved decisions** (owner, 2026-11-16): 20 tables (15 source, five index), existing Docker, PostgreSQL in G3 and Qdrant in G4, three host service identities, one timer, one Qdrant collection with controlled publication downtime, PG vector cache for no-paid-call restore, and date-qualified historical legal search. All PIKI project files, WAL, local fenced capture and restore under `/data`. Two synchronized copies (PIKI and Medo) are a later goal, not the current state; Medo remains read-only until separately approved. The real independent encrypted backup location is **UNDECIDED** and explicitly deferred to [OLC-94](https://linear.app/openlegalcore/issue/OLC-94) after verified full sync. No paid embeddings without explicit measured owner authorization.

**Completion predicate for the documentation itself:** (1) every intended phase and required source class has exactly one canonical contract and acceptance test, (2) repository file/anchor links and source field matrix are internally consistent, (3) no stale historical NOT_RUN/NOT_VERIFIED note is presented as current state, (4) no additional technical architecture decision is necessary to implement the documented design, and (5) all nontechnical/external decisions are explicitly enumerated as gates with responsible actor. An immutable Git publication alone is **not** a formal owner signoff. Until the final owner decision on the exact reviewed commit, report DOCUMENTATION_FINAL_ACCEPTED=NO.

## Scope and gates

Integrate the official authorized catalogue, projection, code-list and state text scope. Record accessible state base and NPB versions with original bytes and independent legal-date/identity fields. Archive local and EU metadata, record any unsupported text by scope and seek owner approval separately before adding another source. Project installation, persistence, temporary work and backup on PIKI belong under `/data`, with only source checkout and essential OS configuration eligible for the system disk. Build no frontend, Engine/case-law changes, or parallel deployment.

| Gate | Output and prerequisite | Status |
|---|---|---|
| G0 Environment and entitlement | Owner-confirmed 2024 PISRS permit and live PIKI access, effective Docker/containerd roots, reserved isolation, adjustable conservative request bounds, local fenced capture capacity. Off-host backup belongs to OLC-94. | **PARTIAL / final owner signoff pending.** Existing PISRS token works on PIKI. Docker `/data/docker` overlayfs, live containerd `/data/containerd`, `/data` 402 GiB free and no observed PIKI container collision at readback PASS. Official numeric rate quota is not documented; do not invent one. Future service grants are G3/G4 preflights. |
| G1 Source contract | Pinned official API, bounded terminal paging and representative positive original-text, EU relation and qualified dictionary sample; unknown or absent reciprocal links remain explicitly unresolved. | **SAMPLED EVIDENCE COMPLETE / FINAL OWNER ACCEPTANCE PENDING.** Previous 17+24 GET checks and three bounded paging terminal controls remain PASS_BOUNDED. Current PIKI operator evidence: ZDR-1 base HTML 265,558 B SHA `d7a47fcafcf3faed5b185088751a7af76c76c95db8eaf0b02b6b4876da04d2b8`, original-matching bytes and content markers PASS_BOUNDED; ZVPot-1 EU record `32011L0083` identifies `ZAKO7054` via EU→RS PASS_BOUNDED, while the RS record's `zveza=[]` and must not be made reciprocal. `/sifranti` parent `128070` = Šifrant Vrsta akta RS; `/sifranti/128070` has 33 entries including `128088` = Pravilnik with `idNadrejeni=128070` PASS_BOUNDED. Prior guide example `13022` was NOT found in this specific parent set and is not mapped to `128088` globally. Full corpus enumeration, text/history parity remain G3 NOT_RUN. |
| G2 Data and release design | Complete architecture, schema, provenance, legal-time, sync, nightly, local recovery and acceptance plan; future off-host backup explicitly deferred. | **FINAL REVIEW CANDIDATE / OWNER G2 SIGNOFF PENDING.** All three bounded G1 positive classes are evidenced; their limits (one-direction EU→RS and unresolved guide code `13022`) are recorded without fabricated data. No additional architectural choice is pending. A separate G3 authorization remains necessary. OLC-94 is not a G2/G3 blocker. |
| G3 Permanent staging and source→PG | Owner-approved setup, role/privilege and recovery preflight, authorized full read, byte-level/projection/history parity and tested resume. | NOT_RUN. |
| G4 Cost and PG→Qdrant | Local tokenizer over actual chunks, frozen plan and rate, separate paid approval then exact manifest parity. | NOT_RUN. |
| G5 Nightly and user acceptance | Actual timer-run evidence, approved alerts, security, isolation and backup restore, read-only user acceptance. | NOT_RUN. |

Use distinct denominator and verification time for each catalogue, source text, normalized text, history and index claim. Report unresolved required cases; only audited exceptions with reasons are eligible for coverage. Before G3 the allowed activities are bounded authorized reads, evidence and design. G3 requires explicit owner acceptance. G4 paid requests require separate explicit owner approval after measured PG token cost.

## G3 transition checklist

| When | Required proof or action |
|---|---|
| Before G3 authorization | Owner explicitly accepts the exact final G2 documentation commit and separately authorizes G3; verify the previously recorded bounded G1 evidence/provenance, existing 2024 credential, selected official scope and conservative request bounds, target PIKI isolation and locally fenced capture/restore capacity. No new G1 requests, renewed SVZ letter or off-host backup location is required for documentation signoff. |
| During G3 preflight before writes | Verify pinned release, PG role and privileges, source route, binds/WAL, negative grants and local protected recovery capture/readback prerequisites under /data. Remote backup destination and Qdrant are not G3 source preflights. |
| During G4 preflight before Qdrant writes | Prove Qdrant service roles, scoped collection, QA fence and recovery from verified PG vectors. Any paid embeddings need separately approved measured token costs. |
| Acceptance with running staging | G3 demonstrates complete PISRS→PG manifests/raw history, idempotence and local fenced capture; G4 demonstrates PG→Qdrant vectors and rebuild; G5 demonstrates genuine nightly, read-only dated QA and isolated local recovery. OLC-94 separately tests true off-host restore after dual-copy synchronization. |

## Consolidated documentation review — 2026-11-16

The canonical candidate was reconciled end to end **without changing the agreed architecture, installing services or developing ingest code**. The source inventory is in API, typed persistence/identity in DATA, staging topology in ARCHITECTURE, transaction/restart and local recovery in SYNC/OPERATIONS and 18 acceptance tests in ACCEPTANCE. AGENTS and README point to this master. AUDIT records dated historical evidence rather than current approvals. The one-off historical G1 readback helper is not part of the future ingest application.

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
| Confidentiality, local recovery and future independent backup | ENV credential register + OPERATIONS recovery + ACCEPTANCE A16/A17 | Local fenced PG capture and isolated restore specified for G3/G5; independent off-host backup deliberately `DEFERRED_OLC94` without a selected destination or custodian. |
| Final release/read-only test-user acceptance | OPERATIONS + ACCEPTANCE A14–A18 | True timer, negative read-access, local restore/PG vector rebuild and dated legal QA in G5; true independent disaster recovery is OLC-94 only. |

**Final static document-review checks:** 11 canonical Markdown files; 73 resolved internal relative links, including 37 checked section-anchor references; 20 declared distinct PostgreSQL tables (15 G3 + five G4); 15 DTO classes/125 mapped fields; 27 official API operations (26 GET, one excluded POST); 18 acceptance areas A01–A18 and complete G0–G5 phase traceability. External URLs were not themselves evidence of runtime behavior. These are consistency checks of the **documented design**, not executed SQL migrations, all-source PISRS enumeration, Qdrant parity, nightly operation, independent disaster recovery or proof that a future approved service is deployed.

**Remaining approvals and runtime evidence:** bounded G1 samples are closed at their observed scope: ZDR-1 base, verified EU→RS edge with the RS side's empty `zveza[]`, and `(128070,128088)` = Pravilnik in the live code list. The older guide value `13022` has **no verified mapping** to the current list; its origin is unproven and must not be guessed. There are no further G1 pilot GETs planned. The next owner decision is **explicit formal G2 acceptance of a single reviewed Git commit**, followed by a separate G3 installation/initial-ingest authorization. Full source→PG and PG→Qdrant coverage, actual nightly and local restoration require later runtime evidence. The independent off-host encrypted backup location/custodian/retention/RPO/RTO remain **UNDECIDED and DEFERRED to [OLC-94](https://linear.app/openlegalcore/issue/OLC-94)** after verified PIKI/Medo synchronization; not a G2/G3 blocker. Medo untouched.

**Status: FINAL_REVIEWED_DOCUMENTATION_CANDIDATE, NOT FORMALLY OWNER ACCEPTED.** No PIKI ingest implementation, runnable SQL migrations or staging services exist on this review branch; the G1 evidence-only historical helper is not application code. The documentation defines complete execution and independent acceptance steps but cannot assert their runtime PASS. Do not conflate owner consent to perform this review with owner approval of the final exact commit. G3 installation/bulk ingest requires a separate explicit owner authorization.

## Next action

**Do not rerun the completed bounded G1 tests, legacy handoffs or the archived one-off G1 evidence helper.** Final positive samples are in [API](PIKI-PISRS-API.md#confirmed-g1-positive-evidence-final-2026-11-16). All new work is limited to owner signoff of the immutable reviewed G2 commit, then a separately authorized G3 implementation and source/PG proof. No new SVZ permission request, off-host backup choice or Medo write.
