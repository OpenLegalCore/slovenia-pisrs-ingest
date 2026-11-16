"""PostgreSQL 18 G3 archive: no source checkpoint without independent full parity."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
import uuid
from typing import Any

from .contract import (
    OPENAPI_SHA256, REVISION, RULES_REVISION, PARSER_REVISION,
    BY_KEY, ContractError, canonical, int64_id, json_pointer,
    parse_response, payload_hash, qualified_identity, request_path, safe_work_key,
)
from .http import Reply, SourceStopped

G2_COMMIT = "2083017e5ccaf578a1226a24b4de064338c5653d"
MIGRATION = Path(__file__).resolve().parent / "migrations" / "001_g3_archive.sql"
LOCK_ID = 3141592671


def protected_file(path: str) -> str:
    """Secrets cannot be read from insecure locations or displayed in logs."""
    p = Path(path)
    if not p.is_absolute() or p.is_symlink():
        raise ValueError("protected_absolute_data_path_required")
    resolved = p.resolve(strict=True)
    if Path("/data") not in resolved.parents:
        raise ValueError("protected_absolute_data_path_required")
    meta = resolved.stat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077:
        raise ValueError("protected_file_must_be_0600")
    if meta.st_uid not in (0, os.geteuid()):
        raise ValueError("protected_file_owner_mismatch")
    return resolved.read_text(encoding="utf-8").strip()


def connect(dsn_path: str):
    import psycopg

    conninfo = protected_file(dsn_path)
    if not conninfo or "\n" in conninfo:
        raise ValueError("invalid_protected_pg_connection")
    # Do not expose conninfo in exception text or logs.
    from psycopg.conninfo import conninfo_to_dict
    try:
        args = conninfo_to_dict(conninfo)
    except Exception:
        raise ValueError("invalid_protected_pg_connection") from None
    if args.get("sslmode") != "verify-full" or not args.get("sslrootcert"):
        raise RuntimeError("postgresql_tls_verification_required")
    try:
        conn = psycopg.connect(conninfo=conninfo, connect_timeout=8, autocommit=True)
    except Exception:
        raise RuntimeError("postgresql_connect_failed") from None
    with conn.cursor() as c:
        c.execute("SELECT current_database(), current_setting('server_version_num')::integer")
        dbname, version = c.fetchone()
        if dbname != "pisrs_staging" or not 180000 <= version < 190000:
            conn.close()
            raise RuntimeError("wrong_database_or_postgresql_major")
    return conn


def migrate(conn) -> str:
    """Only exact approved G3 migration, transactional/locked, never destructive."""
    sql = MIGRATION.read_bytes()
    digest = hashlib.sha256(sql).digest()
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
        exists = conn.execute("SELECT to_regclass('pisrs.migration_log')").fetchone()[0]
        if exists:
            rows = conn.execute(
                "SELECT migration_hash FROM pisrs.migration_log WHERE version = 1"
            ).fetchall()
            if rows:
                if bytes(rows[0][0]) != digest:
                    raise RuntimeError("applied_migration_hash_drift")
                return digest.hex()
            # A present schema with no signed migration row must not be clobbered.
            raise RuntimeError("unverified_existing_schema")
        # psycopg 3 supports an unparameterized multi-statement simple query.
        with conn.cursor() as c:
            c.execute(sql.decode("utf-8"), prepare=False)
        conn.execute(
            "INSERT INTO pisrs.migration_log(version,migration_hash) VALUES (1,%s)",
            (digest,),
        )
    return digest.hex()


def verify_tables(conn) -> dict[str, Any]:
    expected = {
        "migration_log", "contract_revision", "source_run", "source_work",
        "source_blob", "source_attempt", "source_record", "record_revision",
        "source_occurrence", "reference_resolution", "identity_event",
        "document_locator", "source_artifact", "parsed_document", "text_block",
    }
    rows = conn.execute(
        "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='pisrs'"
    ).fetchall()
    found = {r[0] for r in rows}
    if found != expected:
        raise RuntimeError("schema_table_inventory_mismatch")
    version = conn.execute(
        "SELECT version, encode(migration_hash, 'hex') FROM pisrs.migration_log"
    ).fetchall()
    if len(version) != 1 or version[0][0] != 1:
        raise RuntimeError("schema_migration_log_mismatch")
    names = {r[0] for r in conn.execute(
        "SELECT conname FROM pg_catalog.pg_constraint WHERE connamespace='pisrs'::regnamespace"
    ).fetchall()}
    must_have = {"source_work_terminal_attempt_fk","source_work_artifact_locator_fk",
                 "source_blob_digest_matches"}
    if not must_have.issubset(names):
        raise RuntimeError("schema_constraint_inventory_unexpected")
    return {"tables": len(found), "constraints": len(names), "migration": version[0][1]}


def source_lock(conn) -> None:
    if not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
        raise RuntimeError("another_g3_source_or_migration_running")


def register_contract(conn) -> None:
    approved = "G2:" + G2_COMMIT
    with conn.transaction():
        conn.execute(
            """INSERT INTO pisrs.contract_revision
               (revision,openapi_hash,schema_version,rules_revision,parser_revision,
                approved_at,approval_ref)
               VALUES (%s,%s,1,%s,%s,clock_timestamp(),%s)
               ON CONFLICT (revision) DO NOTHING""",
            (REVISION, bytes.fromhex(OPENAPI_SHA256), RULES_REVISION, PARSER_REVISION, approved),
        )
        actual = conn.execute(
            """SELECT openapi_hash,schema_version,rules_revision,parser_revision,approval_ref
               FROM pisrs.contract_revision WHERE revision=%s""",
            (REVISION,),
        ).fetchone()
        expected = (bytes.fromhex(OPENAPI_SHA256), 1, RULES_REVISION, PARSER_REVISION, approved)
        if not actual or (bytes(actual[0]), *actual[1:]) != expected:
            raise RuntimeError("pinned_contract_drift")


def verify_registered_contract(conn) -> None:
    approved = "G2:" + G2_COMMIT
    actual = conn.execute(
        """SELECT openapi_hash,schema_version,rules_revision,parser_revision,approval_ref
           FROM pisrs.contract_revision WHERE revision=%s""",
        (REVISION,),
    ).fetchone()
    expected = (bytes.fromhex(OPENAPI_SHA256), 1, RULES_REVISION, PARSER_REVISION, approved)
    if not actual or (bytes(actual[0]), *actual[1:]) != expected:
        raise RuntimeError("pinned_contract_drift")


def get_or_create_open_run(conn) -> str:
    row = conn.execute(
        """SELECT run_id FROM pisrs.source_run
           WHERE revision=%s AND kind='INITIAL' AND status IN ('OPEN','INCOMPLETE')
           ORDER BY started_at LIMIT 1""",
        (REVISION,),
    ).fetchone()
    if row:
        return str(row[0])
    run = uuid.uuid4()
    with conn.transaction():
        conn.execute(
            """INSERT INTO pisrs.source_run
               (run_id,revision,kind,status,evidence)
               VALUES (%s,%s,'INITIAL','OPEN',%s::jsonb)""",
            (run, REVISION, canonical({"g2_commit": G2_COMMIT, "scope": "G3_open_unpublished"})),
        )
    return str(run)


def queue_work(conn, run: str, key: int, *, sweep: int = 0,
               page: int | None = None, identifier: str | None = None,
               locator_id: int | None = None) -> str:
    op = BY_KEY[key]
    work_key = safe_work_key(op, sweep, page=page, identifier=identifier)
    path = request_path(op, identifier=identifier)
    params = {"page": page, "pageSize": 50} if page is not None else {}
    with conn.transaction():
        conn.execute(
            """INSERT INTO pisrs.source_work
               (run_id,revision,source_key,sweep,work_key,request_target,
                query_args,status,locator_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'QUEUED',%s)
               ON CONFLICT (run_id,sweep,work_key) DO NOTHING""",
            (uuid.UUID(run), REVISION, key, sweep, work_key, path, canonical(params), locator_id),
        )
        row = conn.execute(
            """SELECT source_key, request_target,query_args,status
               FROM pisrs.source_work
               WHERE run_id=%s AND sweep=%s AND work_key=%s""",
            (uuid.UUID(run), sweep, work_key),
        ).fetchone()
        if not row or row[0] != key or row[1] != path or canonical(row[2]) != canonical(params):
            raise RuntimeError("work_key_collision_or_contract_drift")
    return work_key


def _date(row: dict[str, Any], name: str) -> date | None:
    value = row.get(name)
    if value is None:
        return None
    if type(value) is not str:
        raise ContractError("invalid_date_type")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError("invalid_date") from exc


def _text(row: dict[str, Any], name: str) -> str | None:
    value = row.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError("invalid_string_projection")
    return value


def _bool(row: dict[str, Any], name: str) -> bool | None:
    value = row.get(name)
    if value is None:
        return None
    if type(value) is not bool:
        raise ContractError("invalid_boolean_projection")
    return value


def _optional_int(row: dict[str, Any], name: str) -> str | None:
    value = row.get(name)
    return int64_id(value) if value is not None else None


def _store_record(conn, run: str, op, row: dict[str, Any], parent: str = "") -> tuple[int, int]:
    namespace, parent_key, source_id = qualified_identity(op, row, parent)
    cur = conn.execute(
        """INSERT INTO pisrs.source_record(namespace,parent_key,source_id,first_run)
           VALUES (%s,%s,%s,%s) ON CONFLICT(namespace,parent_key,source_id) DO NOTHING
           RETURNING record_id""",
        (namespace, parent_key, source_id, uuid.UUID(run)),
    )
    result = cur.fetchone()
    record_id = result[0] if result else conn.execute(
        "SELECT record_id FROM pisrs.source_record WHERE namespace=%s AND parent_key=%s AND source_id=%s",
        (namespace, parent_key, source_id),
    ).fetchone()[0]
    fields = (
        _text(row, "naziv"), _text(row, "kratica"), _text(row, "citat"),
        _text(row, "kategorizacijaAkta"), _text(row, "notifikacijskeIzjaveURL"),
        _text(row, "mopedId"), _text(row, "mopedPlusId"), _text(row, "eva"),
        _text(row, "epa"), _text(row, "eda"), _text(row, "sop"),
        _text(row, "idProstorskiAkt"),
        _bool(row, "osnovni"), _bool(row, "prostorskiAkt"),
        _date(row, "datumSprejetja"), _date(row, "datumObjave"),
        _date(row, "datumZacetkaVeljavnosti"), _date(row, "datumZacetkaUporabe"),
        _date(row, "datumPrenehanjaVeljavnosti"), _date(row, "datumKoncaUporabe"),
        _date(row, "datumDolocitveOznake"), _date(row, "datumRokaZaPrenos"),
        _date(row, "datumDokumenta"), _text(row, "stevilka"),
        _optional_int(row, "idNadrejeni"),
    )
    vh = payload_hash(row)
    query = """INSERT INTO pisrs.record_revision (
        record_id,revision,value_hash,raw_jsonb,title,short_title,citation,category_label,
        notification_url,moped_id,moped_plus_id,eva,epa,eda,sop,spatial_act_id,
        is_basic,is_spatial,adopted_on,published_on,effective_from,applicable_from,
        effective_until,applicable_until,designation_on,transposition_due_on,
        document_date,document_number,parent_code_id
    ) VALUES (%s,%s,%s,%s::jsonb,
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(record_id,revision,value_hash) DO NOTHING
        RETURNING record_revision_id"""
    rec = conn.execute(query, (record_id, REVISION, vh, canonical(row), *fields)).fetchone()
    revision_id = rec[0] if rec else conn.execute(
        """SELECT record_revision_id FROM pisrs.record_revision
           WHERE record_id=%s AND revision=%s AND value_hash=%s""",
        (record_id, REVISION, vh),
    ).fetchone()[0]
    return record_id, revision_id


def _link_rows(row: dict[str, Any]):
    """Yield only source-present links; never materialize a reverse from empty zveza[]!"""
    groups = {
        "zveza": None,  # EU references contain MOPED; state references contain CELEX
        "podlaga": "MOPED", "podrejeniPredpisi": "MOPED",
        "posegaVPredpise": "MOPED", "posegiVPredpis": "MOPED",
        "vplivaNaPredpise": "MOPED", "vpliviNaPredpis": "MOPED",
        "vrstaAkta": "CODE", "podrocje": "CODE", "organKiJeSprejelOzIzdalAkt": "CODE",
        "organOdgovorenZaPripravo": "CODE", "kazaloPravnihAktov": "CODE",
        "organOdgovorenZaSprejetje": "CODE", "vrstaAktaEu": "CODE",
        "podrocjeEu": "CODE",
    }
    for field, default_kind in groups.items():
        value = row.get(field)
        if value is None:
            continue
        vals = value if isinstance(value, list) else [value]
        for ordinal, item in enumerate(vals):
            if not isinstance(item, dict):
                raise ContractError("nonobject_reference")
            if field == "zveza":
                kind, token = ("CELEX", item["celex"]) if "celex" in item else (
                    ("MOPED", item["mopedID"]) if "mopedID" in item else ("MOPED", None))
            elif default_kind == "MOPED":
                kind, token = ("MOPED", item.get("mopedID"))
            else:
                kind = "CODE"
                token = int64_id(item["id"]) if "id" in item else None
            if token is not None and not isinstance(token, str):
                raise ContractError("invalid_link_token")
            suffix = f"/{ordinal}" if isinstance(value, list) else ""
            yield field, ordinal, f"/{field}{suffix}", kind, token, item.get("naziv")


def _record_references(conn, run: str, revision_id: int, row: dict[str, Any]) -> None:
    for field, ordinal, pointer, kind, token, label in _link_rows(row):
        conn.execute(
            """INSERT INTO pisrs.reference_resolution
               (record_revision_id,run_id,rules_revision,json_pointer,
                source_field,ordinal,kind,token,label,status,candidate_ids,evidence)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'UNRESOLVED','{}'::bigint[],%s::jsonb)
               ON CONFLICT(record_revision_id,run_id,rules_revision,json_pointer) DO NOTHING""",
            (revision_id, uuid.UUID(run), RULES_REVISION, pointer,
             field, ordinal, kind, token, label if isinstance(label, str) else None,
             canonical({"source_direction": field, "auto_reverse": False})),
        )


def begin_attempt(conn, run: str, key: int, work_key: str, *, sweep: int = 0) -> int:
    with conn.transaction():
        work = conn.execute(
            """SELECT status FROM pisrs.source_work
               WHERE run_id=%s AND sweep=%s AND work_key=%s FOR UPDATE""",
            (uuid.UUID(run), sweep, work_key),
        ).fetchone()
        if not work or work[0] not in ("QUEUED", "RETRY"):
            raise RuntimeError("work_not_claimable")
        retry = conn.execute(
            """SELECT count(*) FROM pisrs.source_attempt
               WHERE run_id=%s AND sweep=%s AND work_key=%s""",
            (uuid.UUID(run), sweep, work_key),
        ).fetchone()[0]
        if retry >= 3:
            raise RuntimeError("attempt_cap")
        conn.execute(
            """UPDATE pisrs.source_work SET status='LEASED',
               lease_until=clock_timestamp()+interval '2 minutes'
               WHERE run_id=%s AND sweep=%s AND work_key=%s""",
            (uuid.UUID(run), sweep, work_key),
        )
        row = conn.execute(
            """INSERT INTO pisrs.source_attempt
               (run_id,source_key,sweep,work_key,retry_no,started_at,result)
               VALUES (%s,%s,%s,%s,%s,clock_timestamp(),'OPEN')
               RETURNING attempt_id""",
            (uuid.UUID(run), key, sweep, work_key, retry),
        ).fetchone()
    return row[0]


def record_stopped(conn, run: str, work_key: str, attempt_id: int, reason: str,
                   *, sweep: int = 0, status: int | None = None) -> None:
    with conn.transaction():
        conn.execute(
            """UPDATE pisrs.source_attempt
               SET ended_at=clock_timestamp(),
                   result=CASE WHEN %s THEN 'TRANSPORT_ERROR' ELSE 'HTTP_INCOMPLETE' END,
                   reason_code=%s,http_status=%s
               WHERE attempt_id=%s AND run_id=%s AND result='OPEN'""",
            (status is None, reason[:80], status, attempt_id, uuid.UUID(run)),
        )
        conn.execute(
            """UPDATE pisrs.source_work SET status='RETRY',lease_until=NULL
               WHERE run_id=%s AND sweep=%s AND work_key=%s""",
            (uuid.UUID(run), sweep, work_key),
        )


def archive_reply(conn, run: str, key: int, work_key: str, attempt_id: int, reply: Reply,
                  *, sweep: int = 0) -> None:
    if hashlib.sha256(reply.body).digest() != reply.sha256:
        raise RuntimeError("source_body_hash_mismatch")
    with conn.transaction():
        conn.execute(
            """INSERT INTO pisrs.source_blob(sha256,raw_bytes,byte_length)
               VALUES (%s,%s,%s) ON CONFLICT(sha256) DO NOTHING""",
            (reply.sha256, reply.body, len(reply.body)),
        )
        prev = conn.execute(
            """SELECT byte_length,raw_bytes FROM pisrs.source_blob WHERE sha256=%s""",
            (reply.sha256,),
        ).fetchone()
        if not prev or prev[0] != len(reply.body) or bytes(prev[1]) != reply.body:
            raise RuntimeError("hash_collision_or_archival_corruption")
        conn.execute(
            """UPDATE pisrs.source_attempt SET ended_at=clock_timestamp(),
               result='HTTP_COMPLETE',http_status=%s,sha256=%s,content_type=%s,
               content_encoding=%s,media_charset=%s,etag=%s,last_modified=%s
               WHERE attempt_id=%s AND run_id=%s AND result='OPEN'""",
            (reply.status, reply.sha256, reply.content_type,reply.content_encoding,
             reply.charset,reply.etag,reply.last_modified,attempt_id,uuid.UUID(run)),
        )


def project_reply(conn, run: str, key: int, work_key: str, attempt_id: int, reply: Reply,
                  *, sweep: int = 0, page: int | None = None,
                  identifier: str | None = None) -> dict[str, Any]:
    """Project already durable original; never promote incomplete run."""
    op = BY_KEY[key]
    if op.kind == "html":
        raise RuntimeError("state_text_projection_requires_verified_locator")
    rows, info = parse_response(op, reply.body, expected_page=page)
    seen = set()
    with conn.transaction():
        for i, row in enumerate(rows):
            namespace, parent, source_id = qualified_identity(op, row, identifier or "")
            triple = (namespace,parent,source_id)
            if triple in seen:
                # Duplicate source entries are retained but do not make a second selected key.
                selected = False
            else:
                seen.add(triple)
                prior = conn.execute(
                    """SELECT 1 FROM pisrs.source_occurrence
                       WHERE run_id=%s AND source_key=%s AND record_id=(
                         SELECT record_id FROM pisrs.source_record
                         WHERE namespace=%s AND parent_key=%s AND source_id=%s)
                       AND selected""",
                    (uuid.UUID(run),key,namespace,parent,source_id),
                ).fetchone()
                selected = prior is None
            record_id,revision_id = _store_record(conn,run,op,row,identifier or "")
            conn.execute(
                """INSERT INTO pisrs.source_occurrence
                   (attempt_id,run_id,source_key,json_pointer,
                    record_id,record_revision_id,ordinal,validation,selected)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'VALID',%s)""",
                (attempt_id,uuid.UUID(run),key,json_pointer(info["pointer"],i),
                 record_id,revision_id,i,selected),
            )
            _record_references(conn,run,revision_id,row)
            if namespace in ("RS_ACT","RS_NPB") and type(row.get("id")) is int:
                kind = "RS_BASE" if namespace == "RS_ACT" else "RS_NPB"
                conn.execute(
                    """INSERT INTO pisrs.document_locator(record_id,kind,request_id,scope_status)
                       VALUES(%s,%s,%s,'CANDIDATE_NEEDS_CONTROL')
                       ON CONFLICT(record_id,kind) DO NOTHING""",
                    (record_id,kind,source_id),
                )
        conn.execute(
            """UPDATE pisrs.source_attempt SET
               data_pointer=%s,page=%s,requested_page_size=%s,
               real_page_size=%s,reported_total_count=%s
               WHERE attempt_id=%s""",
            (info["pointer"], info.get("page"),info.get("requested_page_size"),
             info.get("real_page_size"),info.get("total_count"),attempt_id),
        )
        conn.execute(
            """UPDATE pisrs.source_work
               SET status='COMPLETE',terminal_attempt_id=%s,lease_until=NULL
               WHERE run_id=%s AND sweep=%s AND work_key=%s AND status='LEASED'""",
            (attempt_id,uuid.UUID(run),sweep,work_key),
        )
    return {"operation": key, "rows": len(rows), "distinct_on_page": len(seen),
            "sha256": reply.sha256.hex(), "bytes": len(reply.body),
            "source_run_published": False}


def verify_archive(conn, attempt_id: int) -> dict[str, Any]:
    """Independent SQL readback of exact body and retained occurrences."""
    row = conn.execute(
        """SELECT a.run_id,a.source_key,a.sha256,a.http_status,b.raw_bytes,b.byte_length
           FROM pisrs.source_attempt a JOIN pisrs.source_blob b ON b.sha256=a.sha256
           WHERE a.attempt_id=%s AND a.result='HTTP_COMPLETE'""",
        (attempt_id,),
    ).fetchone()
    if not row:
        raise RuntimeError("complete_attempt_missing")
    run,key,digest, status,body, byte_length = row
    if status != 200 or len(body) != byte_length or hashlib.sha256(bytes(body)).digest()!=bytes(digest):
        raise RuntimeError("archive_readback_mismatch")
    count = conn.execute(
        "SELECT count(*) FROM pisrs.source_occurrence WHERE attempt_id=%s",
        (attempt_id,),
    ).fetchone()[0]
    return {"run":str(run),"source_key":key,"bytes":byte_length,
            "sha256":bytes(digest).hex(),"occurrences":count,"raw_parity":True}


def latest_attempt(conn, run: str, work_key: str) -> int:
    row = conn.execute(
        """SELECT attempt_id FROM pisrs.source_attempt
           WHERE run_id=%s AND work_key=%s ORDER BY attempt_id DESC LIMIT 1""",
        (uuid.UUID(run),work_key),
    ).fetchone()
    if not row:
        raise RuntimeError("attempt_not_found")
    return row[0]
