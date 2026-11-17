"""G3 operator CLI. No implicit deployment, no automatic source sweep."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from uuid import UUID

from .contract import BY_KEY, PAGED_KEYS, ARRAY_KEYS, OPENAPI_SHA256, ContractError
from .http import Client, SourceStopped
from .storage import (
    connect, migrate, verify_tables, protected_file, source_lock,
    register_contract, verify_registered_contract, get_or_create_canary_run, queue_work, begin_attempt,
    record_stopped, archive_reply, project_reply, latest_attempt, verify_archive,
    protected_sifranti_reply, requeue_quarantined_sifranti,
)


def host_guard() -> None:
    if socket.gethostname().split(".")[0] != "piki":
        raise RuntimeError("operator_requires_piki")
    if os.geteuid() == 0:
        raise RuntimeError("no_root_source_client")


def source_role(conn) -> None:
    data = conn.execute(
        """SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls
           FROM pg_catalog.pg_roles WHERE rolname=current_user"""
    ).fetchone()
    if not data or data[0] != "pisrs_source" or any(data[1:]):
        raise RuntimeError("wrong_or_privileged_source_role")


def close_safely(conn) -> None:
    if conn is not None:
        conn.close()


def check_contract() -> dict:
    from .storage import MIGRATION
    from .contract import OPS
    if len(OPS) != 26 or tuple(sorted(op.key for op in OPS)) != tuple(range(1,27)):
        raise RuntimeError("operation_registry_not_26")
    if len(PAGED_KEYS) != 13 or len(ARRAY_KEYS) != 10:
        raise RuntimeError("operation_class_mismatch")
    sql = MIGRATION.read_text(encoding="utf-8")
    if sql.count("CREATE TABLE pisrs.") != 15:
        raise RuntimeError("wrong_archive_table_count")
    if "index_generation" in sql or "embedding_request" in sql:
        raise RuntimeError("g4_schema_attempt_in_g3")
    return {"openapi_sha256":OPENAPI_SHA256,
            "ingest_operations":len(OPS),
            "paged":len(PAGED_KEYS),"arrays":len(ARRAY_KEYS),
            "source_tables":15,"network_calls":0}


def migrate_command(args) -> dict:
    host_guard()
    conn = connect(args.pg_conn_file)
    try:
        # G3 owner approval exists, but migration is explicitly invoked after
        # operator checks DB identity, storage binds, roles and mount isolation.
        digest = migrate(conn)
        register_contract(conn)
        return {"migration_sha256":digest, **verify_tables(conn),
                "source_publication":"NOT_RUN"}
    finally:
        close_safely(conn)


def preflight_command(args) -> dict:
    host_guard()
    conn = connect(args.pg_conn_file)
    try:
        return {"database":"pisrs_staging","version":"18",
                **verify_tables(conn), "source_publication":"NOT_RUN"}
    finally:
        close_safely(conn)


def canary_command(args) -> dict:
    host_guard()
    original = None
    client = None
    if args.evidence_file:
        original = protected_sifranti_reply(args.evidence_file, args.max_response_bytes)
    else:
        client = Client(protected_file(args.token_file), min_interval=args.pace, max_requests=1,
                        max_response_bytes=args.max_response_bytes,
                        max_total_bytes=args.max_response_bytes, max_seconds=args.deadline)
    conn = connect(args.pg_conn_file)
    try:
        verify_tables(conn)
        source_role(conn)
        source_lock(conn)
        verify_registered_contract(conn)
        run = get_or_create_canary_run(conn)
        op = BY_KEY[25]  # fixed, known-safe bounded dictionary index
        key = queue_work(conn,run,op.key)
        old = conn.execute(
            """SELECT status FROM pisrs.source_work
               WHERE run_id=%s AND sweep=0 AND work_key=%s""",
            (UUID(run),key),
        ).fetchone()[0]
        if old == "COMPLETE":
            old_id = latest_attempt(conn,run,key)
            return {"canary":"ALREADY_ARCHIVED",
                    **verify_archive(conn,old_id,expected_sifranti=original),
                    "get_requests":0,"source_publication":"NOT_RUN"}
        if old == "LEASED":
            raise RuntimeError("active_or_stale_lease_requires_review")
        if old == "QUARANTINED" and original is not None and args.retry_quarantined_capture:
            requeue_quarantined_sifranti(conn, run, key, original)
        attempt = begin_attempt(conn,run,op.key,key)
        reply = original
        try:
            if client is not None:
                reply = client.get(op.path)
        except SourceStopped as stop:
            record_stopped(conn,run,key,attempt,stop.reason,status=stop.status)
            return {"canary":"STOPPED","reason":stop.reason,"http_status":stop.status,
                    "get_requests":client.requests_used,"source_publication":"NOT_RUN"}
        requests_used = client.requests_used if client is not None else 0
        archive_reply(conn,run,op.key,key,attempt,reply,protected_capture=original is not None)
        try:
            proof=project_reply(conn,run,op.key,key,attempt,reply)
        except (ValueError, TypeError) as exc:
            # The complete original survives; typed projection is quarantined.
            with conn.transaction():
                conn.execute(
                    """UPDATE pisrs.source_attempt
                       SET result='CONTRACT_ERROR',reason_code=%s
                       WHERE attempt_id=%s""",
                    ("projection_rejected",attempt),
                )
                conn.execute(
                    """UPDATE pisrs.source_work SET status='QUARANTINED',lease_until=NULL
                       WHERE run_id=%s AND work_key=%s""",
                    (UUID(run),key),
                )
            projection_reason = (
                "invalid_parent_code_int64" if str(exc) == "invalid_parent_code_int64"
                else "projection_rejected"
            )
            return {"canary":"QUARANTINED","reason":projection_reason,
                    "get_requests":requests_used,"source_publication":"NOT_RUN"}
        independent=verify_archive(conn,attempt,expected_sifranti=original)
        return {"canary":"RAW_AND_TYPED_ARCHIVED","source_operation":25,"run_id":run,
                "attempt_id":attempt,"http_status":reply.status,**proof,
                "readback":independent,"get_requests":requests_used}
    finally:
        close_safely(conn)


def readback_command(args) -> dict:
    host_guard()
    original = protected_sifranti_reply(args.evidence_file, 4 * 1024 * 1024) if args.evidence_file else None
    conn = connect(args.pg_conn_file)
    try:
        return verify_archive(conn,args.attempt_id,expected_sifranti=original)
    finally:
        close_safely(conn)


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(
        prog="pisrs-g3",
        description="PIKI G3 guarded archive (G2 signed, G3 explicitly authorized)")
    sub=parser.add_subparsers(dest="action",required=True)
    sub.add_parser("check-contract",help="offline fixed registry and migration checks")
    for action in ("preflight","migrate","canary","readback"):
        p=sub.add_parser(action)
        p.add_argument("--pg-conn-file",required=True,help="private 0600 /data libpq conninfo")
        if action=="canary":
            capture = p.add_mutually_exclusive_group(required=True)
            capture.add_argument("--token-file",help="private 0600 /data PISRS token for one GET")
            capture.add_argument("--evidence-file",help="private original /sifranti capture pinned by G1")
            p.add_argument("--retry-quarantined-capture", action="store_true",
                           help="retry projection only when the quarantined archive matches the evidence")
            p.add_argument("--pace",type=float,default=3.0)
            p.add_argument("--max-response-bytes",type=int,default=4*1024*1024)
            p.add_argument("--deadline",type=int,default=90)
        if action=="readback":
            p.add_argument("--attempt-id",type=int,required=True)
            p.add_argument("--evidence-file",help="compare with the independent protected G1 original")
    args=parser.parse_args(argv)
    if args.action == "canary" and args.retry_quarantined_capture and not args.evidence_file:
        parser.error("--retry-quarantined-capture requires --evidence-file")
    try:
        result=check_contract() if args.action=="check-contract" else {
            "preflight":preflight_command,
            "migrate":migrate_command,
            "canary":canary_command,
            "readback":readback_command,
        }[args.action](args)
        stopped = result.get("canary") in {"STOPPED", "QUARANTINED"}
        print(json.dumps({"result":"STOPPED" if stopped else "PASS",**result},ensure_ascii=False,sort_keys=True))
        return 2 if stopped else 0
    except (ContractError,SourceStopped,RuntimeError,ValueError,OSError) as exc:
        # No exception trace/DSN/body/credential leaves the CLI.
        code=str(exc)
        allowed={
            "operator_requires_piki","no_root_source_client","wrong_database_or_postgresql_major",
            "postgresql_connect_failed","wrong_or_privileged_source_role",
            "schema_table_inventory_mismatch","schema_migration_log_mismatch",
            "schema_constraint_inventory_unexpected","applied_migration_hash_drift",
            "unverified_existing_schema","another_g3_source_or_migration_running",
            "work_not_claimable","active_or_stale_lease_requires_review","attempt_cap",
            "protected_absolute_data_path_required","protected_file_must_be_0600",
            "protected_file_owner_mismatch","invalid_protected_pg_connection",
            "protected_evidence_hash_mismatch","archive_original_mismatch",
            "archive_identity_or_occurrence_mismatch","archive_attempt_not_open",
            "postgresql_tls_verification_required","body_budget","unbounded_source_budget",
            "wrong_staging_connection_target",
            "quarantined_capture_not_replayable",
        }
        print(json.dumps({"result":"STOPPED",
                          "reason":code if code in allowed else "review_required"},
                         ensure_ascii=False))
        return 2
    except Exception as exc:
        # Database exceptions may contain SQL details and protected row values.
        psycopg = sys.modules.get("psycopg")
        if psycopg is None or not isinstance(exc, psycopg.Error):
            raise
        print(json.dumps({"result":"STOPPED","reason":"postgresql_operation_failed",
                          "sqlstate":exc.sqlstate}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
