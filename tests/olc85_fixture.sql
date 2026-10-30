CREATE SCHEMA pisrs;
CREATE TABLE pisrs.acts (
 id bigint PRIMARY KEY, register_id bigint UNIQUE NOT NULL, sop text, moped_id text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE pisrs.laws (register_id bigint, sop text, moped_id text);
CREATE TABLE pisrs.act_sync_catalog (
 register_id bigint, sop text, moped_id text, status text,
 imported_at timestamptz, status_reason text, updated_at timestamptz DEFAULT now()
);
CREATE TABLE pisrs.npb_catalog (
 id bigint PRIMARY KEY, text_id bigint UNIQUE NOT NULL, naziv text,
 datum_dokumenta date, stevilka_dokumenta text, sop_from_docno text,
 npb_label text, raw_item jsonb NOT NULL DEFAULT '{}', status text DEFAULT 'imported',
 updated_at timestamptz NOT NULL DEFAULT '2026-01-01Z'
);
CREATE TABLE pisrs.act_text_versions (
 id bigint PRIMARY KEY, act_id bigint REFERENCES pisrs.acts, text_id bigint UNIQUE NOT NULL,
 sop text, sop_from_docno text, npb_label text NOT NULL, naziv text, title text, raw_meta jsonb NOT NULL DEFAULT '{}',
 updated_at timestamptz NOT NULL DEFAULT '2026-01-01Z'
);
CREATE TABLE pisrs.act_text_blocks (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 version_id bigint NOT NULL REFERENCES pisrs.act_text_versions,
 act_id bigint REFERENCES pisrs.acts, text_id bigint NOT NULL,
 block_index integer NOT NULL, block_type text NOT NULL,
 article_no text, article_title text, class_list text[] NOT NULL DEFAULT '{}', text text NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT '2026-01-01Z', UNIQUE(version_id,block_index)
);
CREATE TABLE pisrs.embedding_chunks (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source text NOT NULL DEFAULT 'pisrs', collection_name text NOT NULL,
 act_id bigint REFERENCES pisrs.acts, version_id bigint NOT NULL REFERENCES pisrs.act_text_versions,
 text_id bigint NOT NULL, sop text, sop_from_docno text, npb_label text NOT NULL,
 naziv text, title text, chunk_index integer NOT NULL, chunk_type text NOT NULL,
 chunk_text text NOT NULL, chunk_text_len integer NOT NULL,
 block_start_index integer, block_end_index integer, block_count integer NOT NULL,
 token_estimate integer NOT NULL, content_hash text NOT NULL,
 is_latest_for_sop boolean NOT NULL, is_active boolean NOT NULL,
 embedding_model text NOT NULL, embedding_dimensions integer NOT NULL,
 qdrant_point_id text, qdrant_status text NOT NULL DEFAULT 'uploaded',
 qdrant_error text, qdrant_upserted_at timestamptz DEFAULT '2026-01-01Z',
 payload jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT '2026-01-01Z',
 UNIQUE(collection_name,text_id,chunk_index)
);

-- Mirrors the read-only production inspection: text status, no enum/CHECK,
-- validated FKs and the sole user trigger changing only updated_at.
CREATE FUNCTION pisrs.touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at=now(); RETURN NEW; END $$;
CREATE TRIGGER trg_embedding_chunks_updated_at BEFORE UPDATE ON pisrs.embedding_chunks
FOR EACH ROW EXECUTE FUNCTION pisrs.touch_updated_at();
