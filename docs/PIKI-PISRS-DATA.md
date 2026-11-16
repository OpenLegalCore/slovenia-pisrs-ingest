# PIKI PostgreSQL and Qdrant data contract

**G2 candidate for owner review.** Database `pisrs_staging`, schema `pisrs`, PostgreSQL 18. The [API](PIKI-PISRS-API.md) defines source facts. The schema below defines intended migrations, not installed objects.

## PostgreSQL model

The proposed schema has **20 tables**, down from 29 in the review root. Each retained table protects an independent grain of identity, evidence, recovery or approval. Install the source subset at G3 and add the five index-specific tables at G4 after their approved prerequisites. Use views to expose the selected catalogue snapshot and the two published checkpoints.

| Consolidation | Why the retained state suffices |
|---|---|
| `catalog_source` and `source_manifest` | The immutable verified release pins the documented operations. Run evidence holds bounded ordered summaries. Durable attempts and occurrences retain independent row/hash-level proof. |
| `source_response`, `document_fetch` and `catalog_membership` | One retry row includes its response; document disposition is work state. Each occurrence keeps its provenance and one selected occurrence marks a member for that run and operation. |
| `reference` | One versioned resolution holds the typed edge and candidates. Identity events remain distinct to preserve explicit review and supersession. |
| `stage_checkpoint`, `index_publication_intent` and `embedding_delivery` | The generation stores publication intent. Checkpoints are the two committed run/generation heads. The immutable request/approval ledger stays separate from the per-input vector and current claim. |


In the table below, columns are required unless marked `?`. FK = foreign key, UQ = unique, PK = primary key, CK = check. Internal `bigint` IDs use identity columns. Digests are `bytea` with a 32-byte length check. Timestamps are `timestamptz` in UTC, legal dates are `date`, identifier strings use deterministic bytewise collation and preserve case and leading zeros. FKs use restrictive deletion by default. Check status fields against the states specified below or in [SYNC](PIKI-PISRS-SYNC.md). Attempt results use OPEN/HTTP_COMPLETE/HTTP_INCOMPLETE/TRANSPORT_ERROR/CONTRACT_ERROR/BODY_WITHHELD, occurrence validation uses VALID/QUARANTINED, parse state uses READY/QUARANTINED. All tables live in `pisrs`. Use only DB-generated ingest times for audit timestamps, and store upstream legal dates separately.

