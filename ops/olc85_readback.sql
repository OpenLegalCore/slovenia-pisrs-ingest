-- READ ONLY: compare fingerprint with the approved pre-repair manifest.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '3s';
SELECT count(*) AS unexplained_null_version_links FROM pisrs.act_text_versions version
WHERE act_id IS NULL AND (SELECT count(*) FROM pisrs.acts act
 WHERE act.sop=version.sop_from_docno AND btrim(version.sop_from_docno)<>'')=1;
SELECT count(*) AS inconsistent_block_links FROM pisrs.act_text_blocks block
JOIN pisrs.act_text_versions version ON version.id=block.version_id
WHERE block.act_id IS DISTINCT FROM version.act_id;
SELECT count(*) AS inconsistent_chunk_links FROM pisrs.embedding_chunks chunk
JOIN pisrs.act_text_versions version ON version.id=chunk.version_id
WHERE chunk.act_id IS DISTINCT FROM version.act_id;
SELECT count(*) AS managed_json_mismatches FROM pisrs.embedding_chunks chunk
WHERE collection_name='pisrs_current'
 AND chunk.payload IS DISTINCT FROM chunk.payload || jsonb_build_object('source', 'pisrs', 'collection_name', chunk.collection_name, 'act_id', chunk.act_id, 'version_id', chunk.version_id, 'text_id', chunk.text_id, 'sop', chunk.sop, 'sop_from_docno', chunk.sop_from_docno, 'npb_label', chunk.npb_label, 'naziv', chunk.naziv, 'title', chunk.title, 'chunk_index', chunk.chunk_index, 'chunk_type', chunk.chunk_type, 'chunk_text_len', chunk.chunk_text_len, 'block_start_index', chunk.block_start_index, 'block_end_index', chunk.block_end_index, 'block_count', chunk.block_count, 'token_estimate', chunk.token_estimate, 'content_hash', chunk.content_hash, 'is_latest_for_sop', chunk.is_latest_for_sop, 'is_active', chunk.is_active, 'embedding_model', chunk.embedding_model, 'embedding_dimensions', chunk.embedding_dimensions, 'text', chunk.chunk_text);
SELECT count(*) AS version_act_sop_mismatch FROM pisrs.act_text_versions version
JOIN pisrs.acts act ON act.id=version.act_id
WHERE version.sop_from_docno IS DISTINCT FROM act.sop;
SELECT qdrant_status,count(*) FROM pisrs.embedding_chunks
WHERE collection_name='pisrs_current' GROUP BY qdrant_status;
SELECT count(*) AS chunks,md5(string_agg(id::text || ':' || collection_name || ':' || text_id::text || ':' || chunk_index::text || ':' || coalesce(qdrant_point_id,'NULL') || ':' || content_hash,',' ORDER BY id)) AS identity_content_fingerprint
FROM pisrs.embedding_chunks WHERE collection_name='pisrs_current';
ROLLBACK;
