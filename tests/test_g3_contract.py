"""Offline, no-network contract and schema regressions."""
import hashlib
import json
from pathlib import Path
import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from pisrs_g3.contract import (
    OPS, BY_KEY, PAGED_KEYS, ARRAY_KEYS, OPENAPI_SHA256,
    ContractError, canonical, strict_json, qualified_identity,
    parse_response, request_path, safe_work_key, payload_hash,
)
from pisrs_g3.http import Reply
from pisrs_g3.storage import _link_rows, _store_record, requeue_quarantined_sifranti, verify_archive
from pisrs_g3.cli import check_contract


RUN_ID = "00000000-0000-0000-0000-000000000001"


class ContractTests(unittest.TestCase):
    def test_registry_exact_26_get(self):
        self.assertEqual([x.key for x in OPS], list(range(1,27)))
        self.assertEqual(len(PAGED_KEYS),13)
        self.assertEqual(len(ARRAY_KEYS),10)
        self.assertEqual(BY_KEY[24].kind,"html")
        self.assertEqual(BY_KEY[25].kind,"dictionary")
        self.assertEqual(BY_KEY[26].kind,"dictionary")
        self.assertEqual(len(OPENAPI_SHA256),64)

    def test_paged_nonempty_and_empty(self):
        page1=json.dumps({"data":[{"id":1}],"error":None,"page":1,
                          "realPageSize":1,"requestedPageSize":50,"totalCount":999}).encode()
        rows,meta=parse_response(BY_KEY[1],page1,1)
        self.assertEqual(len(rows),1)
        self.assertEqual(meta["page"],1)
        empty=page1.replace(b'"data": [{"id": 1}]',b'"data": []').replace(
            b'"realPageSize": 1',b'"realPageSize": 0').replace(
            b'"page": 1',b'"page": 2')
        rows,_=parse_response(BY_KEY[1],empty,2)
        self.assertEqual(len(rows),0)
        with self.assertRaises(ContractError):
            parse_response(BY_KEY[1],page1,2)

    def test_double_key_rejected(self):
        with self.assertRaises(ContractError):
            strict_json(b'{"data":[],"data":[],"error":null}')
        with self.assertRaises(ContractError):
            strict_json(b'{"data":[{"id":1,"id":2}]}')

    def test_numeric_and_raw_canonical(self):
        value=strict_json('{"a": 12.250,"b":[3, null],"c":"č"}'.encode("utf-8"))
        self.assertEqual(value["a"],Decimal("12.250"))
        self.assertEqual(canonical(value),'{"a":12.250,"b":[3,null],"c":"č"}')
        self.assertEqual(payload_hash(value),hashlib.sha256(canonical(value).encode()).digest())

    def test_code_parent_not_code_value(self):
        op=BY_KEY[26]
        self.assertEqual(qualified_identity(op,{"id":128088,"idNadrejeni":128070,"naziv":"Pravilnik"},"128070"),
                         ("CODE_VALUE","128070","128088"))
        self.assertNotEqual("13022","128088")
        with self.assertRaises(ContractError):
            qualified_identity(op,{"id":128088},"")
        with self.assertRaises(ContractError):
            qualified_identity(op,{"id":128088},str(2**63))

    def test_direction_no_invented_reverse(self):
        rs={"mopedId":"ZAKO7054","zveza":[]}
        eu={"celex":"32011L0083","zveza":[{"mopedID":"ZAKO7054","naziv":"ZVPot-1"}]}
        self.assertEqual(list(_link_rows(rs)),[])
        refs=list(_link_rows(eu))
        self.assertEqual(len(refs),1)
        self.assertEqual(refs[0][3],"MOPED")
        self.assertEqual(refs[0][4],"ZAKO7054")

    def test_signed_parent_metadata_is_preserved_in_record_revision(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (1,)
        row = {"id": 123, "idNadrejeni": -7, "naziv": "Example"}
        _store_record(conn, RUN_ID, BY_KEY[25], row)
        sql, parameters = conn.execute.call_args.args
        self.assertIn("parent_code_id", sql)
        self.assertEqual(len(parameters), sql.count("%s"))
        self.assertEqual(parameters[-1], "-7")
        self.assertEqual(json.loads(parameters[3]), row)
        with self.assertRaises(ContractError):
            qualified_identity(BY_KEY[25], {"id": -7})
        for invalid_parent in (-(2**63) - 1, 2**63, True, "-7"):
            with self.subTest(invalid_parent=invalid_parent), self.assertRaisesRegex(
                ContractError, "invalid_parent_code_int64"
            ):
                _store_record(conn, RUN_ID, BY_KEY[25], dict(row, idNadrejeni=invalid_parent))

    def test_quarantined_retry_requires_same_archived_bytes_without_occurrences(self):
        body = b'{"data":[]}'
        reply = Reply(200, body, hashlib.sha256(body).digest(), "application/json", None,
                      "identity", None, None, 0)
        conn = MagicMock()
        old = ("CONTRACT_ERROR", "projection_rejected", 200, reply.sha256, body, False)
        conn.execute.return_value.fetchone.return_value = old
        conn.execute.return_value.rowcount = 1
        requeue_quarantined_sifranti(conn, RUN_ID, "op25:all", reply)
        self.assertEqual(conn.execute.call_count, 2)
        self.assertIn("status='QUARANTINED'", conn.execute.call_args.args[0])
        self.assertIn("status='RETRY'", conn.execute.call_args.args[0])
        for invalid in (None, (*old[:4], b"other", False), (*old[:-1], True)):
            with self.subTest(source=invalid), self.assertRaisesRegex(
                RuntimeError, "quarantined_capture_not_replayable"
            ):
                conn.execute.reset_mock()
                conn.execute.return_value.fetchone.return_value = invalid
                requeue_quarantined_sifranti(conn, RUN_ID, "op25:all", reply)
            self.assertEqual(conn.execute.call_count, 1)

    def test_readback_verifies_typed_parent_in_addition_to_raw_bytes(self):
        item = {"id": 123, "idNadrejeni": -7}
        body = json.dumps({"data": [item]}).encode()
        reply = Reply(200, body, hashlib.sha256(body).digest(), "application/json", None,
                      "identity", None, None, 0)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (RUN_ID, 25, reply.sha256, 200, body, len(body))
        row = (0, "/data/0", "CODE_LIST", "", "123", item)
        conn.execute.return_value.fetchall.return_value = [(*row, "-7", True)]
        self.assertTrue(verify_archive(conn, 1, expected_sifranti=reply)["identity_parity"])
        conn.execute.return_value.fetchall.return_value = [(*row, None, True)]
        with self.assertRaisesRegex(RuntimeError, "archive_identity_or_occurrence_mismatch"):
            verify_archive(conn, 1, expected_sifranti=reply)

    def test_missing_or_bad_locator_fails_closed(self):
        self.assertEqual(request_path(BY_KEY[26],"128070"),"/sifranti/128070")
        with self.assertRaises(ContractError):
            request_path(BY_KEY[26],"../arbitrary")
        with self.assertRaises(ContractError):
            request_path(BY_KEY[24],"ZAKO7054")
        self.assertEqual(safe_work_key(BY_KEY[1],0,page=2),"op01:page:2")
        with self.assertRaises(ContractError):
            safe_work_key(BY_KEY[1],0,page=0)

    def test_sql_exact_fifteen_tables(self):
        sql=(Path(__file__).resolve().parent.parent/"pisrs_g3"/"migrations"/"001_g3_archive.sql").read_text()
        self.assertEqual(sql.count("CREATE TABLE pisrs."),15)
        for table in ("migration_log","source_run","source_work","source_attempt",
                      "source_blob","source_occurrence","document_locator","source_artifact"):
            self.assertIn("CREATE TABLE pisrs."+table,sql)
        self.assertIn("source_work_terminal_attempt_fk",sql)
        self.assertIn("FOREIGN KEY(run_id,sweep,work_key,source_key)",sql)
        self.assertNotIn("CREATE TABLE pisrs.embedding_request",sql)
        self.assertNotIn("CREATE TABLE pisrs.index_generation",sql)

    def test_no_network_contract_check(self):
        self.assertEqual(check_contract()["network_calls"],0)


if __name__ == "__main__":
    unittest.main()
