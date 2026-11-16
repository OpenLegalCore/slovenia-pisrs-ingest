# PIKI — staging environment, access, credentials and operational inventory

**Status 2026-11-16: G0 NOT_VERIFIED. No direct PIKI host inventory or credential test exists in this GitHub documentation pass.**
Project authority: [PIKI-PISRS-MASTER.md](PIKI-PISRS-MASTER.md). API authority: [PIKI-PISRS-API.md](PIKI-PISRS-API.md).

## Separation and authority

- **PIKI** is to host a new *permanent* staging PISRS ingestion deployment for test users: its own PostgreSQL instance/database, Qdrant instance/collection, state, systemd service, backups and logging. It is not an ephemeral test sandbox.
- **MEDO** is legacy production/reference. Previous inspection from PIKI reportedly found PISRS release `84b72b1` with a failing nightly since 10 November, `appdb.pisrs` and `pisrs_current` containing valuable data. Do not fix, stop, export, delete or restore anything on Medo under this staging mandate. SSH `rajko@medo` may be used read-only if already authorized. Medo service secrets are not PIKI staging credentials.
- **GitHub** existing public reference: `OpenLegalCore/slovenia-pisrs-ingest`; main commit `b2fd71f8568a36271607ce847d7f1a47325a1631` has the same file-tree content as September `aa791949...` but is **not** the new staging deployment. Choose one canonical Git strategy only once G2 is reviewed.
- **No hosting on PIKI has yet been confirmed by a privileged readout in this document**. Do not infer OS, capacity, free ports, database availability, credentials or containers from a previous PIKI shell screenshot or a Medo report.

## Immutable inventory requirements (G0)

Record **actual measured values** using non-interactive read-only commands on PIKI, with UTC/local timestamp and provenance:
1. Machine hostname/OS/kernel/architecture; timezone/NTP, current boot ID, UID/GID, SSH setup; virtualization / container runtime.
2. RAM `MemTotal/MemAvailable`, swap used/free and memory PSI, disk free, mountpoints, filesystem and inode capacity; estimate stored-source expansion after source scan, not guessed guardrails.
3. Running units, enabled/failed systemd units; Docker/Podman availability, existing containers, volumes and bind mounts, ownership; ports and listening applications. No `prune`/cleanup.
4. Presence/versions of Python, `uv`, Git, PostgreSQL server/client, Qdrant, Docker/Podman and dependency libraries.
5. Working directory path, `git status --porcelain`, exact HEAD/branch/remotes; no secret file paths exposed in public repo other than placeholder paths.
6. DNS/proxy/TLS route from **the eventual service user** to the documented authorized PISRS API; distinguish direct user `407` from service-authorized `200` and make no blind proxy changes.
7. Backup target/mount capacity, retention and **isolated restore** feasibility for PostgreSQL/Qdrant and checkpoint(s); credentials and privileges limited to staging resources.
8. Staging test-user access: required hostnames/ports, TLS certificate, ingress policy and network isolation from Medo/Engine.

**G0 proof is a timestamped private infrastructure inventory.** Git/Linear store only sanitized PASS/FAIL and references/hashes, not secrets or raw DSNs.

## Credential matrix — required before implementation

**Current state is NOT_VERIFIED for PIKI unless a live proof is attached.** Use `SET`, `UNSET`, `NOT_VERIFIED`, `INVALID` or `PASS` and a timestamp; never the credential itself.

