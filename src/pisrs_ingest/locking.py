"""Single application-owned non-blocking advisory lock."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import IO


class LockBusyError(RuntimeError):
    """Raised when another mutating invocation already owns the lock."""


class ApplicationLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[str] | None = None

    def __enter__(self) -> ApplicationLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise LockBusyError(f"another mutating pisrs-ingest process owns {self.path}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._handle = handle
        return self

    def __exit__(self, *_: object) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None
