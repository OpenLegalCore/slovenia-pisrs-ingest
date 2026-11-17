#!/usr/bin/env bash
# Read-only preflight for the permanent PIKI PostgreSQL staging install.
set -euo pipefail
stop() { printf 'PREFLIGHT FAIL %s\n' "$1" >&2; exit 2; }
[[ $(hostname -s) == piki ]] || stop wrong_host
docker_cli=(/usr/bin/docker --host unix:///var/run/docker.sock)
if (( EUID != 0 )) && ! "${docker_cli[@]}" info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
    docker_cli=(sudo -- "${docker_cli[@]}")
fi
runtime=$("${docker_cli[@]}" info --format '{{.DockerRootDir}} {{.Driver}}') || stop docker_unavailable
[[ $runtime == '/data/docker overlayfs' ]] || stop unexpected_docker_root_or_driver
mount=$(findmnt -n --mountpoint /data -o FSTYPE,OPTIONS)
[[ $mount == 'ext4 rw' || $mount == 'ext4 rw,'* ]] || stop unexpected_data_mount
avail=$(df -kP /data | awk 'NR == 2 {print $4}')
[[ $avail =~ ^[0-9]+$ ]] || stop storage_inventory_missing
(( avail > 0 )) || stop data_full
[[ ! -e /data/pisrs-staging && ! -L /data/pisrs-staging ]] || stop existing_project_path
names=$("${docker_cli[@]}" ps -a --format '{{.Names}}')
count=0
while IFS= read -r name; do
    [[ -n $name ]] || continue
    ((count+=1))
    [[ $name != pisrs-piki-pg && $name != pisrs-piki-qdrant ]] || stop project_container_exists
    if ! "${docker_cli[@]}" inspect --type container \
        --format '{{range .Mounts}}{{println .Source}}{{end}}{{range .HostConfig.PortBindings}}{{range .}}{{println .HostPort}}{{end}}{{end}}' \
        "$name" | awk '$0 == "15432" || $0 == "16333" || $0 ~ /^\/data\/pisrs-staging(\/|$)/ {exit 2}'
    then
        stop docker_binding_conflict_or_unverified
    fi
done <<< "$names"
networks=$("${docker_cli[@]}" network ls --format '{{.Name}}')
[[ ! $'\n'"${networks}"$'\n' == *$'\n'pisrs-piki-staging$'\n'* ]] || stop project_network_exists
volumes=$("${docker_cli[@]}" volume ls --filter name=pisrs-piki --format '{{.Name}}')
[[ -z $volumes ]] || stop project_named_volume_exists
listeners=$(ss -H -ltn '( sport = :15432 or sport = :16333 )') || stop port_inventory_unverified
[[ -z $listeners ]] || stop project_port_in_use
if getent passwd 70 >/dev/null || getent group 70 >/dev/null; then stop image_uid_or_gid_in_use; fi
/usr/bin/python3 -B -c 'import sys; assert sys.version_info[:2] == (3, 14)' || stop python_version
printf 'PREFLIGHT PASS host=piki docker_root=/data/docker containers=%d data_available_kib=%s ports=15432,16333\n' "$count" "$avail"
