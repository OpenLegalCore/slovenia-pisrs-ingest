# PISRS backup and isolated restore on Medo

This is a reviewed procedure, not authorization to execute production capture or
act-link apply. Keep backup bytes, the source context, fingerprints and reports
private. No production capture or historical full restore is claimed by publishing
this runbook. A synthetic end-to-end drill exercises the actual dump, snapshot,
restore and fingerprint paths separately from production evidence.

## 1. Scope and acceptance boundary

Capture all tables, functions, sequences, indexes and constraints in appdb's pisrs
schema; every point, actual vector, payload and payload index in pisrs_current;
and the exact checkpoint bytes. Record the active release SHA and pinned PG/Qdrant
image IDs in private metadata. Capture the collection's aliases separately if used;
the isolated drill intentionally restores only the canonical collection, never a
production alias. Inventory extension or cross-schema dependencies before capture.
Stop if such dependencies have not been included in the reviewed restore plan.

A schema-scoped dump does not contain cluster roles, passwords, other databases or
tablespaces. The isolated restore uses its own owner and no source ACLs. Preserve
minimal role/privilege declarations without passwords separately for a real
owner-approved disaster recovery, and keep environment credentials in the existing
secret-management path. No live EnvironmentFile is mounted in the drill.

## 2. Consistency and space

Choose an agreed maintenance window in which the entire capture and fingerprints
finish before the next nightly. Leave timer/unit/checkpoint configuration untouched.
Require the existing service inactive and hold its exact nonblocking application
flock for the entire capture, without truncating the lock file. All PISRS writers
must cooperate with it. Abort on service activation, replaced lock inode or any
checkpoint change. This is a coordinated logical backup across stores, not a
cross-store atomic snapshot; independent writers bypassing the lock invalidate it.

pg_dump supplies a consistent database snapshot. The application fence keeps logical
PISRS content stable through the Qdrant snapshot and source fingerprints; Qdrant's
own snapshot mechanism handles its storage/optimizer state. Never copy a running
PGDATA directory or a live Qdrant collection directory with cp/tar.

Use a private new directory, mode 0700, with files 0600. Let P be measured PISRS PG
relation/index bytes and Q be measured pisrs_current storage bytes. A conservative
shared-filesystem gate is at least 2*P + 4*Q + 32 GiB free for source snapshot,
backup files, expanded isolated copies, indexes and restore WAL. It is a planning
reserve, not a prediction of WAL/compression. Recheck actual free space after each
phase; stop on inadequate headroom. Count each filesystem once. Require memory/CPU
headroom for the drill's 2 GiB PG and 8 GiB Qdrant caps; schedule bulk I/O away from
nightly. An additional verified encrypted copy on another storage device/host is
needed for recovery from loss of Medo's data filesystem. No off-host upload is
performed by this procedure automatically.

## 3. Production capture, after a separate explicit approval

Prepare a PRIVATE JSON context with: pg_container, pg_user, qdrant_container,
checkpoint, pg_bytes, qdrant_bytes, and active_release_sha. Obtain exact identities
from the effective PISRS configuration/installed containers. The selected Qdrant
snapshot directory must be writable. A read-only mount at the default snapshots
path does not describe an explicit snapshots_path override. Verify the effective
path and its actual free space first; do not change Qdrant configuration to make
this runbook pass.

Save the following reviewed Python block as a private capture script. Pass the
private context, new absolute backup directory and reviewed checkout as positional
arguments; pkexec strips ordinary shell environment variables. Invoke it through
`pkexec /usr/bin/timeout --kill-after=30s 7200s /path/to/reviewed/python -B
/private/capture_pisrs.py /private/context.json /private/NEW_BACKUP /reviewed/checkout`.
Use the same legitimate local authentication path as the preparation. It contains a production snapshot-creation call
and must not be run as a diagnostic. No point/row/checkpoint is changed by capture.

