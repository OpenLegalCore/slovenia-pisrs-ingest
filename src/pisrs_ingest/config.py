"""Fail-closed environment configuration."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .models import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL


class ConfigError(RuntimeError):
    """Raised before I/O when required configuration is absent or unsafe."""


BASE_REQUIRED = (
    "PISRS_DATABASE_DSN",
    "PISRS_EXPECTED_DATABASE",
    "PISRS_QDRANT_URL",
    "PISRS_QDRANT_COLLECTION",
    "PISRS_LOCK_PATH",
    "PISRS_ALLOW_EXTERNAL_API",
    "PISRS_ALLOW_WRITES",
    "PISRS_RECONCILE_MAX_CHANGES",
)

NIGHTLY_REQUIRED = BASE_REQUIRED + (
    "PISRS_PORTAL_BASE_URL",
    "PISRS_API_TOKEN",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "PISRS_EMBEDDING_MODEL",
    "PISRS_EMBEDDING_DIMENSIONS",
    "PISRS_CHECKPOINT_PATH",
    "PISRS_INITIAL_SINCE",
    "PISRS_MAX_DOCUMENTS_PER_RUN",
    "PISRS_EMBED_BATCH_SIZE",
    "PISRS_MAX_EMBEDDING_INPUT_BYTES_PER_RUN",
)


@dataclass(frozen=True)
class Settings:
    database_dsn: str = field(repr=False)
    expected_database: str
    qdrant_url: str
    collection: str
    lock_path: Path
    allow_external_api: bool
    allow_writes: bool
    reconcile_max_changes: int
    portal_base_url: str | None = None
    portal_token: str | None = field(default=None, repr=False)
    openai_api_key: str | None = field(default=None, repr=False)
    openai_base_url: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    checkpoint_path: Path | None = None
    initial_since: datetime | None = None
    max_documents_per_run: int | None = None
    embed_batch_size: int | None = None
    max_embedding_input_bytes_per_run: int | None = None


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"required configuration is missing: {name}")
    return value


def _flag(value: str, name: str) -> bool:
    if value not in {"0", "1"}:
        raise ConfigError(f"{name} must be 0 or 1")
    return value == "1"


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be greater than zero")
    return parsed


def _absolute_path(value: str, name: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ConfigError(f"{name} must be an absolute path")
    return path


def _url(value: str, name: str, *, https_only: bool) -> str:
    parsed = urlsplit(value)
    allowed = {"https"} if https_only else {"http", "https"}
    if parsed.scheme not in allowed or not parsed.hostname or parsed.username or parsed.password:
        scheme = "HTTPS" if https_only else "HTTP(S)"
        raise ConfigError(f"{name} must be a credential-free {scheme} URL")
    if parsed.query or parsed.fragment:
        raise ConfigError(f"{name} must not contain a query or fragment")
    return value.rstrip("/")


DATABASE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\Z")


def _dsn(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise ConfigError("PISRS_DATABASE_DSN must be a PostgreSQL DSN with a host")
    database = unquote(parsed.path.removeprefix("/"))
    if not database or "/" in database:
        raise ConfigError("PISRS_DATABASE_DSN must identify a database")
    return value, database


def _database_name(value: str) -> str:
    if not DATABASE_NAME_PATTERN.fullmatch(value):
        raise ConfigError("PISRS_EXPECTED_DATABASE must be a credential-free database name")
    return value


def _timestamp(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ConfigError(f"{name} must include a timezone")
    return parsed


def load_settings(command: str, environ: Mapping[str, str] | None = None) -> Settings:
    """Load and validate every value needed by *command* before any adapter is opened."""

    source = os.environ if environ is None else environ
    required = NIGHTLY_REQUIRED if command in {"nightly", "preflight"} else BASE_REQUIRED
    values = {name: _required(source, name) for name in required}

    collection = values["PISRS_QDRANT_COLLECTION"]
    if collection != "pisrs_current":
        raise ConfigError("PISRS_QDRANT_COLLECTION must preserve the pisrs_current contract")

    database_dsn, dsn_database = _dsn(values["PISRS_DATABASE_DSN"])
    expected_database = _database_name(values["PISRS_EXPECTED_DATABASE"])
    if dsn_database != expected_database:
        raise ConfigError("PISRS_DATABASE_DSN database does not match PISRS_EXPECTED_DATABASE")

    settings = Settings(
        database_dsn=database_dsn,
        expected_database=expected_database,
        qdrant_url=_url(values["PISRS_QDRANT_URL"], "PISRS_QDRANT_URL", https_only=False),
        collection=collection,
        lock_path=_absolute_path(values["PISRS_LOCK_PATH"], "PISRS_LOCK_PATH"),
        allow_external_api=_flag(values["PISRS_ALLOW_EXTERNAL_API"], "PISRS_ALLOW_EXTERNAL_API"),
        allow_writes=_flag(values["PISRS_ALLOW_WRITES"], "PISRS_ALLOW_WRITES"),
        reconcile_max_changes=_positive_int(
            values["PISRS_RECONCILE_MAX_CHANGES"], "PISRS_RECONCILE_MAX_CHANGES"
        ),
    )

    if command == "preflight" and settings.allow_writes:
        raise ConfigError("preflight requires PISRS_ALLOW_WRITES=0")

    if command not in {"nightly", "preflight"}:
        return settings

    dimensions = _positive_int(values["PISRS_EMBEDDING_DIMENSIONS"], "PISRS_EMBEDDING_DIMENSIONS")
    if dimensions != EMBEDDING_DIMENSIONS:
        raise ConfigError(
            f"PISRS_EMBEDDING_DIMENSIONS must preserve the {EMBEDDING_DIMENSIONS} contract"
        )
    if values["PISRS_EMBEDDING_MODEL"] != EMBEDDING_MODEL:
        raise ConfigError(
            f"PISRS_EMBEDDING_MODEL must be {EMBEDDING_MODEL}; changes require full reindex"
        )

    return Settings(
        **{
            name: getattr(settings, name)
            for name in settings.__dataclass_fields__
            if name
            not in {
                "portal_base_url",
                "portal_token",
                "openai_api_key",
                "openai_base_url",
                "embedding_model",
                "embedding_dimensions",
                "checkpoint_path",
                "initial_since",
                "max_documents_per_run",
                "embed_batch_size",
                "max_embedding_input_bytes_per_run",
            }
        },
        portal_base_url=_url(
            values["PISRS_PORTAL_BASE_URL"], "PISRS_PORTAL_BASE_URL", https_only=True
        ),
        portal_token=values["PISRS_API_TOKEN"],
        openai_api_key=values["OPENAI_API_KEY"],
        openai_base_url=_url(values["OPENAI_BASE_URL"], "OPENAI_BASE_URL", https_only=True),
        embedding_model=values["PISRS_EMBEDDING_MODEL"],
        embedding_dimensions=dimensions,
        checkpoint_path=_absolute_path(values["PISRS_CHECKPOINT_PATH"], "PISRS_CHECKPOINT_PATH"),
        initial_since=_timestamp(values["PISRS_INITIAL_SINCE"], "PISRS_INITIAL_SINCE"),
        max_documents_per_run=_positive_int(
            values["PISRS_MAX_DOCUMENTS_PER_RUN"], "PISRS_MAX_DOCUMENTS_PER_RUN"
        ),
        embed_batch_size=_positive_int(values["PISRS_EMBED_BATCH_SIZE"], "PISRS_EMBED_BATCH_SIZE"),
        max_embedding_input_bytes_per_run=_positive_int(
            values["PISRS_MAX_EMBEDDING_INPUT_BYTES_PER_RUN"],
            "PISRS_MAX_EMBEDDING_INPUT_BYTES_PER_RUN",
        ),
    )


def require_external(settings: Settings) -> None:
    if not settings.allow_external_api:
        raise ConfigError("PISRS_ALLOW_EXTERNAL_API=1 is required for nightly")


def require_writes(settings: Settings) -> None:
    if not settings.allow_writes:
        raise ConfigError("PISRS_ALLOW_WRITES=1 is required for this mutating command")


def validate_runtime_paths(settings: Settings) -> dict[str, str]:
    """Read-only validation of directories/files needed by locking and checkpoint writes."""

    paths = {"lock": settings.lock_path}
    if settings.checkpoint_path is not None:
        paths["checkpoint"] = settings.checkpoint_path
    for name, path in paths.items():
        parent = path.parent
        if not parent.is_dir():
            raise ConfigError(f"{name} parent directory does not exist: {parent}")
        if not os.access(parent, os.W_OK | os.X_OK):
            raise ConfigError(f"{name} parent directory is not writable: {parent}")
        if path.exists() and (not path.is_file() or not os.access(path, os.R_OK)):
            raise ConfigError(f"{name} path is not a readable regular file: {path}")
    return {name: "ok" for name in paths}
