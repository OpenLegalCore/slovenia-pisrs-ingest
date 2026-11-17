"""Opt-in acceptance checks against the permanent PIKI archive."""
from argparse import Namespace
import os
import unittest
from unittest.mock import patch

from pisrs_g3.cli import canary_command
from pisrs_g3.http import SourceStopped
from pisrs_g3.storage import connect


SOURCE_CONN = os.environ.get("PISRS_G3_TEST_SOURCE")
READER_CONN = os.environ.get("PISRS_G3_TEST_READER")


class ArchiveAcceptanceTests(unittest.TestCase):
    @unittest.skipUnless(SOURCE_CONN, "PIKI PostgreSQL source connection required")
    def test_transport_failure_leaves_no_success_checkpoint(self):
        from psycopg.errors import CheckViolation

        with connect(SOURCE_CONN) as conn, conn.transaction(force_rollback=True):
            with self.assertRaises(CheckViolation), conn.transaction():
                conn.execute(
                    "INSERT INTO pisrs.source_blob(sha256,raw_bytes,byte_length) VALUES (%s,%s,%s)",
                    (bytes(32), b"offline-test", 12),
                )
            baseline = conn.execute(
                """SELECT run_id,published_at FROM pisrs.source_run
                   WHERE published_at IS NOT NULL OR status='PUBLISHED'"""
            ).fetchall()
            work = conn.execute(
                "SELECT count(*) FROM pisrs.source_run WHERE evidence->>'scope'='G3_sifranti_canary'"
            ).fetchone()[0]
            self.assertEqual(work, 0, "run before importing the first protected capture")
            args = Namespace(pg_conn_file=SOURCE_CONN, token_file=None, evidence_file=None,
                             pace=3.0, deadline=90, max_response_bytes=4096)
            with (patch("pisrs_g3.cli.connect", return_value=conn),
                  patch("pisrs_g3.cli.close_safely"),
                  patch("pisrs_g3.cli.protected_file", return_value="offline-test"),
                  patch("pisrs_g3.cli.Client.get", side_effect=SourceStopped("transport_failure"))):
                result = canary_command(args)
            self.assertEqual(result["canary"], "STOPPED")
            self.assertEqual(result["get_requests"], 0)
            state = conn.execute(
                """SELECT r.status,w.status,a.result,w.terminal_attempt_id IS NULL
                   FROM pisrs.source_run r JOIN pisrs.source_work w USING(run_id)
                   JOIN pisrs.source_attempt a USING(run_id,source_key,sweep,work_key)
                   WHERE r.evidence->>'scope'='G3_sifranti_canary'"""
            ).fetchall()
            self.assertEqual(state, [("OPEN", "RETRY", "TRANSPORT_ERROR", True)])
            actual = conn.execute(
                """SELECT run_id,published_at FROM pisrs.source_run
                   WHERE published_at IS NOT NULL OR status='PUBLISHED'"""
            ).fetchall()
            self.assertTrue(actual == baseline)
        print("CHECKPOINT_FAILURE PASS")

    @unittest.skipUnless(READER_CONN, "PIKI PostgreSQL read-only connection required")
    def test_initial_archive_counts_and_role_boundaries(self):
        with connect(READER_CONN) as conn:
            privileges = conn.execute(
                """SELECT current_user, has_schema_privilege(current_user,'pisrs','CREATE'),
                     has_table_privilege(current_user,'pisrs.source_blob','SELECT'),
                     has_table_privilege(current_user,'pisrs.source_blob','INSERT,UPDATE,DELETE,TRUNCATE'),
                     has_schema_privilege('pisrs_source','pisrs','CREATE'),
                     has_table_privilege('pisrs_source','pisrs.source_blob','INSERT'),
                     has_table_privilege('pisrs_source','pisrs.source_blob','UPDATE,DELETE,TRUNCATE'),
                     has_table_privilege('pisrs_source','pisrs.migration_log','INSERT,UPDATE,DELETE,TRUNCATE'),
                     has_table_privilege('pisrs_source','pisrs.contract_revision','INSERT,UPDATE,DELETE,TRUNCATE'),
                     (SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())"""
            ).fetchone()
            self.assertEqual(privileges, ("pisrs_backup", False, True, False, False, True,
                                          False, False, False, True))
            counts = conn.execute(
                """SELECT (SELECT count(*) FROM pisrs.source_blob),
                          (SELECT count(*) FROM pisrs.source_record),
                          (SELECT count(*) FROM pisrs.record_revision),
                          (SELECT count(*) FROM pisrs.source_occurrence),
                          (SELECT count(*) FROM pisrs.source_attempt
                           WHERE result='HTTP_COMPLETE' AND reason_code='protected_g1_capture'),
                          (SELECT count(*) FROM pisrs.source_work),
                          (SELECT count(*) FROM pisrs.source_run),
                          (SELECT count(*) FROM pisrs.source_run
                           WHERE status='PUBLISHED' OR published_at IS NOT NULL)"""
            ).fetchone()
            self.assertEqual(counts, (1, 13, 13, 13, 1, 1, 1, 0))
        print("REPLAY_COUNTS_AND_ROLE_BOUNDARIES PASS")
