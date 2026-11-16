"""Pinned PISRS OpenAPI 1.0.0 G3 source contract. No network side effects."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re
from typing import Any

OPENAPI_SHA256 = "ba228a17f852520c2f746709ae9ad43be6f15366327e36686606c9229b8b8e82"
REVISION = "pisrs-openapi-1.0.0-g3-v1"
RULES_REVISION = "pisrs-g3-identity-v1"
PARSER_REVISION = "pisrs-g3-html-v1"
BASE = "https://pisrs.si/extapi"


@dataclass(frozen=True)
class Operation:
    key: int
    path: str
    kind: str
    namespace: str | None


# Only documented GET operations. Credential-request POST (operation 27) is excluded.
OPS = (
    Operation(1, "/predpis/register-predpisov", "paged", "RS_ACT"),
    Operation(2, "/predpis/register-predpisov/seznam", "array", "RS_ACT"),
    Operation(3, "/predpis/predpisi-v-pripravi", "paged", "RS_ACT"),
    Operation(4, "/predpis/predpisi-v-pripravi/seznam", "array", "RS_ACT"),
    Operation(5, "/predpis/obsoletni-in-konzumirani-predpisi", "paged", "RS_ACT"),
    Operation(6, "/predpis/obsoletni-in-konzumirani-predpisi/seznam", "array", "RS_ACT"),
    Operation(7, "/predpis/neveljavni-predpisi", "paged", "RS_ACT"),
    Operation(8, "/predpis/neveljavni-predpisi/seznam", "array", "RS_ACT"),
    Operation(9, "/predpis/evidenca-normodajalcev", "paged", "RS_ACT"),
    Operation(10, "/predpis/evidenca-normodajalcev/seznam", "array", "RS_ACT"),
    Operation(11, "/predpis/drugi-splosni-in-posamicni-akti", "paged", "RS_ACT"),
    Operation(12, "/predpis/drugi-splosni-in-posamicni-akti/seznam", "array", "RS_ACT"),
    Operation(13, "/predpis/splosni-akti-za-izvrsevanje-javnih-pooblastil", "paged", "RS_ACT"),
    Operation(14, "/predpis/splosni-akti-za-izvrsevanje-javnih-pooblastil/seznam", "array", "RS_ACT"),
    Operation(15, "/npb", "paged", "RS_NPB"),
    Operation(16, "/predpis-eu", "paged", "EU"),
    Operation(17, "/akt-ls/veljavni-akti", "paged", "LS_ACT"),
    Operation(18, "/akt-ls/veljavni-akti/seznam", "array", "LS_ACT"),
    Operation(19, "/akt-ls/akti-v-pripravi", "paged", "LS_ACT"),
    Operation(20, "/akt-ls/akti-v-pripravi/seznam", "array", "LS_ACT"),
    Operation(21, "/akt-ls/neveljavni-akti", "paged", "LS_ACT"),
    Operation(22, "/akt-ls/neveljavni-akti/seznam", "array", "LS_ACT"),
    Operation(23, "/npb-ls", "paged", "LS_NPB"),
    Operation(24, "/besedilo/{idZbirkaElement}", "html", None),
    Operation(25, "/sifranti", "dictionary", "CODE_LIST"),
    Operation(26, "/sifranti/{id}", "dictionary", "CODE_VALUE"),
)
BY_KEY = {op.key: op for op in OPS}
PAGED_KEYS = tuple(op.key for op in OPS if op.kind == "paged")
ARRAY_KEYS = tuple(op.key for op in OPS if op.kind == "array")


class ContractError(ValueError):
    """Source response cannot be trusted or categorized within the pinned contract."""


def _object_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ContractError("duplicate_json_key")
        if "\x00" in key:
            raise ContractError("nul_json_key")
        out[key] = value
    return out


def strict_json(raw: bytes) -> Any:
    try:
        result = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_object_unique,
                            parse_float=Decimal,
                            parse_constant=lambda _: (_ for _ in ()).throw(ContractError("nonfinite_json")))
    except (UnicodeError, json.JSONDecodeError, OverflowError) as exc:
        raise ContractError("invalid_json") from exc
    if _has_nul(result):
        raise ContractError("nul_json_value")
    return result


def _has_nul(value: Any) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, list):
        return any(_has_nul(v) for v in value)
    if isinstance(value, dict):
        return any(_has_nul(v) for v in value.values())
    return False


def canonical(value: Any) -> str:
    """Exact integer/decimal-preserving deterministic JSON for typed value hashes."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if type(value) is int:
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ContractError("nonfinite_decimal")
        return format(value, "f")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, list):
        return "[" + ",".join(canonical(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(canonical(k) + ":" + canonical(value[k])
                              for k in sorted(value)) + "}"
    raise ContractError("unknown_json_type")


def payload_hash(value: Any) -> bytes:
    return hashlib.sha256(canonical(value).encode("utf-8")).digest()


def int64_id(value: Any) -> str:
    if type(value) is not int or not 0 <= value <= 9223372036854775807:
        raise ContractError("invalid_int64_source_id")
    return str(value)


def qualified_identity(op: Operation, row: dict[str, Any], parent: str = "") -> tuple[str, str, str]:
    if not isinstance(row, dict):
        raise ContractError("row_not_object")
    if op.namespace is None:
        raise ContractError("no_identity_for_html")
    if op.namespace == "EU":
        c = row.get("celex")
        if not isinstance(c, str) or not c.strip() or len(c) > 256:
            raise ContractError("invalid_celex")
        return ("EU", "", c)
    source = int64_id(row.get("id"))
    if op.namespace == "CODE_VALUE":
        return ("CODE_VALUE", int64_id(int(parent)) if re.fullmatch(r"[0-9]{1,19}", parent) else _missing_parent(), source)
    return (op.namespace, "", source)


def _missing_parent() -> str:
    raise ContractError("missing_verified_dictionary_parent")


def parse_response(op: Operation, raw: bytes, expected_page: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if op.kind == "html":
        raise ContractError("html_requires_separate_capture")
    decoded = strict_json(raw)
    if op.kind == "array":
        if not isinstance(decoded, list) or any(not isinstance(r, dict) for r in decoded):
            raise ContractError("array_shape")
        return decoded, {"pointer": "", "page": None}
    if not isinstance(decoded, dict) or decoded.get("error") not in (None, ""):
        raise ContractError("envelope_error")
    rows = decoded.get("data")
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ContractError("envelope_data")
    if op.kind == "paged":
        if type(decoded.get("page")) is not int or decoded["page"] != expected_page:
            raise ContractError("page_echo_mismatch")
        if type(decoded.get("realPageSize")) is not int or decoded["realPageSize"] != len(rows):
            raise ContractError("page_size_mismatch")
    return rows, {
        "pointer": "/data",
        "page": decoded.get("page"),
        "requested_page_size": decoded.get("requestedPageSize"),
        "real_page_size": decoded.get("realPageSize"),
        "total_count": decoded.get("totalCount"),
    }


def json_pointer(prefix: str, position: int) -> str:
    if position < 0:
        raise ContractError("negative_pointer")
    return f"{prefix}/{position}"


def request_path(op: Operation, identifier: str | None = None) -> str:
    if op.key == 24:
        if identifier is None or not re.fullmatch(r"[0-9]{1,19}", identifier):
            raise ContractError("invalid_state_text_locator")
        return op.path.replace("{idZbirkaElement}", identifier)
    if op.key == 26:
        if identifier is None or not re.fullmatch(r"[0-9]{1,19}", identifier):
            raise ContractError("invalid_dictionary_id")
        return op.path.replace("{id}", identifier)
    if identifier is not None:
        raise ContractError("unexpected_path_parameter")
    return op.path


def safe_work_key(op: Operation, sweep: int, page: int | None = None, identifier: str | None = None) -> str:
    if not 0 <= sweep <= 32767:
        raise ContractError("invalid_sweep")
    if op.kind == "paged":
        if not isinstance(page, int) or page < 1:
            raise ContractError("invalid_page")
        return f"op{op.key:02d}:page:{page}"
    if op.key in (24, 26):
        request_path(op, identifier)
        return f"op{op.key:02d}:id:{identifier}"
    if page is not None or identifier is not None:
        raise ContractError("unexpected_parameter")
    return f"op{op.key:02d}:whole"
