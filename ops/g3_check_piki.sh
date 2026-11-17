#!/usr/bin/env bash
# Read-only preflight for the permanent PIKI PostgreSQL staging install.
# Supports direct invocation by the privileged bootstrap or an operator with Docker access.
set -euo pipefail
stop() { printf 'PREFLIGHT FAIL %s\n' "$1" >&2; exit 2; }
[[ $(hostname -s) == piki ]] || stop wrong_host
root=/data/pisrs-staging
docker_cli=(/usr/bin/docker --host unix:///var/run/docker.sock)
if (( EUID != 0 )) && ! "${docker_cli[@]}" info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
    docker_cli=(sudo -n -- "${docker_cli[@]}")
fi
runtime=$("${docker_cli[@]}" info --format '{{.DockerRootDir}} {{.Driver}}') || stop docker_unavailable
[[ $runtime == '/data/docker overlayfs' ]] || stop unexpected_docker_root_or_driver
mount=$(findmnt -n --mountpoint /data -o FSTYPE,OPTIONS) || stop data_mount_unverified
[[ $mount == 'ext4 rw' || $mount == 'ext4 rw,'* ]] || stop unexpected_data_mount
avail=$(df -kP /data | awk 'NR == 2 {print $4}') || stop storage_inventory_missing
[[ $avail =~ ^[0-9]+$ ]] || stop storage_inventory_missing
(( avail > 0 )) || stop data_full
[[ ! -e $root && ! -L $root ]] || stop existing_project_path
names=$("${docker_cli[@]}" ps -a --format '{{.Names}}') || stop container_inventory_unverified
count=0
while IFS= read -r name; do
    [[ -n $name ]] || continue
    ((count+=1))
    [[ $name != pisrs-piki-pg && $name != pisrs-piki-qdrant ]] || stop project_container_exists
    bindings=$("${docker_cli[@]}" inspect --type container \
        --format '{{range .Mounts}}{{if .Source}}{{printf "mount %s\n" .Source}}{{end}}{{end}}{{range .HostConfig.PortBindings}}{{range .}}{{printf "port %s\n" .HostPort}}{{end}}{{end}}' \
        "$name") || stop docker_binding_unverified
    while IFS= read -r binding; do
        case "$binding" in
            'port 15432'|'port 16333') stop docker_port_binding_conflict ;;
            'mount '*)
                source=$(realpath -m -- "${binding#mount }") || stop docker_binding_unverified
                if [[ $source == / || $source == "$root" || $source == "$root"/* || $root == "$source"/* ]]; then
                    stop docker_mount_binding_conflict
                fi
                ;;
        esac
    done <<< "$bindings"
done <<< "$names"
networks=$("${docker_cli[@]}" network ls --format '{{.Name}}') || stop network_inventory_unverified
[[ ! $'\n'"${networks}"$'\n' == *$'\n'pisrs-piki-staging$'\n'* ]] || stop project_network_exists
volumes=$("${docker_cli[@]}" volume ls --format '{{.Name}}') || stop volume_inventory_unverified
while IFS= read -r volume; do
    case "$volume" in
        pisrs-piki|pisrs-piki-*|pisrs_piki|pisrs_piki_*) stop project_named_volume_exists ;;
    esac
done <<< "$volumes"
listeners=$(ss -H -ltn '( sport = :15432 or sport = :16333 )') || stop port_inventory_unverified
[[ -z $listeners ]] || stop project_port_in_use
for database in passwd group; do
    for identity in 70 pisrs-source pisrs-backup; do
        if getent "$database" "$identity" >/dev/null; then
            stop "identity_in_use:$database:$identity"
        elif [[ $? != 2 ]]; then
            stop "identity_inventory_unverified:$database"
        fi
    done
done
/usr/bin/python3 -B -c 'import sys; assert sys.version_info[:2] == (3, 14)' || stop python_version
printf 'PREFLIGHT PASS host=piki docker_root=/data/docker containers=%d data_available_kib=%s ports=15432,16333\n' "$count" "$avail"
