# PISRS PIKI agent execution contract

Before work read [Master](docs/PIKI-PISRS-MASTER.md), [API](docs/PIKI-PISRS-API.md), [Environment](docs/PIKI-PISRS-ENV.md), [Data](docs/PIKI-PISRS-DATA.md), the [Linear project](https://linear.app/openlegalcore/project/pisrs-complete-source-to-index-synchronization-b47e7deb7c78) and [OLC-91](https://linear.app/openlegalcore/issue/OLC-91/pisrs-piki-g0-g2-credentials-uradni-openapi-in-ciljna-postgresql). Follow the linked architecture, synchronization, operations and acceptance contracts for design details.

- PIKI is new permanent staging. Medo is legacy production and may be inspected only through authorized bounded reads. Keep Engine and case-law outside this work.
- G0–G2 need owner acceptance. Limit work to authorized reads, docs and design until then. No setup, service actions, schema or data writes, ingestion, deployment or experimental branches. Owner must separately authorize paid G4 operation based on local token accounting over actual PG chunks.
- Official raw OpenAPI and redacted live evidence have different scopes. Preserve original source bytes in the design. Never infer catalogue, text or file identity or numeric coverage from counts. Record PASS, FAIL, NOT_VERIFIED or NOT_RUN with evidence and one next action.
- Keep project installs and data under `/data`, including Docker/PG/Qdrant storage, WAL, logs, cache, scratch and recovery. System disk holds source checkout and essential OS config.
- Keep tokens, DSNs, protected responses and private logs out of public artifacts and tool output. Use explicit service identities, redacted evidence and noninteractive no-pager reads. Never bypass privilege controls. No copying production secrets or private data.
- This is the single staging plan and review branch. Keep the existing main, Medo, Engine and case-law untouched. Require protected workflows and owner approval for any implementation baseline.
