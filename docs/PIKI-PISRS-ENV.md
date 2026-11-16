# PIKI environment and credentials

**G0 NOT ACCEPTED.** Independent, read-only PIKI observation at 08:12 CET on 2026-11-16, using host commands outside the restricted audit mount namespace. `hostname=piki`, Ubuntu 26.04.1 LTS, kernel `7.0.0-43-generic`, x86-64, 8 logical CPUs, NTP synchronized, Europe/Ljubljana. RAM 46 GiB with 38 GiB available, swap 31 GiB with zero used at that point. `/data` ext4 mounted read/write, 402 GiB free; root filesystem 85 GiB free. Python 3.14.4, Git 2.53.0, Docker 29.9.3. Docker and containerd systemd services active. No matching PISRS/PG/Qdrant unit files, no proposed or standard PG/Qdrant TCP listeners, no named candidate or conventional service users in the bounded query. This establishes observed inventory. Effective container, volume and port reservations still require operator review.

Previous read-only configuration evidence lists Docker `data-root=/data/docker`, containerd root `/data/containerd`, Docker mount dependency on `/data`. Socket access remained unavailable to the audit account. The host operator must verify effective roots, storage-driver backend, relevant container/bind/volume inventory and port reservations. `/data` root was previously inspected as root-owned mode 0755. The project root is a proposed path. [Architecture and exact paths](PIKI-PISRS-ARCHITECTURE.md#network-and-files)

## Credential register

Store only presence and proof metadata in Git/Linear. `NOT_VERIFIED` means service identity/presence or relevant entitlement has yet to be demonstrated. The PISRS 2024 token matched the Medo service token in the owner's protected comparison and a TLS-approved PIKI request succeeded in the previous cycle. The owner confirmed on 2026-11-16 that an authorized probe credential context is currently unavailable. The new G1 pilot is NOT_RUN. Those results are recorded in [API](PIKI-PISRS-API.md) and [OLC-91](https://linear.app/openlegalcore/issue/OLC-91/pisrs-piki-g0-g2-credentials-uradni-openapi-in-ciljna-postgresql). The issuer's permitted PIKI staging usage and sustained request policy and the staging service secret context remain **NOT_VERIFIED**. No further 407 diagnostics are required for the observed working profile.

| Credential or authorization | Owner and location | Evidence to record | Rotation and recovery |
|---|---|---|---|
| PISRS API token and use grant | Source operator, private PIKI source credential from the original issuer grant if authorized. Source job reads only its own credential. | Previous owner-run reachability PASS. Issuer grant/allowed source scope, allowed host/egress, cadence and least-privileged service GET pending. | Confirm replacement or issuer permission privately; switch protected source credential at run boundary, verify bounded GET, resume source. Retain prior authorized credential only until issuer permits revocation. |
| PIKI source TLS trust/egress | Network operator, OS CA bundle or approved dedicated CA file and scoped route config. | Certificate/hostname validation in source service, route controls, dedicated context NOT_VERIFIED. | Update trust roots by staged overlap, verify approved host and reduce trust after migration. |
| PG bootstrap and migration admin | Host/DB operator, private credential read only for controlled setup/migration. DB owner is NOLOGIN by design. | Expected server identity, schema ownership and migration checksum, all NOT_VERIFIED. | Rotate after bootstrap if used; restore roles and definition from reviewed operator manifest. Application roles never get owner/admin access. |
| PG source/index/QA/backup roles | Database operator, separate service credentials; PG SCRAM over TLS. `pisrs_source` owns no schema and writes archive/ledger only. `pisrs_index` reads published source views and writes index ledger. `pisrs_qa` SELECT on approved views. `pisrs_backup` read-only dump privileges. | Prescribed role and DB, positive/negative grants, proof of no cross role or host writes NOT_VERIFIED. | Replace each role credential, drain connections from that role, reload protected files, re-run grant and identity checks. Restore credentials independently of dumps. |
| Qdrant admin and index writer | Operator controls master credential at container. Restrict the index credential to data read/write for the one project collection; creation/configuration is an operator task at G4. | TLS, allowed scoped access, rejected admin calls by readers, collection names and negative role tests NOT_VERIFIED. | Introduce new key and verify scoped collection reads before revocation. Recreate scoped keys on restore. Use a fixed scoped collection name. |
| Qdrant QA access | Read-only credential held by the restricted staging query command for the one collection. PG backup needs no Qdrant credential. | Scoped read, fail-closed publication gate and rejection of bypass/write NOT_VERIFIED. | Rotate TLS/token and validate publication/read checks. |
| OpenAI billing project and key | Billing owner and index service, separate project-restricted embedding key stored for approved use only. | Project ID provenance, approved data-use scope, model entitlement and rate snapshot. No paid probe. NOT_VERIFIED. | Disable sender first and reconcile uncertain requests. Rotate at plan boundary after owner approval, resume using durable request ledger. |
| SSH test identities and staging TLS | Access operator, separate authorized SSH identities and TLS key/cert mounts. | Individual test user, restricted command and no direct backend bypass; server name/CA verification NOT_VERIFIED. | Remove SSH access on revoke, rotate cert/key with verified trust and directed port tests. |
| Backup encryption and off-host access | Backup operator and designated recovery custodian, private encryption/transport creds outside archive. | Independent failure domain, permissions, retention, decryptability and restore proof NOT_VERIFIED. | Rotate with overlap, retain decryptability for retained manifests, run a restore after changes. |

The pre-install G0 boundary is approval of intended credentials/privileges, effective isolation and verified available evidence. Service-dependent tests for targets that have yet to be provisioned are **NOT_RUN** and must be scheduled as first G3 stop checks before source writes. No target may be assumed ready from an inventory of configured paths. Scope and approval conditions are in the [Master](PIKI-PISRS-MASTER.md).

## One operator evidence request

Provide one timestamped, redacted evidence packet in OLC-91. Use the already authorized PIKI host, database and recovery operators. Record scope, responsible role, PASS/FAIL/NOT_VERIFIED/NOT_RUN and minimal proof for each line. Keep passwords, tokens, DSNs, private endpoints and protected outputs out of the packet. This is a read-only request.

| Evidence | Operator action and return |
|---|---|
| Docker and storage | Read effective Docker `DockerRootDir` and storage driver, the running containerd root and Docker mount ordering. Compare them with the existing `/data` mount. Inspect only candidate path/port/name conflicts, live bind/volume locations and effective UID/GID ownership relevant to PIKI, and verify no unrelated moves are required. Read-only examples are `docker info --format '{{.DockerRootDir}} {{.Driver}}'`, `findmnt /data` and an operator-filtered `docker inspect --format '{{json .Mounts}}' <approved-container>`. Return only approved paths, conflict outcomes and spare capacity. |
| Staging rights and source grant | Confirm intended PG owner/roles, Qdrant writer and restricted QA read path, the three Unix identities and distinct store UIDs against reserved ports and ownership. Confirm issuer grant, permitted PIKI route, quota/cadence and availability of an authorized probe context. Test existing role/route evidence where already provisioned and authorized. Mark nonexistent-target login and negative grant checks NOT_RUN and schedule them as G3/G4 first stop checks before writes. |
| Recovery rights and capacity | Confirm `/data` backup/scratch/restore path ownership, free-space envelope, an approved independent encrypted failure domain, recovery custodian, readback entitlement and expected RPO/RTO. Verify existing destination metadata or access only. Schedule a full isolated PG recovery and Qdrant rebuild drill in G5, recording time and zero paid requests. |

The operator runs privileged reads with existing authorization; Docker group membership and new credentials are outside this request. If evidence depends on a non-provisioned target, record the pre-install decision and the exact future validation rather than forcing early provisioning. [Storage and service boundaries](PIKI-PISRS-ARCHITECTURE.md#network-and-files)

## Read-only G0 execution, 2026-11-16 at 10:08 CET

| Check | State | Evidence and remaining action |
|---|---|---|
| Docker/containerd effective state | NOT_VERIFIED | Both systemd services active. Docker requires `/data`. Readable configuration declares `/data/docker` and `/data/containerd`. Docker's effective info call with `sudo -n` returned “interactive authentication is required”. Effective storage driver, runtime roots, containers, volumes and binds still need the operator read. |
| /data and isolation | Mount PASS; isolation NOT_VERIFIED | `ext4 rw`, 402 GiB free, 30,524,473 free inodes, root:root 0755. No visible host TCP listener on 5432, 15432, 6333, 6334 or 16333. Daemon-side bind conflicts and staging isolation were not established. |
| Staging rights | NOT_VERIFIED; target grants NOT_RUN | No matching staging/database unit files, no designated service accounts, no visible proposed project data paths. PostgreSQL is scheduled for G3 and Qdrant for G4. Check actual role/UID grants and negative access before first writes. |
| Backup and restore | NOT_VERIFIED | Proposed backup, work and restore paths were not visible. No independently verified recovery destination, custodian access or agreed RPO/RTO in available records. Owner/operator decision remains open. |
| PISRS grant and context | NOT_VERIFIED | Earlier successful TLS PIKI GET and existing December 2024 credential are on record. Shell variables were UNSET and no source runtime credential path was visible. The issuer's permitted PIKI scope, cadence and restrictions remain undocumented in the available evidence. |

## Operator terminal handoff

Run the Bash block below from a normal non-root PIKI terminal, or extract the marked block into Bash from this trusted worktree file. Only the Docker inventory commands ask for sudo. The API pilot runs as the unprivileged user, requires confirmation of the issuer's allowed reads, and reads the existing token via the terminal. Its output is limited to status, shape, counts and hashes. No auth value or payload is emitted. Return only sanitized results and the backup/source-grant evidence requested above.

<!-- OLC91-HANDOFF-BEGIN -->
```bash
set +x
[ "$(hostname -s)" = piki ] && [ -t 0 ] && [ "$(id -u)" -ne 0 ] || {
  printf '%s\n' 'Run as a non-root operator in a normal terminal on PIKI.'
  exit 1
}
docker_read() { sudo -- /usr/bin/docker "$@"; }
findmnt -n -o TARGET,FSTYPE,OPTIONS /data
df -hP /data | tail -n 1
if details=$(docker_read info --format '{{.DockerRootDir}} {{.Driver}}'); then
  printf 'DOCKER_RUNTIME %s\n' "$details"
  if ids=$(docker_read ps -aq); then
    if [ -n "$ids" ]; then
      # The daemon's container IDs contain only hexadecimal digits.
      for id in $ids; do
        case "$id" in *[!0-9a-f]*) printf '%s\n' 'DOCKER_INSPECT NOT_VERIFIED'; break;; esac
        docker_read inspect --type container --format '{{.Name}}|{{range .Mounts}}{{.Source}};{{end}}|{{range .HostConfig.PortBindings}}{{range .}}{{.HostPort}};{{end}}{{end}}' "$id" |
          awk -F '|' '
            $1 ~ /^\/pisrs-piki-(pg|qdrant)$/ {print "PROJECT_CONTAINER_NAME_OCCUPIED"}
            $2 ~ /(^|;)\/data\/pisrs-staging([/;]|$)/ {print "PROJECT_BIND_OCCUPIED"}
            $3 ~ /(^|;)(15432|16333);/ {print "PROJECT_PORT_BINDING_OCCUPIED"}
          '
        [ "${PIPESTATUS[0]}" -eq 0 ] || printf '%s\n' 'DOCKER_INSPECT NOT_VERIFIED'
      done
    else
      printf '%s\n' 'NO_DOCKER_CONTAINERS'
    fi
  fi
  volumes=$(docker_read volume ls --filter name=pisrs --format '{{.Name}}') || printf '%s\n' 'DOCKER_VOLUMES NOT_VERIFIED'
  for volume in $volumes; do
    case "$volume" in
      pisrs-piki-*|pisrs_piki_*)
        docker_read volume inspect --format '{{.Mountpoint}}' "$volume" |
          awk '/^\/data\// {print "PROJECT_NAMED_VOLUME_UNDER_DATA"; next} {print "PROJECT_NAMED_VOLUME_OUTSIDE_DATA"}'
        [ "${PIPESTATUS[0]}" -eq 0 ] || printf '%s\n' 'PROJECT_VOLUME_MOUNT NOT_VERIFIED'
        ;;
    esac
  done
fi
pid=$(systemctl show containerd.service -p MainPID --value)
if [ "${pid:-0}" -gt 0 ] && [ -r "/proc/$pid/cmdline" ]; then
  python3 - "$pid" <<'PY'
from pathlib import Path
import sys, tomllib
try:
    args = Path(f"/proc/{int(sys.argv[1])}/cmdline").read_bytes().decode().strip("\0").split("\0")
    def flag(*names):
        for i, item in enumerate(args):
            for name in names:
                if item.startswith(name + "="):
                    return item.split("=", 1)[1]
                if item == name:
                    return args[i + 1]
    root = flag("--root")
    config = flag("--config", "-c") or "/etc/containerd/config.toml"
    if root:
        print("CONTAINERD_PROCESS_ROOT", root if root.startswith("/data/") else "OUTSIDE_DATA")
    else:
        data = tomllib.loads(Path(config).read_text())
        root = data.get("root", "")
        print("CONTAINERD_CONFIG_ROOT", root if root.startswith("/data/") else "NOT_VERIFIED")
        print("CONTAINERD_RUNTIME_ROOT NOT_VERIFIED unless corroborated at service startup")
except (ValueError, OSError, IndexError):
    print("CONTAINERD_RUNTIME_ROOT NOT_VERIFIED")
PY
else
  printf '%s\n' 'CONTAINERD_RUNTIME_ROOT NOT_VERIFIED'
fi
ss -H -ltn | awk '$4 ~ /:(5432|15432|6333|6334|16333)$/ {print "CANDIDATE_LISTENER",$4}'
for role in pisrs-source pisrs-index pisrs-backup; do
  getent passwd "$role" | cut -d: -f1,3,4
done
for path in /data /data/pisrs-staging /data/pisrs-staging/backup /data/pisrs-staging/restore; do
  if [ -e "$path" ]; then stat -c '%n %U:%G %a' "$path"; else printf '%s NOT_VISIBLE\n' "$path"; fi
done
printf '%s\n' 'Record issuer-approved route/scope/cadence and independent encrypted backup/restore entitlement privately; return only sanitized statuses.'
python3 - <<'PY'
import getpass, hashlib, math, re, sys, time, unicodedata, warnings
from html.parser import HTMLParser
import requests

def ask(message):
    with open("/dev/tty") as tty:
        print(message, end="", file=sys.stderr, flush=True)
        return tty.readline().strip()

if ask("Issuer grant permits these PIKI reads now [yes/skip]? ") != "yes":
    print("GET_REQUESTS_EXECUTED 0/21; G1 NOT_RUN")
    raise SystemExit
warnings.simplefilter("error", getpass.GetPassWarning)
try:
    token = getpass.getpass("Existing December 2024 PISRS credential (hidden): ")
except (EOFError, getpass.GetPassWarning):
    token = ""
if not token:
    print("GET_REQUESTS_EXECUTED 0/21; G1 NOT_RUN")
    raise SystemExit

class Stop(Exception):
    pass

calls = 0
session = requests.Session()
session.headers.update({
    "Accept": "application/json, text/html",
    "Accept-Encoding": "identity",
    "User-Agent": "OpenLegalCore-pisrs-ingest/0.1.0",
    "X-API-KEY": token,
    "Authorization": f"Bearer {token}",
})
def read(path, label, **params):
    global calls
    if calls >= 21:
        raise Stop
    calls += 1
    try:
        deadline = time.monotonic() + 45
        with session.get("https://pisrs.si/extapi" + path, params=params, stream=True,
                         timeout=(8, 25), allow_redirects=False, verify=True) as response:
            mime = response.headers.get("Content-Type", "").split(";",1)[0].strip().lower()
            mime = mime if mime in ("application/json","text/html") else "other"
            print(label, "HTTP", response.status_code, mime)
            if response.status_code in (401,403,407,498) or 300 <= response.status_code < 400:
                raise Stop
            if response.status_code != 200 or mime == "other":
                return None
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                print(label, "NOT_VERIFIED_CONTENT_CODING")
                return None
            body = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                body.extend(chunk)
                if len(body) > 8 * 1024 * 1024 or time.monotonic() > deadline:
                    print(label, "BODY_LIMIT")
                    return None
            print(label, "bytes", len(body), "sha256", hashlib.sha256(body).hexdigest())
            if mime == "application/json":
                import json
                return json.loads(body)
            return bytes(body)
    except (requests.RequestException, ValueError, UnicodeError):
        print(label, "NOT_VERIFIED_TRANSPORT_OR_SHAPE")
        return None

def rows(value):
    if isinstance(value,dict) and not value.get("error"):
        data = value.get("data")
        if isinstance(data,list) and all(isinstance(row,dict) for row in data):
            return data
    return None

def page(path, label, number):
    data = read(path, f"{label} page={number}", page=number, pageSize=50)
    items = rows(data)
    if items is None:
        return None, None
    ids = [row.get("id") for row in items]
    fields = [data.get(k) for k in ("page","requestedPageSize","realPageSize","totalCount")]
    echo, requested, real, total = [v if type(v) is int else None for v in fields]
    print(label, "page", number, "echo", echo, "requested", requested, "real", real,
          "total_hint", total, "rows", len(ids))
    if echo != number or requested != 50 or real != len(ids):
        return None, total
    if not all(type(i) is int for i in ids) or len(ids) != len(set(ids)):
        return None, total
    return set(ids), total

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if self.hidden == 0:
            self.parts.append(data)

def body_text(body):
    doc = VisibleText()
    doc.feed(body.decode("utf-8", "replace"))
    return " ".join(doc.parts)

def normal(text):
    return " ".join(unicodedata.normalize("NFC",text).casefold().split())

try:
    for label, slug in ((17,"veljavni-akti"),(19,"akti-v-pripravi"),(21,"neveljavni-akti")):
        path = "/akt-ls/" + slug
        first, total = page(path,label,1)
        second, _ = page(path,label,2)
        end = math.ceil(total / 50) if type(total) is int and 0 < total <= 1_000_000 else 0
        if first and second and first.isdisjoint(second) and len(first)==len(second)==50 and end >= 3:
            last, _ = page(path,label,end)
            empty, _ = page(path,label,end+1)
            control, _ = page(path,label,end+2)
            if last and empty == set() and control == set() and last.isdisjoint(first|second):
                print(label, "BOUNDED_TERMINAL_OBSERVED; corroborate endpoint stop semantics")
                continue
        print(label,"TERMINAL NOT_VERIFIED")

    sop = ask("Known state SOP for base text and optional CELEX pair [skip=empty]: ")
    if re.fullmatch(r"\d{4}-\d{2}-\d{4}",sop):
        source = rows(read("/predpis/register-predpisov","state locator",sop=sop,page=1,pageSize=2))
        state = [row for row in (source or []) if row.get("sop")==sop and type(row.get("id")) is int]
        if len(state)==1:
            article = state[0]
            body = read("/besedilo/" + str(article["id"]), "state base text")
            marker = ask("Independently known base-version text marker, not just the title [skip=empty]: ")
            ok = isinstance(body,bytes) and bool(marker) and normal(marker) in normal(body_text(body))
            print("STATE_BASE_TEXT", "MATCH_OBSERVED" if ok else "NOT_VERIFIED")
            references = article.get("zveza")
            edges = {item["celex"] for item in (references if isinstance(references,list) else [])
                     if isinstance(item,dict) and isinstance(item.get("celex"),str)}
            eu = rows(read("/predpis-eu","targeted CELEX",celex=next(iter(edges)),page=1,pageSize=2)) if len(edges)==1 else None
            matches = [item for item in (eu or []) if item.get("celex") in edges]
            print("CELEX_EDGE", "SAMPLED_MATCH" if len(matches)==1 else "NOT_VERIFIED")
        else:
            print("STATE_BASE_TEXT NOT_VERIFIED")
    lookup = ask("Known dictionary ID and expected entry ID (two decimals) [skip=empty]: ")
    if re.fullmatch(r"[0-9]{1,19} [0-9]{1,19}",lookup):
        dictionary, entry = lookup.split()
        scoped = rows(read("/sifranti/" + dictionary,"scoped dictionary"))
        matches = [item for item in (scoped or []) if str(item.get("id"))==entry]
        print("CODE_ENTRY", "SAMPLED_MATCH" if len(matches)==1 else "NOT_VERIFIED")
    print("LOCAL_LINEAGE prior recorded Ljubljana evidence; no new assertion")
except Stop:
    print("G1_STOPPED")
finally:
    session.close()
    print(f"GET_REQUESTS_EXECUTED {calls}/21")
PY
```
<!-- OLC91-HANDOFF-END -->
