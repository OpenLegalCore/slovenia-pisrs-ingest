# PostgreSQL metadata integrity contract (OLC-85 candidate)

This is a local candidate, not deployment or repair authorization. PostgreSQL
columns are authoritative; `embedding_chunks.payload` is a materialized cache;
Qdrant is a derived index. The point ID, content hash, chunk text, text/version
identity, model, dimensions and checkpoint are invariant under metadata repair.

## Act identity

An existing non-NULL act link is evidence and is never reassigned by this repair.
For a NULL link, match the exact nonempty `sop_from_docno` to `acts.sop`:

- zero matches: retain NULL, report `unmatched`;
- one match: fill the parent and its NULL child links in one transaction;
- multiple matches: retain NULL, report `ambiguous`; never merge acts or select an
  arbitrary register identity. Existing proven links in that SOP remain unchanged.

Freeze actor candidate membership with `LOCK TABLE pisrs.acts IN SHARE MODE`,
lock target parents/children, validate child identities and JSON object shape,
and stop before writes on a conflicting non-NULL child link. Lock timeout is 3s;
statement timeout is 30s. Inspect permissions and concurrent writers before any
future approved execution. The nightly version budget also bounds link repair;
overflow blocks without truncating.

The nightly invokes `repair_act_links()` after catalog/document persistence and
before rollover, restricted to versions with local JSON boolean
`raw_meta.automatic_act_link_repair=true`. Only the first local import of a new
version grants that marker. Existing versions without the marker retain NULL
act_id even if re-fetched after a catalog update; a refresh never enrolls them.
The marker is not taken from source metadata and survives reimports, late acts,
failures and checkpoint boundaries. There is no deployment-time enrollment or
implicit historical sweep. Historical links require the separately approved
`approved_targets` map in the manifest maintenance window. Ambiguous SOPs still
cannot supply a link. It does not refetch unchanged documents. Repaired versions get
an updated timestamp; indexed changed chunks get `qdrant_status=payload_pending`.
`touched_sops()` includes this persisted queue independently of checkpoint time.

## Materialized payload

`canonical_payload()` and SQL materialization share `CANONICAL_PAYLOAD_COLUMNS`.
Repair uses `old_payload || canonical_payload_from_columns`: canonical keys win,
including explicit nulls; unknown PG provenance keys retain their exact JSON
values. Nonobject payloads require manual review. Unknown PG-only keys are never
copied into Qdrant's managed payload. Future chunk upserts preserve those extras
and compare the merged result so a second identical upsert remains a no-op.
Every touched SOP refreshes all its materialized rows, including older inactive
rows. Existing untouched legacy rows need the separately approved bounded repair.

This contract includes `text`; storage/WAL/free-space impact must be measured
before repair. Flag-only normalization is not a complete cache repair. The
internal `refresh_stored_payloads(..., ids=batch)` requires explicit distinct
positive PKs and rejects None, missing IDs, duplicates and batches over 1000 before
SQL. An empty batch is a no-op. There is no all-row or SOP argument on that API.
Normal touched-SOP selection uses keyset reads and the same <=1000-PK UPDATEs;
link repair also materializes its changed chunks in <=1000-PK batches.
No new general-purpose maintenance apply CLI is introduced.

## Qdrant and recovery

A `payload_pending` row requires an existing point with matching content hash,
model and dimensions. Validate the whole marked subset before any provider call
or Qdrant write. Missing/mismatched vectors or unknown Qdrant payload keys block
repair. No vector is created or replaced on this path. Both active and inactive
rows receive payload patches and are acknowledged as `uploaded` only after the
Qdrant operation succeeds. A failed acknowledgement is safe to repeat.

The marker survives partial PG/Qdrant failure and is retried even outside the
checkpoint interval. Checkpoint advancement remains the last successful nightly
operation. On a healthy index, changing only act_id requires only a payload patch.
The one-time repair uses `maintenance.run_manifest_repair`, not a second
`reconcile --apply` process. The function acquires exactly one ApplicationLock,
runs the reviewed PG callback, applies pinned Qdrant changes, acknowledges PG,
and performs final readback before releasing that same owner. Callback code must
not acquire another ApplicationLock or invoke a locking CLI. Nightly uses only
the automatic scope described above; maintenance is a separate, explicitly
authorized operation.

## Manifest-bound one-time maintenance (R1–R2)