| Table | Columns and types | Keys, checks and indexes |
|---|---|---|
| `contract_revision` | `revision text, openapi_hash digest, schema_version integer, rules_revision text, parser_revision text, approved_at timestamptz?, approval_ref text?` | PK revision; schema_version > 0; approval date and reference appear together. Approved revision is explicit per run. |
| `source_run` | `run_id uuid, revision text, kind text, predecessor_run uuid?, started_at timestamptz, ended_at timestamptz?, published_at timestamptz?, status text, evidence_hash digest?, evidence jsonb, reason text?` | PK run_id, FK revision and predecessor; UQ (run_id, revision); kind INITIAL/NIGHTLY/VERIFY; status OPEN/INCOMPLETE/READY/PUBLISHED/SUPERSEDED/ABANDONED; index (status, started_at). One active PUBLISHED run. Bounded per-operation/sweep summaries store terminal proof, cutoffs, counts and independent digests, with detailed rows rebuilt from attempts and occurrences. |
| `source_work` | `run_id uuid, revision text, source_key smallint, sweep smallint, work_key text, request_target text?, query_args jsonb, status text, lease_until timestamptz?, next_attempt_at timestamptz?, terminal_attempt_id bigint?, locator_id bigint?, artifact_id bigint?, disposition text?, decision_ref text?` | PK (run_id, sweep, work_key); FK (run_id, revision), terminal attempt, locator and (artifact_id, locator_id). Status QUEUED/LEASED/RETRY/COMPLETE/QUARANTINED; partial UQ (run_id, locator_id) for document work; index (run_id, status, next_attempt_at). Scope exceptions can complete without dispatch and need a recorded disposition and the discovery operation's source key. Artifact reuse follows SYNC. |
| `source_blob` | `sha256 digest, raw_bytes bytea, byte_length bigint` | PK sha256; CK length equality and >= 0; insert verifies digest, re-read verifies integrity. Limit objects in the fetch profile below PostgreSQL field limits, record oversize as unresolved. Hash collisions require byte equality before reuse. |
| `source_attempt` | `attempt_id bigint, run_id uuid, source_key smallint, sweep smallint, work_key text, retry_no integer, started_at timestamptz, ended_at timestamptz?, result text, reason_code text?, retry_after timestamptz?, http_status smallint?, sha256 digest?, content_type text?, content_encoding text?, media_charset text?, etag text?, last_modified text?, data_pointer text?, error_text text?, page integer?, requested_page_size integer?, real_page_size integer?, reported_total_count integer?` | PK attempt_id, FK work and blob; UQ (run_id, sweep, work_key, retry_no); positive status range 100–599 and retry_no >= 0. Index (sha256). Null digest for no received entity, 304, incomplete or withheld capture. Work fixes the sanitized request; attempts retain response provenance including failures. |
| `source_record` | `record_id bigint, namespace text, source_id text, parent_key text, first_run uuid` | PK record_id, FK first_run, UQ (namespace, parent_key, source_id); non-empty source_id. `parent_key=''` except code values, where parent_key is the external dictionary ID. Namespace vocabulary below. |
| `record_revision` | `record_revision_id bigint, record_id bigint, revision text, value_hash digest, raw_jsonb jsonb, title text?, short_title text?, citation text?, category_label text?, notification_url text?, moped_id text?, moped_plus_id text?, eva text?, epa text?, eda text?, sop text?, spatial_act_id text?, is_basic boolean?, is_spatial boolean?, adopted_on date?, published_on date?, effective_from date?, applicable_from date?, effective_until date?, applicable_until date?, designation_on date?, transposition_due_on date?, document_date date?, document_number text?, parent_code_id text?` | PK ID, UQ (record_id, revision, value_hash), UQ (record_revision_id, record_id); FK record_id, revision. Partial indexes for non-null (moped_id), (moped_plus_id), (sop), (eda), (document_date, record_id). Source equality uses exact semantic JSON under a versioned canonical profile, with original bytes separately preserved. |
| `source_occurrence` | `attempt_id bigint, run_id uuid, source_key smallint, json_pointer text, record_id bigint?, record_revision_id bigint?, ordinal integer, validation text, diagnostic text?, selected boolean` | PK (attempt_id, json_pointer); FK attempt and revision/record pair MATCH FULL; UQ (attempt_id, ordinal), partial UQ (run_id, source_key, record_id) WHEN selected. Index (record_id, run_id); selected implies VALID and a record key. DB checks attempt/run/source against the pinned work and forbids retroactive edits to published selections. Preserve every extra occurrence by pointer. |
| `reference_resolution` | `record_revision_id bigint, run_id uuid, rules_revision text, json_pointer text, source_field text, ordinal integer, kind text, token text?, label text?, parent_token text?, status text, target_record_id bigint?, candidate_ids bigint[], evidence jsonb` | PK (record_revision_id, run_id, rules_revision, json_pointer); FK revision, run and target; index (kind, token). Kind CODE/MOPED/CELEX/NPB_SOP, ordinal >= 0. Status RESOLVED/AMBIGUOUS/UNRESOLVED/NOT_APPLICABLE; selected target iff RESOLVED and equals sole candidate. Original link, typed fields and unresolved candidates remain together. |
| `identity_event` | `event_id bigint, run_id uuid, record_id bigint, field text, old_value text?, new_value text?, status text, evidence jsonb, decision_ref text?` | PK event_id; FK run, record; UQ (run_id, record_id, field); status OBSERVED/APPROVED/QUARANTINED; index (status, run_id). Membership disappearance uses a dedicated field and explicit status. |
| `document_locator` | `locator_id bigint, record_id bigint, kind text, request_id text?, scope_status text` | PK locator_id; FK record; UQ (record_id, kind); partial index (kind, request_id); kind RS_BASE/RS_NPB/LS_NPB/EU. A verified numeric request ID is required for callable locators. Namespace, kind and ID relationship must validate before enqueue. |
| `source_artifact` | `artifact_id bigint, locator_id bigint, sha256 digest, first_attempt_id bigint` | PK artifact_id; FK locator, blob and attempt; UQ (locator_id, sha256), UQ (artifact_id, locator_id). First attempt must have matching hash and request. Work rows and later attempts track subsequent reads. |
| `parsed_document` | `parse_id bigint, artifact_id bigint, parser_revision text, media_profile text, decoded_charset text?, state text, warnings jsonb, normalized_text text?, text_hash digest?, language text?` | PK parse_id, FK artifact, UQ (artifact_id, parser_revision, media_profile); successful parse requires text/hash. |
| `text_block` | `parse_id bigint, ordinal integer, parent_ordinal integer?, kind text, legal_label text?, dom_locator text, source_start bigint?, source_end bigint?, normalized_text text, properties jsonb` | PK (parse_id, ordinal); FK parse and same-parse parent; ordinal >= 0, parent < child; both offsets or neither, 0 <= start < end for original byte positions. DOM locator and original artifact, or exact byte span, suffice to locate source. |
| `index_generation` | `generation_id uuid, source_run_id uuid, index_revision text, expected_hash digest?, evidence jsonb, state text, created_at timestamptz, verified_at timestamptz?, published_at timestamptz?, previous_generation uuid?` | PK generation_id, FK run and predecessor. States PLANNED/READY/APPLYING/PUBLISHED/RETIRED/FAILED. One PUBLISHED and one APPLYING by partial unique indexes. APPLYING is the durable publication intent and read fence. A failed rollout stays APPLYING until reconciled or the previous manifest is restored. |
| `embedding_input` | `input_id bigint, model text, dimensions integer, text_hash digest, input_text text, tokenizer_revision text, token_count integer, request_id uuid?, request_ordinal integer?, vector_hash digest?, vector_f32 bytea?, completed_at timestamptz?` | PK input_id, UQ (model, dimensions, text_hash); FK request, UQ (request_id, request_ordinal). Exact input bytes on reuse, positive dimensions/tokens, request and ordinal paired. Vector/hash/completion appear together with validated completed request and finite nonzero little-endian float32 vector of length 4 × dimensions. The request ledger retains immutable ordered input IDs for previous attempts. |
| `embedding_approval` | `approval_ref text, generation_id uuid, plan_hash digest, allowed_tokens bigint, usd_cap numeric(14,6), usd_per_million numeric(14,6), tariff_ref text, approved_at timestamptz, expires_at timestamptz` | PK approval_ref, FK generation, budgets nonnegative and expiry after approval. Hash includes input IDs, measured counts, request mode, model, data-use scope and rate. |
| `embedding_request` | `request_id uuid, approval_ref text, request_hash digest, attempt_no integer, item_ids bigint[], reserved_tokens bigint, actual_tokens bigint?, provider_request_id text?, state text, started_at timestamptz, ended_at timestamptz?` | PK request_id, FK approval, UQ (approval_ref, request_hash, attempt_no). States RESERVED/SENT/UNKNOWN/REJECTED/COMPLETE. Only after proven rejection or explicit exception may a new attempt claim the exact IDs. Unknown outcomes retain reservations. |
| `index_member` | `generation_id uuid, point_id uuid, parse_id bigint, input_id bigint, block_start integer, block_end integer, chunk_ordinal integer, span jsonb, legal_windows jsonb, payload jsonb, payload_hash digest` | PK (generation_id, point_id); FK generation, parse and input; UQ (generation_id, parse_id, chunk_ordinal); inclusive start/end block FKs with start <= end. Index and parity scan by generation/point. Versioned legal windows include rule/evidence locators and are sealed alongside the materialized payload. Unresolved spans remain in the source archive and in the bounded eligibility-gap summary in generation evidence. |
| `migration_log` | `version integer, migration_hash digest, applied_at timestamptz` | PK version, > 0; lock migrations and refuse edited applied files. |

