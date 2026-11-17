#!/usr/bin/env bash
# Operator entry point for the first permanent PIKI PostgreSQL archive.
set -euo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
stage=preflight
exit_reason=command_failed
state_file=
network_id=
container_id=
manage_container=no
temporary_files=()
label=org.openlegalcore.pisrs.bootstrap
stop() { exit_reason=$1; exit 2; }

record_state() {
    printf 'status=%s stage=%s commit=%s run=%s network=%s container=%s reason=%s container_action=%s\n' \
        "$1" "$stage" "$commit" "$run_id" "${network_id:-none}" "${container_id:-none}" \
        "${2:-none}" "${3:-none}" >> "$state_file"
}

begin_stage() { stage=$1; record_state IN_PROGRESS; }

remove_temporary_files() {
    if (( ${#temporary_files[@]} > 0 )); then
        rm -f -- "${temporary_files[@]}" || return 1
        temporary_files=()
    fi
}

finish() {
    local rc=$1 status=FAILED container_action=not_created running
    (( rc != 0 )) || return 0
    trap '' HUP INT TERM
    case "$exit_reason" in SIGHUP|SIGINT|SIGTERM) status=INTERRUPTED ;; esac
    if [[ ${mode:-} == resume && -n $state_file ]]; then
        container_action=already_stopped
    fi
    if [[ $manage_container == yes ]]; then
        if ! running=$(timeout -k 3s 20s "${docker_cli[@]}" inspect --type container \
            --format "{{index .Config.Labels \"$label\"}} {{.State.Running}}" "$container_id"); then
            container_action=inspect_failed
        elif [[ $running == "$run_id false" ]]; then
            container_action=already_stopped
        elif [[ $running != "$run_id true" ]]; then
            container_action=ownership_not_verified
        elif timeout -k 3s 20s "${docker_cli[@]}" stop --timeout 10 "$container_id" >/dev/null; then
            container_action=stopped
        else
            container_action=stop_failed
        fi
    fi
    if ! remove_temporary_files; then
        printf 'OLC97 protected_copy_cleanup_failed stage=%s\n' "$stage" >&2
    fi
    if [[ -n $state_file ]] && ! record_state "$status" "$exit_reason" "$container_action"; then
        printf 'OLC97 state_write_failed path=%s\n' "$state_file" >&2
    fi
    printf 'OLC97 FAIL status=%s stage=%s reason=%s exit=%s state=%s container_action=%s\n' \
        "$status" "$stage" "$exit_reason" "$rc" "${state_file:-none}" "$container_action" >&2
}

trap 'finish "$?"' EXIT
trap 'exit_reason=SIGHUP; exit 129' HUP
trap 'exit_reason=SIGINT; exit 130' INT
trap 'exit_reason=SIGTERM; exit 143' TERM

[[ $(hostname -s) == piki && $(uname -m) == x86_64 && $EUID == 0 ]] || stop requires_piki_operator
operator=${SUDO_USER:-}
[[ -n $operator && $(id -u "$operator") != 0 ]] || stop requires_named_operator
repo=/data/projects/pisrs-piki-staging-foundation
root=/data/pisrs-staging
archive_hash=3876f37e71817888ec4a96354343253af1f238bb78c9dc24053b10e7b98082e4
image=docker.io/library/postgres@sha256:fa1b61f5a4844f4d4b73c9b15716cfc75fe70c931f2d32723630f3b900056366
container=pisrs-piki-pg
bridge=pisrs-piki-staging
docker_cli=(/usr/bin/docker --host unix:///var/run/docker.sock)
operator_git() { /usr/sbin/runuser -u "$operator" -- /usr/bin/git -C "$repo" "$@"; }

start_postgresql() {
    local attempt
    manage_container=yes
    "${docker_cli[@]}" start "$container_id" >/dev/null
    for ((attempt=0; attempt<60; attempt++)); do
        if "${docker_cli[@]}" exec --user 70:70 "$container_id" pg_isready -q -h 127.0.0.1; then
            [[ $("${docker_cli[@]}" port "$container_id" 5432/tcp) == 127.0.0.1:15432 ]] || stop unexpected_pg_publish
            return
        fi
        sleep 1
    done
    stop postgresql_not_ready
}

app_as() {
    local account=$1
    shift
    /usr/sbin/runuser -u "$account" -- "$python" -IB "${app_args[@]}" "$@"
}

accept_capture() {
    local first second rc attempt_id path
    local source_conn=$root/secrets/pisrs-source/conninfo
    local reader_conn=$root/secrets/pisrs-backup/conninfo
    local source_original=$root/work/pisrs-source/sifranti-index.body
    local reader_original=$root/work/pisrs-backup/sifranti-index.body
    local canary_args=(canary --pg-conn-file "$source_conn" --evidence-file "$source_original")
    local expected=RAW_AND_TYPED_ARCHIVED
    if [[ $mode == resume ]]; then
        canary_args+=(--retry-quarantined-capture)
        expected=ALREADY_ARCHIVED
    fi
    for path in "$source_original" "$reader_original"; do
        [[ ! -e $path && ! -L $path ]] || stop acceptance_copy_already_exists
    done
    temporary_files+=("$source_original" "$reader_original")
    install -m 0600 -o pisrs-source "${captures[0]}" "$source_original"
    install -m 0600 -o pisrs-backup "${captures[0]}" "$reader_original"
    cd "$release/src/tests"
    if [[ $mode == fresh ]]; then
        /usr/sbin/runuser -u pisrs-source -- env "PISRS_G3_TEST_SOURCE=$source_conn" \
            "$python" -B -m unittest test_g3_postgres.ArchiveAcceptanceTests.test_transport_failure_leaves_no_success_checkpoint
    fi
    if first=$(app_as pisrs-source "${canary_args[@]}"); then
        printf '%s\n' "$first"
    else
        rc=$?
        printf '%s\n' "$first" >&2
        exit_reason=first_canary_failed
        exit "$rc"
    fi
    attempt_id=$("$python" -IB -c 'import json,sys; r=json.load(sys.stdin); assert r["result"]=="PASS" and r["canary"] in {"RAW_AND_TYPED_ARCHIVED", sys.argv[1]} and r["get_requests"]==0; print(int(r["attempt_id"]))' "$expected" <<< "$first")
    app_as pisrs-backup readback --pg-conn-file "$reader_conn" \
        --attempt-id "$attempt_id" --evidence-file "$reader_original"
    if second=$(app_as pisrs-source "${canary_args[@]}"); then
        printf '%s\n' "$second"
    else
        rc=$?
        printf '%s\n' "$second" >&2
        exit_reason=replay_canary_failed
        exit "$rc"
    fi
    "$python" -IB -c 'import json,sys; r=json.load(sys.stdin); assert r["result"]=="PASS" and r["canary"]=="ALREADY_ARCHIVED" and r["attempt_id"]==int(sys.argv[1]) and r["get_requests"]==0' "$attempt_id" <<< "$second"
    /usr/sbin/runuser -u pisrs-backup -- env "PISRS_G3_TEST_READER=$reader_conn" \
        "$python" -B -m unittest test_g3_postgres.ArchiveAcceptanceTests.test_initial_archive_counts_and_role_boundaries
    remove_temporary_files || stop protected_copy_cleanup_failed
    begin_stage enable_restart_policy
    "${docker_cli[@]}" update --restart unless-stopped "$container_id" >/dev/null
    stage=finished
    record_state COMPLETE
    printf 'OLC97 PASS protected_capture_attempt=%s live_gets=0\n' "$attempt_id"
}

resume_acceptance() {
    local ledger=$root/bootstrap.state original last original_commit image_id identity mounts ports net listeners app_archive path
    local first_pattern='^status=IN_PROGRESS stage=release commit=([0-9a-f]{40}) run=([0-9a-f]{32}) network=none container=none reason=none container_action=none$'
    local last_pattern='^status=(FAILED|INTERRUPTED) stage=(acceptance|enable_restart_policy) commit=([0-9a-f]{40}) run=([0-9a-f]{32}) network=([0-9a-f]{64}) container=([0-9a-f]{64}) reason=[a-zA-Z0-9_]+ container_action=(stopped|already_stopped)$'
    [[ ! -L $root && $(stat -c '%u:%a' "$root") == 0:755 ]] || stop resume_root_unverified
    [[ -f $ledger && ! -L $ledger && $(stat -c '%u:%a' "$ledger") == 0:600 ]] || stop resume_state_unverified
    [[ -d $root/work && ! -L $root/work && $(stat -c '%u:%a' "$root/work") == 0:755 ]] || stop resume_work_path_unverified
    for path in "$root/work/pisrs-source" "$root/work/pisrs-backup"; do
        [[ -d $path && ! -L $path && $(stat -c '%u:%a' "$path") == 0:750 ]] || stop resume_work_path_unverified
        [[ ! -e $path/sifranti-index.body && ! -L $path/sifranti-index.body ]] || stop acceptance_copy_already_exists
    done
    IFS= read -r original < "$ledger" || stop resume_state_unverified
    [[ $original =~ $first_pattern ]] || stop resume_state_unverified
    original_commit=${BASH_REMATCH[1]}
    run_id=${BASH_REMATCH[2]}
    last=$(tail -n 1 -- "$ledger")
    [[ $last =~ $last_pattern && ${BASH_REMATCH[4]} == "$run_id" ]] || stop resume_state_unverified
    network_id=${BASH_REMATCH[5]}
    container_id=${BASH_REMATCH[6]}
    operator_git merge-base --is-ancestor "$original_commit" "$commit" || stop resume_release_unverified
    operator_git diff --quiet "$original_commit" "$commit" -- pisrs_g3/migrations || stop resume_migration_changed
    release=$root/releases/$original_commit
    python=$release/venv/bin/python
    [[ -x $python && -d $release/src/tests ]] || stop resume_release_unverified

    image_id=$("${docker_cli[@]}" image inspect --format '{{.Id}}' "$image") || stop resume_image_unverified
    [[ $image_id =~ ^sha256:[0-9a-f]{64}$ ]] || stop resume_image_unverified
    identity=$("${docker_cli[@]}" inspect --type container --format \
        "{{.Name}} {{.Image}} {{.State.Status}} {{.HostConfig.RestartPolicy.Name}} {{.HostConfig.NetworkMode}} {{index .Config.Labels \"$label\"}}" "$container_id") || stop resume_container_unverified
    [[ $identity == "/$container $image_id exited no $network_id $run_id" ]] || stop resume_container_unverified
    # Capture before comparing so Docker's extra trailing newline is stripped.
    mounts=$("${docker_cli[@]}" inspect --type container --format \
        '{{range .Mounts}}{{printf "%q %q %q %t\n" .Type .Source .Destination .RW}}{{end}}' "$container_id") || stop resume_mounts_inspect_failed
    local config_mount="\"bind\" \"$root/pg/conf\" \"/run/pisrs-pg\" false"
    local data_mount="\"bind\" \"$root/pg/data\" \"/var/lib/postgresql\" true"
    [[ $mounts == "$config_mount"$'\n'"$data_mount" || $mounts == "$data_mount"$'\n'"$config_mount" ]] || stop resume_mounts_unverified
    ports=$("${docker_cli[@]}" inspect --type container --format \
        '{{range $port,$bindings := .HostConfig.PortBindings}}{{range $bindings}}{{println $port .HostIp .HostPort}}{{end}}{{end}}' "$container_id") || stop resume_port_unverified
    [[ $ports == '5432/tcp 127.0.0.1 15432' ]] || stop resume_port_unverified
    net=$("${docker_cli[@]}" network inspect --format "{{.Name}} {{.Driver}} {{index .Labels \"$label\"}}" "$network_id") || stop resume_network_unverified
    [[ $net == "$bridge bridge $run_id" ]] || stop resume_network_unverified
    listeners=$(ss -H -ltn '( sport = :15432 )') || stop resume_port_unverified
    [[ -z $listeners ]] || stop project_port_in_use

    state_file=$ledger
    begin_stage acceptance
    # Use the existing environment and a root-owned snapshot of the reviewed fix.
    app_archive=$(mktemp "$root/work/acceptance-code.XXXXXXXX.zip")
    temporary_files+=("$app_archive")
    operator_git archive --format=zip "$commit" pisrs_g3 > "$app_archive"
    chmod 0444 "$app_archive"
    app_args=(-c 'import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module("pisrs_g3",run_name="__main__",alter_sys=True)' "$app_archive")
    start_postgresql
    app_as "$operator" preflight --pg-conn-file "$root/secrets/operator/conninfo"
    accept_capture
}

case "$#:${1:-}" in
    0:) mode=fresh ;;
    1:--check) mode=check ;;
    1:--resume-acceptance) mode=resume ;;
    *) stop unexpected_arguments ;;