```python
import argparse, fcntl, hashlib, importlib.util, json, os, pwd, subprocess, sys, time
from pathlib import Path
from urllib.parse import quote

parser = argparse.ArgumentParser()
parser.add_argument("context", type=Path)
parser.add_argument("backup_dir", type=Path)
parser.add_argument("checkout", type=Path)
args = parser.parse_args()
ctx = json.loads(args.context.read_text())
root = args.checkout.resolve()
spec = importlib.util.spec_from_file_location("drill", root / "ops/pisrs_restore_drill.py")
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)
out = args.backup_dir
assert os.geteuid() == 0 and out.is_absolute() and not out.exists()
os.umask(0o077)
pg, q = ctx["pg_container"], ctx["qdrant_container"]
for identity, port in [(pg, "5432"), (q, "6333")]:
    bindings = D.inspect(identity)["NetworkSettings"]["Ports"][port + "/tcp"]
    assert any(x["HostIp"] == "127.0.0.1" and x["HostPort"] == port for x in bindings)
checkpoint = Path(ctx["checkpoint"])
assert checkpoint == Path("/var/lib/pisrs-ingest/checkpoint.json")
lock = Path("/run/pisrs-ingest/ingest.lock")
assert not lock.is_symlink()
reserve = 2 * ctx["pg_bytes"] + 4 * ctx["qdrant_bytes"] + 32 * 1024**3
out.mkdir(mode=0o700)


def save(name, data):
    with (out / name).open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def check():
    assert time.monotonic() - started < 7200
    assert (lock.stat().st_dev, lock.stat().st_ino) == inode
    assert (
        subprocess.check_output(
            ["systemctl", "show", "pisrs-ingest.service", "-p", "ActiveState", "--value"]
        ).strip()
        == b"inactive"
    )
    assert os.statvfs(out).f_bavail * os.statvfs(out).f_frsize > reserve


with lock.open("rb") as held:
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    st = os.fstat(held.fileno())
    assert st.st_uid == pwd.getpwnam("pisrs-ingest").pw_uid
    inode = (st.st_dev, st.st_ino)
    started = time.monotonic()
    check()
    old_checkpoint = checkpoint.read_bytes()
    save("checkpoint.json", old_checkpoint)
    with (out / "pg.dump").open("xb") as f:
        subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                "PGOPTIONS=-c default_transaction_read_only=on",
                pg,
                "pg_dump",
                "-U",
                ctx["pg_user"],
                "-d",
                "appdb",
                "-Fc",
                "--schema=pisrs",
                "--no-owner",
                "--no-privileges",
                "--no-tablespaces",
                "--lock-wait-timeout=3s",
            ],
            stdout=f,
            check=True,
            timeout=3600,
        )
        f.flush()
        os.fsync(f.fileno())
    check()
    snap = D.q_request(q, "/collections/pisrs_current/snapshots", {})
    name = snap["name"]
    assert Path(name).name == name
    pid = D.inspect(q)["State"]["Pid"]
    with (out / "pisrs_current.snapshot").open("xb") as f:
        subprocess.run(
            [
                "/usr/bin/nsenter",
                "--target",
                str(pid),
                "--net",
                "/usr/bin/curl",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                "3600",
                "http://127.0.0.1:6333/collections/pisrs_current/snapshots/" + quote(name, safe=""),
            ],
            stdout=f,
            check=True,
            timeout=3700,
        )
        f.flush()
        os.fsync(f.fileno())
    check()
    baseline = {
        "pg": D.pg_fingerprint(pg, "appdb", ctx["pg_user"]),
        "qdrant": D.q_fingerprint(q),
        "checkpoint_sha256": hashlib.sha256(old_checkpoint).hexdigest(),
    }
    assert checkpoint.read_bytes() == old_checkpoint
    check()
    save("baseline.json", (json.dumps(baseline, sort_keys=True) + "\n").encode())
    save(
        "images.json",
        (
            json.dumps(
                {
                    "postgres": D.inspect(pg)["Image"],
                    "qdrant": D.inspect(q)["Image"],
                    "required_free_bytes": reserve,
                }
            )
            + "\n"
        ).encode(),
    )
    save(
        "source-context.json",
        (json.dumps({**ctx, "snapshot_name": name}, sort_keys=True) + "\n").encode(),
    )
    lines = []
    for p in sorted(out.iterdir()):
        h = hashlib.sha256()
        with p.open("rb") as f:
            while data := f.read(8 * 1024 * 1024):
                h.update(data)
        lines.append(h.hexdigest() + "  " + p.name + "\n")
    save("SHA256SUMS", "".join(lines).encode())
    fd = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)
    check()
print("CAPTURED, NOT YET RESTORE-VERIFIED")
```

