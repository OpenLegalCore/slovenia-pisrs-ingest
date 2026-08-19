from __future__ import annotations

import fcntl
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import requests

from pisrs_ingest import cli
from pisrs_ingest.checkpoint import CheckpointError, CheckpointStore, Interval
from pisrs_ingest.client import HttpClient, HttpError, RetryPolicy
from pisrs_ingest.config import ConfigError, load_settings
from pisrs_ingest.locking import ApplicationLock, LockBusyError
from pisrs_ingest.models import (
    NpbDocument,
    SourceInvariantError,
    VectorRow,
    canonical_content_hash,
    make_chunks,
    parse_html,
    qdrant_point_id,
    version_rank,
)
from pisrs_ingest.pipeline import (
    DocumentBatchError,
    PipelineError,
    apply_reconciliation,
    plan_reconciliation,
    run_nightly,
)
from pisrs_ingest.qdrant import PointState, QdrantInvariantError, payload_patch


def vector_row(*, active: bool, latest: bool, text_id: int, chunk_index: int = 1) -> VectorRow:
    return VectorRow(
        database_id=text_id,
        point_id=qdrant_point_id("pisrs_current", text_id, chunk_index),
        act_id=10,
        version_id=text_id + 100,
        text_id=text_id,
        sop="SOP-1",
        sop_from_docno="SOP-1",
        npb_label="npb02" if latest else "npb01",
        naziv="Fixture act",
        title="Fixture version",
        chunk_index=chunk_index,
        chunk_type="text",
        chunk_text=f"fixture text {text_id}",
        chunk_text_len=len(f"fixture text {text_id}"),
        block_start_index=1,
        block_end_index=1,
        block_count=1,
        token_estimate=4,
        content_hash=canonical_content_hash(f"fixture text {text_id}"),
        is_latest_for_sop=latest,
        is_active=active,
        embedding_model="text-embedding-3-large",
        embedding_dimensions=3072,
        collection_name="pisrs_current",
    )


class FakeCheckpoint:
    def __init__(self) -> None:
        self.advanced: list[datetime] = []
        self.start = datetime(2026, 1, 1, tzinfo=UTC)
        self.end = datetime(2026, 1, 2, tzinfo=UTC)

    def interval(self, _: datetime) -> Interval:
        return Interval(self.start, self.end)

    def advance(self, end: datetime) -> None:
        self.advanced.append(end)


class FakeClient:
    def discover_acts(self) -> list[object]:
        return []

    def discover_npbs(self) -> list[object]:
        return []

    def fetch_text(self, text_id: int) -> str:
        raise AssertionError(f"unexpected fetch: {text_id}")

    def source_url(self, text_id: int) -> str:
        return f"https://example.invalid/besedilo/{text_id}"