`PinnedManifest.from_bytes` requires an externally approved SHA-256 of the exact
private manifest bytes. It never computes approval from a new dry-run itself.
The manifest binds exact canonical point IDs, old NULL/new positive act_id,
full before-payloads, a unique version-to-act map, the collection point count,
and SHA-256 fingerprint of the complete preapproved canonical collection.
Duplicate/unknown fields, types, identities, contracts or budget excess fail closed.
Every approved version must have at least one manifest point; versions without
indexed points require a separately reviewed PG-only procedure. Before any PG
callback, compare the exact point-ID sets per approved version against both the
complete authoritative PG iterator and Qdrant iterator, including inactive and
nonlatest points. A missing sibling, an omitted version or extra membership
fails with zero PG/Qdrant writes. The same gate runs on resume and rollback;
normalizing before/after act_id does not relax version membership.
Keep manifests/before-images private: they contain text and are not repository data.

The complete PG and Qdrant canonical payloads are fingerprinted under the owner;
only manifest act_id before/after states are normalized. Matched PG/Qdrant drift
on a different point also fails the baseline hash. Before PG writes and again
before Qdrant writes, require the approved full baseline and no unexplained
missing/orphan/unsafe point. The approved version map is passed to
`repair_act_links(..., approved_targets=...)`; any new or changed candidate
stops that transaction before writing. Cache repair uses only approved explicit
PK batches. PG cache-only updates do not change canonical Qdrant payloads.

Forward maintenance uses only literal
`set_payload(approved_point_id, {"act_id": approved_target})`. Qdrant 1.17.1 treats
merge `act_id: null` as key deletion, so inverse maintenance uses native
`overwrite_payload(approved_point_id, exact_approved_before_payload)`. Both require
the same exact manifest identity and before/after image validation. Missing keys
are never treated as null. An inverse call requires the approved complete vector
fingerprint, reads the target vector before/after each replacement and performs a
complete bounded vector fingerprint readback. Every other key must remain exact. The owner and payload are rechecked after the
vector read immediately before replacement. Qdrant offers no atomic payload CAS;
exclusive exclusion of other writers is still required, including external clients.
It does not call broad apply, vector upsert, deletion, embedding or an apply subprocess. Re-read
each point immediately before writing and after writing; perform full collection
readback before PG acknowledgement and again afterwards. Unexpected pre-existing
changes stop before writes. A failure or change arising during apply stops the
next operation and retains approved partial states for resume; it is not a claim
that Qdrant provides a distributed transaction or protection against rogue admins.

For rollback use the same manifest and `direction="rollback"`; its inverse target
is the recorded old act_id. Restore approved semantic PG before-images with CAS
in the owner callback, then the same restricted writer restores only those point
act_ids. Already-applied forward/inverse entries are no-ops. Provenance, vectors,
content hashes and IDs remain immutable. The production touch_updated_at trigger
stays enabled, so rollback restores semantic data, not historical updated_at
bytes. No disabling trigger, schema mutation or checkpoint rewrite is implied.

The function defaults to writes disabled and requires external=false. There is no
new general apply CLI. See the private candidate runbook for concrete callback
wiring and production gates; executing tests does not authorize production repair.

## Exclusive maintenance window (R4)

`SystemdMaintenanceWindow` only reads systemd. It requires an **effectively masked**
service (LoadState=masked, UnitFileState=masked or masked-runtime), inactive/dead,
zero main/control PID, inactive timer, no queued PISRS jobs, and an explicit
deadline within two hours. Timer calendar files are not changed by this guard.
Known writers must be excluded by a separately approved operational procedure.
Out-of-band PG/Qdrant writers that ignore the application lock must also be
excluded; the code cannot grant that assurance on behalf of the owner.

A runtime mask is not assumed sufficient for a locally installed /etc unit:
/etc has precedence over /run and systemctl masking can fail for local units.
Observe the actual effective mask after an approved exclusion procedure; command
success or an operator assertion alone is insufficient. Do not move, replace,
mask, stop or reload production units under this candidate's authorization.
If effective exclusion cannot be provided, STOP; an inode check is not a substitute.

The canonical runtime lock directory must already exist, be private and owned by
the executing service identity. The maintenance entry creates no directory or
permissions. ApplicationLock.assert_owned verifies the original PID and live
inode; the owner also checks the parent inode, checkpoint bytes and deadline.
Systemd state is rechecked before every write/phase; read-only scan batches check
inodes/checkpoint/deadline without thousands of redundant systemctl subprocesses.
A cleanup, replacement, unmask, queued job, timer restart or deadline causes STOP.
No mask/timer/checkpoint operations are executed by this candidate.

