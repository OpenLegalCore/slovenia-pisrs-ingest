# Slovenian Legislation Ingest (PISRS)

A focused Python CLI that discovers PISRS legislative metadata and consolidated
texts (NPB), stores structured records in PostgreSQL, and maintains derived
article-aware vectors in Qdrant. This is an independent, **source-available**
component, not an official Republic of Slovenia or PISRS service, legal search
platform, legal-analysis engine, or case-law ingester.

**License:** [BUSL-1.1](LICENSE). Credentials and legislative text are not
distributed with this repository.

## Actual scope and limitations

As of **30 October 2026**, `main` implements discovery from **seven state
`/predpis/...` catalogs and `/npb`**. This is source *discovery support*,
not proof that every available act or historical text is already persisted
in production.

The remaining documented API families — EU acts (`/predpis-eu`), three
local-authority act catalogs (`/akt-ls/...`) and local consolidated texts
(`/npb-ls`) — are **not yet ingested**. Complete historical coverage and
legally accessible Official Gazette coverage are **not yet established**.
The current text pipeline processes selected NPB documents; it does not
guarantee source text for every act.

**Engineering evidence is not a completeness certificate:** the August 2026
controlled acceptance established a narrower pipeline contract, not complete
historical/current PISRS coverage. The newer state-catalog code has passed CI,
but its deployment and end-to-end completeness are not established by that fact.

The latest public tag is [v0.1.0](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/tree/v0.1.0).
The `main` branch may contain changes not present in that tag. The package
metadata currently remains `0.1.0`; do not infer deployment or release status
from the branch name or package version.

## Requirements

- Linux, Python **3.12**, [uv](https://docs.astral.sh/uv/).
- Authorized PISRS API access and credentials under the source's terms.
- A compatible **existing** PostgreSQL database/schema (`appdb/pisrs` in
  the project deployment) and Qdrant collection (`pisrs_current`).
  This repository does **not** provision PostgreSQL, install its schema, or
  create Qdrant collections.
- An embedding-provider account compatible with
  `text-embedding-3-large` / 3,072 dimensions and the target collection's
  Cosine distance contract, if new vectors are to be created.

Do not publish source credentials, provider keys, database DSNs or private
service addresses.

## Install and read-only preflight

```bash
git clone https://github.com/OpenLegalCore/slovenia-pisrs-ingest.git
cd slovenia-pisrs-ingest
uv sync --locked --no-dev
uv run pisrs-ingest --help
```

Review [`.env.example`](.env.example) and supply the required values
**outside version control**. The CLI does not automatically load a dotenv
file: export the reviewed environment through the shell or service manager.
For an ordinary non-systemd preflight, set the checkpoint and lock paths
to an existing, private writable local directory; the production systemd
`RuntimeDirectory` is created by the service, not an interactive shell.

```bash
PISRS_ALLOW_EXTERNAL_API=0 PISRS_ALLOW_WRITES=0 \
  uv run pisrs-ingest preflight
```

Preflight checks the configured targets and contracts without writing to
PostgreSQL, Qdrant, or the checkpoint and without embedding calls. A separate
read-only PISRS probe is possible with `PISRS_ALLOW_EXTERNAL_API=1` when
specifically authorized.

## Commands and safety

| Command | Function | External effects |
| --- | --- | --- |
| `pisrs-ingest preflight` | Validate configuration, PostgreSQL and Qdrant contracts | Read-only (optional authorized PISRS probe) |
| `pisrs-ingest nightly` | Discover, import, embed and synchronize | **May write PG/Qdrant, incur API cost and advance checkpoint** |
| `pisrs-ingest reconcile --dry-run` | Compare canonical PostgreSQL and Qdrant payloads | Read-only |
| `pisrs-ingest reconcile --apply` | Apply bounded payload-only corrections | **Mutates Qdrant payloads**; not a vector reindex |

**Never use `nightly` as a discovery-only probe.** The program has no
catalog-only, read-only CLI command. Do not run write-enabled commands,
backfills or scheduler changes without approval and an operation-specific
backup/rollback/readback plan.

The repository includes reviewed [systemd templates](deploy/systemd/),
**not** an automatic installer. The template timer is configured for
03:00 Europe/Ljubljana; that schedule is not a guarantee that PISRS has
already completed its own daily source refresh.

## Development checks

```bash
uv sync --locked --all-extras
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run python -m build --no-isolation
```

Use the checked-in `uv.lock`; do not silently regenerate it.
Keep changes focused. See [`AGENTS.md`](AGENTS.md) for agent
instructions, [`CONTRIBUTING.md`](CONTRIBUTING.md) for submissions,
and [`SECURITY.md`](SECURITY.md) for responsible vulnerability
reporting. Do not confuse code/test success with production completeness.

## Data contract

PostgreSQL is the authoritative local state; Qdrant `pisrs_current` is a
derived semantic index. Identity and version matching must remain
deterministic; SOP is not a safe unique act identifier. Only generate
embeddings for eligible source text, never for absent or fabricated text.
The embedding/vector contract is fixed at 3,072 dimensions and Cosine.

For official API behavior and access terms, consult
[pisrs.si/swagger/navodila](https://pisrs.si/swagger/navodila).
