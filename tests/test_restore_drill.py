from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest
import requests
from test_act_link_manifest import operation_case  # noqa: F401
from test_act_links import pg_links  # noqa: F401

spec = importlib.util.spec_from_file_location(
    "pisrs_restore_drill", Path(__file__).parents[1] / "ops/pisrs_restore_drill.py"
)
drill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drill)


def capture_runbook():
    text = (Path(__file__).parents[1] / "docs/pisrs-backup-restore.md").read_text()
    return text.split("```python\n", 1)[1].split("\n```", 1)[0]


def test_capture_uses_documented_positional_paths_with_stripped_environment(tmp_path, monkeypatch):
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps({"pg_container": "synthetic-pg", "qdrant_container": "synthetic-q"})
    )
    checkout = tmp_path / "checkout"
    (checkout / "ops").mkdir(parents=True)
    # Stop at the first source inspection. No Docker, lock or production file is accessed.
    (checkout / "ops/pisrs_restore_drill.py").write_text(
        "def inspect(identity):\n    raise RuntimeError('synthetic source boundary')\n"
    )
    target = tmp_path / "new-backup"
    for name in ["PISRS_BACKUP_CONTEXT", "PISRS_REVIEW_CHECKOUT", "PISRS_BACKUP_DIR"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("sys.argv", ["capture_pisrs.py", str(context), str(target), str(checkout)])
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "umask", lambda _: 0)
    namespace = {}
    with pytest.raises(RuntimeError, match="synthetic source boundary"):
        exec(compile(capture_runbook(), "capture_pisrs.py", "exec"), namespace)
    assert namespace["ctx"] == json.loads(context.read_text())
    assert namespace["root"] == checkout
    assert namespace["out"] == target
    assert not target.exists()


def test_capture_missing_arguments_stops_before_source_access(monkeypatch):
    monkeypatch.setattr("sys.argv", ["capture_pisrs.py"])
    for name in ["PISRS_BACKUP_CONTEXT", "PISRS_REVIEW_CHECKOUT", "PISRS_BACKUP_DIR"]:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit) as stopped:
        exec(compile(capture_runbook(), "capture_pisrs.py", "exec"), {})
    assert stopped.value.code == 2


def test_bundle_checksum_rejects_unlisted_scope(tmp_path):
    (tmp_path / "SHA256SUMS").write_bytes(b"")
    with pytest.raises(ValueError, match="incomplete"):
        drill.verify_bundle(tmp_path, hashlib.sha256(b"").hexdigest())


def test_pg_full_isolated_restore_drill(operation_case, tmp_path):  # noqa: F811
    if os.environ.get("PISRS_TEST_RESTORE_DRILL") != "1" or os.geteuid() != 0:
        pytest.skip("requires explicitly enabled root-only isolated Docker restore drill")
    resource = Path(os.environ["PISRS_TEST_RESTORE_RESOURCES"])
    config = json.loads(resource.read_text())
    assert config["production_mounts"] == 0 and config["pg_port"] not in [5432, 6333, 6334]
    c, m, q, _, _, _ = operation_case
    url = config["q_url"]
    base = url + "/collections/pisrs_current"
    session = requests.Session()
    session.trust_env = False
    assert session.put(base, json={"vectors": {"size": 3072, "distance": "Cosine"}}, timeout=10).ok
    bundle = tmp_path / "backup"
    bundle.mkdir(mode=0o700)
    work = Path("/tmp") / ("pisrs-restore-test-" + uuid.uuid4().hex)
    try:
        points = [
            {"id": pid, "payload": p["payload"], "vector": p["vector"]}
            for pid, p in q.points.items()
        ]
        assert session.put(base + "/points?wait=true", json={"points": points}, timeout=10).ok
        snapshot = session.post(base + "/snapshots", timeout=20)
        snapshot.raise_for_status()
        name = snapshot.json()["result"]["name"]
        data = session.get(base + "/snapshots/" + name, timeout=20)
        data.raise_for_status()
        (bundle / "pisrs_current.snapshot").write_bytes(data.content)
        with (bundle / "pg.dump").open("wb") as f:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    config["pg_id"],
                    "pg_dump",
                    "-U",
                    "postgres",
                    "-d",
                    "pisrs_test_late_links",
                    "-Fc",
                    "--schema=pisrs",
                    "--no-owner",
                    "--no-privileges",
                ],
                stdout=f,
                check=True,
            )
        checkpoint = b'{"version":1,"last_successful_interval_end":"2026-10-30T00:00:00+00:00"}\n'
        (bundle / "checkpoint.json").write_bytes(checkpoint)
        baseline = {
            "pg": drill.pg_fingerprint(config["pg_id"], "pisrs_test_late_links", "postgres"),
            "qdrant": drill.q_fingerprint(config["q_id"]),
            "checkpoint_sha256": hashlib.sha256(checkpoint).hexdigest(),
        }
        (bundle / "baseline.json").write_text(json.dumps(baseline, sort_keys=True))
        (bundle / "images.json").write_text(
            json.dumps(
                {
                    "postgres": config["pg_image"],
                    "qdrant": config["q_image"],
                    "required_free_bytes": 64 * 1024 * 1024,
                }
            )
        )
        members = sorted(bundle.iterdir())
        sums = "".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in members
        ).encode()
        (bundle / "SHA256SUMS").write_bytes(sums)
        report = drill.restore(bundle, hashlib.sha256(sums).hexdigest(), work)
        assert report["result"] == "PASS_ISOLATED_RESTORE"
        assert report["fingerprints"] == baseline
        assert json.loads((work / "report.json").read_text())["network"] == "none"
        # No source table was changed by dump, fingerprints or restore.
        assert (
            drill.pg_fingerprint(config["pg_id"], "pisrs_test_late_links", "postgres")
            == baseline["pg"]
        )
        assert drill.q_fingerprint(config["q_id"]) == baseline["qdrant"]
        if path := os.environ.get("PISRS_TEST_RESTORE_REPORT"):
            proof = Path(path)
            proof.write_text(json.dumps(report, sort_keys=True, indent=2))
            proof.chmod(0o600)
    finally:
        assert session.delete(base, timeout=10).ok
        # Only the unique directory created by this test is deleted.
        if work.exists():
            import shutil

            shutil.rmtree(work)


def test_optimizer_resume_cannot_target_source(monkeypatch):
    monkeypatch.setattr(
        drill,
        "inspect",
        lambda _: {
            "HostConfig": {"NetworkMode": "bridge"},
            "Config": {"Labels": {}},
            "State": {"Pid": 1},
        },
    )
    with pytest.raises(ValueError, match="restricted"):
        drill.q_request(
            "synthetic-source",
            "/collections/pisrs_current",
            {"optimizers_config": {}},
            method="PATCH",
        )
