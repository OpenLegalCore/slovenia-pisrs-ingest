-- G3 source/archive PostgreSQL 18 schema. Exact 15 approved tables.
-- Applied once under an advisory lock in a single transaction by the migration CLI.
-- No G4 tables, paid calls, Qdrant, or Medo access.
CREATE SCHEMA IF NOT EXISTS pisrs;

CREATE TABLE pisrs.migration_log (
    version integer PRIMARY KEY CHECK (version > 0),
    migration_hash bytea NOT NULL CHECK (octet_length(migration_hash) = 32),
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE pisrs.contract_revision (
    revision text PRIMARY KEY CHECK (length(revision) > 0),
    openapi_hash bytea NOT NULL CHECK (octet_length(openapi_hash) = 32),
    schema_version integer NOT NULL CHECK (schema_version > 0),
    rules_revision text NOT NULL,
    parser_revision text NOT NULL,
    approved_at timestamptz,
    approval_ref text,
    CHECK ((approved_at IS NULL) = (approval_ref IS NULL))
);

CREATE TABLE pisrs.source_run (
    run_id uuid PRIMARY KEY,
    revision text NOT NULL REFERENCES pisrs.contract_revision(revision) ON DELETE RESTRICT,
    predecessor_run uuid REFERENCES pisrs.source_run(run_id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN ('INITIAL','NIGHTLY','VERIFY')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    ended_at timestamptz,
    published_at timestamptz,
    status text NOT NULL CHECK (status IN ('OPEN','INCOMPLETE','READY','PUBLISHED','SUPERSEDED','ABANDONED')),
    evidence_hash bytea CHECK (evidence_hash IS NULL OR octet_length(evidence_hash) = 32),
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    reason text,
    UNIQUE (run_id,revision),
    CHECK (status <> 'PUBLISHED' OR published_at IS NOT NULL)
);
CREATE UNIQUE INDEX source_one_published ON pisrs.source_run ((true)) WHERE status='PUBLISHED';
CREATE INDEX source_run_status_time ON pisrs.source_run (status,started_at);

CREATE TABLE pisrs.source_blob (
    sha256 bytea PRIMARY KEY CHECK (octet_length(sha256) = 32),
    raw_bytes bytea NOT NULL,
    byte_length bigint NOT NULL CHECK (byte_length >= 0 AND byte_length = octet_length(raw_bytes)),
    CONSTRAINT source_blob_digest_matches CHECK (sha256(raw_bytes) = sha256)
);

CREATE TABLE pisrs.source_record (
    record_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    namespace text NOT NULL CHECK (namespace IN ('RS_ACT','RS_NPB','LS_ACT','LS_NPB','EU','CODE_LIST','CODE_VALUE')),
    source_id text NOT NULL CHECK (length(source_id) > 0),
    parent_key text NOT NULL DEFAULT '',
    first_run uuid NOT NULL REFERENCES pisrs.source_run(run_id) ON DELETE RESTRICT,
    UNIQUE(namespace,parent_key,source_id),
    CHECK ((namespace = 'CODE_VALUE' AND length(parent_key) > 0)
        OR (namespace <> 'CODE_VALUE' AND parent_key = ''))
);

CREATE TABLE pisrs.record_revision (
    record_revision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    record_id bigint NOT NULL REFERENCES pisrs.source_record(record_id) ON DELETE RESTRICT,
    revision text NOT NULL REFERENCES pisrs.contract_revision(revision) ON DELETE RESTRICT,
    value_hash bytea NOT NULL CHECK (octet_length(value_hash) = 32),
    raw_jsonb jsonb NOT NULL,
    title text,
    short_title text,
    citation text,
    category_label text,
    notification_url text,
    moped_id text,
    moped_plus_id text,
    eva text,
    epa text,
    eda text,
    sop text,
    spatial_act_id text,
    is_basic boolean,
    is_spatial boolean,
    adopted_on date,
    published_on date,
    effective_from date,
    applicable_from date,
    effective_until date,
    applicable_until date,
    designation_on date,
    transposition_due_on date,
    document_date date,
    document_number text,
    parent_code_id text,
    UNIQUE(record_id,revision,value_hash),
    UNIQUE(record_revision_id,record_id)
);
CREATE INDEX record_revision_moped ON pisrs.record_revision(moped_id) WHERE moped_id IS NOT NULL;
CREATE INDEX record_revision_moped_plus ON pisrs.record_revision(moped_plus_id) WHERE moped_plus_id IS NOT NULL;
CREATE INDEX record_revision_sop ON pisrs.record_revision(sop) WHERE sop IS NOT NULL;
CREATE INDEX record_revision_eda ON pisrs.record_revision(eda) WHERE eda IS NOT NULL;
CREATE INDEX record_revision_doc_date ON pisrs.record_revision(document_date,record_id);

CREATE TABLE pisrs.document_locator (
    locator_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    record_id bigint NOT NULL REFERENCES pisrs.source_record(record_id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN ('RS_BASE','RS_NPB','LS_NPB','EU')),
    request_id text,
    scope_status text NOT NULL,
    UNIQUE(record_id,kind),
    CHECK (request_id IS NULL OR request_id ~ '^[0-9]+$')
);
CREATE INDEX document_locator_request ON pisrs.document_locator(kind,request_id) WHERE request_id IS NOT NULL;

CREATE TABLE pisrs.source_work (
    run_id uuid NOT NULL,
    revision text NOT NULL,
    source_key smallint NOT NULL CHECK (source_key BETWEEN 1 AND 26),
    sweep smallint NOT NULL CHECK (sweep >= 0),
    work_key text NOT NULL CHECK (length(work_key) > 0),
    request_target text,
    query_args jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL CHECK (status IN ('QUEUED','LEASED','RETRY','COMPLETE','QUARANTINED')),
    lease_until timestamptz,
    next_attempt_at timestamptz,
    terminal_attempt_id bigint,
    locator_id bigint REFERENCES pisrs.document_locator(locator_id) ON DELETE RESTRICT,
    artifact_id bigint,
    disposition text,
    decision_ref text,
    PRIMARY KEY(run_id,sweep,work_key),
    UNIQUE(run_id,sweep,work_key,source_key),
    FOREIGN KEY(run_id,revision) REFERENCES pisrs.source_run(run_id,revision) ON DELETE RESTRICT,
    CHECK (artifact_id IS NULL OR locator_id IS NOT NULL)
);
CREATE UNIQUE INDEX source_work_unique_locator ON pisrs.source_work(run_id,locator_id) WHERE locator_id IS NOT NULL;
CREATE INDEX source_work_queue ON pisrs.source_work(run_id,status,next_attempt_at);

CREATE TABLE pisrs.source_attempt (
    attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL,
    source_key smallint NOT NULL CHECK (source_key BETWEEN 1 AND 26),
    sweep smallint NOT NULL CHECK (sweep >= 0),
    work_key text NOT NULL,
    retry_no integer NOT NULL CHECK (retry_no >= 0),
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    result text NOT NULL CHECK (result IN ('OPEN','HTTP_COMPLETE','HTTP_INCOMPLETE','TRANSPORT_ERROR','CONTRACT_ERROR','BODY_WITHHELD')),
    reason_code text,
    retry_after timestamptz,
    http_status smallint CHECK (http_status BETWEEN 100 AND 599),
    sha256 bytea REFERENCES pisrs.source_blob(sha256) ON DELETE RESTRICT,
    content_type text,
    content_encoding text,
    media_charset text,
    etag text,
    last_modified text,
    data_pointer text,
    error_text text,
    page integer,
    requested_page_size integer,
    real_page_size integer,
    reported_total_count integer,
    UNIQUE(run_id,sweep,work_key,retry_no),
    UNIQUE(attempt_id,run_id,source_key),
    UNIQUE(attempt_id,run_id,sweep,work_key),
    UNIQUE(attempt_id,sha256),
    FOREIGN KEY(run_id,sweep,work_key,source_key) REFERENCES pisrs.source_work(run_id,sweep,work_key,source_key) ON DELETE RESTRICT
);
CREATE INDEX source_attempt_blob ON pisrs.source_attempt(sha256);
ALTER TABLE pisrs.source_work
    ADD CONSTRAINT source_work_terminal_attempt_fk
    FOREIGN KEY(terminal_attempt_id,run_id,sweep,work_key)
    REFERENCES pisrs.source_attempt(attempt_id,run_id,sweep,work_key) ON DELETE RESTRICT;

CREATE TABLE pisrs.source_occurrence (
    attempt_id bigint NOT NULL,
    run_id uuid NOT NULL,
    source_key smallint NOT NULL,
    json_pointer text NOT NULL,
    record_id bigint,
    record_revision_id bigint,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    validation text NOT NULL CHECK (validation IN ('VALID','QUARANTINED')),
    diagnostic text,
    selected boolean NOT NULL DEFAULT false,
    PRIMARY KEY(attempt_id,json_pointer),
    UNIQUE(attempt_id,ordinal),
    FOREIGN KEY(attempt_id,run_id,source_key)
        REFERENCES pisrs.source_attempt(attempt_id,run_id,source_key) ON DELETE RESTRICT,
    FOREIGN KEY(record_revision_id,record_id)
        REFERENCES pisrs.record_revision(record_revision_id,record_id) MATCH FULL ON DELETE RESTRICT,
    CHECK (NOT selected OR (validation = 'VALID' AND record_id IS NOT NULL))
);
CREATE UNIQUE INDEX source_occurrence_selected
    ON pisrs.source_occurrence(run_id,source_key,record_id) WHERE selected;
CREATE INDEX source_occurrence_record_run ON pisrs.source_occurrence(record_id,run_id);

CREATE TABLE pisrs.reference_resolution (
    record_revision_id bigint NOT NULL REFERENCES pisrs.record_revision(record_revision_id) ON DELETE RESTRICT,
    run_id uuid NOT NULL REFERENCES pisrs.source_run(run_id) ON DELETE RESTRICT,
    rules_revision text NOT NULL,
    json_pointer text NOT NULL,
    source_field text NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    kind text NOT NULL CHECK (kind IN ('CODE','MOPED','CELEX','NPB_SOP')),
    token text,
    label text,
    parent_token text,
    status text NOT NULL CHECK (status IN ('RESOLVED','AMBIGUOUS','UNRESOLVED','NOT_APPLICABLE')),
    target_record_id bigint REFERENCES pisrs.source_record(record_id) ON DELETE RESTRICT,
    candidate_ids bigint[] NOT NULL DEFAULT '{}'::bigint[],
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY(record_revision_id,run_id,rules_revision,json_pointer),
    CHECK ((status = 'RESOLVED' AND target_record_id IS NOT NULL AND cardinality(candidate_ids)=1)
        OR (status <> 'RESOLVED' AND target_record_id IS NULL))
);
CREATE INDEX reference_kind_token ON pisrs.reference_resolution(kind,token);

CREATE TABLE pisrs.identity_event (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES pisrs.source_run(run_id) ON DELETE RESTRICT,
    record_id bigint NOT NULL REFERENCES pisrs.source_record(record_id) ON DELETE RESTRICT,
    field text NOT NULL,
    old_value text,
    new_value text,
    status text NOT NULL CHECK (status IN ('OBSERVED','APPROVED','QUARANTINED')),
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    decision_ref text,
    UNIQUE(run_id,record_id,field)
);
CREATE INDEX identity_event_status ON pisrs.identity_event(status,run_id);

CREATE TABLE pisrs.source_artifact (
    artifact_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    locator_id bigint NOT NULL REFERENCES pisrs.document_locator(locator_id) ON DELETE RESTRICT,
    sha256 bytea NOT NULL REFERENCES pisrs.source_blob(sha256) ON DELETE RESTRICT,
    first_attempt_id bigint NOT NULL,
    FOREIGN KEY(first_attempt_id,sha256) REFERENCES pisrs.source_attempt(attempt_id,sha256) ON DELETE RESTRICT,
    UNIQUE(locator_id,sha256),
    UNIQUE(artifact_id,locator_id)
);
ALTER TABLE pisrs.source_work
    ADD CONSTRAINT source_work_artifact_locator_fk
    FOREIGN KEY(artifact_id,locator_id)
    REFERENCES pisrs.source_artifact(artifact_id,locator_id) ON DELETE RESTRICT;

CREATE TABLE pisrs.parsed_document (
    parse_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artifact_id bigint NOT NULL REFERENCES pisrs.source_artifact(artifact_id) ON DELETE RESTRICT,
    parser_revision text NOT NULL,
    media_profile text NOT NULL,
    decoded_charset text,
    state text NOT NULL CHECK (state IN ('READY','QUARANTINED')),
    warnings jsonb NOT NULL DEFAULT '{}'::jsonb,
    normalized_text text,
    text_hash bytea CHECK (text_hash IS NULL OR octet_length(text_hash)=32),
    language text,
    UNIQUE(artifact_id,parser_revision,media_profile),
    CHECK (state <> 'READY' OR (normalized_text IS NOT NULL AND text_hash IS NOT NULL))
);

CREATE TABLE pisrs.text_block (
    parse_id bigint NOT NULL REFERENCES pisrs.parsed_document(parse_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    parent_ordinal integer,
    kind text NOT NULL,
    legal_label text,
    dom_locator text NOT NULL,
    source_start bigint,
    source_end bigint,
    normalized_text text NOT NULL,
    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY(parse_id,ordinal),
    FOREIGN KEY(parse_id,parent_ordinal) REFERENCES pisrs.text_block(parse_id,ordinal) ON DELETE RESTRICT,
    CHECK (parent_ordinal IS NULL OR parent_ordinal < ordinal),
    CHECK ((source_start IS NULL AND source_end IS NULL)
        OR (source_start >= 0 AND source_end > source_start))
);

-- G3 least-privilege grants. Roles are created and reviewed by the PIKI
-- database operator BEFORE this migration. Source can never alter schema
-- or mutate the signed contract/migration ledger. QA has no raw-table access.
GRANT USAGE ON SCHEMA pisrs TO pisrs_source, pisrs_backup;
GRANT SELECT ON pisrs.migration_log, pisrs.contract_revision TO pisrs_source;
GRANT SELECT, INSERT, UPDATE ON
    pisrs.source_run, pisrs.source_work, pisrs.source_attempt,
    pisrs.document_locator TO pisrs_source;
GRANT SELECT, INSERT ON
    pisrs.source_blob, pisrs.source_record, pisrs.record_revision,
    pisrs.source_occurrence, pisrs.reference_resolution, pisrs.identity_event,
    pisrs.source_artifact, pisrs.parsed_document, pisrs.text_block TO pisrs_source;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA pisrs TO pisrs_source;
GRANT SELECT ON ALL TABLES IN SCHEMA pisrs TO pisrs_backup;
