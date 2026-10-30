-- READ ONLY plan. No repairs, no provider calls, no checkpoint changes.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '3s';
SET LOCAL max_parallel_workers_per_gather = 0;
WITH candidates AS (
 SELECT version.id, count(act.id) AS matches
 FROM pisrs.act_text_versions version LEFT JOIN pisrs.acts act
 ON act.sop=version.sop_from_docno AND btrim(version.sop_from_docno)<>''
 WHERE version.act_id IS NULL GROUP BY version.id
)
SELECT count(*) FILTER(WHERE matches=1) AS unique_repairable_versions,
 count(*) FILTER(WHERE matches=0) AS unmatched_versions,
 count(*) FILTER(WHERE matches>1) AS ambiguous_versions FROM candidates;
WITH targets AS (
 SELECT version.id FROM pisrs.act_text_versions version JOIN pisrs.acts act
 ON act.sop=version.sop_from_docno WHERE version.act_id IS NULL
 AND btrim(version.sop_from_docno)<>'' GROUP BY version.id HAVING count(act.id)=1
)
SELECT (SELECT count(*) FROM pisrs.act_text_blocks WHERE version_id IN(SELECT id FROM targets) AND act_id IS NULL) AS blocks_to_link,
 (SELECT count(*) FROM pisrs.embedding_chunks WHERE collection_name='pisrs_current' AND version_id IN(SELECT id FROM targets) AND act_id IS NULL) AS chunks_to_link;
SELECT count(*) AS chunks_checked,
 count(*) FILTER(WHERE chunk.payload IS DISTINCT FROM chunk.payload || jsonb_build_object('source', 'pisrs', 'collection_name', chunk.collection_name, 'act_id', chunk.act_id, 'version_id', chunk.version_id, 'text_id', chunk.text_id, 'sop', chunk.sop, 'sop_from_docno', chunk.sop_from_docno, 'npb_label', chunk.npb_label, 'naziv', chunk.naziv, 'title', chunk.title, 'chunk_index', chunk.chunk_index, 'chunk_type', chunk.chunk_type, 'chunk_text_len', chunk.chunk_text_len, 'block_start_index', chunk.block_start_index, 'block_end_index', chunk.block_end_index, 'block_count', chunk.block_count, 'token_estimate', chunk.token_estimate, 'content_hash', chunk.content_hash, 'is_latest_for_sop', chunk.is_latest_for_sop, 'is_active', chunk.is_active, 'embedding_model', chunk.embedding_model, 'embedding_dimensions', chunk.embedding_dimensions, 'text', chunk.chunk_text)) AS managed_json_mismatches,
 count(*) FILTER(WHERE jsonb_typeof(chunk.payload)<>'object') AS nonobject_payloads
FROM pisrs.embedding_chunks chunk WHERE collection_name='pisrs_current';
SELECT key,count(*) AS rows_preserved FROM pisrs.embedding_chunks chunk,
 LATERAL jsonb_object_keys(chunk.payload) AS key
 WHERE collection_name='pisrs_current' AND key NOT IN ('source',
 'collection_name','act_id','version_id','text_id','sop','sop_from_docno','npb_label','naziv','title','chunk_index','chunk_type','chunk_text_len','block_start_index','block_end_index','block_count','token_estimate','content_hash','is_latest_for_sop','is_active','embedding_model','embedding_dimensions','text')
 GROUP BY key;
SELECT sop,array_agg(register_id ORDER BY register_id) AS distinct_register_identities
FROM pisrs.acts WHERE btrim(sop)<>'' GROUP BY sop HAVING count(*)>1;
SELECT count(*) AS chunks,md5(string_agg(id::text || ':' || collection_name || ':' || text_id::text || ':' || chunk_index::text || ':' || coalesce(qdrant_point_id,'NULL') || ':' || content_hash,',' ORDER BY id)) AS identity_content_fingerprint
FROM pisrs.embedding_chunks WHERE collection_name='pisrs_current';
ROLLBACK;
