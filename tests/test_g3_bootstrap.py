"""Exercise the operator scripts with an isolated filesystem and command stubs."""
import fcntl
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = b"offline capture for bootstrap regression tests"
COMMIT = "c" * 40
RUN = "a" * 32
CONTAINER = "b" * 64
NETWORK = "d" * 64

SHIM = r'''#!/bin/bash
set -eu
command=${0##*/}
case "$command" in
    hostname) echo piki ;;
    uname) echo x86_64 ;;
    id) if [[ $1 == -gn ]]; then echo operator; else echo 1000; fi ;;
    findmnt) echo 'ext4 rw,relatime' ;;
    df) printf 'header\n/dev/data 100 10 90 10%% /data\n' ;;
    getent)
        case "$SCENARIO:$1:$2" in
            account_conflict:passwd:pisrs-source) exit 0 ;;
            group_conflict:group:pisrs-backup) exit 0 ;;
            unknown_identities:group:70) exit 1 ;;
            *) exit 2 ;;
        esac
        ;;
    ss) if [[ $SCENARIO == listener_conflict ]]; then echo listener; fi ;;
    sudo)
        printf 'sudo %s\n' "$*" >> "$TRACE"
        [[ $1 == -n && $2 == -- ]]
        shift 2
        DOCKER_VIA_SUDO=yes exec "$@"
        ;;
    runuser)
        shift 3
        if [[ ${1##*/} == git ]]; then
            case "$4" in
                branch) echo piki/staging-foundation ;;
                status|merge-base|archive) : ;;
                rev-parse) echo "$COMMIT" ;;
                *) exit 91 ;;
            esac
        else
            printf 'app %s\n' "$*" >> "$TRACE"
            [[ $SCENARIO == copy_failure || $SCENARIO == success ]] || exit 92
            if [[ $* == *' canary '* ]]; then echo '{}'; fi
        fi
        ;;
    tar) mkdir -p "$3/tests" ;;
    useradd|chown|chgrp) echo "$command" >> "$TRACE" ;;
    install)
        original=("$@")
        args=()
        while (( $# )); do
            case "$1" in
                -g|-o) shift 2 ;;
                *) args+=("$1"); shift ;;
            esac
        done
        if [[ $SCENARIO == copy_failure && ${original[*]} == *'-o pisrs-backup'*'sifranti-index.body'* ]]; then
            exit 3
        fi
        exec /usr/bin/install "${args[@]}"
        ;;
    openssl)
        if [[ $1 == rand ]]; then echo "$RUN"; exit 0; fi
        while (( $# )); do
            case "$1" in
                -out|-keyout) touch -- "$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        ;;
    python3|python)
        if [[ $* == '-m venv '* ]]; then
            mkdir -p "$3/bin"
            ln -s "$BIN/python3" "$3/bin/python"
        elif [[ $* == *' download '* && $SCENARIO == release_failure ]]; then
            exit 3
        elif [[ $* == *' wheel '* ]]; then
            while [[ $1 != --wheel-dir ]]; do shift; done
            touch "$2/openlegalcore_pisrs_g3-test.whl"
        elif [[ $* == '-IB -c '* ]]; then
            cat >/dev/null
            echo 1
        fi
        ;;
    docker)
        shift 2
        printf 'docker %s\n' "$*" >> "$TRACE"
        case "$1" in
            info)
                if [[ $2 == --format && $3 == '{{.ServerVersion}}' ]]; then
                    [[ $SCENARIO != sudo_required ]]
                else
                    [[ $SCENARIO != sudo_required || ${DOCKER_VIA_SUDO:-} == yes ]]
                    echo "$DATA/docker overlayfs"
                fi
                ;;
            ps)
                case "$SCENARIO" in
                    container_conflict) echo pisrs-piki-pg ;;
                    mount_conflict|port_conflict|inspect_failure) echo unrelated ;;
                esac
                ;;
            inspect)
                case "$SCENARIO" in
                    mount_conflict) echo "mount $WORK/data-alias" ;;
                    port_conflict) echo 'port 15432' ;;
                    inspect_failure) exit 4 ;;
                    wrong_owner) echo 'another-run true' ;;
                    *) [[ ${!#} == "$CONTAINER" ]]; echo "$RUN true" ;;
                esac
                ;;
            volume)
                if [[ $SCENARIO == volume_conflict ]]; then echo pisrs_piki_archive; fi ;;
            network)
                case "$2" in
                    ls) if [[ $SCENARIO == network_conflict ]]; then echo pisrs-piki-staging; fi ;;
                    create) echo "$NETWORK" ;;
                    inspect) [[ ${!#} == "$NETWORK" ]]; echo 172.23.0.1 ;;
                    *) exit 93 ;;
                esac
                ;;
            pull|start|stop|update) : ;;
            create) echo "$CONTAINER" ;;
            exec)
                if [[ $* == *' pg_isready '* ]]; then
                    if [[ $SCENARIO == interrupted ]]; then kill -TERM "$PPID"; fi
                elif [[ $* == *'SHOW server_version_num' ]]; then
                    echo 180007
                else
                    cat >/dev/null
                fi
                ;;
            port)
                case "$SCENARIO" in
                    copy_failure|success) echo 127.0.0.1:15432 ;;
                    *) echo invalid ;;
                esac
                ;;
            *) exit 94 ;;
        esac
        ;;
    *) exit 95 ;;
esac
'''


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.data = self.work / "data"
        self.data.mkdir()
        (self.work / "data-alias").symlink_to(self.data)
        self.staging = self.data / "pisrs-staging"
        self.state = self.staging / "bootstrap.state"
        self.trace = self.work / "trace"
        self.trace.touch()
        self.repo = self.data / "projects/pisrs-piki-staging-foundation"
        (self.repo / "ops").mkdir(parents=True)
        self.capture = self.data / "projects/.pisrs-g1-evidence/original/sifranti-index.body"
        self.capture.parent.mkdir(parents=True)
        self.capture.write_bytes(CAPTURE)
        self.capture.chmod(0o600)
        self.bin = self.work / "bin"
        self.bin.mkdir()
        shim = self.bin / "shim"
        shim.write_text(SHIM)
        shim.chmod(0o755)
        for name in ("hostname", "uname", "id", "findmnt", "df", "getent", "ss", "sudo",
                     "runuser", "tar", "useradd", "chown", "chgrp", "install", "openssl",
                     "python3", "docker"):
            (self.bin / name).symlink_to(shim)

        # Redirect hard-coded paths and the privilege probe only in the test copies.
        digest = hashlib.sha256(CAPTURE).hexdigest()
        for name in ("g3_bootstrap_pg.sh", "g3_check_piki.sh"):
            script = (ROOT / "ops" / name).read_text()
            script = re.sub(r"(?<![\w/])/data(?=[/\s'\"]|$)", str(self.data), script)
            script = re.sub(r"/usr/(?:s)?bin/(docker|runuser|python3)", str(self.bin) + r"/\1", script)
            script = script.replace("export PATH=", f"export PATH={self.bin}:")
            script = script.replace("EUID", "TEST_EUID")
            script = re.sub(r"(?m)^archive_hash=.*$", f"archive_hash={digest}", script)
            (self.repo / "ops" / name).write_text(script)

    def run_script(self, scenario="", *args, script="g3_bootstrap_pg.sh", euid="0"):
        environment = {"PATH": f"{self.bin}:/usr/bin:/bin", "TEST_EUID": euid,
                       "SUDO_USER": "operator", "TRACE": str(self.trace), "DATA": str(self.data),
                       "WORK": str(self.work), "BIN": str(self.bin), "SCENARIO": scenario,
                       "COMMIT": COMMIT, "RUN": RUN, "CONTAINER": CONTAINER, "NETWORK": NETWORK}
        return subprocess.run(
            ["/bin/bash", str(self.repo / "ops" / script), *args], env=environment,
            text=True, capture_output=True, timeout=10,
        )

    def assert_no_provisioning(self):
        trace = self.trace.read_text()
        self.assertNotRegex(trace, r"(?m)^(docker (pull|network create|create|start|stop|update)|useradd)")

    def test_root_check_and_unprivileged_docker_fallback(self):
        result = self.run_script("", "--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OLC97 CHECK PASS", result.stdout)
        self.assertNotIn("sudo ", self.trace.read_text())

        result = self.run_script("sudo_required", script="g3_check_piki.sh", euid="1000")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo -n -- ", self.trace.read_text())
        self.assertFalse(self.staging.exists())
        self.assert_no_provisioning()

    def test_conflicts_and_unverified_inventory_stop_before_mutation(self):
        for scenario, reason in (
            ("account_conflict", "identity_in_use:passwd:pisrs-source"),
            ("group_conflict", "identity_in_use:group:pisrs-backup"),
            ("unknown_identities", "identity_inventory_unverified:group"),
            ("container_conflict", "project_container_exists"),
            ("mount_conflict", "docker_mount_binding_conflict"),
            ("port_conflict", "docker_port_binding_conflict"),
            ("inspect_failure", "docker_binding_unverified"),
            ("volume_conflict", "project_named_volume_exists"),
            ("network_conflict", "project_network_exists"),
            ("listener_conflict", "project_port_in_use"),
        ):
            with self.subTest(scenario=scenario):
                result = self.run_script(scenario)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(reason, result.stderr)
                self.assertFalse(self.staging.exists())
                self.assert_no_provisioning()

    def test_existing_path_is_preserved(self):
        self.staging.mkdir()
        existing = self.staging / "preexisting"
        existing.write_text("preserve me")
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn("existing_project_path", result.stderr)
        self.assertEqual(existing.read_text(), "preserve me")
        self.assertFalse(self.state.exists())
        self.assert_no_provisioning()

    def test_concurrent_bootstrap_stops_before_provisioning(self):
        descriptor = os.open(self.data, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            result = self.run_script()
        finally:
            os.close(descriptor)
        self.assertEqual(result.returncode, 2)
        self.assertIn("bootstrap_lock_unavailable", result.stderr)
        self.assertFalse(self.staging.exists())
        self.assert_no_provisioning()

    def test_failed_release_records_state_and_blocks_retry(self):
        result = self.run_script("release_failure")
        self.assertEqual(result.returncode, 3, result.stderr)
        state = self.state.read_text()
        self.assertIn("status=FAILED stage=release", state)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn("existing_project_path", result.stderr)
        self.assertEqual(self.state.read_text(), state)
        self.assert_no_provisioning()

    def assert_container_failure(self, scenario, rc, status, action):
        result = self.run_script(scenario)
        self.assertEqual(result.returncode, rc, result.stderr)
        state = self.state.read_text()
        self.assertIn(f"status={status} stage=start_postgresql_container", state)
        self.assertIn(f"container_action={action}", state)
        trace = self.trace.read_text()
        self.assertIn(f"--restart no --label org.openlegalcore.pisrs.bootstrap={RUN}", trace)
        self.assertEqual(f"docker stop --timeout 10 {CONTAINER}" in trace, action == "stopped")
        self.assertNotRegex(trace, r"(?m)^docker (rm|network rm|volume rm|update)")
        self.assertTrue(self.staging.is_dir())

    def test_failure_stops_only_created_container(self):
        self.assert_container_failure("bad_publish", 2, "FAILED", "stopped")

    def test_interrupt_records_state_and_stops_created_container(self):
        self.assert_container_failure("interrupted", 143, "INTERRUPTED", "stopped")

    def test_failure_never_stops_container_with_wrong_label(self):
        self.assert_container_failure("wrong_owner", 2, "FAILED", "ownership_not_verified")

    def test_second_copy_failure_removes_only_staged_copies(self):
        result = self.run_script("copy_failure")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("status=FAILED stage=acceptance", self.state.read_text())
        self.assertFalse(list((self.staging / "work").glob("pisrs-*/sifranti-index.body")))
        self.assertEqual(self.capture.read_bytes(), CAPTURE)

    def test_restart_policy_is_enabled_after_successful_acceptance(self):
        result = self.run_script("success")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OLC97 PASS", result.stdout)
        self.assertIn("status=COMPLETE stage=finished", self.state.read_text())
        trace = self.trace.read_text().splitlines()
        self.assertIn("test_initial_archive_counts_and_role_boundaries", trace[-2])
        self.assertEqual(trace[-1], f"docker update --restart unless-stopped {CONTAINER}")
        self.assertFalse(list((self.staging / "work").glob("pisrs-*/sifranti-index.body")))
