"""Offline, no-network contract and schema regressions."""
import hashlib
import json
from pathlib import Path
import unittest
from decimal import Decimal

from pisrs_g3.contract import (
    OPS, BY_KEY, PAGED_KEYS, ARRAY_KEYS, OPENAPI_SHA256,
    ContractError, canonical, strict_json, qualified_identity,
    parse_response, request_path, safe_work_key, payload_hash,
)
from pisrs_g3.storage import _link_rows
from pisrs_g3.cli import check_contract


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
        value=strict_json(b'{"a": 12.250,"b":[3, null],"c":"č"}')
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
