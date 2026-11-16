# PISRS API — canonical source inventory for PIKI

**Contract status: SOURCE LIST CONFIRMED / OPENAPI SCHEMA & LIVE PIKI RESPONSES NOT VERIFIED.**
**Reviewed:** 2026-11-16. **Do not implement from this file alone.** Project authority: [PIKI-PISRS-MASTER.md](PIKI-PISRS-MASTER.md).

## Authority, provenance and method

Primary government sources:
- Official PISRS Swagger UI: https://pisrs.si/swagger (displays **PISRS API 1.0.0, OAS3**).
- Official operation/field guide: https://pisrs.si/swagger/navodila (sections 3, 4.1–4.5).
- An *actual machine-readable OpenAPI JSON/YAML download and SHA-256* has **NOT** yet been obtained, checked into this branch or verified from PIKI. `openapi_document_url`, exact `servers`, `securitySchemes`, `components.schemas`, HTTP error structures, query parameter types and pagination DTOs are all **NOT_VERIFIED**. A Swagger UI listing is not proof of all hidden/undocumented API capabilities.
- No authorized API request was made from PIKI in this documentation pass. The 2026-11-07 Medo catalog counts are **historic execution evidence**, not PIKI acceptance.

Evidence levels for subsequent entries:
- **OFFICIAL**: operation/field category expressly listed in government Swagger or guide.
- **LEGACY_OBSERVED**: earlier Medo code or reported real execution, not a verified PIKI contract.
- **UNVERIFIED**: exact API schema, identity meaning, response/pagination behavior, or PIKI access still requires a real authorized request.

## Exhaustive list of the 27 operations visible in official Swagger UI

| # | HTTP | Path | Controller / purpose | Evidence | Mandatory PIKI verification |
|---:|---|---|---|---|---|
| 01 | GET | `/predpis/register-predpisov` | State acts, register | OFFICIAL | PredpisDTO, filters, pagination |
| 02 | GET | `/predpis/register-predpisov/seznam` | State ID/list projection | OFFICIAL | PredpisSeznamDTO |
| 03 | GET | `/predpis/predpisi-v-pripravi` | State acts in preparation | OFFICIAL | DTO and availability |
| 04 | GET | `/predpis/predpisi-v-pripravi/seznam` | State list projection | OFFICIAL | Projection fields |
| 05 | GET | `/predpis/obsoletni-in-konzumirani-predpisi` | State obsolete/consumed acts | OFFICIAL | DTO, overlaps |
| 06 | GET | `/predpis/obsoletni-in-konzumirani-predpisi/seznam` | State list projection | OFFICIAL | Projection fields |
| 07 | GET | `/predpis/neveljavni-predpisi` | State invalid acts | OFFICIAL | DTO, historical retention |
| 08 | GET | `/predpis/neveljavni-predpisi/seznam` | State list projection | OFFICIAL | Projection fields |
| 09 | GET | `/predpis/evidenca-normodajalcev` | State norm-givers registry | OFFICIAL | Payload semantics |
| 10 | GET | `/predpis/evidenca-normodajalcev/seznam` | State list projection | OFFICIAL | Payload semantics |
| 11 | GET | `/predpis/drugi-splosni-in-posamicni-akti` | Other general/individual acts | OFFICIAL | DTO, overlaps |
| 12 | GET | `/predpis/drugi-splosni-in-posamicni-akti/seznam` | State list projection | OFFICIAL | Projection fields |
| 13 | GET | `/predpis/splosni-akti-za-izvrsevanje-javnih-pooblastil` | Acts for public powers | OFFICIAL | DTO |
| 14 | GET | `/predpis/splosni-akti-za-izvrsevanje-javnih-pooblastil/seznam` | State list projection | OFFICIAL | Projection fields |
| 15 | GET | `/npb` | State consolidated-text catalogue | OFFICIAL | NpbDTO, version identities |
| 16 | GET | `/predpis-eu` | EU legal act registry | OFFICIAL | PredpisEuDTO, CELEX |
| 17 | GET | `/akt-ls/veljavni-akti` | Local valid acts | OFFICIAL | AktDTO, status |
| 18 | GET | `/akt-ls/veljavni-akti/seznam` | Local list projection | OFFICIAL | AktSeznamDTO |
| 19 | GET | `/akt-ls/akti-v-pripravi` | Local acts in preparation | OFFICIAL | AktDTO |
| 20 | GET | `/akt-ls/akti-v-pripravi/seznam` | Local list projection | OFFICIAL | AktSeznamDTO |
| 21 | GET | `/akt-ls/neveljavni-akti` | Local invalid acts | OFFICIAL | AktDTO |
| 22 | GET | `/akt-ls/neveljavni-akti/seznam` | Local list projection | OFFICIAL | AktSeznamDTO |
| 23 | GET | `/npb-ls` | Local consolidated-text catalogue | OFFICIAL | NpbDTO; NOT a file ID |
| 24 | GET | `/besedilo/{idZbirkaElement}` | Consolidated text of **state** NPB | OFFICIAL | Actual ID semantics, HTML bytes |
| 25 | GET | `/sifranti` | Code-list catalogue | OFFICIAL | DTO and coverage |
| 26 | GET | `/sifranti/{id}` | Individual code list | OFFICIAL | Values and type |
| 27 | POST | `/api-access/request-access` | Application for PISRS API token | OFFICIAL | NOT to be invoked during inspection |