Preserve a failed partial set with its failure evidence; do not call it a backup
PASS, delete source snapshots, or restart a partial capture into the same directory.
Do not combine a historic Qdrant snapshot, current PG dump and an older checkpoint
and label them a consistent set. No checkpoint rewind is part of this runbook.

## 4. Restore only into an isolated destination

First verify SHA256SUMS and its own recorded SHA-256. Keep the source bundle read
only. Use the exact local image IDs from images.json, no pulls or package installs.
The executable creates new labelled containers with --network none, no published
ports, no source data/config mounts and no credentials. Writable mounts are only
new, dedicated PG/Qdrant data directories below a fresh work directory. Snapshot
input is mounted read only. Qdrant cluster mode and telemetry are disabled.

```bash
pkexec /path/to/reviewed/python -B ops/pisrs_restore_drill.py \
  --bundle /private/path/to/complete-backup \
  --bundle-sha256 APPROVED_SHA256_OF_SHA256SUMS \
  --work /var/lib/pisrs-restore-drills/NEW_UNIQUE_RUN
```

Create the private parent /var/lib/pisrs-restore-drills first if absent. The tool
refuses an existing work directory. PostgreSQL restores only into its newly created
pisrs_test_restore database with pg_restore --single-transaction --exit-on-error,
without --clean, --create or --disable-triggers. Qdrant restores at startup from the
read-only snapshot into a fresh absent collection. No restore HTTP request targets
production: verification runs via curl inside the target container's network
namespace using nsenter. The default source namespace is never reused as a target.
A restored snapshot can start in grey status with paused optimizations. Only on
its own network-isolated labelled Qdrant target, the tool may send one empty
optimizers_config PATCH to resume them, then waits for green and the exact point
count. No vector/point is supplied by this PATCH; complete actual-vector hashes
are compared afterward. This operation is never sent to the source container.
The checkpoint is copied only into the isolated work directory and compared byte
for byte. No timer, service or ingestion process starts in the drill.

## 5. Required success evidence and limitations

PASS requires all of the following, not just exit zero:

- Backup member and manifest SHA-256 verification before restore.
- Exact table membership, row counts and deterministic full-row stream SHA-256 for
  every PISRS table, matching the fenced source baseline.
- Sequence last_value/is_called and sequence parameters preserved; FK definitions
  and validation flags match. pg_restore validates constraints while loading the
  complete dump; no constraint-trigger suppression is used.
- Exact point count and ordered SHA-256 over every Qdrant point ID, full payload
  and actual vector; vector configuration and payload-index schema match.
- Checkpoint bytes/hash match; the copied checkpoint is not installed in production.
- Fresh target identities, network=none, no published ports or source data mounts;
  no production data changes, provider calls or embeddings.
- A private report.json with elapsed time, disk/free-space observations and memory/CPU
  caps. These are not peak-memory or WAL-attribution measurements. The tool removes only its own labelled containers; restored files
  remain for inspection. Remove them later only by their exact owned work path.

Full-row fingerprints cover all columns. The utility also compares sequence/constraint metadata and schema hashes for
columns, defaults, functions, views, indexes and user-trigger definitions/states.
Archive TOC/schema review remains required for extension and role dependencies. A synthetic
successful drill proves the command path, not restorability of an old production
archive or external PISRS source completeness. Historical snapshots require their
own compatible-version restore and comparison evidence. Same-filesystem copies
and act-link before-images alone are not a verified disaster-recovery backup set.

Primary references: [pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html),
[pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html),
[Qdrant snapshots](https://qdrant.tech/documentation/snapshots/),
[grey collection status](https://qdrant.tech/documentation/manage-data/collections/#grey-collection-status).
