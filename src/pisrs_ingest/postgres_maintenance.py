"""Concrete OLC-85 callbacks backed by approved private immutable row images.

No CLI or schema migration. Capture is read-only; its returned index SHA must be
reviewed separately. Each data transaction addresses at most 1000 explicit PKs.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from psycopg.types.json import Jsonb

from .maintenance import MaintenanceError, MaintenanceOwner, PinnedManifest, _verify_scope
from .models import canonical_payload
from .postgres_chunks import ChunkStore

TABLES = ("act_text_versions", "act_text_blocks", "embedding_chunks")


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()


def _same(left: Any, right: Any) -> bool:
    return _json(left) == _json(right)


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _ids(values: list[int]) -> list[int]:
    if not isinstance(values, list) or any(type(i) is not int or i <= 0 for i in values):
        raise MaintenanceError("explicit positive PK list required")
    if len(set(values)) != len(values):
        raise MaintenanceError("duplicate maintenance PK")
    return sorted(values)


def _batches(values, size=1000):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _private_directory(path: Path) -> None:
    s = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
        raise MaintenanceError("row-image directory must be owned, private and not a symlink")


def _read(path: Path) -> bytes:
    _private_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if (
            not stat.S_ISREG(s.st_mode)
            or s.st_uid != os.getuid()
            or stat.S_IMODE(s.st_mode) != 0o600
            or s.st_nlink != 1
            or s.st_size > 128 * 1024 * 1024
        ):
            raise MaintenanceError("unsafe private row-image file")
        with os.fdopen(fd, "rb", closefd=False) as f:
            return f.read()
    finally:
        os.close(fd)


def _write(path: Path, body: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(body)
        f.flush()
        os.fsync(f.fileno())


def _sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _topology(c, versions: list[int]) -> dict[str, list[int]]:
    result = {"versions": versions, "blocks": [], "chunks": []}
    for table, key in (("act_text_blocks", "blocks"), ("embedding_chunks", "chunks")):
        for version_batch in _batches(versions):
            last = 0
            while True:
                rows = c.execute(
                    f"SELECT id FROM pisrs.{table} WHERE version_id=ANY(%s) "
                    "AND id>%s ORDER BY id LIMIT 1000",
                    (version_batch, last),
                ).fetchall()
                if not rows:
                    break
                result[key].extend(r["id"] for r in rows)
                last = rows[-1]["id"]
        result[key].sort()
    return result


def _images(table: str, before: dict, links: dict[int, int], points: set[str]) -> dict:
    staged = copy.deepcopy(before)
    version_id = before["id"] if table == "act_text_versions" else before["version_id"]
    target = links.get(version_id)
    if table == "act_text_versions" and before["act_id"] is not None:
        raise MaintenanceError("private version before-image must contain original NULL")
    if target is not None:
        if before["act_id"] not in (None, target):
            raise MaintenanceError("conflicting approved child act link")
        staged["act_id"] = target
    if table == "embedding_chunks":
        if before["collection_name"] != "pisrs_current" or not isinstance(before["payload"], dict):
            raise MaintenanceError("unsafe cache row")
        staged["payload"] = before["payload"] | canonical_payload(SimpleNamespace(**staged))
        if (
            before["act_id"] is None
            and target is not None
            and before["qdrant_status"] == "uploaded"
        ):
            staged["qdrant_status"] = "payload_pending"
    acknowledged = copy.deepcopy(staged)
    if table == "embedding_chunks" and before["qdrant_point_id"] in points:
        if before["qdrant_status"] != "uploaded":
            raise MaintenanceError(
                "capture must precede metadata repair; indexed rows must be uploaded"
            )
        acknowledged["qdrant_status"] = "uploaded"
        acknowledged["qdrant_error"] = None
        # Metadata-only acknowledgement does not claim a new vector upsert time.
    return {"id": before["id"], "before": before, "staged": staged, "acknowledged": acknowledged}


def capture_pg_images(
    *,
    database: Any,
    owner: MaintenanceOwner,
    manifest: PinnedManifest,
    qdrant: Any,
    cache_ids: list[int],
    directory: Path,
    max_rows: int,
) -> str:
    """Read-only capture; durable atomic publication, never implicit approval."""
    owner.check()
    _private_directory(directory.parent)
    if directory.exists() or directory.is_symlink() or type(max_rows) is not int or max_rows <= 0:
        raise MaintenanceError("new private image directory and explicit row budget required")
    cache_ids = _ids(cache_ids)
    _verify_scope(
        owner,
        manifest,
        SimpleNamespace(chunks=ChunkStore(database, "pisrs_current")),
        qdrant,
        "forward",
        target_pg=False,
        target_q=False,
    )
    vector_fingerprint = qdrant.vector_fingerprint()
    links = dict(manifest.version_links)
    points = {p.point_id for p in manifest.points}
    staging = Path(tempfile.mkdtemp(prefix=".pg-images-", dir=directory.parent))
    try:
        with database.connect(read_only=True) as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            c.execute("SET LOCAL statement_timeout='30s'")
            topology = _topology(c, sorted(links))
            scope = {
                TABLES[0]: topology["versions"],
                TABLES[1]: topology["blocks"],
                TABLES[2]: sorted(set(topology["chunks"]) | set(cache_ids)),
            }
            if sum(map(len, scope.values())) > max_rows:
                raise MaintenanceError("private image capture exceeds reviewed row budget")
            index = {
                "version": 1,
                "manifest_sha256": manifest.approved_sha256,
                "database": c.execute("SELECT current_database() AS name").fetchone()["name"],
                "collection": "pisrs_current",
                "vector_fingerprint": vector_fingerprint,
                "topology": topology,
                "scope": scope,
                "batches": [],
            }
            parent_text_ids = {}
            for table, ids in scope.items():
                for number, batch in enumerate(_batches(ids)):
                    owner.check()
                    rows = c.execute(
                        f"SELECT to_jsonb(r)-'updated_at' AS image FROM pisrs.{table} r "
                        "WHERE id=ANY(%s) ORDER BY id",
                        (batch,),
                    ).fetchall()
                    if [r["image"]["id"] for r in rows] != batch:
                        raise MaintenanceError("missing explicit maintenance PK")
                    records = []
                    for row in rows:
                        before = row["image"]
                        if table == TABLES[0]:
                            if before["act_id"] is not None:
                                raise MaintenanceError(
                                    "new capture requires original NULL version links"
                                )
                            parent_text_ids[before["id"]] = before["text_id"]
                        elif (
                            before["version_id"] in links
                            and before["text_id"] != parent_text_ids[before["version_id"]]
                        ):
                            raise MaintenanceError("child text identity mismatch")
                        records.append(_images(table, before, links, points))
                    body = _json(records)
                    filename = f"{table}-{number:06d}.json"
                    _write(staging / filename, body)
                    index["batches"].append(
                        {"table": table, "file": filename, "sha256": _sha(body), "ids": batch}
                    )
        owner.check()
        if qdrant.vector_fingerprint() != vector_fingerprint:
            raise MaintenanceError("vectors changed during before-image capture")
        owner.check()
        body = _json(index)
        _write(staging / "index.json", body)
        _sync_dir(staging)
        os.rename(staging, directory)
        _sync_dir(directory.parent)
        return _sha(body)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


class PgMaintenanceCallbacks:
    """Exact approved before/staged/ack images; progress is inferred from CAS state."""

    def __init__(
        self, database: Any, directory: Path, approved_sha256: str, manifest: PinnedManifest
    ):
        self.database, self.directory, self.approved_sha256 = database, directory, approved_sha256
        self.manifest_sha256 = manifest.approved_sha256
        self.links = dict(manifest.version_links)
        self.points = {p.point_id for p in manifest.points}
        self.index = self._index()
        self.vector_fingerprint = self.index["vector_fingerprint"]
        if not re.fullmatch(r"[0-9a-f]{64}", self.vector_fingerprint):
            raise MaintenanceError("private images require an approved vector baseline")
        seen = {t: [] for t in TABLES}
        for descriptor, records in self._records():
            seen[descriptor["table"]].extend(r["id"] for r in records)
        if seen != self.index["scope"]:
            raise MaintenanceError("private image PK index is incomplete or duplicated")

    def _index(self) -> dict:
        body = _read(self.directory / "index.json")
        if (
            not re.fullmatch(r"[0-9a-f]{64}", self.approved_sha256)
            or _sha(body) != self.approved_sha256
        ):
            raise MaintenanceError("private images differ from explicitly approved SHA")
        index = json.loads(body)
        if (
            index.get("version") != 1
            or index.get("manifest_sha256") != self.manifest_sha256
            or index.get("collection") != "pisrs_current"
            or set(index["scope"]) != set(TABLES)
            or index["topology"]["versions"] != sorted(self.links)
        ):
            raise MaintenanceError("private image operation binding mismatch")
        if (
            index["scope"][TABLES[0]] != index["topology"]["versions"]
            or index["scope"][TABLES[1]] != index["topology"]["blocks"]
            or not set(index["topology"]["chunks"]) <= set(index["scope"][TABLES[2]])
        ):
            raise MaintenanceError("private images omit approved parents or children")
        for ids in [*index["scope"].values(), *index["topology"].values()]:
            if _ids(ids) != ids:
                raise MaintenanceError("unordered private image PKs")
        return index

    def _records(self):
        for descriptor in self._index()["batches"]:
            table, filename = descriptor["table"], descriptor["file"]
            if table not in TABLES or not re.fullmatch(table + r"-\d{6}\.json", filename):
                raise MaintenanceError("invalid private image batch")
            ids = _ids(descriptor["ids"])
            if not ids or len(ids) > 1000 or ids != descriptor["ids"]:
                raise MaintenanceError("private image batch exceeds 1000 explicit PKs")
            body = _read(self.directory / filename)
            if _sha(body) != descriptor["sha256"]:
                raise MaintenanceError("private image batch changed")
            records = json.loads(body)
            if [r["id"] for r in records] != ids:
                raise MaintenanceError("private image batch identities changed")
            for r in records:
                if not _same(r, _images(table, r["before"], self.links, self.points)):
                    raise MaintenanceError("unapproved after-image modification")
            yield descriptor, records

    def _check(self, owner, manifest):
        owner.check()
        if manifest.approved_sha256 != self.manifest_sha256:
            raise MaintenanceError("callback manifest changed")
        with self.database.connect(read_only=True) as c:
            c.execute("SET LOCAL statement_timeout='30s'")
            if (
                c.execute("SELECT current_database() AS name").fetchone()["name"]
                != self.index["database"]
            ):
                raise MaintenanceError("private images belong to another database")
            if _topology(c, sorted(self.links)) != self.index["topology"]:
                raise MaintenanceError("approved parent/child membership changed")
            self._unique_links(c)

    def _unique_links(self, c):
        for batch in _batches(sorted(self.links)):
            matches = c.execute(
                "SELECT v.id,count(a.id) AS n,min(a.id) AS act_id "
                "FROM pisrs.act_text_versions v LEFT JOIN pisrs.acts a "
                "ON a.sop=v.sop_from_docno AND btrim(v.sop_from_docno)<>'' "
                "WHERE v.id=ANY(%s) GROUP BY v.id ORDER BY v.id",
                (batch,),
            ).fetchall()
            if len(matches) != len(batch) or any(
                r["n"] != 1 or r["act_id"] != self.links[r["id"]] for r in matches
            ):
                raise MaintenanceError("approved unique act identity changed")

    def _current(self, c, table, ids, *, lock=False):
        rows = c.execute(
            f"SELECT to_jsonb(r)-'updated_at' AS image FROM pisrs.{table} r "
            "WHERE id=ANY(%s) ORDER BY id" + (" FOR UPDATE" if lock else ""),
            (ids,),
        ).fetchall()
        if [r["image"]["id"] for r in rows] != ids:
            raise MaintenanceError("explicit image PK disappeared")
        return [r["image"] for r in rows]

    @staticmethod
    def _allowed(record, phase, direction):
        if direction == "rollback":
            return (
                [record["before"]]
                if phase != "prepare"
                else [record[k] for k in ("before", "staged", "acknowledged")]
            )
        return [
            record[k]
            for k in (
                ("before", "staged", "acknowledged")
                if phase == "prepare"
                else ("staged", "acknowledged")
            )
        ]

    def _verify(self, owner, phase, direction):
        for descriptor, records in self._records():
            owner.check()
            with self.database.connect(read_only=True) as c:
                current = self._current(c, descriptor["table"], descriptor["ids"])
            for row, record in zip(current, records, strict=True):
                allowed = self._allowed(record, phase, direction)
                if phase == "readback":
                    allowed = [
                        record["before"] if direction == "rollback" else record["acknowledged"]
                    ]
                if not any(_same(row, image) for image in allowed):
                    raise MaintenanceError("row acquired an unapproved image; CAS refused")

    def _apply(self, owner, manifest, phase, direction):
        if direction not in ("forward", "rollback"):
            raise MaintenanceError("invalid PG callback direction")
        self._check(owner, manifest)
        self._verify(owner, phase, direction)  # reject existing drift before any data UPDATE
        for descriptor, records in self._records():
            owner.check()
            table = descriptor["table"]
            with self.database.connect() as c, c.transaction():
                c.execute("SET LOCAL statement_timeout='30s'")
                c.execute("SET LOCAL lock_timeout='3s'")
                c.execute("LOCK TABLE pisrs.acts IN SHARE MODE")
                self._unique_links(c)
                current = self._current(c, table, descriptor["ids"], lock=True)
                changes = []
                for row, record in zip(current, records, strict=True):
                    if not any(
                        _same(row, image) for image in self._allowed(record, phase, direction)
                    ):
                        raise MaintenanceError("concurrent image change; CAS refused")
                    target = (
                        record["before"]
                        if direction == "rollback"
                        else record["staged" if phase == "prepare" else "acknowledged"]
                    )
                    if (
                        direction == "forward"
                        and phase == "prepare"
                        and _same(row, record["acknowledged"])
                    ):
                        continue  # completed forward replay must not recreate pending markers
                    if not _same(row, target):
                        changes.append({"id": record["id"], "before": row, "after": target})
                if changes:
                    fields = "act_id=(t.after->>'act_id')::bigint,updated_at=now()"
                    if table == "embedding_chunks":
                        fields += (
                            ",payload=t.after->'payload',qdrant_status=t.after->>'qdrant_status'"
                            ",qdrant_error=t.after->>'qdrant_error'"
                            ",qdrant_upserted_at=(t.after->>'qdrant_upserted_at')::timestamptz"
                        )
                    owner.check()
                    result = c.execute(
                        "WITH t AS (SELECT (x->>'id')::bigint AS id,"
                        "x->'before' AS before,x->'after' AS after "
                        "FROM jsonb_array_elements(%s::jsonb) x) "
                        f"UPDATE pisrs.{table} r SET {fields} FROM t WHERE r.id=t.id "
                        "AND (to_jsonb(r)-'updated_at')=t.before "
                        "RETURNING r.id,to_jsonb(r)-'updated_at' AS image",
                        (Jsonb(changes),),
                    ).fetchall()
                    expected = {r["id"]: r["after"] for r in changes}
                    if not _same({r["id"]: r["image"] for r in result}, expected):
                        raise MaintenanceError("CAS update or after-image readback failed")
                owner.check()  # a lost owner rolls back the current <=1000-PK transaction
        self._check(owner, manifest)
        self._verify(owner, "prepared" if phase == "prepare" else "readback", direction)

    def prepare_pg(self, owner, manifest, direction):
        self._apply(owner, manifest, "prepare", direction)

    def acknowledge_pg(self, owner, manifest, direction):
        self._apply(owner, manifest, "acknowledge", direction)

    def readback_pg(self, owner, manifest, direction):
        self._check(owner, manifest)
        self._verify(owner, "readback", direction)
