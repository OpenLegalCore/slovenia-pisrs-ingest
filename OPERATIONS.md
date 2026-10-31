# Operations

## Documented deployment versus installed state

deploy/systemd/pisrs-ingest.service and .timer are templates, not installation evidence.
They specify a dedicated service user, an active-release symlink, a private EnvironmentFile,
read-only ExecStartPre and a mutating nightly ExecStart. The timer specifies 03:00
Europe/Ljubljana, Persistent=true and no random delay. Verify actual units and overrides.
An inactive oneshot service between runs is normal; inspect its last result and timer state.

Configuration is defined by config.py and .env.example. Confirm target database identity,
collection, model/dimensions, checkpoint/lock paths, initial boundary and document/embedding
caps without exposing values of tokens, passwords or DSNs. Report secrets only as SET/UNSET.
Read environment files as configuration; do not blindly execute their contents as shell code.

## Routine verification

Use the existing CLI only after inspecting the actual installed command and configuration.
preflight requires writes disabled and can disable external API access; it does not call embeddings.
reconcile --dry-run reads PostgreSQL/Qdrant; assess its counters rather than exit status alone.
Do not execute nightly, reconcile --apply, checkpoint repair or embeddings as a diagnostic shortcut.
RuntimeDirectory may exist only during the systemd service: a standalone path-check failure
must be distinguished from a failed scheduled ExecStartPre. Do not create host paths to hide it.

## Dedicated host Codex handoff: P1 / OLC-77

Work in the existing local PISRS checkout. First establish its actual path, remote, branch,
commit and host identity; do not assume the active release equals that checkout.
Read these development documents from the approved development revision before execution.
Perform only read-only host diagnostics:

1. Inspect current and legacy PISRS timer/service units, overrides, actual command, user,
   scheduling, last three run summaries and success/failure timestamps.
2. Resolve the active release and identify the installed package/source hash; compare relevant
   source with the reviewed public baseline. Do not switch symlinks, fetch into production or install.
3. Read checkpoint and lock ownership/state without creating, deleting or acquiring a mutating
   application lock. Distinguish file existence from actual lock ownership.
4. In read-only PostgreSQL transactions with bounded statement timeouts, verify database/schema,
   catalog/version/block/chunk counts, missing or ambiguous act links, stored JSON versus canonical
   columns, pending/error state, historical ranges and duplicate identities.
5. Inspect Qdrant health/contract and exact canonical point/payload coverage using the installed
   read-only comparison if appropriate. Identify vector-history limits separately.
6. Recheck the checkpoint and relevant run timestamps. If nightly overlaps a comparison,
   record the inconsistency window and repeat bounded affected reads; do not stop the timer.
7. Return sanitized evidence with timestamps, release identity, commands/checks performed,
   counters and PASS/FAIL/UNKNOWN per check. Compare dated OLC-77/OLC-85 findings without treating
   them as current measurements. Keep full private output outside public Git/Linear.

No production writes, service changes, deployments, paid calls or data exports.
If permissions are insufficient, report the exact blocked read and continue independent checks.

## Approved release procedure

Prepare an immutable tested candidate and its diff, source/build hashes, compatibility,
expected data changes, measured workload/cost and rollback before requesting production approval.
Before approved execution, verify restorable PG/Qdrant/checkpoint backups and prevent concurrent
mutating runs using the existing operational lock; preserve the old release and configuration.
Activate only within the approved change, verify readback and a supervised scheduled path,
and keep the old release available until postflight acceptance. Rollback must account for
committed database/vector changes as well as the executable; never blindly rewind a checkpoint.