**Accounting:** 7 state act catalogues + 7 state `/seznam` + 3 local act catalogues + 3 local `/seznam` + 1 state NPB + 1 local NPB + 1 EU + 1 text + 2 code lists + 1 authorization request = **27** displayed operations. Thus **13 main catalogues** does NOT mean 13 operations total. Any subsequent OpenAPI revision that adds/removes operations requires updating this table and its source hash.

## Official DTO names visible in Swagger (schema body not yet independently extracted)

`PredpisDTO`, `PredpisSeznamDTO`, `PredpisEuDTO`, `AktDTO`, `AktSeznamDTO`, `NpbDTO`, `ZbirkaSifrantElementDTO`, `ZbirkaPovezavaPredpisEuElemnetDTO`, `ZetonZahtevekDTO`, `DataContainerDTOListPredpisDTO`, `DataContainerDTOListZbirkaSifrantElementDTO`, `DataContainerDTOListNpbDTO`, `DataContainerDTOListPredpisEuDTO`, `DataContainerDTOListAktDTO`.

These are **names, not audited schema definitions**. Enumerate every property, exact JSON case, type, nullable/optional rule, nested DTO, enum, status/error DTO, constraints, query parameter, and response media type from actual OpenAPI + redacted live responses on PIKI before G1 PASS.

## Officially documented field *meanings* (human terms, not guaranteed JSON keys)

- **State act (seven `/predpis/*`):** title, citation, abbreviation, ID, MopedID, EVA, EOA, SOP, act type/category, basic-act indicator, adoption/publication/effect/cessation/end-of-use dates, responsible entities, legal bases, incoming/outgoing amendments/influences, sub-acts, thematic classification. The guide says absent attributes may be empty.
- **State NPB (`/npb`):** NPB title, ID, document date and number; filters named EVA/SOP/EPA/document date.
- **EU (`/predpis-eu`):** title, CELEX, act type, responsible implementing/transposing organ, publication/effect/expiry/transposition-deadline dates, Official Journal citations, links to national acts, notification links, classification (guide mentions EuroVoc filters).
- **Local acts (three `/akt-ls/*`):** ID, title, short title, MOPED-PLUS identifier, EDA, SOP, spatial-act ID and indicator, legal-act index, basic-act indicator, designation/adoption/publication/effect/application/cessation/end-of-use dates, citation, act type, official gazette, category, adopting body.
- **Local NPB (`/npb-ls`):** NPB title, ID, date and document number; filters MOPED-PLUS/EDA/SOP/date.
- **State `/seznam`:** title, SOP, EVA, EPA, ID, Moped ID (guide §4.4).
- **Local `/seznam`:** title, SOP, EDA, ID, MOPED-PLUS ID (guide §4.5).
- **Code lists:** list and per-ID values and descriptions; exact ID universe NOT_VERIFIED.
- **Text:** the official Swagger calls `/besedilo/{idZbirkaElement}` the state NPB text service. It does **not** establish that local NPB IDs or EU CELEX are accepted by that endpoint.

## Pagination, refresh and access: do not invent a wire contract

Government guide: normal UI default 10 rows, UI maximum 1,000 rows/page, JSON download option for larger sets; data typically refreshed daily by ~07:00. It does **not** prove that every REST collection uses exactly `page/pageSize` with stable `totalCount` in every response. Those fields were assumed/observed in earlier Medo client code. Verify actual OpenAPI parameter names and all-page termination, plus changes between pages, explicit count and duplicate identity checks on PIKI.

PISRS access requires approved credentials issued by SVZ; exact `securitySchemes`, header name(s), expiry/rotation, scope/allowed usage, and proxy/TLS behavior are **NOT_VERIFIED on PIKI**. Do not send the access-request POST or expose tokens to prove access.

## Keep the integration API, portal and external sources separate

**Legacy observed (not an approved API contract):** during November 2026 diagnostics, PISRS portal appeared to use `/api/rezultat/zbirka/id/{MP_ID}`, `/api/rezultat/neuradno-precisceno-besedilo/{LS_NPB_ID}/details`, and file links `/api/datoteke/integracije/{FILE_ID}`. Three local HTML text examples were reported. These are **portal operations** and the file ID is not the local NPB ID. Do not build a large-scale ingestion client from these observations without proving endpoint contract, terms/permissions, source bytes, version identity and network access from PIKI.

Likewise: EUR-Lex is not the PISRS `/predpis-eu` metadata endpoint; fetching EU full texts from EUR-Lex or original gazette archives is a **separate source proposal**, subject to explicit owner scope decision.

## G1 acceptance evidence register — complete before code

For **every one of the 27 operations**, complete an evidence row containing:
`method,path,Swagger operationId,source OAS SHA256,base URL,security requirement,exact parameters/types,all response codes/content-types,all DTO nested properties,primary and alternative IDs,pagination/filters,update timestamp,source data shape,successful authorized sample ID/status/shape,source sha256,verified_at,limitations`.

Perform a bounded authorized GET with PIKI credentials and TLS (secrets redacted) for each **read** operation as appropriate; do not invoke `POST /api-access/request-access`. Prove at least one real state text, one case with historical state versions, EU and LS catalog entries, and code-list resolution. For absent content, record source-reported status and reason rather than guessing. Hash raw response bytes; avoid publishing raw sensitive data. Verify 100%-coverage possibility per operation, not just one record.

**G1 PASS requires:** machine OpenAPI definition and hash + complete field/parameter/response matrix + credentialed PIKI samples for all relevant GET families + proof of known limits. Until then G1 is **NOT_VERIFIED**.
