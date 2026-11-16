# OpenLegalCore PISRS — PIKI staging master contract

**Canonical start point; decision date 2026-11-16; status: DOCUMENTED DESIGN BASELINE / G0–G2 NOT ACCEPTED / IMPLEMENTATION HOLD.**

**Owner's mission:** build a new, durable, **test-user-ready PISRS staging ingestion system on PIKI**. It must capture **100% of the documented, authorized, actually retrievable PISRS source records**, including their available data, texts, original artifacts and historical versions, in a traceable PostgreSQL archive, then separately build the explicitly approved Qdrant index. It must operate reliably nightly and provide evidence of source→PG and PG→Qdrant parity. Do not modify Medo/Engine/case-law or improvise short-lived test infrastructure.

## Canonical documents — read in this order

1. **This document** — owner goal, status, gates, order of work and final acceptance.
2. [PIKI-PISRS-API.md](PIKI-PISRS-API.md) — authoritative-source inventory, all 27 published Swagger operations, official field families and exact missing live/OpenAPI evidence.
3. [PIKI-PISRS-ENV.md](PIKI-PISRS-ENV.md) — PIKI environment, resource/port/secret ownership, credentials matrix, systemd, persistent storage, staging access and mandatory preflights.
4. [PIKI-PISRS-DATA.md](PIKI-PISRS-DATA.md) — **candidate** source/field → PostgreSQL tables and raw artifacts, version/relationship rules, two checkpoints and proposed Qdrant contract.
5. [../AGENTS.md](../AGENTS.md) — guardrails for agents.
6. Current Linear [PISRS project](https://linear.app/openlegalcore/project/pisrs-complete-source-to-index-synchronization-b47e7deb7c78) / [OLC-91](https://linear.app/openlegalcore/issue/OLC-91/pisrs-piki-g0-g2-credentials-uradni-openapi-in-ciljna-postgresql) — task progress only; do not treat an issue description as an authenticated source or excuse to bypass gates.

**No parallel alternative master plan, new Linear project or experimental branch zoo.** New evidence updates these files consistently, with an exact date/source/hash. Source facts, existing-legacy observations, proposed design, unknowns and owner approvals must be separated.

## Present facts and status

| Item | Supported current statement | Evidence status |
|---|---|---|
| PISRS public API | Government Swagger displays PISRS API 1.0.0 OAS3, 13 main catalogues and 27 operations in total | OFFICIAL UI / live PIKI NOT_VERIFIED |
| Full OpenAPI document | JSON/YAML bytes, URL, SHA-256, exact property definitions/security/pagination not yet retrieved on PIKI | NOT_VERIFIED |
| PIKI SSH/OS/network/storage | PIKI is the new development and intended staging host by owner's decision; actual OS, capacity, ports, services not enumerated in this documentation pass | NOT_VERIFIED |
| PIKI credentials | PISRS token, PostgreSQL users, Qdrant access and OpenAI project/key/billing cannot be inferred from Medo | NOT_VERIFIED |
| PIKI PG/Qdrant | No verified permanent staging installation/DB/collection/backup or isolated restore | NOT_VERIFIED / installation HOLD |
| Legacy Medo | Local Codex read-only report dated 16 Nov: installed `84b72b1`, 7 nightly failures; source data PG and old Qdrant retained. Not a valid PIKI target/secret reference | LEGACY OBSERVED; MEDO NO WRITE |
| Existing GitHub | `OpenLegalCore/slovenia-pisrs-ingest`, protected `main` at `b2fd71f...`, tree equals 20 September `aa791949...` | GITHUB CHECKED / not accepted new runtime |
| Source→PG field mapping | Candidate logical model exists in DATA, but actual OpenAPI property-by-property mapping and source fixtures incomplete | G2 PROPOSED / NOT_VERIFIED |
| Source→Qdrant scope | Old Medo model `text-embedding-3-large` 3072; PIKI model, current/history eligibility, payload and collection still to be approved | PROPOSED / NOT_VERIFIED |

**No implementation or paid embeddings are authorized by the existence of this document.** Owner approval of the six-phase *plan* is NOT approval to pass any unproven gate or initiate paid requests, production/staging deployment or database writes before evidence review.

## Exact scope and acceptance meaning

- **In scope:** the official API operations and resources proven to be part of the approved, callable PISRS contract, all relevant DTO fields including nested relationships/code lists, all records returned after complete enumeration, all retrievable sanctioned NPB texts and historical versions. Preserve raw source plus normalized interpretation. Include reason-coded unsupported/unavailable content.
- **Out of scope without new owner decision:** full EU text retrieval from EUR-Lex, unofficial portal APIs and files outside authorized integration API, other gazette archives, changes to Medo or Engine, unrelated legal sources, silent data imports from older databases.
- **100% means:** for **every required endpoint and qualifying source identity** a recorded, reproducible `IMPORTED`, `SOURCE_NOT_AVAILABLE`, `NOT_SUPPORTED_BY_API` or other evidence-based reason, with independently checked set/count/hash equality; no unexplained missing/duplicate records. Differentiate metadata 100%, raw text 100% of available, full history, and eligible Qdrant 100% separately. Never claim coverage based solely on matching counts.
- **No history loss:** historical versions must stay in PG even if only latest text is indexed; Qdrant history boundary is an owner decision. No automatic reuse/assumption of existing Medo vectors.
- **No '0 USD' guess for future:** catalogue imports are not embedding calls; exact cost only after all new actual chunk texts are in PG and locally tokenized. No paid calls in cost simulation; owner separately approves any embeddings.

## Critical path — exactly six controlled gates

| Gate | Output and exact evidence | Stop condition | Current |
|---|---|---|---|
| **G0 PIKI infrastructure + credentials** | Timestamped read-only PIKI inventory of OS/RAM/swap/disk/ports/units/storage; target separation, named credentials in `SET/UNSET` matrix, successful approved auth probes and resource/backup design | Any key, service account, network route or durable storage cannot be demonstrated; never clone Medo secrets blindly | NOT_VERIFIED |
| **G1 source API contract** | Versioned full OpenAPI bytes/hash; **all 27 operations** with params/response schemas/DTO fields, real bounded authorized samples, pagination, error/absence behavior, provenance and exact source limits | Undocumented or unverified source semantics, especially local/EU texts or modified IDs | NOT_VERIFIED |
| **G2 source→storage specification** | Complete field-by-field official DTO→PG raw/normalized table/column, original bytes/hash and relations/versioning; approved history/index boundary; target PG/Qdrant architecture, migration and acceptance test designs | Any source field/version has no destination/status; no actual PIKI storage/rights evidence; owner has not signed off | PROPOSED / NOT_ACCEPTED |
| **G3 permanent staging + source→PG** | One reviewed, durable PG/Qdrant runtime and systemd deployment, segregated secrets and backup; lossless import of every eligible catalog/text/history item, resume proof, source↔PG independent parity, source exceptions enumerated | Unexplained gaps/identity collisions, unrecoverable storage, residual temporary resources | NOT_STARTED |
| **G4 local cost + PG→Qdrant** | Actual PG chunk set; local tokenizer count and exact USD quote using valid OpenAI rate; only after owner's paid-call approval embed idempotently with content/model provenance and full indexed set parity | No owner payment approval or incomplete token count/index contract | NOT_STARTED |
| **G5 staging/nightly acceptance** | Real timer-triggered nightly across source changes, controlled retry, no extra embeddings, backups and isolated restore, test-user access, audit of all gap statuses, resource consumption and documentation | Any nightly failure, source omissions, missing restoration proof or unexpected Engine/Medo effect | NOT_STARTED |

**Gate transitions are explicit owner decisions.** The owner may accept individual results as evidence but must never be told that an incomplete G1/G2 is ready to code.

## Required acceptance tests, defined before code

- **A0 Foundation:** complete verified PIKI inventory/credentials; hash-locked official API contract and exact mapping; owner-approved schema and history/Qdrant boundary. This is the primary engineering gate.
- **A1 Source enumeration:** all documented relevant collections, code lists and list endpoints, complete pagination, stable identity and overlap checks. Unexplained missing IDs = 0.
- **A2 Source→PG:** identity and per-source raw response/file hash parity, all DTO properties mapped or raw retained, distinct official absence/error statuses.
- **A3 Text fidelity:** original bytes/MIME/hash retained, parser does not drop articles, numbering, tables or annexes; traceable source locator and version.
- **A4 Identity and version history:** namespace-qualified primary keys, version lineage, legal dates, ambiguous links recorded without guesses; changed IDs produce versioned evidence, not endless nightly failure.
- **A5 PG integrity:** declarative FK/unique/check constraints, true import/status counts, independent current/previous source inventory, idempotent replay after partial writes.
- **A6 Qdrant:** expected eligible chunk set vs exact point IDs, payload, vector existence/dimensions/model and source-hash provenance; no unexplained omissions/orphans.
- **A7 Cost and retry:** local token count before paid call; explicitly approved budget/scope; zero duplicate embeddings on identical content.
- **A8 Nightly:** genuine scheduled successful execution, success-only stage-specific checkpoints, retries and reconciliation under legitimate source modifications.
- **A9 Operations:** immutable deployment/release, least-privileged service users, logs without secrets, backup+isolated restoration and documented separation from Medo, test-user access.

A passing CI test cannot by itself certify A1–A9 or 100% upstream completeness.

## Repository and Linear operating rules

- GitHub `main` remains the historical public reference until a documented repo-policy decision after G2. A **single docs-only review PR** is permitted to publish this foundation under required protected-branch checks. No code/build/dependency changes are part of foundation authoring.
- Public docs should not contain secret values, private DSNs, tokens, raw protected source data or production personal identifiers.
- Linear project above is the single plan; OLC-91 is the only new staging preparation task. Legacy Medo fixes are not part of its execution. Avoid duplicating six more implementation issues before gates pass.
- For any change, report `DONE` / `NOT_VERIFIED` / `BLOCKED`, exact proof of what was run, what was written, and precisely one next gated action. Do not silently declare success.
- Engineering goal is a small, reusable, professionally documented, production-quality staging component with **minimal permanent infrastructure**; no extraneous scripts, ad hoc containers, extra DBs, repo proliferation or needless repeat audits.

## Next action

**Complete G0 and G1 evidence on PIKI, then propose a final G2 schema and mapping for owner review.** No deployment or ingestion until that acceptance. The required missing facts are recorded explicitly in the three companion documents; they are NOT an invitation to invent values.
