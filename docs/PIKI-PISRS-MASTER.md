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
| G2 Data and release design | Complete architecture, schema, provenance, legal-time, sync, nightly and local recovery design; future backup explicitly deferred. | OWNER DESIGN DECISIONS APPROVED; exact documentation commit still needs separate final owner G2 signoff, then distinct G3 authorization. G1 positive cases remain to be evidenced. OLC-94 is not a G2/G3 blocker. |
| G3 Permanent staging and source→PG | Owner-approved setup, role/privilege and recovery preflight, authorized full read, byte-level/projection/history parity and tested resume. | NOT_RUN. |
| G4 Cost and PG→Qdrant | Local tokenizer over actual chunks, frozen plan and rate, separate paid approval then exact manifest parity. | NOT_RUN. |
| G5 Nightly and user acceptance | Actual timer-run evidence, approved alerts, security, isolation and backup restore, read-only user acceptance. | NOT_RUN. |

Use distinct denominator and verification time for each catalogue, source text, normalized text, history and index claim. Report unresolved required cases; only audited exceptions with reasons are eligible for coverage. Before G3 the allowed activities are bounded authorized reads, evidence and design. G3 requires explicit owner acceptance. G4 paid requests require separate explicit owner approval after measured PG token cost.

## G3 transition checklist

| When | Required proof or action |
|---|---|
| Before G3 authorization | Confirm accepted exact documentation commit, current protected 2024 credential, selected PIKI scope and conservative source pace/limits, staging path capacity and locally fenced capture/restore plan. Resolve targeted G1 positives or explicitly document approved exceptions; owner separately authorizes G3. Do not require a backup location or new SVZ letter. |
| During G3 preflight before writes | Verify pinned release, PG role and privileges, source route, binds/WAL, negative grants and local protected recovery capture/readback prerequisites under /data. Remote backup destination and Qdrant are not G3 source preflights. |
| During G4 preflight before Qdrant writes | Prove Qdrant service roles, scoped collection, QA fence and recovery from verified PG vectors. Any paid embeddings need separately approved measured token costs. |
| Acceptance with running staging | G3 demonstrates complete PISRS→PG manifests/raw history, idempotence and local fenced capture; G4 demonstrates PG→Qdrant vectors and rebuild; G5 demonstrates genuine nightly, read-only dated QA and isolated local recovery. OLC-94 separately tests true off-host restore after dual-copy synchronization. |

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
| Confidentiality, local recovery and future independent backup | ENV credential register + OPERATIONS recovery + ACCEPTANCE A16/A17 | Local fenced PG capture and isolated restore specified for G3/G5; independent off-host backup deliberately `DEFERRED_OLC94` without a selected destination or custodian. |
| Final release/read-only test-user acceptance | OPERATIONS + ACCEPTANCE A14–A18 | True timer, negative read-access, local restore/PG vector rebuild and dated legal QA in G5; true independent disaster recovery is OLC-94 only. |

**Static candidate checks:** 11 existing project documents traversed; 73 internal relative links and anchors resolvable; 20 declared tables; 15 DTO/125 mapped fields; 27 official operations (26 GET, one POST); A01–A18 all present; no obvious long API-token patterns in inspected document contents. These checks validate internal consistency of the **documentation**, not actual PostgreSQL migrations, source completeness, Qdrant vector correctness, real nightly performance or legal/source entitlement.

**Remaining evidence and decisions**: the three G1 sample areas are evidenced to the observed source boundary (ZDR-1 base, one-direction EU→RS, parent-scoped code value 128088 Pravilnik). Historic guide example `13022` differs and is retained as a distinct unresolved cross-namespace reference, not a live source ID. Next: final static QA and owner's explicit acceptance of the precise G2 documentation commit, then separately authorized G3 installation and runtime parity; source permission remains owner-confirmed. Independent off-host encrypted backup destination, custodian, RPO/RTO are UNDECIDED and DEFERRED to [OLC-94](https://linear.app/openlegalcore/issue/OLC-94) after complete PIKI/Medo synchronization; do not make them a G2/G3 blocker. Medo untouched.

**Status: CONSOLIDATED_SPECIFICATION_CANDIDATE, NOT OWNER ACCEPTED.** No implementation code or runnable SQL migration exists on this review branch. Static consistency is not runtime verification; final owner acceptance on the exact reviewed commit and a separate G3 authorization are required before installation or bulk ingestion. Record these decisions in the existing OLC-91 without creating new projects.

## Next action

**Do not rerun the completed bounded G1 samples or their HTTP profiles.** Current positive evidence is consolidated in [API](PIKI-PISRS-API.md#confirmed-g1-positive-evidence-final-2026-11-16). The original 2024 permission is owner-confirmed and no new letter is required. Owner signoff of an exact reviewed G2 commit is still pending; no G3 deploy yet, no independent backup location selection now.
