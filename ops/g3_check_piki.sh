#!/usr/bin/env bash
# Read-only PIKI G3 preflight. Does not install, create or change any resource.
set -euo pipefail
[ "$(hostname -s)" = piki ] || { echo 'BLOCKED: wrong host'; exit 2; }
[ "$(id -u)" -ne 0 ] || { echo 'BLOCKED: run as unprivileged operator'; exit 2; }
printf 'HOST %s\n' "$(hostname -s)"
findmnt -n -o TARGET,FSTYPE,OPTIONS /data
df -hP /data | tail -n 1
python3 - <<'PY'
import sys
if sys.version_info[:2] != (3,14):
    print("PYTHON_RUNTIME BLOCKED: CPython 3.14 required")
    sys.exit(2)
print("PYTHON_RUNTIME PASS",sys.version.split()[0])
PY
if docker info --format '{{.DockerRootDir}} {{.Driver}}' >/dev/null 2>&1; then
  data=$(docker info --format '{{.DockerRootDir}} {{.Driver}}')
else
  data=$(sudo -- /usr/bin/docker info --format '{{.DockerRootDir}} {{.Driver}}')
fi
printf 'DOCKER_RUNTIME %s\n' "$data"
[ "$data" = '/data/docker overlayfs' ] || { echo 'BLOCKED: docker data root/driver changed'; exit 2; }
for name in pisrs-piki-pg pisrs-piki-qdrant; do
  if sudo -- /usr/bin/docker inspect --type container "$name" >/dev/null 2>&1; then
    echo "PROJECT_CONTAINER_EXISTS $name; inspect identity before any new install"
  else
    echo "PROJECT_CONTAINER_ABSENT $name"
  fi
done
if [ -e /data/pisrs-staging ]; then
  printf 'PROJECT_PATH_EXISTS '; stat -c '%n %U:%G %a' /data/pisrs-staging
else
  echo 'PROJECT_PATH_ABSENT /data/pisrs-staging'
fi
for port in 15432 16333; do
  if ss -H -ltn "( sport = :$port )" | grep -q .; then
    printf 'PORT_RESERVED %s\n' "$port"
  else
    printf 'PORT_FREE %s\n' "$port"
  fi
done
echo 'G3_READONLY_PREFLIGHT COMPLETE. No filesystem, role, DB or container mutation.'
