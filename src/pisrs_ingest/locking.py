"""Single application-owned non-blocking advisory lock."""

from __future__ import annotations

import fcntl
import os
import stat
from pathlib import Path
from typing import IO


class LockBusyError(RuntimeError):
    """Raised when another mutating invocation already owns the lock."""


class LockLostError(RuntimeError):
    """The original owner or lock inode is no longer valid."""


class ApplicationLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[str] | None = None
        self._owner_pid: int | None = None

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
        self._owner_pid = os.getpid()
        return self

    def assert_owned(self) -> None:
        if self._handle is None or self._owner_pid != os.getpid():
            raise LockLostError("maintenance requires the original live lock owner")
        try:
            descriptor = os.fstat(self._handle.fileno())
            path = self.path.stat(follow_symlinks=False)
        except (OSError, ValueError) as exc:
            raise LockLostError("maintenance lock disappeared") from exc
        if (
            not stat.S_ISREG(path.st_mode)
            or descriptor.st_nlink != 1
            or (path.st_dev, path.st_ino) != (descriptor.st_dev, descriptor.st_ino)
        ):
            raise LockLostError("maintenance lock inode was replaced or unlinked")

    def __exit__(self, *_: object) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None
        self._owner_pid = None