esac
[[ $(operator_git branch --show-current) == piki/staging-foundation ]] || stop wrong_branch
checkout_status=$(operator_git status --porcelain=v1) || stop checkout_status_unverified
[[ -z $checkout_status ]] || stop dirty_checkout
commit=$(operator_git rev-parse HEAD) || stop checkout_commit_unverified
operator_git merge-base --is-ancestor 62410ea890f82ae25aa9ddbfa19cca6c7a319a6f "$commit" || stop wrong_candidate
# Keep the check and reservation exclusive without creating a lock file.
exec {lock_fd}</data
flock --exclusive --nonblock "$lock_fd" || stop bootstrap_lock_unavailable
if [[ $mode != resume ]]; then
    /bin/bash "$repo/ops/g3_check_piki.sh" || stop preflight_rejected
fi
mapfile -t captures < <(find /data/projects/.pisrs-g1-evidence -maxdepth 2 -type f -name sifranti-index.body)
[[ ${#captures[@]} == 1 ]] || stop original_evidence_missing_or_ambiguous
[[ $(stat -c '%a' "${captures[0]}") == 600 ]] || stop original_evidence_permissions
[[ $(sha256sum < "${captures[0]}") == "$archive_hash  -" ]] || stop original_evidence_digest
if [[ $mode == check ]]; then
    printf 'OLC97 CHECK PASS commit=%s\n' "$commit"
    exit 0
fi
if [[ $mode == resume ]]; then
    resume_acceptance
    exit 0
fi

stage=reserve_project_path
run_id=$(openssl rand -hex 16)
mkdir -m 0755 -- "$root" || stop project_path_reservation_failed
state_file=$root/bootstrap.state
begin_stage release
umask 022
install -d -m 0755 "$root/releases" "$root/runtime" "$root/work" "$root/pg"
install -d -m 0711 "$root/secrets"
release=$root/releases/$commit
install -d -m 0755 "$release" "$release/src"
install -d -m 0700 "$root/runtime/wheels" "$root/work/bootstrap"
export TMPDIR=$root/work/bootstrap
operator_git archive "$commit" pisrs_g3 pyproject.toml ops/g3_requirements.txt tests |
    tar -x -C "$release/src" --no-same-owner
/usr/bin/python3 -m venv "$release/venv"
python=$release/venv/bin/python
pip=("$python" -I -m pip --isolated --disable-pip-version-check --no-cache-dir)
lock=$release/src/ops/g3_requirements.txt
"${pip[@]}" download --quiet --only-binary=:all: --require-hashes -r "$lock" \
    --index-url https://pypi.org/simple --dest "$root/runtime/wheels"
"${pip[@]}" install --quiet --no-index --only-binary=:all: --require-hashes \
    --find-links "$root/runtime/wheels" -r "$lock"
"${pip[@]}" wheel --quiet --no-index --no-deps --no-build-isolation \
    --wheel-dir "$release" "$release/src"
wheel=("$release"/openlegalcore_pisrs_g3-*.whl)
[[ ${#wheel[@]} == 1 && -f ${wheel[0]} ]] || stop release_wheel_missing
"${pip[@]}" install --quiet --no-index --no-deps "${wheel[0]}"
"${pip[@]}" check
printf 'RELEASE PASS %s %s\n' "$commit" "$(sha256sum < "${wheel[0]}" | cut -d' ' -f1)"
umask 077

begin_stage pull_postgresql_image
"${docker_cli[@]}" pull --quiet --platform linux/amd64 "$image"
for principal in pisrs-source pisrs-backup; do
    begin_stage "create_host_account_$principal"
    useradd --system --user-group --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin "$principal"
    install -d -m 0750 -g "$principal" "$root/secrets/$principal" "$root/work/$principal"
done
begin_stage configure_postgresql
install -d -m 0750 -g "$(id -gn "$operator")" "$root/secrets/operator"
install -d -m 0700 -o 70 -g 70 "$root/pg/data"
install -d -m 0750 -g 70 "$root/pg/conf"
openssl req -quiet -x509 -newkey rsa:3072 -nodes -days 730 \
    -subj '/CN=PIKI PISRS staging PostgreSQL CA' -addext 'basicConstraints=critical,CA:TRUE' \
    -keyout "$root/secrets/pg_ca.key" -out "$root/pg/conf/ca.crt"
openssl req -quiet -new -newkey rsa:3072 -nodes -subj '/CN=127.0.0.1' \
    -keyout "$root/pg/conf/server.key" -out "$TMPDIR/server.csr"
openssl x509 -req -in "$TMPDIR/server.csr" -CA "$root/pg/conf/ca.crt" \
    -CAkey "$root/secrets/pg_ca.key" -set_serial "0x$(openssl rand -hex 16)" -days 365 \
    -extfile <(printf 'subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\n') \
    -out "$root/pg/conf/server.crt"
openssl rand -hex 32 > "$root/pg/conf/bootstrap.password"
chown 70:70 "$root/pg/conf/"{server.key,server.crt,bootstrap.password}
chmod 0400 "$root/pg/conf/"{server.key,bootstrap.password}
chmod 0444 "$root/pg/conf/"{server.crt,ca.crt}

begin_stage create_docker_network
new_network=$("${docker_cli[@]}" network create --driver bridge --label "$label=$run_id" "$bridge")
[[ $new_network =~ ^[0-9a-f]{64}$ ]] || stop unexpected_network_id
network_id=$new_network
begin_stage configure_network_access
gateway=$("${docker_cli[@]}" network inspect --format '{{(index .IPAM.Config 0).Gateway}}' "$network_id")
[[ $gateway =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || stop unexpected_docker_gateway
cat > "$root/pg/conf/pg_hba.conf" <<HBA
local all postgres peer
local all all reject
hostssl pisrs_staging pisrs_migrator,pisrs_source,pisrs_backup $gateway/32 scram-sha-256
hostssl pisrs_staging pisrs_migrator,pisrs_source,pisrs_backup 127.0.0.1/32 scram-sha-256
host all all 0.0.0.0/0 reject
host all all ::/0 reject
HBA
chmod 0640 "$root/pg/conf/pg_hba.conf"
chgrp 70 "$root/pg/conf/pg_hba.conf"
begin_stage create_postgresql_container
new_container=$("${docker_cli[@]}" create --name "$container" --platform linux/amd64 --user 70:70 \
    --network "$network_id" --publish 127.0.0.1:15432:5432 --restart no --label "$label=$run_id" \
    --memory 8g --cpus 3 --log-driver json-file --log-opt max-size=20m --log-opt max-file=3 \
    --mount "type=bind,src=$root/pg/data,dst=/var/lib/postgresql" \
    --mount "type=bind,src=$root/pg/conf,dst=/run/pisrs-pg,readonly" \
    --env PGDATA=/var/lib/postgresql/cluster --env POSTGRES_PASSWORD_FILE=/run/pisrs-pg/bootstrap.password \
    "$image" postgres -c hba_file=/run/pisrs-pg/pg_hba.conf \
    -c ssl=on -c ssl_cert_file=/run/pisrs-pg/server.crt -c ssl_key_file=/run/pisrs-pg/server.key)
[[ $new_container =~ ^[0-9a-f]{64}$ ]] || stop unexpected_container_id
container_id=$new_container
begin_stage start_postgresql_container
start_postgresql
psql() {
    "${docker_cli[@]}" exec --user 70:70 -i "$container_id" psql -X -v ON_ERROR_STOP=1 \
        -h /var/run/postgresql -U postgres -d postgres "$@"
}
begin_stage create_postgresql_roles
[[ $(psql -Atqc 'SHOW server_version_num') == 180007 ]] || stop unexpected_pg_version
psql -q <<'SQL'
CREATE ROLE pisrs_migrator LOGIN;
CREATE ROLE pisrs_source LOGIN;
CREATE ROLE pisrs_backup LOGIN;
CREATE DATABASE pisrs_staging OWNER pisrs_migrator;
REVOKE ALL ON DATABASE pisrs_staging FROM PUBLIC;
GRANT CONNECT ON DATABASE pisrs_staging TO pisrs_source, pisrs_backup;
SQL
begin_stage configure_postgresql_credentials
for role in pisrs_migrator pisrs_source pisrs_backup; do
    case "$role" in
        pisrs_migrator) account=$operator; dest=$root/secrets/operator ;;
        pisrs_source) account=pisrs-source; dest=$root/secrets/pisrs-source ;;
        pisrs_backup) account=pisrs-backup; dest=$root/secrets/pisrs-backup ;;
    esac
    password=$(openssl rand -hex 32)
    if ! printf '%s\n%s\n' "$password" "$password" | psql -q -c "\\password $role" >/dev/null 2>&1; then
        stop role_password_setup_failed
    fi
    install -m 0444 "$root/pg/conf/ca.crt" "$dest/ca.crt"
    printf 'host=127.0.0.1 port=15432 dbname=pisrs_staging user=%s sslmode=verify-full sslrootcert=%s/ca.crt password=%s\n' \
        "$role" "$dest" "$password" > "$dest/conninfo"
    chown "$account" "$dest/conninfo"
    unset password
done
printf 'POSTGRESQL PASS version=18.7 port=127.0.0.1:15432 image=%s\n' "$image"

begin_stage migration
cd "$release"
/usr/sbin/runuser -u "$operator" -- "$python" -IB -m pisrs_g3 migrate \
    --pg-conn-file "$root/secrets/operator/conninfo"
begin_stage acceptance
app_args=(-m pisrs_g3)
accept_capture