Raw HTTP entity means original application body octets with content coding, without TLS or chunked transport framing. Request `Accept-Encoding: identity`; if a coding is returned, store the received coded bytes and header, then decode separately with hard encoded and decoded size limits. Store full successful bodies including all envelope keys and root array elements. Safe error metadata is always recorded. Archive complete error bodies only when source rights and sanitization permit, using explicit `BODY_WITHHELD` otherwise. Never record authorization headers, cookies, credentials, or uncontrolled exception strings. `jsonb` is a query projection. A strict JSON reader detects duplicate keys, NULs and illegal types before JSONB conversion. Commit the raw body even if projection fails, record its failure, and keep that scope out of promotion. Use integer-preserving JSON and a versioned canonical serializer for value hashes (sorted keys, original sequence for arrays, lossless decimals, no Unicode normalization). JSON pointers use RFC 6901.

Namespaces are `RS_ACT`, `RS_NPB`, `LS_ACT`, `LS_NPB`, `EU`, `CODE_LIST`, `CODE_VALUE`. Normalize spec int64 IDs to canonical decimal text after exact integer validation. Retain the lexical source value in raw bytes. CELEX uses the original nonempty string. Projection and detail membership keep distinct endpoint provenance. Alternate IDs are time-varying attributes, no unique index or rewrite of old keys. A corrected numeric identity is a new record plus reviewed lineage evidence. Inferred NPB amending SOP, base SOP and ordinal are stored under the chosen rules revision in `reference_resolution.evidence` as `amending_sop`, `base_sop`, `version_ordinal` and `rule`, with literal null for unavailable values and `version_ordinal` a positive integer when present. A single raw record may yield new parse/resolution revisions without replacing earlier work. The supported definition of archival history is all observable versions and byte revisions since first acquisition plus all retrievable upstream NPB history at the accepted source boundary.

