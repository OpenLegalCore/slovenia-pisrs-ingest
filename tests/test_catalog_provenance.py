from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from pisrs_ingest import cli
from pisrs_ingest.catalog_provenance import (
    ENDPOINTS,
    METADATA,
    TABLES,
    CatalogScopeError,
    ProvenancePlan,
    _plan,
    _source,
)
from pisrs_ingest.config import load_settings
from pisrs_ingest.locking import ApplicationLock
from pisrs_ingest.models import Act
from pisrs_ingest.postgres import ACT_CATALOG_UPSERT, ACTS_UPSERT


def acts():
    return [
        replace(
            Act.from_raw({"id": i, "mopedId": f"M{i}", "naziv": f"Act {i}"}, ENDPOINTS[3]),
            seen_in_endpoints=tuple(dict.fromkeys((ENDPOINTS[3], ep))),
        )
        for i, ep in enumerate(ENDPOINTS, 1)
    ]


def stored(source):
    result = {t: [] for t in TABLES}
    for t in TABLES:
        for a in source:
            before = [e for e in a.seen_in_endpoints if e in ENDPOINTS[:4]]
            envelope = {**a.provenance(), "seen_in_endpoints": before, "extra": {"keep": 1}}
            envelope.pop("raw")
            result[t].append(
                {
                    "id": a.register_id + 100,
                    "register_id": a.register_id,
                    **{k: getattr(a, k) for k in METADATA},
                    "endpoint": before[0],
                    "seen_in_endpoints": before,
                    "envelope": envelope,
                    "row_hash": f"before-{a.register_id}",
                    "other_hash": "other",
                    "source_rest_hash": "source",
                }
            )
    return result


def test_plan_is_append_only_and_binds_all_identities_and_rows():
    source = acts()
    rows = stored(source)
    plan = _plan(source, rows, {"database": "fixture"})
    assert plan.identities == 7
    assert {t: len(c) for t, c in plan.changes.items()} == {t: 3 for t in TABLES}
    assert sum(plan.links_added.values()) == 3
    assert plan.summary()["sequence_calls"] == 0
    for table in TABLES:
        for c in plan.changes[table]:
            before = next(r for r in rows[table] if r["id"] == c["id"])
            assert c["seen"][: len(before["seen_in_endpoints"])] == before["seen_in_endpoints"]
    drifted = deepcopy(rows)
    drifted["acts"][0]["row_hash"] = "unrelated metadata changed"
    assert _plan(source, drifted, {"database": "fixture"}).sha256 != plan.sha256


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate"])
def test_changed_identity_set_is_rejected(change):
    source = acts()
    rows = stored(source)
    if change == "missing":
        rows["acts"].pop()
    elif change == "extra":
        rows["acts"].append({**rows["acts"][0], "register_id": 999})
    else:
        source.append(source[0])
    with pytest.raises(CatalogScopeError):
        _plan(source, rows, {})


@pytest.mark.parametrize("change", ["metadata", "envelope", "legacy", "table_conflict"])
def test_unexpected_metadata_or_provenance_is_rejected(change):
    source = acts()
    rows = stored(source)
    if change == "metadata":
        rows["acts"][0]["naziv"] = "different title"
    elif change == "envelope":
        rows["acts"][0]["envelope"]["register_id"] = 999
    elif change == "legacy":
        rows["acts"][0]["seen_in_endpoints"] = [ENDPOINTS[3]]
        rows["acts"][0]["envelope"]["seen_in_endpoints"] = [ENDPOINTS[3]]
    else:
        rows["acts"][-1]["seen_in_endpoints"].append(ENDPOINTS[-1])
        rows["acts"][-1]["envelope"]["seen_in_endpoints"] = rows["acts"][-1]["seen_in_endpoints"]
    with pytest.raises(CatalogScopeError):
        _plan(source, rows, {})


def test_old_four_catalog_input_is_rejected_and_old_upserts_overwrite_provenance():
    old = [
        replace(a, seen_in_endpoints=tuple(e for e in a.seen_in_endpoints if e in ENDPOINTS[:4]))
        for a in acts()
    ]
    with pytest.raises(CatalogScopeError, match="seven"):
        _source(old)
    for statement in [ACTS_UPSERT, ACT_CATALOG_UPSERT]:
        assert "seen_in_endpoints = EXCLUDED.seen_in_endpoints" in statement