class FakePostgres:
    def __init__(
        self,
        rows: list[VectorRow],
        *,
        fail_mark_once: bool = False,
        rollover_rows: dict[str, list[VectorRow]] | None = None,
    ) -> None:
        self.rows = rows
        self.fail_mark_once = fail_mark_once
        self.rollover_rows = rollover_rows
        self.refreshed_point_ids: set[str] | None = None
        self.marked: list[str] = []
        self.catalogs = SimpleNamespace(synchronize=self.synchronize_catalogs)
        self.documents = SimpleNamespace(
            pending=self.pending_versions, synchronize=self.synchronize_version
        )
        self.chunks = SimpleNamespace(
            touched_sops=self.touched_sops,
            prepare_rollover=self.prepare_rollover,
            rows_for_point_ids=self.rows_for_point_ids,
            mark_uploaded=self.mark_uploaded,
            iter_authoritative_payload_batches=self.iter_authoritative_payload_batches,
        )

    def synchronize_catalogs(self, acts: list[object], npbs: list[object]) -> None:
        assert not acts and not npbs

    def pending_versions(self, limit: int, since: datetime) -> list[object]:
        assert limit > 0
        assert since == datetime(2026, 1, 1, tzinfo=UTC)
        return []

    def synchronize_version(self, document: object, parsed: object, source_url: str) -> None:
        raise AssertionError((document, parsed, source_url))

    def touched_sops(self, since: datetime) -> list[str]:
        assert since.tzinfo is not None
        return list(self.rollover_rows) if self.rollover_rows is not None else ["SOP-1"]

    def prepare_rollover(self, sop: str, model: str, dimensions: int) -> list[VectorRow]:
        assert (model, dimensions) == ("text-embedding-3-large", 3072)
        if self.rollover_rows is not None:
            return self.rollover_rows[sop]
        assert sop == "SOP-1"
        return self.rows

    def rows_for_point_ids(self, point_ids: set[str]) -> list[VectorRow]:
        self.refreshed_point_ids = point_ids
        return self.rows

    def mark_uploaded(self, rows: list[VectorRow]) -> None:
        if self.fail_mark_once:
            self.fail_mark_once = False
            raise RuntimeError("simulated PostgreSQL failure after Qdrant upsert")
        self.marked.extend(row.point_id for row in rows)

    def iter_authoritative_payload_batches(self) -> list[list[VectorRow]]:
        return [self.rows]


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[0.0] * 3072 for _ in texts]


class FakeQdrant:
    def __init__(self, rows: list[VectorRow] = ()) -> None:
        self.points = {row.point_id: dict(row.payload()) for row in rows}
        self.upsert_calls = 0
        self.payload_calls = 0
        self.validate_calls = 0
        self.collection = "pisrs_current"

    def validate_collection(
        self, dimensions: int | None = None, model: str | None = None
    ) -> dict[str, object]:
        self.validate_calls += 1
        assert dimensions in {None, 3072}
        assert model in {None, "text-embedding-3-large"}
        return {"status": "green"}

    def get_point(self, point_id: str) -> PointState | None:
        payload = self.points.get(point_id)
        return PointState(point_id, dict(payload)) if payload is not None else None

    def upsert(self, rows: list[VectorRow], vectors: list[list[float]]) -> None:
        assert len(rows) == len(vectors)
        self.upsert_calls += 1
        for row in rows:
            self.points[row.point_id] = dict(row.payload())

    def set_payload(self, point_id: str, patch: dict[str, object]) -> None:
        self.payload_calls += 1
        self.points[point_id].update(patch)

    def retrieve_points(self, point_ids: list[str]) -> dict[str, PointState]:
        return {
            point_id: PointState(point_id, dict(self.points[point_id]))
            for point_id in point_ids
            if point_id in self.points
        }

    def iter_point_batches(self) -> list[list[PointState]]:
        return [[PointState(point_id, dict(payload)) for point_id, payload in self.points.items()]]


def test_missing_configuration_fails_before_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_nightly", lambda _: pytest.fail("side effect dispatch occurred"))
    assert cli.main(["nightly"], environ={}) == cli.EXIT_CONFIG