Operational constraints that span tables must be enforced in a transaction and independently audited. These include attempt/run/source provenance, eligible artifact-to-locator and response alignment, one coherent membership manifest, legal classification rules, finite vectors and generation completeness. Migrations introduce database/roles, archive and pinned contract, typed reconciliation, parser and text tables, then index ledger. A03/A11 cover selected-occurrence stability and historical replays. Acquire and publish the source and index heads independently. Apply each migration with lock and version/hash reconciliation. Back up before any migration that changes persisted semantics. Do not delete history to roll back a parser/schema interpretation.

## Field matrix

Operation numbers and request parameters are in [API](PIKI-PISRS-API.md#operations). Read parameters map to `source_work.request_target/query_args`, excluding secrets. Every source value below has an independent original body pointer. The access form has no application persistence. Work and attempt operation numbers reference the pinned operation registry in the release, with range 1–26 and shape/operation checks in preflight and migration tests. A `data[]` entry uses `/data/<i>`, top-level projection uses `/<i>`. Nested references repeat the child rows at the parent path and record their full JSON pointer. Scalar code objects use ordinal 0. Wrappers have the same destination for each of their declared properties. For properties described by a typed column, missing/null yields SQL null except required target identity. Bad values are retained in raw with a diagnostic and require explicit disposition before publication.

| DTO | Property | OpenAPI type | PostgreSQL target | SQL type | Rule |
|---|---|---|---|---|---|
| `AktDTO` | `citat` | `string` | `record_revision.citation` | text | Traceable nullable projection. |
| `AktDTO` | `datumDolocitveOznake` | `string(date)` | `record_revision.designation_on` | date | Traceable nullable projection. |
| `AktDTO` | `datumKoncaUporabe` | `string(date)` | `record_revision.applicable_until` | date | Traceable nullable projection. |
| `AktDTO` | `datumObjave` | `string(date)` | `record_revision.published_on` | date | Traceable nullable projection. |
| `AktDTO` | `datumPrenehanjaVeljavnosti` | `string(date)` | `record_revision.effective_until` | date | Traceable nullable projection. |
| `AktDTO` | `datumSprejetja` | `string(date)` | `record_revision.adopted_on` | date | Traceable nullable projection. |
| `AktDTO` | `datumZacetkaUporabe` | `string(date)` | `record_revision.applicable_from` | date | Traceable nullable projection. |
| `AktDTO` | `datumZacetkaVeljavnosti` | `string(date)` | `record_revision.effective_from` | date | Traceable nullable projection. |
| `AktDTO` | `eda` | `string` | `record_revision.eda` | text | Traceable nullable projection. |
| `AktDTO` | `id` | `integer(int64)` | `source_record.source_id` | text | Namespace-qualified; opaque CELEX or canonical decimal int64. |
| `AktDTO` | `idProstorskiAkt` | `string` | `record_revision.spatial_act_id` | text | Traceable nullable projection. |
| `AktDTO` | `kategorizacijaAkta` | `string` | `record_revision.category_label` | text | Traceable nullable projection. |
| `AktDTO` | `kazaloPravnihAktov` | `ZbirkaSifrantElementDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `kratica` | `string` | `record_revision.short_title` | text | Traceable nullable projection. |
| `AktDTO` | `mopedPlusId` | `string` | `record_revision.moped_plus_id` | text | Traceable nullable projection. |
| `AktDTO` | `naziv` | `string` | `record_revision.title` | text | Traceable nullable projection. |
| `AktDTO` | `obcinskiOrganOdgovorenZaSprejetje` | `ZbirkaSifrantElementDTO` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `organKiJeSprejelOzIzdalAkt` | `ZbirkaSifrantElementDTO` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `osnovni` | `boolean` | `record_revision.is_basic` | boolean | Traceable nullable projection. |
| `AktDTO` | `podlaga` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `podrejeniPredpisi` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `podrocje` | `ZbirkaSifrantElementDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `posegaVPredpise` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `posegiVPredpis` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `prostorskiAkt` | `boolean` | `record_revision.is_spatial` | boolean | Traceable nullable projection. |
| `AktDTO` | `sop` | `string` | `record_revision.sop` | text | Traceable nullable projection. |
| `AktDTO` | `uradnoGlasilo` | `ZbirkaSifrantElementDTO` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `vplivaNaPredpise` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `vpliviNaPredpis` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `vrstaAkta` | `ZbirkaSifrantElementDTO` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktDTO` | `zveza` | `ZbirkaPovezavaPredpisEuElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `AktSeznamDTO` | `eda` | `string` | `record_revision.eda` | text | Traceable nullable projection. |
| `AktSeznamDTO` | `id` | `integer(int64)` | `source_record.source_id` | text | Namespace-qualified; opaque CELEX or canonical decimal int64. |
| `AktSeznamDTO` | `mopedPlusId` | `string` | `record_revision.moped_plus_id` | text | Traceable nullable projection. |
| `AktSeznamDTO` | `naziv` | `string` | `record_revision.title` | text | Traceable nullable projection. |
| `AktSeznamDTO` | `sop` | `string` | `record_revision.sop` | text | Traceable nullable projection. |
| `DataContainerDTOListAktDTO` | `data` | `AktDTO[]` | `source_attempt.data_pointer + source_occurrence.json_pointer` | text | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListAktDTO` | `error` | `string` | `source_attempt.error_text` | text | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListAktDTO` | `page` | `integer(int32)` | `source_attempt.page` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListAktDTO` | `realPageSize` | `integer(int32)` | `source_attempt.real_page_size` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListAktDTO` | `requestedPageSize` | `integer(int32)` | `source_attempt.requested_page_size` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListAktDTO` | `totalCount` | `integer(int32)` | `source_attempt.reported_total_count` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListNpbDTO` | `data` | `NpbDTO[]` | `source_attempt.data_pointer + source_occurrence.json_pointer` | text | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListNpbDTO` | `error` | `string` | `source_attempt.error_text` | text | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListNpbDTO` | `page` | `integer(int32)` | `source_attempt.page` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListNpbDTO` | `realPageSize` | `integer(int32)` | `source_attempt.real_page_size` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListNpbDTO` | `requestedPageSize` | `integer(int32)` | `source_attempt.requested_page_size` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListNpbDTO` | `totalCount` | `integer(int32)` | `source_attempt.reported_total_count` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisDTO` | `data` | `PredpisDTO[]` | `source_attempt.data_pointer + source_occurrence.json_pointer` | text | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisDTO` | `error` | `string` | `source_attempt.error_text` | text | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisDTO` | `page` | `integer(int32)` | `source_attempt.page` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisDTO` | `realPageSize` | `integer(int32)` | `source_attempt.real_page_size` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisDTO` | `requestedPageSize` | `integer(int32)` | `source_attempt.requested_page_size` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisDTO` | `totalCount` | `integer(int32)` | `source_attempt.reported_total_count` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisEuDTO` | `data` | `PredpisEuDTO[]` | `source_attempt.data_pointer + source_occurrence.json_pointer` | text | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisEuDTO` | `error` | `string` | `source_attempt.error_text` | text | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisEuDTO` | `page` | `integer(int32)` | `source_attempt.page` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisEuDTO` | `realPageSize` | `integer(int32)` | `source_attempt.real_page_size` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisEuDTO` | `requestedPageSize` | `integer(int32)` | `source_attempt.requested_page_size` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListPredpisEuDTO` | `totalCount` | `integer(int32)` | `source_attempt.reported_total_count` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListZbirkaSifrantElementDTO` | `data` | `ZbirkaSifrantElementDTO[]` | `source_attempt.data_pointer + source_occurrence.json_pointer` | text | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListZbirkaSifrantElementDTO` | `error` | `string` | `source_attempt.error_text` | text | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListZbirkaSifrantElementDTO` | `page` | `integer(int32)` | `source_attempt.page` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListZbirkaSifrantElementDTO` | `realPageSize` | `integer(int32)` | `source_attempt.real_page_size` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListZbirkaSifrantElementDTO` | `requestedPageSize` | `integer(int32)` | `source_attempt.requested_page_size` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `DataContainerDTOListZbirkaSifrantElementDTO` | `totalCount` | `integer(int32)` | `source_attempt.reported_total_count` | integer | Diagnostics and original envelope; child entries apply their referenced rows. |
| `NpbDTO` | `datumDokumenta` | `string(date)` | `record_revision.document_date` | date | Traceable nullable projection. |
| `NpbDTO` | `id` | `integer(int64)` | `source_record.source_id` | text | Namespace-qualified; opaque CELEX or canonical decimal int64. |
| `NpbDTO` | `naziv` | `string` | `record_revision.title` | text | Traceable nullable projection. |
| `NpbDTO` | `stevilkaDokumenta` | `string` | `record_revision.document_number` | text | Traceable nullable projection. |
| `PredpisDTO` | `citat` | `string` | `record_revision.citation` | text | Traceable nullable projection. |
| `PredpisDTO` | `datumKoncaUporabe` | `string(date)` | `record_revision.applicable_until` | date | Traceable nullable projection. |
| `PredpisDTO` | `datumObjave` | `string(date)` | `record_revision.published_on` | date | Traceable nullable projection. |
| `PredpisDTO` | `datumPrenehanjaVeljavnosti` | `string(date)` | `record_revision.effective_until` | date | Traceable nullable projection. |
| `PredpisDTO` | `datumSprejetja` | `string(date)` | `record_revision.adopted_on` | date | Traceable nullable projection. |
| `PredpisDTO` | `datumZacetkaUporabe` | `string(date)` | `record_revision.applicable_from` | date | Traceable nullable projection. |
| `PredpisDTO` | `datumZacetkaVeljavnosti` | `string(date)` | `record_revision.effective_from` | date | Traceable nullable projection. |
| `PredpisDTO` | `epa` | `string` | `record_revision.epa` | text | Traceable nullable projection. |
| `PredpisDTO` | `eva` | `string` | `record_revision.eva` | text | Traceable nullable projection. |
| `PredpisDTO` | `id` | `integer(int64)` | `source_record.source_id` | text | Namespace-qualified; opaque CELEX or canonical decimal int64. |
| `PredpisDTO` | `kategorizacijaAkta` | `string` | `record_revision.category_label` | text | Traceable nullable projection. |
| `PredpisDTO` | `kazaloPravnihAktov` | `ZbirkaSifrantElementDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `kratica` | `string` | `record_revision.short_title` | text | Traceable nullable projection. |
| `PredpisDTO` | `mopedId` | `string` | `record_revision.moped_id` | text | Traceable nullable projection. |
| `PredpisDTO` | `naziv` | `string` | `record_revision.title` | text | Traceable nullable projection. |
| `PredpisDTO` | `organKiJeSprejelOzIzdalAkt` | `ZbirkaSifrantElementDTO` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `organOdgovorenZaPripravo` | `ZbirkaSifrantElementDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `osnovni` | `boolean` | `record_revision.is_basic` | boolean | Traceable nullable projection. |
| `PredpisDTO` | `podlaga` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `podrejeniPredpisi` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `podrocje` | `ZbirkaSifrantElementDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `posegaVPredpise` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `posegiVPredpis` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `sop` | `string` | `record_revision.sop` | text | Traceable nullable projection. |
| `PredpisDTO` | `vplivaNaPredpise` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `vpliviNaPredpis` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `vrstaAkta` | `ZbirkaSifrantElementDTO` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisDTO` | `zveza` | `ZbirkaPovezavaPredpisEuElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisEuDTO` | `celex` | `string` | `source_record.source_id` | text | Namespace-qualified; opaque CELEX or canonical decimal int64. |
| `PredpisEuDTO` | `citatUL` | `string` | `record_revision.citation` | text | Traceable nullable projection. |
| `PredpisEuDTO` | `datumObjave` | `string(date)` | `record_revision.published_on` | date | Traceable nullable projection. |
| `PredpisEuDTO` | `datumPrenehanjaVeljavnosti` | `string(date)` | `record_revision.effective_until` | date | Traceable nullable projection. |
| `PredpisEuDTO` | `datumRokaZaPrenos` | `string(date)` | `record_revision.transposition_due_on` | date | Traceable nullable projection. |
| `PredpisEuDTO` | `datumZacetkaVeljavnosti` | `string(date)` | `record_revision.effective_from` | date | Traceable nullable projection. |
| `PredpisEuDTO` | `naziv` | `string` | `record_revision.title` | text | Traceable nullable projection. |
| `PredpisEuDTO` | `notifikacijskeIzjaveURL` | `string` | `record_revision.notification_url` | text | Traceable nullable projection. |
| `PredpisEuDTO` | `organOdgovorenZaPrenosOzIzvajanje` | `ZbirkaSifrantElementDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisEuDTO` | `podrocjeEu` | `ZbirkaSifrantElementDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisEuDTO` | `vrstaAktaEu` | `ZbirkaSifrantElementDTO` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisEuDTO` | `zveza` | `ZbirkaPovezavaElemnetDTO[]` | `reference_resolution.source_field + json_pointer + ordinal` | text + text + integer | Apply referenced child rows and keep direction. |
| `PredpisSeznamDTO` | `epa` | `string` | `record_revision.epa` | text | Traceable nullable projection. |
| `PredpisSeznamDTO` | `eva` | `string` | `record_revision.eva` | text | Traceable nullable projection. |
| `PredpisSeznamDTO` | `id` | `integer(int64)` | `source_record.source_id` | text | Namespace-qualified; opaque CELEX or canonical decimal int64. |
| `PredpisSeznamDTO` | `mopedId` | `string` | `record_revision.moped_id` | text | Traceable nullable projection. |
| `PredpisSeznamDTO` | `naziv` | `string` | `record_revision.title` | text | Traceable nullable projection. |
| `PredpisSeznamDTO` | `sop` | `string` | `record_revision.sop` | text | Traceable nullable projection. |
| `ZbirkaPovezavaElemnetDTO` | `mopedID` | `string` | `reference_resolution.token` | text | Exact source link; resolve separately. |
| `ZbirkaPovezavaElemnetDTO` | `naziv` | `string` | `reference_resolution.label` | text | Exact source link; resolve separately. |
| `ZbirkaPovezavaPredpisEuElemnetDTO` | `celex` | `string` | `reference_resolution.token` | text | Exact source link; resolve separately. |
| `ZbirkaPovezavaPredpisEuElemnetDTO` | `naziv` | `string` | `reference_resolution.label` | text | Exact source link; resolve separately. |
| `ZbirkaSifrantElementDTO` | `id` | `integer(int64)` | `source_record.source_id or reference_resolution.token` | text | Code endpoint root entry vs nested code reference; IDs retain dictionary scope. |
| `ZbirkaSifrantElementDTO` | `idNadrejeni` | `integer(int64)` | `record_revision.parent_code_id or reference_resolution.parent_token` | text | Code endpoint root entry vs nested code reference; IDs retain dictionary scope. |
| `ZbirkaSifrantElementDTO` | `naziv` | `string` | `record_revision.title or reference_resolution.label` | text | Code endpoint root entry vs nested code reference; IDs retain dictionary scope. |
| `ZetonZahtevekDTO` | `email` | `string` | `No application storage` | — | Access request only. Documented, no execution. |
| `ZetonZahtevekDTO` | `organizacija` | `string` | `No application storage` | — | Access request only. Documented, no execution. |

Operation 24 maps `idZbirkaElement` to `document_locator.request_id` and `source_work.request_target`. The returned representation maps to `source_blob.raw_bytes` and `source_artifact`. Its media, content coding and charset remain attached to the individual response. Resolve the state base vs state NPB class before attributing bytes to either. Catalogue and code-list request parameters have request provenance and no intrinsic legal update time.

## Qdrant contract

One physical collection `pisrs_piki_staging`, with `text-embedding-3-large`, 3,072-dimensional unnamed float32 vectors and Cosine. PostgreSQL owns the eligibility manifest and cached vectors. Replay the same inputs and restore the same points from PostgreSQL. [Publication and recovery](PIKI-PISRS-SYNC.md#qdrant-publication)

| Scope | Search by date | Costs and operation |
|---|---|---|
| Current-only | Serves current text. Historical lexical/structured reads from PostgreSQL can still work. Historical semantic recall stays outside this index. | Fewer embedded inputs and points. Rollover may discard vectors for previously served versions unless cached in PG. |
| Current and qualified historical versions | Semantic retrieval across supported dates. Current search uses today's legal date with the same temporal filter. | More unique chunks, points and storage. Exact text reuse deduplicates embedding costs across versions, with a separate point for each legal context. One collection, one publication pipeline. |

**Recommendation for owner approval** is the historical option with proven temporal applicability. PostgreSQL keeps all retrievable history under either option. Architecture approval covers scope and date semantics; G4 paid approval remains separate and binds measured unique missing input tokens, a current tariff, transfer scope and cap.

### Legal date eligibility

- The caller selects a civil date in Europe/Ljubljana; the default is today. PostgreSQL derives legal windows under a versioned evidence rule and records whether the result is applicability or validity. They are distinct concepts. Publication, source observation and NPB document dates remain provenance. No legal window is inferred solely from consolidation order, title or document date.
- Normalize approved boundaries to half-open day intervals `[from_day, to_day)`, using integer days from 1970-01-01. Convert an inclusive end only when the source meaning is known. A verified open end uses `open_end=true` and no `to_day`. Unknown endpoints have a distinct unresolved disposition. Preserve the underlying dates, rule and evidence.
- Default search answers what text applies on the selected date under the approved rules and evidence available to the archive. If the question is historical knowledge as of a publication cutoff, that is a separate mode; use publication/observation constraints only when explicitly requested and supported. Handle retroactivity, transitional provisions and applicability after repeal under separately approved rules. If a version contains provisions with different windows, split at those boundaries or exclude the unresolved span from dated search. A mixed or ambiguous span cannot inherit dates from a sibling. Return traceable gaps from PG, with no nearest-version substitution.
- Qdrant uses a nested window filter so start and end constraints apply to the same window object. Match requested `kind`, then `from_day <= date` and `to_day > date` or verified `open_end`. The query path rechecks each returned point against the published PG generation, window and requested date. Time coverage is evaluated per supported legal scope. [Qdrant filtering](https://qdrant.tech/documentation/search/filtering/)

Point ID = UUIDv5 under RFC 4122 URL namespace over UTF-8 canonical compact JSON array of `["urn:openlegalcore:pisrs:piki:point:v1", locator_kind, source_id, raw_sha256_hex, parser_revision, chunker_revision, chunk_ordinal, model, dimensions, text_sha256_hex]`. A legal-date or link correction updates payload and provenance while retaining the input cache key. All fields are present unless their row specifies the optional endpoint of a verified open interval.

| Field | Type and invariant |
|---|---|
| `index_revision`, `namespace`, `source_id`, `locator_kind` | Strings for contract, qualified source record and locator class. |
| `act_namespace`, `act_source_id`, `source_url` | Resolved strings for act and exact HTTPS locator. An unresolved act link is ineligible for legal-date search. |
| `document_number`, `document_date`, `version_label` | Nullable strings, with a date-only document date. Inferred labels remain identified in the archive. |
| `legal_windows` | Nonempty array of objects with `kind` (APPLICABLE/VALID), `from_day` integer, `open_end` boolean and `to_day` integer except for a verified open end. Each window has underlying approved PG evidence. |
| `chunk_ordinal`, `block_start`, `block_end`, `span` | Three nonnegative integers and a structured exact block/subspan sequence. |
| `artifact_sha256`, `text_sha256`, `parser_revision`, `chunker_revision`, `embedding_model`, `embedding_dimensions` | Five strings and one integer. The artifact hash ties the point to the retained original. |

Index fields actually required by the staging query profile, including day-boundary fields and scope. Scope, parsed evidence and input cache remain independent of the storage format of Qdrant.
