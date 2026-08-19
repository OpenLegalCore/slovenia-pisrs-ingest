"""The single manual and scheduled command surface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime

from .checkpoint import CheckpointError, CheckpointStore
from .client import PisrsClient
from .config import (
    ConfigError,
    Settings,
    load_settings,
    require_external,
    require_writes,
    validate_runtime_paths,
)
from .embeddings import EmbeddingClient
from .locking import ApplicationLock, LockBusyError
from .models import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
from .pipeline import PipelineError, apply_reconciliation, plan_reconciliation, run_nightly
from .postgres import PostgresBoundary
from .qdrant import QdrantStore

EXIT_ERROR = 1
EXIT_CONFIG = 2
EXIT_RECONCILE_BLOCKED = 3
EXIT_LOCK_BUSY = 75


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="pisrs-ingest")
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("preflight", help="read-only configuration and service contract check")
    subcommands.add_parser("nightly", help="run one checkpointed ingest interval")
    reconcile = subcommands.add_parser("reconcile", help="compare or repair Qdrant payload only")
    mode = reconcile.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="report changes without writes")
    mode.add_argument("--apply", action="store_true", help="apply payload-only changes")
    return result


def main(argv: Iterable[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    args = parser().parse_args(list(argv) if argv is not None else None)
    config_command = args.command
    try:
        settings = load_settings(config_command, environ)
        if args.command == "preflight":
            return _preflight(settings)
        if args.command == "nightly":
            require_external(settings)
            require_writes(settings)
            with ApplicationLock(settings.lock_path):
                return _nightly(settings)
        if args.apply:
            require_writes(settings)
            with ApplicationLock(settings.lock_path):
                return _reconcile(settings, apply=True)
        return _reconcile(settings, apply=False)
    except LockBusyError as exc:
        print(f"lock busy: {exc}", file=sys.stderr)
        return EXIT_LOCK_BUSY
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except (CheckpointError, PipelineError) as exc:
        print(f"operation blocked: {exc}", file=sys.stderr)
        return EXIT_RECONCILE_BLOCKED
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR


def _preflight(settings: Settings) -> int:
    assert settings.embedding_model is not None
    assert settings.embedding_dimensions is not None
    assert settings.checkpoint_path is not None
    assert settings.initial_since is not None
    paths = validate_runtime_paths(settings)
    checkpoint = CheckpointStore(settings.checkpoint_path, settings.initial_since).validate()
    postgres = PostgresBoundary.create(settings.database_dsn, settings.collection)
    qdrant = QdrantStore(settings.qdrant_url, settings.collection)
    pg_result = postgres.database.preflight(
        settings.collection,
        settings.embedding_model,
        settings.embedding_dimensions,
        expected_database=settings.expected_database,
    )
    collection = qdrant.validate_collection(settings.embedding_dimensions, settings.embedding_model)
    portal = "skipped_by_policy"
    if settings.allow_external_api:
        assert settings.portal_base_url is not None and settings.portal_token is not None
        PisrsClient(settings.portal_base_url, settings.portal_token).probe()
        portal = "read_only_get_ok"
    print(
        json.dumps(
            {
                "status": "ok",
                "postgres": pg_result,
                "qdrant": {
                    "status": collection.get("status"),
                    "points_count": collection.get("points_count"),
                },
                "pisrs": portal,
                "paths": paths,
                "checkpoint": checkpoint,
                "writes": 0,
                "embedding_calls": 0,
            },
            sort_keys=True,
        )
    )
    return 0


def _nightly(settings: Settings) -> int:
    required = (
        settings.portal_base_url,
        settings.portal_token,
        settings.openai_api_key,
        settings.openai_base_url,
        settings.embedding_model,
        settings.embedding_dimensions,
        settings.checkpoint_path,
        settings.initial_since,
        settings.max_documents_per_run,
        settings.embed_batch_size,
        settings.max_embedding_input_bytes_per_run,
    )
    assert all(value is not None for value in required)
    checkpoint = CheckpointStore(settings.checkpoint_path, settings.initial_since)
    interval = checkpoint.interval(datetime.now(UTC))
    postgres = PostgresBoundary.create(settings.database_dsn, settings.collection)
    qdrant = QdrantStore(settings.qdrant_url, settings.collection)
    postgres.database.preflight(
        settings.collection,
        settings.embedding_model,
        settings.embedding_dimensions,
        expected_database=settings.expected_database,
    )
    qdrant.validate_collection(settings.embedding_dimensions, settings.embedding_model)
    client = PisrsClient(settings.portal_base_url, settings.portal_token)
    embedder = EmbeddingClient(
        settings.openai_base_url,
        settings.openai_api_key,
        settings.embedding_model,
        settings.embedding_dimensions,
    )
    stats = run_nightly(
        client=client,
        postgres=postgres,
        embedder=embedder,
        qdrant=qdrant,
        checkpoint=checkpoint,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        max_documents=settings.max_documents_per_run,
        embed_batch_size=settings.embed_batch_size,
        max_embedding_input_bytes=settings.max_embedding_input_bytes_per_run,
        interval=interval,
    )
    print(json.dumps(asdict(stats), sort_keys=True))
    return 0


def _reconcile(settings: Settings, *, apply: bool) -> int:
    postgres = PostgresBoundary.create(settings.database_dsn, settings.collection)
    qdrant = QdrantStore(settings.qdrant_url, settings.collection)
    postgres.database.preflight(
        settings.collection,
        EMBEDDING_MODEL,
        EMBEDDING_DIMENSIONS,
        expected_database=settings.expected_database,
    )
    plan = plan_reconciliation(postgres, qdrant, settings.reconcile_max_changes)
    summary = {"mode": "apply" if apply else "dry-run", **plan.summary()}
    if apply:
        apply_reconciliation(plan, qdrant)
        summary["applied"] = plan.change_count
    else:
        summary["applied"] = 0
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
