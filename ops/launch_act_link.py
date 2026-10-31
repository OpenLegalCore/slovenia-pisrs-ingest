#!/usr/bin/env python3
"""Verify the approved closed package before loading its code. Default: verify only."""

from __future__ import annotations

import argparse
import hashlib
import os
import runpy
import stat
import sys
from pathlib import Path


def verified_files(package, expected_hash):
    manifest = (package / "SHA256SUMS").read_bytes()
    if hashlib.sha256(manifest).hexdigest() != expected_hash:
        raise ValueError("package hash changed")
    result = {"SHA256SUMS": manifest}
    for line in manifest.decode().splitlines():
        h, name = line.split(None, 1)
        name = name.strip()
        p = package / name
        if name in result or p.is_symlink() or not p.resolve().is_relative_to(package.resolve()):
            raise ValueError("unsafe package member")
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != h:
            raise ValueError("package member changed")
        result[name] = data
    return result


def stage(files, directory):
    if not directory.exists():
        directory.mkdir(mode=0o700)
    if (
        directory.is_symlink()
        or directory.stat().st_uid != os.geteuid()
        or stat.S_IMODE(directory.stat().st_mode) != 0o700
    ):
        raise ValueError("unsafe immutable execution directory")
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.exists():
            if path.is_symlink() or path.read_bytes() != data:
                raise ValueError("immutable execution copy changed")
            continue
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.read_bytes() != data:
            raise ValueError("execution copy readback failed")
    for path in [directory, *[p for p in directory.rglob("*") if p.is_dir()]]:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(fd)
        os.close(fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", nargs="?", choices=["verify", "apply", "rollback"], default="verify"
    )
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--package-sha256", required=True)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    files = verified_files(args.package, args.package_sha256)
    if args.mode == "verify":
        print("VERIFIED_ONLY: no production connection or write")
        return
    if (
        os.geteuid() != 0
        or args.manifest_sha256 != hashlib.sha256(files["manifest.json"]).hexdigest()
    ):
        raise ValueError("separate approval of exact manifest and local pkexec required")
    directory = Path("/var/lib/pisrs-ingest") / (".act-link-code-" + args.package_sha256)
    stage(files, directory)
    sys.path.insert(0, str(directory / "src"))
    sys.argv = [
        str(directory / "ops/act_link_operation.py"),
        args.mode,
        "--package",
        str(directory),
        "--approved-package-sha256",
        args.package_sha256,
        "--approved-manifest-sha256",
        args.manifest_sha256,
    ]
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("STOPPED: " + type(error).__name__ + "; no automatic mutation retry", flush=True)
        sys.exit(1)
