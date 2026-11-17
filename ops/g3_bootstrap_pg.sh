#!/usr/bin/env bash
# Operator entry point for the first permanent PIKI PostgreSQL archive.
set -euo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
stop() { printf 'OLC97 FAIL %s\n' "$1" >&2; exit 2; }
stage=preflight
trap 'printf "OLC97 FAIL stage=%s line=%d\n" "$stage" "$LINENO" >&2' ERR

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

[[ $# == 0 ]] || stop unexpected_arguments
[[ $(operator_git branch --show-current) == piki/staging-foundation ]] || stop wrong_branch
[[ -z $(operator_git status --porcelain=v1) ]] || stop dirty_checkout
commit=$(operator_git rev-parse HEAD)
operator_git merge-base --is-ancestor 62410ea890f82ae25aa9ddbfa19cca6c7a319a6f "$commit"
/bin/bash "$repo/ops/g3_check_piki.sh"
for principal in pisrs-source pisrs-backup; do
    if getent passwd "$principal" >/dev/null || getent group "$principal" >/dev/null; then
        stop existing_project_service_identity
    fi
done
mapfile -t captures < <(find /data/projects/.pisrs-g1-evidence -maxdepth 2 -type f -name sifranti-index.body)
[[ ${#captures[@]} == 1 ]] || stop original_evidence_missing_or_ambiguous
[[ $(stat -c '%a' "${captures[0]}") == 600 ]] || stop original_evidence_permissions
[[ $(sha256sum < "${captures[0]}") == "$archive_hash  -" ]] || stop original_evidence_digest

stage=release
umask 022
install -d -m 0755 "$root" "$root/releases" "$root/runtime" "$root/work" "$root/pg"
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

stage=postgresql
"${docker_cli[@]}" pull --quiet --platform linux/amd64 "$image"
for principal in pisrs-source pisrs-backup; do
    useradd --system --user-group --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin "$principal"
    install -d -m 0700 -o "$principal" "$root/secrets/$principal" "$root/work/$principal"
done
install -d -m 0700 -o "$operator" "$root/secrets/operator"
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

"${docker_cli[@]}" network create --driver bridge "$bridge" >/dev/null
gateway=$("${docker_cli[@]}" network inspect --format '{{(index .IPAM.Config 0).Gateway}}' "$bridge")
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
"${docker_cli[@]}" run --detach --name "$container" --platform linux/amd64 --user 70:70 \
    --network "$bridge" --publish 127.0.0.1:15432:5432 --restart unless-stopped \
    --memory 8g --cpus 3 --log-driver json-file --log-opt max-size=20m --log-opt max-file=3 \
    --mount "type=bind,src=$root/pg/data,dst=/var/lib/postgresql" \
    --mount "type=bind,src=$root/pg/conf,dst=/run/pisrs-pg,readonly" \
    --env PGDATA=/var/lib/postgresql/cluster --env POSTGRES_PASSWORD_FILE=/run/pisrs-pg/bootstrap.password \
    "$image" postgres -c hba_file=/run/pisrs-pg/pg_hba.conf \
    -c ssl=on -c ssl_cert_file=/run/pisrs-pg/server.crt -c ssl_key_file=/run/pisrs-pg/server.key >/dev/null
ready=0
for ((attempt=0; attempt<60; attempt++)); do
    if "${docker_cli[@]}" exec --user 70:70 "$container" pg_isready -q -h 127.0.0.1; then
        ready=1
        break
    fi
    sleep 1
done
(( ready == 1 )) || stop postgresql_not_ready
[[ $("${docker_cli[@]}" port "$container" 5432/tcp) == 127.0.0.1:15432 ]] || stop unexpected_pg_publish
psql() {
    "${docker_cli[@]}" exec --user 70:70 -i "$container" psql -X -v ON_ERROR_STOP=1 \
        -h /var/run/postgresql -U postgres -d postgres "$@"
}
psql -q <<'SQL'
CREATE ROLE pisrs_migrator LOGIN;
CREATE ROLE pisrs_source LOGIN;
CREATE ROLE pisrs_backup LOGIN;
CREATE DATABASE pisrs_staging OWNER pisrs_migrator;
REVOKE ALL ON DATABASE pisrs_staging FROM PUBLIC;
GRANT CONNECT ON DATABASE pisrs_staging TO pisrs_source, pisrs_backup;
SQL
[[ $(psql -Atqc 'SHOW server_version_num') == 180007 ]] || stop unexpected_pg_version
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

stage=migration
cd "$release"
/usr/sbin/runuser -u "$operator" -- "$python" -IB -m pisrs_g3 migrate \
    --pg-conn-file "$root/secrets/operator/conninfo"
stage=acceptance
source_conn=$root/secrets/pisrs-source/conninfo
reader_conn=$root/secrets/pisrs-backup/conninfo
source_original=$root/work/pisrs-source/sifranti-index.body
reader_original=$root/work/pisrs-backup/sifranti-index.body
install -m 0600 -o pisrs-source "${captures[0]}" "$source_original"
install -m 0600 -o pisrs-backup "${captures[0]}" "$reader_original"
trap 'rm -f -- "$source_original" "$reader_original"' EXIT
cd "$release/src/tests"
/usr/sbin/runuser -u pisrs-source -- env "PISRS_G3_TEST_SOURCE=$source_conn" \
    "$python" -B -m unittest test_g3_postgres.ArchiveAcceptanceTests.test_transport_failure_leaves_no_success_checkpoint
canary() {
    /usr/sbin/runuser -u pisrs-source -- "$python" -IB -m pisrs_g3 canary \
        --pg-conn-file "$source_conn" --evidence-file "$source_original"
}
first=$(canary)
printf '%s\n' "$first"
attempt_id=$(printf '%s' "$first" | "$python" -IB -c 'import json,sys; r=json.load(sys.stdin); assert r["canary"]=="RAW_AND_TYPED_ARCHIVED"; print(r["attempt_id"])')
/usr/sbin/runuser -u pisrs-backup -- "$python" -IB -m pisrs_g3 readback \
    --pg-conn-file "$reader_conn" --attempt-id "$attempt_id" --evidence-file "$reader_original"
second=$(canary)
printf '%s\n' "$second"
printf '%s' "$second" | "$python" -IB -c 'import json,sys; r=json.load(sys.stdin); assert r["canary"]=="ALREADY_ARCHIVED" and r["attempt_id"]==int(sys.argv[1]) and r["get_requests"]==0' "$attempt_id"
/usr/sbin/runuser -u pisrs-backup -- env "PISRS_G3_TEST_READER=$reader_conn" \
    "$python" -B -m unittest test_g3_postgres.ArchiveAcceptanceTests.test_initial_archive_counts_and_role_boundaries
printf 'OLC97 PASS protected_capture_attempt=%s live_gets=0\n' "$attempt_id"
