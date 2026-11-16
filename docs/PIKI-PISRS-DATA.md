# PIKI PISRS — proposed source → PostgreSQL → Qdrant data contract

**Status: G2 DESIGN PROPOSAL / NOT OWNER-ACCEPTED / NO DATABASE CHANGES.**
The official PISRS API's 27 operations are inventoried in [PIKI-PISRS-API.md](PIKI-PISRS-API.md); exact OpenAPI property definitions and PIKI live payloads are missing. This document **cannot** yet be treated as a final executable SQL specification. Missing fields are not to be silently dropped or guessed. Authority: [PIKI-PISRS-MASTER.md](PIKI-PISRS-MASTER.md).

## Nonnegotiable data semantics

1. **Source of truth**: staging PostgreSQL stores each observed original API payload plus its normalized interpretation, all available texts and historical versions. Original response/file bytes must be hash-verifiable and retrievable independently of the embedding provider.
2. **Stable namespace-qualified keys**: never equate a state `register_id`, `text_id`, local `LS_ACT.id`, local `LS_NPB.id`, portal `MP_*`, `MOPED-PLUS`, `EDA`, `SOP`, `CELEX` or `FILE_ID`. SOP is an attribute/link candidate, not a guaranteed global primary key.
3. **No silent overwrite of history**: retain an append-only source observation and version/fingerprint boundary; source changes can legitimately alter metadata or links. Preserve previous observations and reason-coded conflicts rather than poisoning the nightly or silently rewriting links.
4. **Absence is not zero**: missing/undocumented source text, HTTP 404, HTTP 407 proxy auth, textless source record, timeout, invalid parse, and unsupported source type must be distinct statuses with timestamps, source and request provenance. Do not declare a local text absent from a 404 on the *state* text endpoint.
5. **Idempotent restarts**: same source identity+representation hash → no extra PG row, no new embedding. Success-only checkpoint per pipeline phase. State of one external API can change mid-pagination; require consistent inventory/completeness evidence.
6. **Explicit publication scope**: no dataset is declared 100% until each *documented and accessible* required source entity has been imported or individually recorded as a verified source limitation. Separate catalogue, raw text, normalized text, historical archive and vectors.
7. **PIKI is independent**: no production schema/collection names, credentials or volumes assumed from Medo. Legacy Medo is a read-only comparison source, not a migration script.

## Candidate logical schema (names provisional until G2 PASS)

Use a **dedicated staging PostgreSQL database** and one schema for PISRS, subject to conflict check in G0. Exact DDL is **NOT AUTHORIZED** yet. Candidate tables:

| Candidate entity | Essential proposed columns / keys | Purpose and proof |
|---|---|---|
| `catalog_source` | `source_key PK, method, path, controller, openapi_sha256, enabled, license_scope` | Exact upstream endpoint and versioned contract |
| `catalog_record` | `namespace, source_id, first_seen_at, last_seen_at, lifecycle_status`; PK `(namespace,source_id)` | Global identity in one namespace, not SOP alone |
| `catalog_observation` | `namespace, source_id, endpoint, response_sha256, raw_jsonb, observed_at, upstream_updated_at, request_run_id`; immutable observation ID | All endpoint-specific current/historic provenance and exact raw JSON; dedup by source+hash/observation |
| `record_relation` | `from_namespace, from_id, relation_type, to_namespace, to_id, source_observation_id, confidence_status, valid_from/to` | State/local/EU relations, evidence and ambiguity retained |
| `document_version` | `namespace, source_version_id, source_record_id, doc_no, version_label, source_date, kind, availability_status, discovery_run_id` | Separate NPB/version identity and legal dates; never substitute latest for requested historical version |
| `source_artifact` | `version_id, source_url, fetched_at, MIME, raw_bytes BYTEA or operator-approved durable large-object scheme, size_bytes, SHA256, extraction_status` | Byte-identical original HTML/PDF/file/JSON when legally accessible; documented storage quota limits and archival rules |
| `parsed_document` | `artifact_id, parser_version, normalized_text, parse_warnings, content_sha256, language` | Reproducible normalized representation, not replacement for original |
| `text_block` | `parsed_document_id, ordinal, block_type, provision_id, parent_locator, original_fragment, normalized_text, source_offsets` | Article/paragraph/table/annex content with ordered provenance |
| `source_attempt` | `run_id, namespace, source_id, URL_ref, response_class, HTTP_status, retry_count, checked_at, reason_code` | Every unreachable/unsupported item remains auditable |
| `source_run` and `source_checkpoint` | `run_id, source_contract_sha, start/end, counts, failures, completion_status, last_success_boundary` | Source→PG progress independent of paid vectors |
| `embedding_plan` | `namespace, version_id, chunk_index, model, dimensions, text_sha256, tokenizer_version, token_count, eligibility, state` | Deterministic exact token costs **before** calling OpenAI; retain all source locators |
| `vector_delivery` and `vector_checkpoint` | `embedding_plan_id, qdrant_point_id, payload_sha256, vector_status, last_success_at, retry_state` | Independent PG→Qdrant resume/parity; model and vector provenance |
| `ingest_contract_revision` | `source_spec_sha256, schema_version, parser_version, accepted_at, approved_by` | Links source definitions, target mapping and gate acceptance |

Do **not** ship DDL until actual PIKI PostgreSQL version/roles/mount capacity are known, all OpenAPI fields have an approved destination, and DB invariants/test migrations have an approved design. A `BYTEA` archival choice needs real document size profiling; external storage is an owner decision, not an improvised fallback.

## Mandatory field mapping matrix (domain-level draft; exact JSON property names and types pending OpenAPI)

