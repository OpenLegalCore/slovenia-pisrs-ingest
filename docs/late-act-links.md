# Late act links (OLC-85)

Development candidate only. Production linkage repair and release activation require
separate approval. This change adds no maintenance CLI, schema or status value.

## Link selection and invariants

After catalog/document persistence, nightly scans versions whose `act_id` is NULL.
An exact, nonempty `sop_from_docno = acts.sop` match is classified as zero, one or
multiple candidates. Only one candidate permits a link; zero and multiple remain
NULL and are counted. A minimum ID is used only inside `HAVING count(act.id)=1`.

The existing document budget also caps the number of repairable versions. Overflow
blocks the whole batch rather than choosing a partial subset. Selection freezes act
membership with a SHARE table lock and locks/revalidates parents and children.
Statement and lock timeouts are 30s and 3s. A child identity, collection, point UUID
or nonobject-payload conflict aborts the transaction. Inspect the service role's
lock/update privileges and the measured child counts before production approval.

One transaction fills the parent and NULL block/chunk links. A matching non-NULL
child link is preserved; a different one is a conflict. Rollover also refuses to
clear or reassign a non-NULL chunk link. Content, version/text identities, point IDs,
model/dimensions, vectors and status values are not changed by the link helper.
The PG JSON update overwrites only `act_id`, retaining every other key and value.
It does not repeat the completed general JSON materialization.

## Existing checkpoint and retry mechanism

`DocumentStore.pending()` selects changed/missing NPB documents, not late act links.
Adding the act alone therefore previously left imported versions with NULL links.
The new selection scans NULL parents independently of the document timestamp, after
the current catalog has been synchronized. No document fetch or HTML parse is added.

A linked version gets `updated_at=now()`. The existing `touched_sops(since)` includes
it and rollover returns all stored chunks in that SOP, including inactive history.
Checkpoint advancement remains the last successful nightly operation. A failure
after the PG commit retains the prior boundary, so the same parents remain reachable
on retry even though there are no longer any NULL links to fill. No `payload_pending`
status or new persistent queue is needed for this failure window.

The existing `uploaded` state identifies vectors that must be handled payload-only.
Nightly validates every such touched point's existence, identity, hash, model and
dimension payload before any embedding or Qdrant write. Missing/incompatible uploads
or unexpected payload keys block the interval. New/content-changed chunks retain the
existing pending/vector path. Matching existing vectors are reused; active and inactive
points receive only the required payload patch. Checkpoint retry safely repeats a
partially completed set of patches, without replacing vectors or re-embedding.

Do not manually advance a failed checkpoint. Recovery after an independently changed
checkpoint or out-of-band PG/Qdrant mutation is outside this interval-based guarantee.
Payload model/hash metadata is not independent proof of numerical embedding provenance.

## Verification layers

- Offline: simulated services prove fail-before-provider guards and payload-only reuse.
- Isolated PostgreSQL: unique/zero/ambiguous matches, existing links, identity conflicts,
  budget overflow, transaction rollback, second-run no-op, late arrival, and retry of
  the unchanged checkpoint with a simulated Qdrant failure.
- Optional isolated PG + real Qdrant: actual payload-only requests, partial failure/retry,
  byte-for-byte returned vector equality and zero embedder/upsert calls during repair.

The PG tests require a dedicated empty `pisrs_test_*` database via
`PISRS_TEST_DATABASE_DSN`. Real Qdrant tests additionally require an isolated
`PISRS_TEST_QDRANT_URL` on a random loopback port; they create/delete only their own
`pisrs_test_links_*` collection. Production ports are rejected by that fixture.

These tests do not establish upstream source completeness or production acceptance.