def environment(tmp_path):
    return {
        "PISRS_DATABASE_DSN": "postgresql://fixture@localhost/fixture",
        "PISRS_EXPECTED_DATABASE": "fixture",
        "PISRS_QDRANT_URL": "http://127.0.0.1:6333",
        "PISRS_QDRANT_COLLECTION": "pisrs_current",
        "PISRS_LOCK_PATH": str(tmp_path / "app.lock"),
        "PISRS_ALLOW_EXTERNAL_API": "1",
        "PISRS_ALLOW_WRITES": "0",
        "PISRS_RECONCILE_MAX_CHANGES": "1",
        "PISRS_PORTAL_BASE_URL": "https://example.invalid/extapi",
        "PISRS_API_TOKEN": "fixture",
    }


def test_catalog_configuration_does_not_require_embedding_or_checkpoint_credentials(tmp_path):
    settings = load_settings("catalog-sync", environment(tmp_path))
    assert settings.openai_api_key is None
    assert settings.checkpoint_path is None


@pytest.mark.parametrize("arguments", [[], ["--dry-run"], ["--apply"]])
def test_cli_boundary_default_readonly_and_explicit_apply(tmp_path, monkeypatch, capsys, arguments):
    env = environment(tmp_path)
    env["PISRS_ALLOW_WRITES"] = "1"  # Dry-run must remain read-only even in this context.
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_bytes(b"untouched")
    calls = []
    plan = ProvenancePlan("a" * 64, 7, {}, {}, {t: [] for t in TABLES}, {})

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden ingest stage")

    class Source:
        def __init__(self, *args):
            pass

        def discover_acts(self):
            return acts()

        discover_npbs = fetch_text = forbidden

    def operation(*args, **kwargs):
        calls.append(kwargs)
        if kwargs["apply"]:
            kwargs["runtime_guard"].verify(object())
            kwargs["before_write"](plan)
        return plan

    monkeypatch.setattr(cli, "PisrsClient", Source)
    monkeypatch.setattr(cli, "catalog_provenance", operation)
    monkeypatch.setattr(cli, "PostgresDatabase", lambda *a: object())
    monkeypatch.setattr(cli, "verify_runtime", lambda *_: "reviewed fixture")
    monkeypatch.setattr(cli, "verify_lock", lambda *_: None)
    monkeypatch.setattr(cli, "CatalogApplicationLock", ApplicationLock)
    monkeypatch.setattr(cli.RuntimeGuard, "verify", lambda *_: None)
    for name in [
        "QdrantStore",
        "EmbeddingClient",
        "CheckpointStore",
        "PostgresBoundary",
        "run_nightly",
    ]:
        monkeypatch.setattr(cli, name, forbidden)
    if "--apply" in arguments:
        env["PISRS_ALLOW_WRITES"] = "1"
        assert cli.main(["catalog-sync", "--apply"], env) == cli.EXIT_CONFIG
        assert not calls
        arguments += ["--expect-plan", "a" * 64, "--confirm-active-catalog-code"]
    assert cli.main(["catalog-sync", *arguments], env) == 0
    assert calls[0]["apply"] == ("--apply" in arguments)
    assert checkpoint.read_bytes() == b"untouched"
    assert "old four-catalog nightly" in capsys.readouterr().out
    if "--apply" not in arguments:
        assert not (tmp_path / "app.lock").exists()


def test_apply_requires_write_permission_and_holds_existing_lock(tmp_path, monkeypatch):
    from pisrs_ingest.locking import ApplicationLock

    env = environment(tmp_path)
    monkeypatch.setattr(cli, "verify_runtime", lambda *_: "reviewed fixture")
    monkeypatch.setattr(cli, "verify_lock", lambda *_: None)
    monkeypatch.setattr(cli, "CatalogApplicationLock", ApplicationLock)
    args = ["catalog-sync", "--apply", "--expect-plan", "a" * 64, "--confirm-active-catalog-code"]
    assert cli.main(args, env) == cli.EXIT_CONFIG
    env["PISRS_ALLOW_WRITES"] = "1"
    with ApplicationLock(tmp_path / "app.lock"):
        assert cli.main(args, env) == cli.EXIT_LOCK_BUSY