Every exact source property (including optional nested arrays and enumerations) must eventually appear in a machine-auditable row with:
`source endpoint+DTO+JSON path+type+nullable → namespace/source identity → PG schema.table.column or fully preserved raw JSON → indexes/FK → transform/version rule → real fixture hash/status`.

| Official source category / reported human-field group | Candidate normalized destination | Identity / invariant | Evidence status |
|---|---|---|---|
| State `PredpisDTO`: ID, MopedID | `catalog_record(RS_ACT)` and `catalog_observation` | Composite namespace+exact state ID; Moped as attributed external ID | Official names; JSON casing NOT_VERIFIED |
| State: title, abbreviation, citation, EVA/EOA/EPA/SOP | `catalog_observation.raw_jsonb` + approved indexed attributes | Do not invent `SOP` unique constraint | Official field meaning; exact DTO paths NOT_VERIFIED |
| State: act type, category, basic indicator, dates, adopting/preparing organ | `raw_jsonb` + normalized typed projection | Legal status vs source collection membership separate | Types/nullable NOT_VERIFIED |
| State: basis, amendments, influences, subordinate acts, thematic classifications | `record_relation` + `catalog_observation.raw_jsonb` | Direction, target namespace/ID, temporal validity | Nested DTO paths NOT_VERIFIED |
| State `NpbDTO`: ID, NPB title, document date/number | `catalog_record(RS_NPB)`, `document_version` | NPB version ID distinct from state act ID | Official meaning, exact JSON types NOT_VERIFIED |
| State `GET /besedilo/{idZbirkaElement}` HTML | `source_artifact`, `parsed_document`, `text_block` | Exact requested RS_NPB ID, preserve response MIME and raw bytes | Official path; PIKI response NOT_VERIFIED |
| EU `PredpisEuDTO`: CELEX, title, act type, EU dates, Official Journal citations, transposition relations, EuroVoc | `catalog_record(EU)`, `catalog_observation`, `record_relation` | CELEX qualified; EU source text not implied | Official metadata; exact DTO paths NOT_VERIFIED |
| Local `AktDTO`: ID, MOPED-PLUS ID, EDA, SOP, dates, spatial act ID/type, official gazette, organs | `catalog_record(LS_ACT)`, `catalog_observation` | Local numeric ID is authoritative record key; changes of Moped+ kept as observations until confirmed | Official fields; identity mutation semantics UNKNOWN |
| Local `NpbDTO`: ID, date, document number, title | `catalog_record(LS_NPB)`, `document_version` | NPB numeric ID never used directly as file ID or RS text ID | Official fields; real text route outside documented text API |
| State/local `/seznam` projection fields | `catalog_observation` with endpoint-specific payload | Cross-check against canonical catalog, do not invent extra full records | Official projection fields; correlation NOT_VERIFIED |
| `/sifranti` and `/sifranti/{id}` | `catalog_record(CODELIST)`, `catalog_observation` | Preserve full code list metadata and values | Official exists; concrete universe/DTO NOT_VERIFIED |
| Portal-only local files/links (if separately authorized) | `source_artifact`, `document_version`, `record_relation` | Exact portal version and original FILE_ID required | NOT an official integration API guarantee |
| Unobtainable/prohibited/not represented source content | `source_attempt` and source contract limitation | Source-proven reason rather than fabricated absence | Must be demonstrated by each source |

**Every property not mapped explicitly to normalized columns must still be preserved in raw JSON without filtering.** This is a proposed fallback for information preservation, not proof that a downstream consumer is complete.

## Historical and identity contract requirements

- Distinguish act registration date, legal effectiveness/application interval, publication, date of NPB document, date observed by ingest, and version label. Do not substitute these dates.
- Version lineage: `source_version_id` + namespace, document number and source record, with explicit source/derived references. Prove all available NPB generations and source files for a sample of state/local acts; do not infer complete history from number of NPB catalogue IDs.
- Local SOP may encode more than one SOP in an NPB document number. Exact parsing rules require real examples and official guide confirmation, and a non-unique association is `AMBIGUOUS`, not a guessed foreign key.
- Model source identity changes (e.g. source correction of MOPED-PLUS for unchanged numeric ID) as versioned observations with evidence and reviewed transition logic. A fail-closed alarm is useful for unknown collisions, but repeating failure on legitimate source corrections is not acceptable nightly behavior.

## Qdrant staging contract — NOT YET APPROVED

- One explicitly named staging-only collection (final name after PIKI inventory), fixed embedding model and distance, deterministic point IDs salted by namespace+version identity+chunk ordinal+model+content contract, not IDs from Medo.
- **Eligibility boundary** must be explicitly decided by owner: only latest current text, also all historical versions, or separately scoped indexes. PostgreSQL retains every source version regardless.
- Vector generation only for changed eligible chunk content; reuse by exact content hash/model/dimensions; retain tokenizer version and `token_count` measured locally.
- Exact required Qdrant payload fields: qualified source ID, version, act link, source URL, legal dates, historical flag, chunk locator, text hash, model, parser provenance; agree on Engine/read-client requirements **without changing Engine**.
- Independently check expected eligible PG chunks versus Qdrant point ID/payload/vector coverage. Counts alone are not parity. Embeddings are paid only after separate explicit owner approval, measured total token cost and idempotent batch plan.

## G2 acceptance (mandatory)

**No implementation until**: machine OpenAPI + sample responses are available; every DTO property is in the final mapping matrix with type, FK, defaults, raw preservation and lineage; actual PIKI PG/Qdrant environments and credentials are proven; identity correction/version rules are specified; source/embedding checkpoint boundaries and errors are specified; source↔PG and PG↔Qdrant 100% acceptance tests are written against the *actual* authoritative source scope. Owner must approve the resulting target schema and index history policy.

**Current status: NOT_VERIFIED; the tables above are candidates, not an installed system.**
