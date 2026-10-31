# Existing architecture

Verified against public baseline b2fd71f8568a36271607ce847d7f1a47325a1631.
This describes implementation, not the current host installation or future source adapters.

## Data flow

1. cli.py validates configuration and acquires the shared mutation lock for nightly.
2. checkpoint.py reads the last successful boundary and fixes the run end.
3. client.py enumerates four state catalogs and /npb; postgres.py synchronizes metadata.
4. postgres_documents.py selects missing or metadata-updated NPB documents that have a
   recognized SOP and version label. client.py fetches /besedilo/{text_id}; models.py parses HTML.
5. PostgreSQL stores the original returned HTML, normalized text and parsed blocks by version.
6. postgres_chunks.py processes touched SOPs, selects the highest NPB rank (text_id tie-break),
   creates chunks for that version and deactivates older existing chunks.
7. pipeline.py reuses matching vectors or obtains embeddings, writes Qdrant payloads/vectors
   and records upload state. The checkpoint advances only after the interval succeeds.

## Authorities and identities

| Layer | Existing contract |
| --- | --- |
| Acts | register_id; required moped_id; SOP is a linkage value, not a globally unique act key. |
| NPB / versions | Numeric text_id; PostgreSQL version and catalog IDs are local relational keys. |
| Blocks | (version_id, block_index). |
| Chunks | (collection_name, text_id, chunk_index); SHA-256 of chunk text. |
| Qdrant | UUIDv5(NAMESPACE_URL, pisrs_current:{text_id}:{chunk_index}). |
| Vectors | text-embedding-3-large, 3072 dimensions, Cosine; collection pisrs_current. |
| State | PostgreSQL authoritative columns; Qdrant derived; atomic success-only checkpoint. |

The relevant tables are pisrs.act_sync_catalog, acts, npb_catalog, act_text_versions,
act_text_blocks and embedding_chunks. Legacy laws participates in act-status reconciliation.
Stored embedding_chunks.payload JSON and payloads reconstructed from columns are distinct
representations and require separate integrity checks.

## Existing limits

- The three requested additional state catalogs have no calls in this baseline.
  Dedicated EU, municipal and Gazette adapters are absent.
- Metadata discovery is broader than text import. Unrecognized SOP/version metadata is not
  selected by pending(); exclusions and missing text must be counted explicitly.
- PostgreSQL retains multiple imported text IDs; pisrs_current is not a complete vector archive
  of every historical version. Highest NPB rank does not itself prove legal applicability.
- Reconciliation compares reconstructed PostgreSQL payloads with Qdrant and scans Qdrant IDs.
  It does not independently prove upstream completeness, stored-JSON correctness, parser fidelity
  or numerical vector provenance. Dry-run can exit zero while reporting differences.
- Discovery completeness and HTML extraction require additional regression/real-source validation.

Source references: [client](src/pisrs_ingest/client.py),
[pipeline](src/pisrs_ingest/pipeline.py), [models](src/pisrs_ingest/models.py),
[PostgreSQL](src/pisrs_ingest/postgres.py), [documents](src/pisrs_ingest/postgres_documents.py),
[chunks](src/pisrs_ingest/postgres_chunks.py), [Qdrant](src/pisrs_ingest/qdrant.py).