| Role/credential | Where stored / least privilege | Verification needed | As of this document |
|---|---|---|---|
| PISRS integration API token | PIKI root-managed runtime secret, only service UID read access; no Medo copy assumed | Scope, valid official base URL, GET one low-cost catalogue sample, TLS, rate/usage permission, authorized service context | NOT_VERIFIED |
| PISRS origin and proxy CA/settings | Whitelisted `PISRS_BASE_URL`, trusted CA and service-local proxy credentials as applicable | Exact host/URL, verified TLS, expected JSON response from PIKI; distinguish source 404 and intermediary 407 | NOT_VERIFIED |
| Staging PostgreSQL admin/bootstrap | Root/operator managed (setup only) | Installed version, storage location, role model, privilege boundary, owner of persistent volume | NOT_VERIFIED |
| Staging PostgreSQL ingest role & DSN | Private service-only env/secret | `current_database()`, `current_user`, allowed schema CRUD, NOT Medo, no access other schemas | NOT_VERIFIED |
| Staging PostgreSQL reader role | Read-only role for QA and measurement | SELECT-only, no INSERT/UPDATE/DELETE or extension CREATE | NOT_VERIFIED |
| Staging Qdrant credential/API endpoint | Private service secret, staging-only collection | Health and collection metadata, exact name, safe write role only after owner approval | NOT_VERIFIED |
| OpenAI project and API key | PIKI secret store/service env | Correct project, billing state, model permission and price snapshot; **no paid embeddings or test embedding request for G0** | NOT_VERIFIED |
| OpenAI model/vector contract | Configuration, no secret | Selected model `text-embedding-3-large`, 3072 dimensions, tokenizer; verify availability and cost before G4 | PROPOSED / NOT_VERIFIED |
| Staging service UID and permissions | Local dedicated least-privileged systemd user | No shell/secrets in logs, owned data state/log dirs, limited `ReadWritePaths` | NOT_VERIFIED |
| Staging TLS/test-user auth | Reverse proxy and local credentials | Authorized users only, TLS, data exposure boundaries | NOT_VERIFIED |
| Staging backups/restore | Isolated backup role and destination | Scheduled logical PG backup, Qdrant snapshot, two checkpoint states; successful isolated restore | NOT_VERIFIED |
| SSH to Medo | Existing operator SSH key; not a staging service dependency | Read-only reachability with BatchMode; no credential copying | REPORTED / NOT_REVERIFIED |

Do not export credentials into interactive shell history, paste them into ChatGPT/Linear, add `.env` to Git, or put them in a `docker inspect`/log dump. A hidden file's mere presence is not authentication success. For operations requiring admin privileges use explicit authorized access; never bypass sudo/password controls.

## Final target topology — candidate, pending inventory and owner signoff

```text
Official approved PISRS API ──TLS/auth──> PIKI staging ingest service
                                        ├─> durable staging PostgreSQL (raw + normalized + history)
                                        ├─> source-ingest checkpoint
                                        └─> embedding planner (initially OFF)
                                                ├─> paid OpenAI only after approval
                                                ├─> Qdrant staging collection
                                                └─> vector-index checkpoint
PIKI test-user environment ──authenticated TLS──> staging read-only consumer
MEDO legacy production: isolated; zero write dependency or side effects
```

No implementation choice about native processes vs containers is approved until G0 determines PIKI resources and current services. **Choose exactly one stable deployment method**, with controlled systemd units, durable volumes and no ad hoc leftover containers. The staging DB/collection names must be approved after avoiding collisions; never default to production `appdb.pisrs` or `pisrs_current` across hosts.

## Ordered preflight gate, without surprise paid operations

**P0 (read-only local):** PIKI host/port/volume inventory; service isolation; Git HEAD and clean status.
**P1 (credentials, no values):** secret availability and correct owning UID; token validity using bounded GET with explicit owner-approved service access; no secret output. Required auth response headers/status are retained privately in redacted form.
**P2 (source):** official OpenAPI document and SHA-256; test 27 operation contracts as defined by [API](PIKI-PISRS-API.md); POST access-request is documented, *not executed*.
**P3 (target design):** exact catalog/document/version → PG mapping signed off; PG/Qdrant acceptance and index-history boundary specified before any schema creation.
**P4 (installation after owner signoff):** one permanent staging PG/Qdrant and one deployable service, backups, limited test-user ingress; verify no effects on Medo.
**P5 (data and payments):** source-to-PG complete readback first; measured chunk tokens, then explicitly approved OpenAI expenses; Qdrant parity afterwards.

Any unmet gate is **BLOCKED or NOT_VERIFIED**, not PASS. The owner decides whether to obtain missing credentials, grant least-privilege access or narrow scope. Never pretend PIKI is ready without an actual host readback.