def test_checkpoint_preflight_validates_format_without_writing(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    store = CheckpointStore(path, datetime(2026, 1, 1, tzinfo=UTC))
    assert store.validate() == {"format_version": 1, "state": "not_created"}
    assert not path.exists()
    path.write_text('{"version": 2, "last_successful_end": "2026-01-02T00:00:00Z"}\n')
    with pytest.raises(CheckpointError, match="invalid checkpoint"):
        store.validate()


def test_secret_values_are_redacted_from_settings_repr(tmp_path) -> None:
    private_dsn = "postgresql://db.example.invalid/production_db"
    env = {
        "PISRS_DATABASE_DSN": private_dsn,
        "PISRS_EXPECTED_DATABASE": "production_db",
        "PISRS_QDRANT_URL": "https://qdrant.example.invalid",
        "PISRS_QDRANT_COLLECTION": "pisrs_current",
        "PISRS_LOCK_PATH": str(tmp_path / "ingest.lock"),
        "PISRS_ALLOW_EXTERNAL_API": "0",
        "PISRS_ALLOW_WRITES": "0",
        "PISRS_RECONCILE_MAX_CHANGES": "100",
    }
    settings = load_settings("reconcile", env)
    assert private_dsn not in repr(settings)
    with pytest.raises(ConfigError, match="PISRS_EXPECTED_DATABASE"):
        load_settings(
            "reconcile",
            {key: value for key, value in env.items() if key != "PISRS_EXPECTED_DATABASE"},
        )
    with pytest.raises(ConfigError, match="does not match"):
        load_settings("reconcile", {**env, "PISRS_EXPECTED_DATABASE": "other_database"})
    with pytest.raises(ConfigError):
        load_settings("reconcile", {**env, "PISRS_QDRANT_COLLECTION": "other"})


def nightly_env(tmp_path) -> dict[str, str]:
    return {
        "PISRS_DATABASE_DSN": "postgresql://db.example.invalid/production_db",
        "PISRS_EXPECTED_DATABASE": "production_db",
        "PISRS_QDRANT_URL": "https://qdrant.example.invalid",
        "PISRS_QDRANT_COLLECTION": "pisrs_current",
        "PISRS_LOCK_PATH": str(tmp_path / "ingest.lock"),
        "PISRS_ALLOW_EXTERNAL_API": "0",
        "PISRS_ALLOW_WRITES": "0",
        "PISRS_RECONCILE_MAX_CHANGES": "10",
        "PISRS_PORTAL_BASE_URL": "https://pisrs.example.invalid/extapi",
        "PISRS_API_TOKEN": "placeholder",
        "OPENAI_API_KEY": "placeholder",
        "OPENAI_BASE_URL": "https://embedding.example.invalid/v1",
        "PISRS_EMBEDDING_MODEL": "text-embedding-3-large",
        "PISRS_EMBEDDING_DIMENSIONS": "3072",
        "PISRS_CHECKPOINT_PATH": str(tmp_path / "checkpoint.json"),
        "PISRS_INITIAL_SINCE": "2026-01-01T00:00:00Z",
        "PISRS_MAX_DOCUMENTS_PER_RUN": "10",
        "PISRS_EMBED_BATCH_SIZE": "5",
        "PISRS_MAX_EMBEDDING_INPUT_BYTES_PER_RUN": "100",
    }


def test_embedding_input_cap_is_required_and_positive(tmp_path) -> None:
    env = nightly_env(tmp_path)
    with pytest.raises(ConfigError, match="PISRS_MAX_EMBEDDING_INPUT_BYTES_PER_RUN"):
        load_settings("nightly", {k: v for k, v in env.items() if "MAX_EMBEDDING" not in k})
    for value in ("invalid", "0", "-1"):
        with pytest.raises(ConfigError, match="PISRS_MAX_EMBEDDING_INPUT_BYTES_PER_RUN"):
            load_settings("nightly", {**env, "PISRS_MAX_EMBEDDING_INPUT_BYTES_PER_RUN": value})


def test_embedding_model_is_pinned_for_existing_collection(tmp_path) -> None:
    env = {**nightly_env(tmp_path), "PISRS_EMBEDDING_MODEL": "other-model"}
    with pytest.raises(ConfigError, match="full reindex"):
        load_settings("preflight", env)


def test_production_point_identity_and_content_hash_golden() -> None:
    assert qdrant_point_id("pisrs_current", 9015630, 1) == "c51a1f3b-fe1a-5ad4-ab8a-6321d8d8c892"
    assert canonical_content_hash("A B") == (
        "fea4c5ce720c1d6a1cbc47c1607cc4ea172a69de8948e76d67910120597950fc"
    )


def test_chunking_is_deterministic() -> None:
    parsed = parse_html(
        "<html><title>Fixture</title><body><div class='mainText'>"
        "<p class='clen'>1. člen</p><p class='odstavek'>A   B</p>"
        "</div></body></html>"
    )
    assert make_chunks(parsed.blocks) == make_chunks(parsed.blocks)
    assert make_chunks(parsed.blocks)[0].chunk_text == "[1. člen] 1. člen [paragraph] A B"


def test_unknown_version_label_fails_closed() -> None:
    assert version_rank("osnovno") == 0
    assert version_rank("npb02") == 2
    with pytest.raises(SourceInvariantError):
        version_rank("draft")


def test_flag_only_rollover_reconciles_without_embedding() -> None:
    old = vector_row(active=False, latest=False, text_id=100)
    new = vector_row(active=True, latest=True, text_id=101)
    qdrant = FakeQdrant([old, new])
    qdrant.points[old.point_id]["is_active"] = True
    qdrant.points[old.point_id]["is_latest_for_sop"] = True
    embedder = FakeEmbedder()
    checkpoint = FakeCheckpoint()
    run_nightly(
        client=FakeClient(),
        postgres=FakePostgres([old, new]),
        embedder=embedder,
        qdrant=qdrant,
        checkpoint=checkpoint,
        model="text-embedding-3-large",
        dimensions=3072,
        max_documents=10,
        embed_batch_size=5,
        max_embedding_input_bytes=100,
        now=checkpoint.end,
    )
    assert embedder.calls == 0
    assert qdrant.points[old.point_id]["is_active"] is False
    assert qdrant.points[old.point_id]["is_latest_for_sop"] is False
    assert checkpoint.advanced == [checkpoint.end]


def moved_sop_rows() -> tuple[VectorRow, VectorRow]:
    stale = replace(
        vector_row(active=False, latest=False, text_id=150),
        sop="A",
        sop_from_docno="A",
        npb_label="npb01",
    )
    final = replace(
        stale,
        sop="B",
        sop_from_docno="B",
        npb_label="npb02",
        is_active=True,
        is_latest_for_sop=True,
    )
    return stale, final


def test_multi_sop_rollover_indexes_only_final_postgres_state() -> None:
    stale, final = moved_sop_rows()
    postgres = FakePostgres([final], rollover_rows={"A": [stale], "B": [final]})
    qdrant = FakeQdrant()
    embedder = FakeEmbedder()
    checkpoint = FakeCheckpoint()
    run_nightly(
        client=FakeClient(),
        postgres=postgres,
        embedder=embedder,
        qdrant=qdrant,
        checkpoint=checkpoint,
        model="text-embedding-3-large",
        dimensions=3072,
        max_documents=10,
        embed_batch_size=5,
        max_embedding_input_bytes=100,
        now=checkpoint.end,
    )
    payload = qdrant.points[final.point_id]
    assert (payload["sop_from_docno"], payload["npb_label"]) == ("B", "npb02")
    assert (payload["is_active"], payload["is_latest_for_sop"]) == (True, True)
    assert postgres.refreshed_point_ids == {final.point_id}
    assert postgres.marked == [final.point_id]
    assert embedder.calls == qdrant.upsert_calls == 1
    assert qdrant.payload_calls == 0
    assert checkpoint.advanced == [checkpoint.end]


def test_missing_final_rollover_row_fails_before_vector_io() -> None:
    stale, final = moved_sop_rows()
    postgres = FakePostgres([], rollover_rows={"A": [stale], "B": [final]})
    qdrant = FakeQdrant()
    embedder = FakeEmbedder()
    checkpoint = FakeCheckpoint()
    with pytest.raises(PipelineError, match="exactly one final row"):
        run_nightly(
            client=FakeClient(),
            postgres=postgres,
            embedder=embedder,
            qdrant=qdrant,
            checkpoint=checkpoint,
            model="text-embedding-3-large",
            dimensions=3072,
            max_documents=10,
            embed_batch_size=5,
            max_embedding_input_bytes=100,
            now=checkpoint.end,
        )
    assert embedder.calls == qdrant.validate_calls == 0
    assert qdrant.upsert_calls == qdrant.payload_calls == 0
    assert checkpoint.advanced == []


@pytest.mark.parametrize(("cap_offset", "blocked"), [(1, False), (0, False), (-1, True)])
def test_embedding_input_byte_cap_boundary(cap_offset: int, blocked: bool) -> None:
    row = replace(
        vector_row(active=True, latest=True, text_id=180),
        chunk_text="é",
        chunk_text_len=1,
        content_hash=canonical_content_hash("é"),
    )
    reusable = vector_row(active=True, latest=True, text_id=182)
    postgres = FakePostgres([row, reusable])
    qdrant = FakeQdrant([reusable])
    qdrant.points[reusable.point_id]["title"] = "stale payload"
    embedder = FakeEmbedder()
    checkpoint = FakeCheckpoint()
    arguments = {
        "client": FakeClient(),
        "postgres": postgres,
        "embedder": embedder,
        "qdrant": qdrant,
        "checkpoint": checkpoint,
        "model": "text-embedding-3-large",
        "dimensions": 3072,
        "max_documents": 10,
        "embed_batch_size": 5,
        "max_embedding_input_bytes": len(row.chunk_text.encode("utf-8")) + cap_offset,
        "now": checkpoint.end,
    }
    if blocked:
        with pytest.raises(PipelineError, match="PISRS_MAX_EMBEDDING_INPUT_BYTES_PER_RUN"):
            run_nightly(**arguments)
        assert embedder.calls == qdrant.upsert_calls == qdrant.payload_calls == 0
        assert postgres.marked == [] and checkpoint.advanced == []
    else:
        run_nightly(**arguments)
        assert embedder.calls == qdrant.upsert_calls == qdrant.payload_calls == 1
        assert checkpoint.advanced == [checkpoint.end]


def test_reused_vector_consumes_zero_embedding_input_bytes() -> None:
    row = vector_row(active=True, latest=True, text_id=181)
    checkpoint = FakeCheckpoint()
    embedder = FakeEmbedder()
    qdrant = FakeQdrant([row])
    stats = run_nightly(
        client=FakeClient(),
        postgres=FakePostgres([row]),
        embedder=embedder,
        qdrant=qdrant,
        checkpoint=checkpoint,
        model="text-embedding-3-large",
        dimensions=3072,
        max_documents=10,
        embed_batch_size=5,
        max_embedding_input_bytes=1,
        now=checkpoint.end,
    )
    assert stats.vectors_reused == 1
    assert embedder.calls == qdrant.upsert_calls == qdrant.payload_calls == 0
    assert checkpoint.advanced == [checkpoint.end]


def test_partial_failure_keeps_checkpoint_and_retry_reuses_vector() -> None:
    row = vector_row(active=True, latest=True, text_id=200)
    postgres = FakePostgres([row], fail_mark_once=True)
    qdrant = FakeQdrant()
    embedder = FakeEmbedder()
    checkpoint = FakeCheckpoint()
    arguments = {
        "client": FakeClient(),
        "postgres": postgres,
        "embedder": embedder,
        "qdrant": qdrant,
        "checkpoint": checkpoint,
        "model": "text-embedding-3-large",
        "dimensions": 3072,
        "max_documents": 10,
        "embed_batch_size": 5,
        "max_embedding_input_bytes": 100,
        "now": checkpoint.end,
    }
    with pytest.raises(RuntimeError, match="simulated PostgreSQL failure"):
        run_nightly(**arguments)
    assert checkpoint.advanced == []
    assert embedder.calls == 1

    run_nightly(**arguments)
    assert embedder.calls == 1
    assert qdrant.upsert_calls == 1
    assert len(qdrant.points) == 1
    assert checkpoint.advanced == [checkpoint.end]


class DocumentClient(FakeClient):
    def __init__(self) -> None:
        self.fail_first = True

    def fetch_text(self, text_id: int) -> str:
        if text_id == 1 and self.fail_first:
            raise ValueError("fixture permanent document error")
        return "<html><body><p class='odstavek'>safe fixture</p></body></html>"


class DocumentRunPostgres:
    def __init__(self) -> None:
        self.documents_list = [
            NpbDocument(1, None, None, "2026-01-0001", "2026-01-0001", "osnovno", {}),
            NpbDocument(2, None, None, "2026-01-0002", "2026-01-0002", "osnovno", {}),
        ]
        self.persisted: set[int] = set()
        self.catalogs = SimpleNamespace(synchronize=lambda acts, npbs: None)
        self.documents = SimpleNamespace(pending=self.pending, synchronize=self.synchronize)
        self.chunks = SimpleNamespace(
            touched_sops=lambda since: [],
            prepare_rollover=lambda sop, model, dimensions: [],
            mark_uploaded=lambda rows: None,
        )

    def pending(self, limit: int, since: datetime) -> list[NpbDocument]:
        return self.documents_list

    def synchronize(self, document: NpbDocument, parsed: object, source_url: str) -> None:
        self.persisted.add(document.text_id)


def test_document_failure_continues_then_fails_and_repeats_interval() -> None:
    client = DocumentClient()
    postgres = DocumentRunPostgres()
    checkpoint = FakeCheckpoint()
    arguments = {
        "client": client,
        "postgres": postgres,
        "embedder": FakeEmbedder(),
        "qdrant": FakeQdrant(),
        "checkpoint": checkpoint,
        "model": "text-embedding-3-large",
        "dimensions": 3072,
        "max_documents": 2,
        "embed_batch_size": 2,
        "max_embedding_input_bytes": 100,
        "now": checkpoint.end,
    }
    with pytest.raises(DocumentBatchError) as failure:
        run_nightly(**arguments)
    assert [(item.text_id, item.phase) for item in failure.value.failures] == [(1, "fetch")]
    assert postgres.persisted == {2}
    assert checkpoint.advanced == []

    client.fail_first = False
    run_nightly(**arguments)
    assert postgres.persisted == {1, 2}
    assert checkpoint.advanced == [checkpoint.end]


def test_document_batch_failure_returns_nonzero_exit(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = SimpleNamespace(
        allow_external_api=True,
        allow_writes=True,
        lock_path=tmp_path / "ingest.lock",
    )
    monkeypatch.setattr(cli, "load_settings", lambda command, environ: settings)

    def fail(_: object) -> int:
        raise DocumentBatchError([SimpleNamespace(text_id=1, phase="fetch")])

    monkeypatch.setattr(cli, "_nightly", fail)
    assert cli.main(["nightly"], environ={}) == cli.EXIT_RECONCILE_BLOCKED


def test_second_lock_owner_is_rejected(tmp_path) -> None:
    path = tmp_path / "ingest.lock"
    with ApplicationLock(path), pytest.raises(LockBusyError), ApplicationLock(path):
        pass


def test_application_lock_interoperates_with_fcntl_flock(tmp_path) -> None:
    path = tmp_path / "dual-ingest.lock"
    with path.open("a+", encoding="utf-8") as shell_equivalent:
        fcntl.flock(shell_equivalent.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(LockBusyError), ApplicationLock(path):
            pass


def test_second_nightly_returns_documented_lock_exit(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "ingest.lock"
    env = {
        **nightly_env(tmp_path),
        "PISRS_LOCK_PATH": str(lock_path),
        "PISRS_ALLOW_EXTERNAL_API": "1",
        "PISRS_ALLOW_WRITES": "1",
    }
    monkeypatch.setattr(cli, "_nightly", lambda _: pytest.fail("nightly dispatch occurred"))
    with ApplicationLock(lock_path):
        assert cli.main(["nightly"], environ=env) == cli.EXIT_LOCK_BUSY


@dataclass
class FakeResponse:
    status_code: int

    def close(self) -> None:
        pass


class FakeSession:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def request(self, *args, **kwargs):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_transient_network_error_has_bounded_retry() -> None:
    session = FakeSession([requests.Timeout(), FakeResponse(200)])
    sleeps: list[float] = []
    client = HttpClient(
        session=session,
        policy=RetryPolicy(max_attempts=3, initial_backoff=0.25, max_backoff=1),
        sleep=sleeps.append,
    )
    assert client.request("GET", "https://example.invalid").status_code == 200
    assert session.calls == 2
    assert sleeps == [0.25]


def test_connection_error_retry_is_structured_and_bounded(caplog) -> None:
    session = FakeSession([requests.ConnectionError(), FakeResponse(200)])
    sleeps: list[float] = []
    client = HttpClient(session=session, sleep=sleeps.append)
    with caplog.at_level("WARNING"):
        assert (
            client.request(
                "GET",
                "https://example.invalid/private/path?credential=hidden",
                phase="act_discovery",
            ).status_code
            == 200
        )
    record = caplog.records[-1].message
    assert '"classification": "connection_error"' in record
    assert '"phase": "act_discovery"' in record
    assert '"request_path": "/private/path"' in record
    assert "credential" not in record


def test_connection_error_exhaustion_propagates_after_four_attempts() -> None:
    error = requests.ConnectionError("remote disconnected")
    session = FakeSession([error, error, error, error])
    client = HttpClient(session=session, sleep=lambda _: None)
    with pytest.raises(requests.ConnectionError, match="remote disconnected"):
        client.request("GET", "https://example.invalid/acts", phase="act_discovery")
    assert session.calls == 4


class DiscoveryFailureClient(FakeClient):
    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def discover_acts(self) -> list[object]:
        self.http.request("GET", "https://example.invalid/acts", phase="act_discovery")
        return []


def test_retry_exhaustion_leaves_checkpoint_unchanged() -> None:
    error = requests.ConnectionError("remote disconnected")
    session = FakeSession([error, error, error, error])
    checkpoint = FakeCheckpoint()
    with pytest.raises(requests.ConnectionError):
        run_nightly(
            client=DiscoveryFailureClient(HttpClient(session=session, sleep=lambda _: None)),
            postgres=FakePostgres([]),
            embedder=FakeEmbedder(),
            qdrant=FakeQdrant(),
            checkpoint=checkpoint,
            model="text-embedding-3-large",
            dimensions=3072,
            max_documents=1,
            embed_batch_size=1,
            max_embedding_input_bytes=100,
            now=checkpoint.end,
        )
    assert checkpoint.advanced == []


def test_permanent_error_is_not_retried() -> None:
    session = FakeSession([FakeResponse(401), FakeResponse(200)])
    sleeps: list[float] = []
    client = HttpClient(session=session, sleep=sleeps.append)
    with pytest.raises(HttpError):
        client.request("GET", "https://example.invalid")
    assert session.calls == 1
    assert sleeps == []


def test_reconciliation_is_payload_only_and_idempotent() -> None:
    row = vector_row(active=False, latest=False, text_id=300)
    postgres = FakePostgres([row])
    qdrant = FakeQdrant([row])
    qdrant.points[row.point_id]["is_active"] = True
    first = plan_reconciliation(postgres, qdrant, max_changes=10)
    assert first.change_count == 1
    assert first.changes[0].patch == {"is_active": False}
    apply_reconciliation(first, qdrant)
    second = plan_reconciliation(postgres, qdrant, max_changes=10)
    assert second.change_count == 0
    assert qdrant.upsert_calls == 0


@pytest.mark.parametrize(
    ("key", "wrong_value"),
    [("is_active", 1), ("embedding_dimensions", 3072.0)],
)
def test_payload_comparison_is_type_strict(key: str, wrong_value: object) -> None:
    expected = vector_row(active=True, latest=True, text_id=350).payload()
    actual = dict(expected)
    actual[key] = wrong_value
    assert payload_patch(expected, actual) == {key: expected[key]}
    del actual[key]
    assert payload_patch(expected, actual) == {key: expected[key]}
    assert payload_patch(expected, dict(expected)) == {}


def test_unexpected_payload_key_blocks_apply_before_writes() -> None:
    row = vector_row(active=True, latest=True, text_id=351)
    safe_drift = vector_row(active=False, latest=False, text_id=352)
    qdrant = FakeQdrant([safe_drift, row])
    qdrant.points[safe_drift.point_id]["is_active"] = True
    qdrant.points[row.point_id]["legacy_field"] = "retained"
    plan = plan_reconciliation(FakePostgres([safe_drift, row]), qdrant, max_changes=10)
    assert plan.change_count == 1
    assert plan.unsafe_payload_count == 1
    assert plan.unsafe_payload_examples == [row.point_id]
    with pytest.raises(PipelineError, match="unexpected payload keys"):
        apply_reconciliation(plan, qdrant)
    assert qdrant.payload_calls == 0
    with pytest.raises(QdrantInvariantError, match="separate explicitly approved"):
        payload_patch(row.payload(), qdrant.points[row.point_id])


def test_orphan_is_planned_for_flag_only_deactivation_and_converges() -> None:
    row = vector_row(active=True, latest=True, text_id=400)
    postgres = FakePostgres([row])
    qdrant = FakeQdrant([row])
    orphan_id = qdrant_point_id("pisrs_current", 401, 0)
    qdrant.points[orphan_id] = {
        "source": "pisrs",
        "collection_name": "pisrs_current",
        "text_id": 401,
        "chunk_index": 0,
        "is_active": True,
        "is_latest_for_sop": True,
    }
    first = plan_reconciliation(postgres, qdrant, max_changes=10)
    orphan_change = next(change for change in first.changes if change.point_id == orphan_id)
    assert first.orphan_count == 1
    assert orphan_change.reason == "orphan_deactivation"
    assert orphan_change.patch == {"is_active": False, "is_latest_for_sop": False}
    apply_reconciliation(first, qdrant)
    second = plan_reconciliation(postgres, qdrant, max_changes=10)
    assert second.orphan_count == 1
    assert second.change_count == 0


def test_unproven_orphan_identity_blocks_apply_before_writes() -> None:
    valid_id = qdrant_point_id("pisrs_current", 401, 0)
    safe_id = qdrant_point_id("pisrs_current", 402, 0)
    mismatched_id = qdrant_point_id("pisrs_current", 403, 0)
    payload = {
        "source": "pisrs",
        "collection_name": "pisrs_current",
        "text_id": True,
        "chunk_index": 0,
        "is_active": True,
        "is_latest_for_sop": True,
    }
    qdrant = FakeQdrant()
    qdrant.points[valid_id] = payload
    qdrant.points[safe_id] = {**payload, "text_id": 402}
    qdrant.points[mismatched_id] = {**payload, "text_id": 401}
    plan = plan_reconciliation(FakePostgres([]), qdrant, max_changes=10)
    assert plan.unsafe_point_count == 2
    assert plan.change_count == 1
    with pytest.raises(PipelineError, match="provable PISRS payload identity"):
        apply_reconciliation(plan, qdrant)
    assert qdrant.payload_calls == 0


def test_missing_point_prevents_any_payload_apply() -> None:
    row = vector_row(active=True, latest=True, text_id=500)
    qdrant = FakeQdrant()
    plan = plan_reconciliation(FakePostgres([row]), qdrant, max_changes=10)
    assert plan.missing_count == 1
    with pytest.raises(PipelineError, match="missing from Qdrant"):
        apply_reconciliation(plan, qdrant)
    assert qdrant.payload_calls == 0
