"""Catalog-only boundaries: no text, vector, embedding or checkpoint adapters."""

from types import SimpleNamespace

import pytest

from pisrs_ingest import cli
from pisrs_ingest.models import Act, ExternalCatalogItem, NpbDocument
from pisrs_ingest.pipeline import PipelineError, run_catalog_import


def fixtures():
    events = []
    act = Act.from_raw(
        {"id": 1, "mopedId": "RS1", "naziv": "Synthetic state act"},
        "/predpis/register-predpisov",
    )
    npb = NpbDocument.from_raw({"id": 2})
    eu = ExternalCatalogItem.from_raw({"celex": "32024R0001"}, "/predpis-eu", "EU")
    local = ExternalCatalogItem.from_raw(
        {"id": 3, "mopedPlusId": "LS3"}, "/akt-ls/veljavni-akti", "LS_ACT"
    )
    local_npb = ExternalCatalogItem.from_raw({"id": 4}, "/npb-ls", "LS_NPB")
    client = SimpleNamespace(
        discover_acts=lambda: [act],
        discover_npbs=lambda: [npb],
        discover_eu_acts=lambda: [eu],
        discover_local_acts=lambda: [local],
        discover_local_npbs=lambda: [local_npb],
        fetch_text=lambda _: pytest.fail("text requested"),
    )
    postgres = SimpleNamespace(
        external=SimpleNamespace(
            synchronize=lambda items: events.append(("external", len(items))),
            synchronize_state_raw=lambda items: events.append(("raw", len(items))),
        ),
        catalogs=SimpleNamespace(
            synchronize=lambda acts, npbs: events.append(("state", len(acts), len(npbs)))
        ),
    )
    return client, postgres, events


def test_catalog_import_defaults_are_read_only_and_apply_matches_same_inventory():
    client, postgres, events = fixtures()
    plan = run_catalog_import(client=client, postgres=postgres, apply=False)
    assert events == []
    assert all(
        plan[k] == 0
        for k in ("text_requests", "embedding_calls", "qdrant_writes", "checkpoint_writes")
    )
    applied = run_catalog_import(
        client=client,
        postgres=postgres,
        apply=True,
        expected_identities=plan["identity_sha256"],
    )
    assert applied["identity_sha256"] == plan["identity_sha256"]
    assert events == [("external", 3), ("state", 1, 1), ("raw", 1)]


def test_catalog_import_rejects_scope_drift_before_any_write():
    client, postgres, events = fixtures()
    with pytest.raises(PipelineError, match="differs from approved inventory"):
        run_catalog_import(
            client=client, postgres=postgres, apply=True, expected_identities="0" * 64
        )
    assert events == []
    client.discover_local_npbs = lambda: (_ for _ in ()).throw(ValueError("incomplete catalog"))
    with pytest.raises(ValueError, match="incomplete catalog"):
        run_catalog_import(client=client, postgres=postgres, apply=True)
    assert events == []


def test_scheduled_catalog_mode_never_opens_full_nightly(tmp_path, monkeypatch):
    settings = SimpleNamespace(
        lock_path=tmp_path / "ingest.lock", allow_external_api=True, allow_writes=True
    )
    monkeypatch.setattr(cli, "load_settings", lambda *args: settings)
    monkeypatch.setattr(cli, "_nightly", lambda _: pytest.fail("full nightly opened"))
    monkeypatch.setattr(cli, "EmbeddingClient", lambda *args: pytest.fail("embedder opened"))
    monkeypatch.setattr(cli, "CheckpointStore", lambda *args: pytest.fail("checkpoint opened"))
    calls = []
    monkeypatch.setattr(cli, "_catalog_import", lambda s, **kwargs: calls.append(kwargs) or 0)
    assert cli.main(["nightly", "--catalogs-only"]) == 0
    assert calls == [{"apply": True}]


def test_catalog_import_cli_requires_explicit_apply_and_identity(tmp_path, monkeypatch):
    settings = SimpleNamespace(
        lock_path=tmp_path / "ingest.lock", allow_external_api=True, allow_writes=True
    )
    monkeypatch.setattr(cli, "load_settings", lambda *args: settings)
    calls = []
    monkeypatch.setattr(cli, "_catalog_import", lambda s, **kwargs: calls.append(kwargs) or 0)
    assert cli.main(["catalog-import"]) == 0
    assert calls == [{"apply": False}]
    assert not settings.lock_path.exists()
    assert cli.main(["catalog-import", "--apply"]) == cli.EXIT_CONFIG
    assert len(calls) == 1
