-- Additive development migration. Apply only in a separately approved deployment.
-- RS identities stay in their existing tables; CELEX and LS IDs are never cast
-- into the RS register_id/text_id namespace.
BEGIN;
CREATE TABLE pisrs.source_catalog_items (
    namespace text NOT NULL CHECK (namespace IN ('EU', 'LS_ACT', 'LS_NPB')),
    source_id text NOT NULL CHECK (source_id <> ''),
    source_id_int bigint,
    title text,
    moped_plus_id text,
    eda text,
    sop text,
    sop_from_docno text,
    npb_label text,
    linked_act_namespace text,
    linked_act_source_id text,
    link_status text,
    seen_in_endpoints text[] NOT NULL,
    raw_by_endpoint jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (namespace, source_id),
    FOREIGN KEY (linked_act_namespace, linked_act_source_id)
        REFERENCES pisrs.source_catalog_items (namespace, source_id),
    CHECK (
        (namespace = 'EU' AND source_id_int IS NULL)
        OR (namespace IN ('LS_ACT', 'LS_NPB') AND source_id_int > 0
            AND source_id = source_id_int::text)
    ),
    CHECK (namespace <> 'LS_ACT' OR moped_plus_id IS NOT NULL),
    CHECK (
        (namespace = 'LS_NPB' AND link_status IS NOT NULL AND link_status IN
            ('UNIQUE_SOP', 'AMBIGUOUS_SOP', 'UNMATCHED_SOP', 'NO_PARSED_SOP'))
        OR (namespace <> 'LS_NPB' AND link_status IS NULL
            AND sop_from_docno IS NULL AND npb_label IS NULL)
    ),
    CHECK (
        (link_status = 'UNIQUE_SOP' AND linked_act_namespace IS NOT DISTINCT FROM 'LS_ACT'
            AND linked_act_source_id IS NOT NULL)
        OR (link_status IS DISTINCT FROM 'UNIQUE_SOP'
            AND linked_act_namespace IS NULL AND linked_act_source_id IS NULL)
    )
);
CREATE TABLE pisrs.state_raw_variants (
    register_id bigint NOT NULL REFERENCES pisrs.acts(register_id),
    endpoint text NOT NULL,
    raw_item jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (register_id, endpoint)
);
CREATE INDEX source_catalog_items_source_id_int_idx
    ON pisrs.source_catalog_items (namespace, source_id_int)
    WHERE source_id_int IS NOT NULL;
CREATE TABLE pisrs.source_text_versions (
    namespace text NOT NULL CHECK (namespace = 'LS_NPB'),
    source_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('imported', 'not_available')),
    last_attempt_reason text,
    source_url text NOT NULL,
    html text,
    plain_text text,
    blocks jsonb,
    articles jsonb,
    parser_warnings jsonb,
    parser_version text,
    content_hash text,
    checked_at timestamptz NOT NULL DEFAULT now(),
    imported_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (namespace, source_id),
    FOREIGN KEY (namespace, source_id)
        REFERENCES pisrs.source_catalog_items (namespace, source_id),
    CHECK (
        (status = 'imported' AND html IS NOT NULL AND plain_text IS NOT NULL
            AND blocks IS NOT NULL AND articles IS NOT NULL AND parser_version IS NOT NULL
            AND content_hash IS NOT NULL AND imported_at IS NOT NULL)
        OR (status = 'not_available'
            AND last_attempt_reason = 'NOT_AVAILABLE_FROM_API:HTTP_404'
            AND html IS NULL AND plain_text IS NULL AND blocks IS NULL AND articles IS NULL
            AND parser_version IS NULL AND content_hash IS NULL)
    )
);
GRANT SELECT, INSERT, UPDATE ON pisrs.source_catalog_items TO pisrs_ingest;
GRANT SELECT, INSERT, UPDATE ON pisrs.source_text_versions TO pisrs_ingest;
GRANT SELECT, INSERT, UPDATE ON pisrs.state_raw_variants TO pisrs_ingest;
COMMIT;
