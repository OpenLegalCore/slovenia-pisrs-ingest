# OpenLegalCore PISRS — agent execution contract (PIKI)

**Before anything else read:**
1. [docs/PIKI-PISRS-MASTER.md](docs/PIKI-PISRS-MASTER.md) — sole project plan, gate states, scope and acceptance.
2. [docs/PIKI-PISRS-API.md](docs/PIKI-PISRS-API.md) — official API operation inventory and exact unverified contracts.
3. [docs/PIKI-PISRS-ENV.md](docs/PIKI-PISRS-ENV.md) — PIKI resources and credential readiness.
4. [docs/PIKI-PISRS-DATA.md](docs/PIKI-PISRS-DATA.md) — proposed PostgreSQL/Qdrant model, **not accepted DDL**.
5. Current [Linear PISRS project](https://linear.app/openlegalcore/project/pisrs-complete-source-to-index-synchronization-b47e7deb7c78) and [OLC-91](https://linear.app/openlegalcore/issue/OLC-91/pisrs-piki-g0-g2-credentials-uradni-openapi-in-ciljna-postgresql).

**Owner decision 2026-11-16:** PIKI is a **new permanent staging deployment**; Medo is separate legacy production. Do not fix or modify Medo, Engine or case-law systems under this work.

**Current gates G0, G1, G2 are NOT accepted.** Until verified source contracts, PIKI host/credentials and owner-accepted target mapping exist, only authorized bounded read-only inventory, source research, docs and design are allowed. No schema creation, container provisioning, service/start/stop, ingestion, paid OpenAI API calls, secret copying, deployment or unrequested Git/Linear scaffolding.

**API rule:** official Swagger `https://pisrs.si/swagger` and its government instructions are authoritative, but Swagger UI and legacy Medo reports are NOT proof of exact OpenAPI schema or live PIKI responses. Never invent an API field/path, equate catalogue ID with text/file ID, or claim 100% by catalogue counts. Name `NOT_VERIFIED` explicitly.

**Credentials:** never print/store tokens, DSNs, root passwords or protected payloads in Git, Linear, agent logs or chat. Record only SET/UNSET/NOT_VERIFIED, service-owner role, secure source, minimal proof timestamp and redacted hashes. Do not assume Medo credentials exist on PIKI. Use non-interactive no-pager commands; never bypass privilege guards.

**Preservation:** PostgreSQL is the proposed durable source archive; Qdrant is derived. No paid embeddings before PG texts, local tokenizer cost calculation and explicit owner approval. No ad hoc Docker volumes, test databases, branches or parallel master plans. No destructive cleanups outside specifically inspected PIKI-owned paths.

**Reporting:** distinguish `PASS`, `FAIL`, `NOT_VERIFIED`, `NOT_RUN`. Record verified evidence and exact blocker, not generic progress. One next action, no unnecessary new scope. Owner approval is required before G3 or paid G4.
