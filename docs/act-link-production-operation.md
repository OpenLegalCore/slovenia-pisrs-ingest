# Closed production act-link operation (review preparation)

Base: `895aee884a1484f30ecace713ead21e5af9bdef0`, PR #15 / OLC-85.
No production apply is authorized by preparing this package.

The nightly helper's count limit is not a closed selector. The separate
`act_link_manifest` API accepts a full approved mapping and before-images, locks
`acts` in SHARE mode and target parents/children in deterministic order, checks
exact full state and unique SOP candidates, then updates only explicit row IDs.
Validated, immediate child FKs plus parent FOR UPDATE locks prevent child inserts
from escaping the membership check. New eligible versions outside the manifest
are ignored. A new child within its parents is drift and stops the operation.

## Package and identity

The private sealed package contains the 352 previously measured version IDs and
only their 22,828 blocks / 1,271 chunks and existing Qdrant IDs. It includes full PG
before-images and Qdrant payload before-images with hashes of actual retrieved
3072-dimensional vectors. No vectors are ever written by the executor.

Preparation used the existing legitimate pkexec path, then dropped to the effective
service user. The canonical application flock is opened without creating/truncating
its file. No runtime directory, timer, unit, role or permission is modified.
PG metadata checks are READ ONLY; SHARE-lock permission is inferred from effective
UPDATE privilege on acts, and tested with that privilege in isolated PostgreSQL.

The default launcher only checks SHA256SUMS and its members. A future explicit
apply/rollback requires the separately approved manifest and package hashes and
pkexec. Verified bytes are staged in a root-owned private directory before any
package code is loaded. Environment secrets remain in memory; no PISRS/OpenAI key
is selected. All production URLs are pinned to the existing loopback identities.

## Proposed apply

1. Verify the sealed files, source/base, effective environment, role/ACLs/triggers,
   inactive service, existing runtime and canonical lock. Do not stop the timer.
2. As the service user, hold that same nonblocking flock for the full operation.
   In one PG transaction, lock and compare exact approved membership, all original
   columns and unique SOP candidates. Limits: statement 30s, lock 3s, idle 120s.
3. Resolve the expected updated_at value from that transaction timestamp. Fsync and
   read back the full before/expected images and hash-bearing commit intent before
   any UPDATE. The reviewed timestamp triggers change updated_at; no status changes.
4. Recheck all affected existing Qdrant payloads and actual vector hashes, then
   update only act_id, chunk JSON act_id and accompanying updated_at in PG.
   Compare every column with the full expected image before commit.
5. Resolve the commit on a fresh connection using blocking row locks. Exact after
   means committed; exact before means NOT_APPLIED_STOP, with no automatic UPDATE
   retry. Mixed/changed state means STOP. No new target discovery is performed.
6. Patch only act_id on existing Qdrant points with wait=true. On resume, retrieve
   and classify every point before patching; already-correct points get no write.
   Lost point responses are resolved by retrieval. Retrieve actual vectors before
   and after, and persist full payload/readback proofs. Confirm full PG state again.

The existing original checkpoint is neither readjusted nor advanced. This operation
never calls nightly, prepare_rollover, fetch/parse, embedding or vector upsert APIs.
The code fails before a write if the canonical lock inode changes or the service
becomes active; the overall mutation budget is one hour.

## Conditional recovery

A separate explicit rollback mode uses the same package, application lock and
journal. First prove exact expected PG state and every Qdrant point as either its
original or this operation's expected state, with unchanged actual vectors. Restore
only points which need it. Qdrant set_payload(null) deletes a key; exact NULL-key
restoration therefore uses overwrite_payload with the checked full original
payload. This changes no other payload values and never includes vectors.

Only after the Qdrant recovery readback does the narrow root broker regenerate the
approved PG recovery SQL. All tables must exactly match their full expected images
under row locks before any UPDATE. It restores only act_id, chunk payload and
updated_at. The three named timestamp triggers are disabled and re-enabled inside
that single bounded transaction. ACCESS EXCLUSIVE locks prevent concurrent access
and trigger-state changes during recovery. FK and other triggers remain enabled,
SET CONSTRAINTS ALL IMMEDIATE is used, and a replica-mode session is rejected.
All outgoing FK values of the closed rows are checked by explicit anti-joins before
and after recovery, including unchanged npb_catalog_id/version_id fields. Incoming
FKs must reference immutable fields. Full-row checks run again before commit;
confirmed restores are not repeated. Corrupt images, unrelated changes or an
unresolved outcome stop recovery. No vector overwrite is available.

### Why the original c51691a used replica mode, and why it is replaced

The installed BEFORE UPDATE ROW triggers are:

- trg_act_text_versions_updated_at
- trg_act_text_blocks_updated_at
- trg_embedding_chunks_updated_at

Each calls pisrs.touch_updated_at(), whose body assigns NEW.updated_at=now() and
returns NEW. An ordinary UPDATE therefore cannot restore the old timestamp.
The original proposal used SET LOCAL session_replication_role=replica to skip those
triggers. That setting also suppresses origin-mode referential-integrity triggers
and rules. The inspected relationship graph contains six FKs and 24 internal RI
triggers (check_ins/check_upd, noaction_upd, setnull_del and cascade_del), all origin
mode, in addition to the three timestamps. Full-row hashes alone are not a fresh
validation of every unchanged FK value.

The reviewed replacement bypasses only the three named, body-checked timestamp
triggers. All three must initially be enabled in origin mode, with no WHEN clause,
column filter or arguments. They are restored to that state before commit, and DDL
rolls back on any failure. No DISABLE TRIGGER ALL/USER and no replica session are
used by recovery. Trigger-management ownership is required for the narrow broker;
the normal application operation still runs as the service user.

The isolated regressions prove an actual FK violation aborts recovery, unchanged FK
orphans are detected, unrelated triggers still fire, and the trigger states/timestamps
are correct after commit or rollback. The original private sealed package remains
unchanged. A new candidate must be resealed with its code and FK/trigger metadata
before any later production approval.

Primary references: [PostgreSQL session replication role](https://www.postgresql.org/docs/18/runtime-config-client.html#GUC-SESSION-REPLICATION-ROLE),
[named trigger enable/disable](https://www.postgresql.org/docs/18/sql-altertable.html).

## Limits

PG and Qdrant have no distributed transaction or Qdrant payload compare-and-swap.
Safety assumes all cooperating writers respect the existing application lock;
external writers bypassing it remain a race. Every observed drift stops processing.
A metadata-only preparation cannot prove production write acceptance. The PG/Qdrant
SQL and HTTP paths are tested on isolated real services; production mutation and
the privileged recovery broker's write path remain unexecuted pending approval.