## Catalog status semantics

`act_sync_catalog.status` belongs to the **legacy laws workflow**, not the NPB or
vector workflow. Its current implementation is retained:

- `imported`: a legacy import assertion. `ACT_STATUS_RECONCILIATION` promotes on
  an existing `laws` row matched by register_id, SOP or moped_id. The status is
  retained on later refreshes; it is not a current completeness proof.
- `pending`: no completed legacy assertion. It may coexist with fully persisted
  NPB versions and uploaded chunks. It does not mean the NPB text is missing.
- `skipped_no_npb`, `skipped_no_text`, `failed`: existing reason-coded legacy
  outcomes retained by catalog upsert; the existing legacy-presence promotion
  can still set imported when a matching law exists.
- `acts.sync_status` labels likewise belong to that legacy metadata/laws view.

Do not run `pending -> imported` based on NPB existence. Report separately:
current legacy presence, known NPB count for the SOP, imported versions,
directly linked versions, unresolved/ambiguous links, eligible latest chunks,
Qdrant readback. SOP-level coverage does not prove which actor in a duplicate
SOP owns a document. No new statuses, mass status rewrite or schema migration
are part of this candidate.

## Standalone preflight

Default `preflight` stays strict for systemd ExecStartPre. Its RuntimeDirectory
is created by systemd and removed after an inactive oneshot service.

For a read-only manual connectivity/contract check with an absent lock directory:

```sh
PISRS_ALLOW_EXTERNAL_API=0 PISRS_ALLOW_WRITES=0 pisrs-ingest preflight --manual
```

Use the existing private environment and service identity. This option creates
no directory, lock, checkpoint or permissions. It can defer only an absent lock
parent, reporting `paths.lock=deferred_missing_parent` and `runtime_ready=false`.
It still validates checkpoint paths, existing paths/permissions, schema, database,
collection and vector contract. It does not establish readiness to run nightly.
Existing inaccessible paths and non-directory paths still fail. Default strict
behavior and the two authorization flags are not relaxed. No unit edit is needed.


## Concrete private PostgreSQL images and callbacks

`postgres_maintenance.capture_pg_images` performs read-only capture under the
existing MaintenanceOwner and executable exclusion guard. Its caller supplies
explicit extra cache PKs and an explicit total row budget. All children of the
approved version IDs are enumerated before review; no child may be omitted. Each
private JSON file contains at most 1000 explicit PKs with complete semantic
before/staged/acknowledged images. They are derived from the shared canonical
payload map, retaining provenance and every source/identity column. The sole
excluded column is trigger-owned `updated_at`, which legitimately advances.
Metadata acknowledgement preserves the original vector upsert timestamp.

The private parent and image directories must be owned mode 0700; regular files
must be owned mode 0600 with one link and no symlinks. Files and directories are
fsynced and the complete index is atomically published before any data UPDATE.
The returned SHA is evidence for separate operator review, never implicit approval.
The index binds the exact manifest SHA, database name, vector baseline, topology,
PK lists and every batch hash. Interrupted capture has no published index and
cannot authorize data writes. A new capture refuses already-linked parent versions.

After review, construct `PgMaintenanceCallbacks(database, directory,
approved_index_sha256, manifest)` and pass its `prepare_pg`, `acknowledge_pg` and
`readback_pg` methods to `run_manifest_repair`, together with
`expected_vector_fingerprint=callbacks.vector_fingerprint`. No second locking CLI
or generic reconcile apply is involved; there is no new production apply CLI.

Before any data UPDATE the callbacks validate the private hashes, full parent/
child topology, unique SOP identity and all current row images. Each transaction
locks at most 1000 explicit rows and uses a full JSON semantic before-image CAS;
returned after-images must equal the approved target. Unique act identity is
checked again while the act table lock is held. Pre-existing drift stops before
any UPDATE. Late concurrent drift aborts its transaction and stops the operation;
previous committed batches remain recoverable. Do not run without start exclusion.

Progress is represented by the actual row image, not a mutable checkpoint or an
in-memory list. A new process accepts only exact approved before, staged or
acknowledged states. Completed forward replay never recreates payload_pending;
inverse restores exact semantic before-images including status/error/cache.
Every batch and final readback is checked under the same live owner. Full images
and vector scans consume storage/read bandwidth; production capacity, permissions,
reviewed manifests and exclusion remain separate operational gates. Keep all
private images outside the repository and out of packages/PR attachments.
