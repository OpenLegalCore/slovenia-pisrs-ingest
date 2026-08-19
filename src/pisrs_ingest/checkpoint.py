"""Atomic file checkpoint representing the last fully successful interval."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class CheckpointError(RuntimeError):
    """Raised when checkpoint state is malformed or cannot advance safely."""


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime


class CheckpointStore:
    def __init__(self, path: Path, initial_since: datetime) -> None:
        self.path = path
        self.initial_since = initial_since.astimezone(UTC)

    def interval(self, end: datetime) -> Interval:
        end = end.astimezone(UTC).replace(microsecond=0)
        start = self._load()
        if end <= start:
            raise CheckpointError("interval end must be later than the last successful checkpoint")
        return Interval(start=start, end=end)

    def validate(self) -> dict[str, object]:
        """Validate an existing checkpoint without creating or changing any file."""

        if not self.path.exists():
            return {"format_version": 1, "state": "not_created"}
        value = self._load()
        return {
            "format_version": 1,
            "state": "valid",
            "last_successful_end": value.isoformat().replace("+00:00", "Z"),
        }

    def _load(self) -> datetime:
        if not self.path.exists():
            return self.initial_since
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") != 1:
                raise ValueError("unsupported checkpoint version")
            value = datetime.fromisoformat(payload["last_successful_end"].replace("Z", "+00:00"))
            if value.tzinfo is None:
                raise ValueError("checkpoint timestamp has no timezone")
            return value.astimezone(UTC)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CheckpointError(f"invalid checkpoint: {self.path}") from exc

    def advance(self, end: datetime) -> None:
        end = end.astimezone(UTC).replace(microsecond=0)
        current = self._load()
        if end < current:
            raise CheckpointError("checkpoint cannot move backwards")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "last_successful_end": end.isoformat().replace("+00:00", "Z"),
        }
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(payload, handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
