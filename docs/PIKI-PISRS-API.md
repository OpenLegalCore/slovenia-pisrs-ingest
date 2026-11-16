# PISRS integration API

## Evidence

- **OFFICIAL_SCHEMA / PASS (independently verified on PIKI, 2026-11-16).** A single public HTTPS GET with certificate verification, identity encoding and no credentials returned 200. The [official OpenAPI](https://pisrs.si/swagger/PisrsAPI.json) is 113,337 bytes, API 1.0.0, OpenAPI 3.0.1. SHA-256 `ba228a17f852520c2f746709ae9ad43be6f15366327e36686606c9229b8b8e82`. The preceding authorized PIKI audit reports identical bytes. A hash change stops promotion pending a structural diff and review.
- **LIVE_VERIFIED (recorded PIKI evidence, 2026-11-16).** OLC-91 and the preserved local review record 26 bounded authorized GETs returning 200. Ten `/seznam` observations cover only the first streamed object. The other rows below link to redacted shape/hash evidence. No authenticated GET was repeated in this independent audit. The access-request POST is outside the ingest and was **NOT_RUN**.
- **INFERRED** means a design inference requiring verification. **NOT_VERIFIED** means the available evidence does not decide the question. **G1 acceptance remains open.**

## Transport and authorization

Use HTTPS base `https://pisrs.si/extapi`. Contract security is the global header `X-API-Key` (case-insensitive). Operation 27 has `security: []`. The observed compatible PIKI GET profile used Python requests with verified TLS, `Accept: application/json, text/html`, `User-Agent: OpenLegalCore-pisrs-ingest/0.1.0`, one `X-API-Key` and `Authorization: Bearer` carrying the same secret. The additional headers are compatibility observations. Their independent necessity is **NOT_VERIFIED**. Send credentials only to the exact approved origin. Do not follow redirects with credentials. [Swagger](https://pisrs.si/swagger) · [Official guide](https://pisrs.si/swagger/navodila)

Only 200 is declared for every operation. JSON-style 200 responses declare `*/*`; PIKI samples returned `application/json`. `/besedilo` declares `text/html`; the form POST 200 declares no response schema or media type. Status 498 for a bad token was observed by the owner on Medo. Historical 407 responses from a different request profile are evidence about that profile. Runtime 401/403/404/407/429/5xx, error payloads and source absence semantics are **NOT_VERIFIED** as an official wire contract. See [retry and classification](PIKI-PISRS-SYNC.md#attempts-and-retries).

## Operations

All paths are relative to the base URL. A parameter group expands exactly as listed below. A dash means no OpenAPI parameters.

| # | Method | Path | operationId | Parameters | 200 schema |
|---:|---|---|---|---|---|
| 01 | GET | `/predpis/register-predpisov` | `getRegisterPredpisov` | P1 | `DataContainerDTOListPredpisDTO` |
| 02 | GET | `/predpis/register-predpisov/seznam` | `getRegisterPredpisov_1` | — | `PredpisSeznamDTO[]` |
| 03 | GET | `/predpis/predpisi-v-pripravi` | `getPredpisiKiSeNeVeljajoInPredpisiVPripravi` | P2 | `DataContainerDTOListPredpisDTO` |
| 04 | GET | `/predpis/predpisi-v-pripravi/seznam` | `getPredpisiKiSeNeVeljajoInPredpisiVPripravi_1` | — | `PredpisSeznamDTO[]` |
| 05 | GET | `/predpis/obsoletni-in-konzumirani-predpisi` | `getObsoletniInKonzumiraniPredpisi` | P1 | `DataContainerDTOListPredpisDTO` |
| 06 | GET | `/predpis/obsoletni-in-konzumirani-predpisi/seznam` | `getObsoletniInKonzumiraniPredpisi_1` | — | `PredpisSeznamDTO[]` |
| 07 | GET | `/predpis/neveljavni-predpisi` | `getNeveljavniPredpisi` | P1 | `DataContainerDTOListPredpisDTO` |
| 08 | GET | `/predpis/neveljavni-predpisi/seznam` | `getNeveljavniPredpisi_1` | — | `PredpisSeznamDTO[]` |
| 09 | GET | `/predpis/evidenca-normodajalcev` | `getEvidencaNormodajalcev` | P3 | `DataContainerDTOListPredpisDTO` |
| 10 | GET | `/predpis/evidenca-normodajalcev/seznam` | `getEvidencaNormodajalcev_1` | — | `PredpisSeznamDTO[]` |
| 11 | GET | `/predpis/drugi-splosni-in-posamicni-akti` | `getDrugiSplosniInPosamicniAkti` | P1 | `DataContainerDTOListPredpisDTO` |
| 12 | GET | `/predpis/drugi-splosni-in-posamicni-akti/seznam` | `getDrugiSplosniInPosamicniAkti_1` | — | `PredpisSeznamDTO[]` |
| 13 | GET | `/predpis/splosni-akti-za-izvrsevanje-javnih-pooblastil` | `getSplosniAktiZaIzvajanjeJavnihPooblastil` | P1 | `DataContainerDTOListPredpisDTO` |
| 14 | GET | `/predpis/splosni-akti-za-izvrsevanje-javnih-pooblastil/seznam` | `getSplosniAktiZaIzvajanjeJavnihPooblastil_1` | — | `PredpisSeznamDTO[]` |
| 15 | GET | `/npb` | `getRegisterPredpisov_3` | P4 | `DataContainerDTOListNpbDTO` |
| 16 | GET | `/predpis-eu` | `getRegisterPredpisov_2` | P5 | `DataContainerDTOListPredpisEuDTO` |
| 17 | GET | `/akt-ls/veljavni-akti` | `getVeljavniAkti` | P6 | `DataContainerDTOListAktDTO` |
| 18 | GET | `/akt-ls/veljavni-akti/seznam` | `getVeljavniAkti_1` | — | `AktSeznamDTO[]` |
| 19 | GET | `/akt-ls/akti-v-pripravi` | `getAktiVPripravi` | P6 | `DataContainerDTOListAktDTO` |
| 20 | GET | `/akt-ls/akti-v-pripravi/seznam` | `getAktiVPripravi_1` | — | `AktSeznamDTO[]` |
| 21 | GET | `/akt-ls/neveljavni-akti` | `getNeveljavniAkti` | P6 | `DataContainerDTOListAktDTO` |
| 22 | GET | `/akt-ls/neveljavni-akti/seznam` | `getNeveljavniAkti_1` | — | `AktSeznamDTO[]` |
| 23 | GET | `/npb-ls` | `getRegisterPredpisov_4` | P7 | `DataContainerDTOListNpbDTO` |
| 24 | GET | `/besedilo/{idZbirkaElement}` | `getBesedilo` | P8 | `string` |
| 25 | GET | `/sifranti` | `getSifranti` | — | `DataContainerDTOListZbirkaSifrantElementDTO` |
| 26 | GET | `/sifranti/{id}` | `getSifranti_1` | P9 | `DataContainerDTOListZbirkaSifrantElementDTO` |
| 27 | POST | `/api-access/request-access` | `getZeton` | — | — |

### Exact parameter groups

Query fields are optional. The two path fields are required. Date-only strings use `format: date`. Only `page=1` and `pageSize=10` declare defaults. No OpenAPI parameter declares a minimum, maximum, enum, or custom serialization. Array query serialization follows the OpenAPI form/explode defaults; server handling of multiple values is **NOT_VERIFIED**. The guide describes a UI maximum of 1,000, and the integration cap and practical rate are **NOT_VERIFIED**.

| Group | Location | Type | Name(s) | Default |
|---|---|---|---|---|
| P1 | query | `string(date)` | `datumKoncaUporabeDo`, `datumKoncaUporabeOd`, `datumObjaveDo`, `datumObjaveOd`, `datumPrenehanjaVeljavnostiDo`, `datumPrenehanjaVeljavnostiOd`, `datumSprejetjaDo`, `datumSprejetjaOd`, `datumZacetkaUporabeDo`, `datumZacetkaUporabeOd`, `datumZacetkaVeljavnostiDo`, `datumZacetkaVeljavnostiOd` | — |
| P1 | query | `string` | `epa`, `eva`, `mopedID`, `sop` | — |
| P1 | query | `integer(int64)[]` | `kategorizacijaAkta`, `organOdgovorenZaPripravo`, `organOdgovorenZaSprejetje`, `podrocje`, `vrstaAkta` | — |
| P1 | query | `boolean` | `osnovni` | — |
| P1 | query | `integer(int32)` | `page` | 1 |
| P1 | query | `integer(int32)` | `pageSize` | 10 |
| P2 | query | `string(date)` | `datumObjaveDo`, `datumObjaveOd`, `datumSprejetjaDo`, `datumSprejetjaOd`, `datumZacetkaUporabeDo`, `datumZacetkaUporabeOd`, `datumZacetkaVeljavnostiDo`, `datumZacetkaVeljavnostiOd` | — |
| P2 | query | `string` | `epa`, `eva`, `mopedID`, `sop` | — |
| P2 | query | `integer(int64)[]` | `kategorizacijaAkta`, `organOdgovorenZaPripravo`, `organOdgovorenZaSprejetje`, `podrocje`, `vrstaAkta` | — |
| P2 | query | `boolean` | `osnovni` | — |
| P2 | query | `integer(int32)` | `page` | 1 |
| P2 | query | `integer(int32)` | `pageSize` | 10 |
| P3 | query | `integer(int64)[]` | `organOdgovorenZaPripravo`, `organOdgovorenZaSprejetje` | — |
| P3 | query | `integer(int32)` | `page` | 1 |
| P3 | query | `integer(int32)` | `pageSize` | 10 |
| P4 | query | `string(date)` | `datumDokumentaDo`, `datumDokumentaOd` | — |
| P4 | query | `string` | `epa`, `eva`, `sop` | — |
| P4 | query | `integer(int32)` | `page` | 1 |
| P4 | query | `integer(int32)` | `pageSize` | 10 |
| P5 | query | `string` | `celex`, `zvezaSop` | — |
| P5 | query | `string(date)` | `datumObjaveDo`, `datumObjaveOd`, `datumPrenehanjaVeljavnostiDo`, `datumPrenehanjaVeljavnostiOd`, `datumRokaZaPrenosDo`, `datumRokaZaPrenosOd`, `datumZacetkaVeljavnostiDo`, `datumZacetkaVeljavnostiOd` | — |
| P5 | query | `integer(int64)[]` | `euroVoc`, `organOdgovorenZaPrenosOzIzvajanje` | — |
| P5 | query | `integer(int32)` | `page` | 1 |
| P5 | query | `integer(int32)` | `pageSize` | 10 |
| P5 | query | `integer(int64)` | `vrstaAktaEu` | — |
| P6 | query | `string(date)` | `datumDolocitveOznakeDo`, `datumDolocitveOznakeOd`, `datumKoncaUporabeDo`, `datumKoncaUporabeOd`, `datumObjaveDo`, `datumObjaveOd`, `datumPrenehanjaVeljavnostiDo`, `datumPrenehanjaVeljavnostiOd`, `datumSprejetjaDo`, `datumSprejetjaOd`, `datumZacetkaUporabeDo`, `datumZacetkaUporabeOd`, `datumZacetkaVeljavnostiDo`, `datumZacetkaVeljavnostiOd` | — |
| P6 | query | `string` | `eda`, `idProstorski`, `sop` | — |
| P6 | query | `integer(int64)[]` | `idObcinskiOrganOdgovorenZaSprejetjeList`, `organOdgovorenZaSprejetje`, `podrocje`, `vrstaAkta` | — |
| P6 | query | `integer(int64)` | `idUradnoGlasilo` | — |
| P6 | query | `boolean` | `osnovni`, `prostorskiAkt` | — |
| P6 | query | `integer(int32)` | `page` | 1 |
| P6 | query | `integer(int32)` | `pageSize` | 10 |
| P7 | query | `string(date)` | `datumDokumentaDo`, `datumDokumentaOd` | — |
| P7 | query | `string` | `eda`, `sop` | — |
| P7 | query | `integer(int32)` | `page` | 1 |
| P7 | query | `integer(int32)` | `pageSize` | 10 |
| P8 | path | `integer(int64)` | `idZbirkaElement` | — |
| P9 | path | `string` | `id` | — |

Operation 27 declares an optional request body at the OpenAPI object level, of media type `application/x-www-form-urlencoded`. If present its `ZetonZahtevekDTO` requires the string properties `organizacija` and `email`. No submission or archival applies to this operation.

## DTO and pagination semantics

The exact properties, types, nested references, and typed storage destinations of all 15 schemas are in the [field matrix](PIKI-PISRS-DATA.md#field-matrix). Response schemas have no property `required` lists or `nullable` declarations. OpenAPI 3.0 defaults `nullable` to false for explicitly typed properties. Live PIKI evidence includes explicit nulls in `eva`, `eda`, dates, `podrejeniPredpisi` and EU `zveza`. The archive preserves omitted, null, empty and unexpected values and reports schema deviations before publication. The five envelopes have `data[]`, `error`, `page`, `requestedPageSize`, `realPageSize` and `totalCount`.

- **OFFICIAL_SCHEMA.** The 13 principal catalogues declare optional page controls. Ten projections are unpaginated top-level arrays. `/sifranti` and `/sifranti/{id}` have envelopes and no pagination controls. The guide mentions MOPED-PLUS filters for local records and EOA for state records. The raw integration paths have no such filter and the published state field is `epa`. The local spatial filter `idProstorski` differs from response `idProstorskiAkt`.
- **LIVE_VERIFIED.** Small pages echoed 1-based paging. Three local act catalogues and state norm-givers all reported 65,349. In the filtered local example, `totalCount` changed from 1 to 0 at the empty page. First objects from state and local projections did not match the first detail objects. The code-list catalogue returned 13 rows. One listed ID used as a decimal string resolved to 57 values. Those two responses had page and requested size zero.
- **NOT_VERIFIED.** Unfiltered terminal behavior, ordering, page caps, snapshot or change feed, relation and projection parity, all code-list values and namespaces, legal interval boundary semantics, and complete history across source records. The guide describes daily refresh around 07:00 local time. Confirm the stable sweep window with the operator. Counters are diagnostics. [Enumeration and publication](PIKI-PISRS-SYNC.md#enumeration-and-publication)

## Identities and authorized content

- **State acts, state NPB.** Numeric catalogue ID and numeric NPB ID have separate namespaces. The official description for operation 24 says it can return either a base act text for a base act ID or NPB text for a specific NPB ID. The recorded live evidence proves the state NPB case. Base-act text identity and completeness remain **NOT_VERIFIED**. Record and test both locator classes separately before using the base-act path at scale. Preserve signed publication or original attachments only when an authorized official locator and contract exist.
- **Local acts, local NPB.** Numeric act ID, `mopedPlusId`, EDA and SOP have distinct roles. SOP can suggest a version-to-base link. A conforming number ending in the base SOP and an NPB ordinal is supporting evidence only. A local NPB ID is not a portal file ID. No authorized local text route is established in this integration API.
- **EU.** Preserve exact CELEX and its dates, classification and edges. Equality or canonicalization beyond the exact source string, and a populated CELEX edge resolved to its exact target, remain **NOT_VERIFIED**. The integration contract offers EU metadata. EUR-Lex retrieval is a separate scope decision.
- **Codes and edges.** The lookup path takes an ID from the dictionary catalogue. Entry IDs and parent IDs are scoped to that dictionary unless verified otherwise. Map every usage field and resolve only with a proven target dictionary. Keep unresolved or ambiguous references alongside the original reference and direction. [Field matrix](PIKI-PISRS-DATA.md#field-matrix)

The portal uses separate routes for local files in legacy observations. Those URLs and identifiers cannot expand the integration scope without an issuer-confirmed contract and owner decision. See also the [official FAQ](https://pisrs.si/swagger/odgovori) and the [MOPED-PLUS local guide](https://www.gov.si/assets/vladne-sluzbe/SVZ/MOPED-PLUS_Navodila_1_2026_LS.pdf).

## Recorded bounded PIKI readback

Previously recorded in OLC-91 and local PIKI evidence. Complete received bodies carry a hash. Partial list samples have no body hash.

| # | OpenAPI operationId | OpenAPI response | Authorized PIKI evidence | Response SHA-256 |
|---:|---|---|---|---|
| 01 | `getRegisterPredpisov` | Envelope `PredpisDTO` | **PASS** — 200 JSON, 2 rows, reported total 15387 | `617e4e12c3978e78de3424086db82d96a15ed73f9feb68b89cd1e418788197ab` |
| 02 | `getRegisterPredpisov_1` | `PredpisSeznamDTO[]` | **PASS** — 200 JSON, array prefix, one parsed row | Partial body |
| 03 | `getPredpisiKiSeNeVeljajoInPredpisiVPripravi` | Envelope `PredpisDTO` | **PASS** — 200 JSON, 2 rows, reported total 1552 | `34f962ad23b92269ec6a4a1d4220d43f3dcc2b185a15e5c0263fb044616b8b2a` |
| 04 | `getPredpisiKiSeNeVeljajoInPredpisiVPripravi_1` | `PredpisSeznamDTO[]` | **PASS** — 200 JSON, array prefix, one parsed row | Partial body |
| 05 | `getObsoletniInKonzumiraniPredpisi` | Envelope `PredpisDTO` | **PASS** — 200 JSON, 2 rows, reported total 1493 | `fb5f4173457c45e8c67a0f9cec8746144f491acf8025197dc18ff1fe4f86aa3b` |
| 06 | `getObsoletniInKonzumiraniPredpisi_1` | `PredpisSeznamDTO[]` | **PASS** — 200 JSON, array prefix, one parsed row | Partial body |
| 07 | `getNeveljavniPredpisi` | Envelope `PredpisDTO` | **PASS** — 200 JSON, 2 rows, reported total 16643 | `3fd31379a47e3174a56c0ac338d4426899264a2540f0d5280ff56de8803dbd4d` |
| 08 | `getNeveljavniPredpisi_1` | `PredpisSeznamDTO[]` | **PASS** — 200 JSON, array prefix, one parsed row | Partial body |
| 09 | `getEvidencaNormodajalcev` | Envelope `PredpisDTO` | **PASS** — 200 JSON, 2 rows, reported total 65349 | `c532f64b717e6c65fd78a6fddcc0fe2f399056a66d0a597ad6a504ca69e8455d` |
| 10 | `getEvidencaNormodajalcev_1` | `PredpisSeznamDTO[]` | **PASS** — 200 JSON, array prefix, one parsed row | Partial body |
| 11 | `getDrugiSplosniInPosamicniAkti` | Envelope `PredpisDTO` | **PASS** — 200 JSON, 2 rows, reported total 24947 | `4e80d1a3a3339a97b13383ff4e837dbc6fc59919f6977f15bb8ca2eb22f5214b` |
| 12 | `getDrugiSplosniInPosamicniAkti_1` | `PredpisSeznamDTO[]` | **PASS** — 200 JSON, array prefix, one parsed row | Partial body |
| 13 | `getSplosniAktiZaIzvajanjeJavnihPooblastil` | Envelope `PredpisDTO` | **PASS** — 200 JSON, 2 rows, reported total 5312 | `33397582140119dd00c3cbf2c49838cff16a7958027eef3bcd163f41368264d7` |
| 14 | `getSplosniAktiZaIzvajanjeJavnihPooblastil_1` | `PredpisSeznamDTO[]` | **PASS** — 200 JSON, array prefix, one parsed row | Partial body |
| 15 | `getRegisterPredpisov_3` | Envelope `NpbDTO` | **PASS** — 200 JSON, 2 rows, reported total 71682 | `e7247a3c52ecb11efb2de8c5d8e42ffff350326839612aa2e07162ce20a08def` |
| 16 | `getRegisterPredpisov_2` | Envelope `PredpisEuDTO` | **PASS** — 200 JSON, 2 rows, reported total 80164 | `e5718817eb91fca2574cf527d22ba01f6a18ad8f3dae68af8fe1a732226a10db` |
| 17 | `getVeljavniAkti` | Envelope `AktDTO` | **PASS** — 200 JSON, 2 rows, reported total 65349 | `10ccbe807ef99615ea4178321708e422d3a24c1f9825c9a40a6d7feece5b5708` |
| 18 | `getVeljavniAkti_1` | `AktSeznamDTO[]` | **PASS** — 200 JSON, array prefix, one parsed row | Partial body |
| 19 | `getAktiVPripravi` | Envelope `AktDTO` | **PASS** — 200 JSON, 2 rows, reported total 65349 | `c532e98e6e337e26765996b6a91dacf5129a1daa471341476e02fa59af69ff37` |
| 20 | `getAktiVPripravi_1` | `AktSeznamDTO[]` | **PASS** — 200 JSON, array prefix, one parsed row | Partial body |
| 21 | `getNeveljavniAkti` | Envelope `AktDTO` | **PASS** — 200 JSON, 2 rows, reported total 65349 | `6082d4a06fa354040e393f1207ab2a0c6cec54b903fd88499c4c087f2ee4fe3a` |
| 22 | `getNeveljavniAkti_1` | `AktSeznamDTO[]` | **PASS** — 200 JSON, array prefix, one parsed row | Partial body |
| 23 | `getRegisterPredpisov_4` | Envelope `NpbDTO` | **PASS** — 200 JSON, 2 rows, reported total 95741 | `ac08ff7dcf1b4e56416f1f2fc84ae1937f8a62d6cf47802c0d2058f79edd1184` |
| 24 | `getBesedilo` | `text/html` string | **PASS** — 200 HTML, 3,804 bytes, one state NPB | `9b8ede3567febe9a31ddbc255662cecc5b70418367e9122ed28fb6c8e5cb4f8a` |
| 25 | `getSifranti` | Envelope `ZbirkaSifrantElementDTO` | **PASS** — 200 JSON, 13 rows, reported total 13 | `3876f37e71817888ec4a96354343253af1f238bb78c9dc24053b10e7b98082e4` |
| 26 | `getSifranti_1` | Envelope `ZbirkaSifrantElementDTO` | **PASS** — 200 JSON, 57 rows, reported total 57 | `0b7a369459bb13c3ae1e2c2f27aef76bf5e61a5a023f0ec8bc07ee98a2cc27cf` |
| 27 | `getZeton` | Form `ZetonZahtevekDTO` → documented 200 without response schema | **NOT_RUN**. State-changing POST documented only. | — |

### Targeted history and relationship readback

| Check | Evidence | Status |
|---|---|---|
| State act vs versions | For [ZDR-1](https://pisrs.si/pregledNpb?idPredpisa=ZAKO5944&idPredpisaChng=ZAKO8096), `sop=2013-01-0784` returned one state register record. State `/npb` reported 15 and returned five with distinct numeric IDs and dates on the sampled page. Those were NPB 10–14. Every number contained two SOPs and ended its SOP sequence with the base SOP. No NPB ID equalled the register ID. | **PASS**, sampled lineage |
| Historical text by ID | The numeric version IDs for sampled ZDR-1 NPB 10 and NPB 14 both returned `200 text/html` and whole, different bodies. NPB 10 was 279,155 bytes, SHA-256 `54da8f744f38fbfc6ae14e3ec8881349c6ea38f89b5463ee600de4e34a82b8a8`. NPB 14 was 296,807 bytes, SHA-256 `43ec2c3c030254c6027daabda85f6660583549bb9717736d82470827bfbb929f`. The different hashes establish different returned bytes. | **PASS**, two historical texts |
| Local act and NPB | For the [Ljubljana ordinance](https://pisrs.si/pregledPredpisa?sop=2015-01-4211), `sop=2015-01-4211` returned one valid local act and one local NPB metadata record with a different ID. The NPB number contained the matching SOP and had no `npbX` suffix. No local file ID was supplied. | **PASS** for bounded metadata association. Full local lineage is **NOT_VERIFIED**. |
| Local pagination termination | With the same Ljubljana SOP filter and `pageSize=2`, local valid acts returned one item and `totalCount=1` on page 1, then `data=[]`, `realPageSize=0`, `totalCount=0` on page 2. The counter changed even though the filter did not. | **PASS** for the observation. A stable `totalCount` must not be assumed. Unfiltered termination is **NOT_VERIFIED**. |
| Cross-namespace links | Some sampled MOPED relation arrays contained `mopedID` and `naziv`. The targeted state act did not contain a populated CELEX reference. The EU sample had null `zveza`. | Nested shape **PASS**, matching a live CELEX edge to its exact target **NOT_VERIFIED**. |
| Local and EU text formats | The raw spec and the successful HTML calls establish the state text route. No authorized integration route for local or EU full text was established. | **NOT_SUPPORTED_BY_API** for this reviewed contract. Availability from another source remains **NOT_VERIFIED**. |

Version ID, base act ID, document number, SOP and response hash all have distinct roles. The confirmed examples establish a useful SOP relation and historical retrieval, with no guarantee that either pattern uniquely resolves every record in the source.

## Bounded G1 closure

**Superseding owner terminal evidence, 2026-11-16:** one subsequently authorized operator execution completed **17 GETs of the previously capped 21** (all HTTP 200), with no production writes or credential disclosure. The previous Codex execution at 10:08 CET was `NOT_RUN 0/21`; do **not** confuse those two runs or re-run the original entire 17-GET handoff. The PIKI operator confirmed the limited read entitlement at the prompt; formal issuer PIKI rate/scope documentation is still **NOT_VERIFIED**. The earlier 26 bounded GET and official OpenAPI evidence remain valid.

| Owner-run target | Observed PIKI response | Interpretation / outstanding |
|---|---|---|
| Local valid acts, op 17 | Page 1/2: 50/50 rows; page 1997: 19 rows; pages 1998/1999: empty, all HTTP 200. Page 1 and 2 total hint 99,819. Page-1997 SHA-256 `9dfe3419f63b7b205bddbca6cf6acd204a7bdaa763f8e77c3589e1430f4415bc`. | **PASS only for bounded terminal observation**, not full enumeration/set parity. |
| Local acts in preparation, op 19 | Page 1/2: 50/50 rows; pages 1997/1998/1999: empty. All HTTP 200. First-page `totalCount=99819` is not an independently proven terminal bound. | Historical 17-GET bracket; the later bisection below supersedes it (PASS_BOUNDED). |
| Local invalid acts, op 21 | Page 1/2: 50/50 rows; pages 1997/1998/1999: empty. All HTTP 200. The repeated 99,819 hint is not an accepted record-count assertion. | Historical 17-GET bracket; the later bisection below supersedes it (PASS_BOUNDED). |
| State ZDR-1 `sop=2013-01-0784` | One state catalog response 200/JSON, 14,859 bytes, SHA-256 `7dfd6437cfcbccbfcd0145dde5bc7195bab72ff18d502bb0f2f82787f86e2711`. State base `/besedilo/{id}`: 200/`text/html`, 265,558 bytes, SHA-256 `d7a47fcafcf3faed5b185088751a7af76c76c95db8eaf0b02b6b4876da04d2b8`. | **PASS for retrieval/MIME/hash; content-to-base identity NOT_VERIFIED** because the entered comparison marker was not independently known. No evidence of wrong text. |
| CELEX edge and dictionary lookup | The optional terminal prompts received prompt text instead of an independently verified marker/numeric dictionary pair; no qualifying downstream GET was sent. | **NOT_VERIFIED / NOT_RUN** for those optional proof checks; do not report negative link/dictionary findings. |

### Local terminal bisection for operations 19 and 21

**Subsequent owner-run target completed — 2026-11-16 10:46:29 UTC:** **24/24 new bounded GETs, all HTTP 200**. The earlier Codex `NOT_RUN (0/24)` is superseded and retained only as historical provenance. Do **not** rerun this bisection. Each endpoint reached a sampled adjacent nonempty/empty pair with stable repeat of the last nonempty page. These observations prove bounded stop behavior for the two tested endpoints at `pageSize=50`, not a complete catalogue scan or longitudinal stability.

| Operation | Established lower bound | Established upper bound | Terminal pair |
|---|---:|---:|---|
| 19 `/akt-ls/akti-v-pripravi` | 2 (50 rows) | 1997 (empty) | **PASS_BOUNDED:** page 3 = 36 rows, page 4 = 0 rows; repeat page 3 stable |
| 21 `/akt-ls/neveljavni-akti` | 2 (50 rows) | 1997 (empty) | **PASS_BOUNDED:** page 507 = 11 rows, page 508 = 0 rows; repeat page 507 stable |

**Immutable evidence of owner-run bisection (not full enumeration):**

| Operation | Last nonempty page | Successor empty page | Control readback |
|---|---|---|---|
| 19 `akti-v-pripravi` | 3, **36** rows, 47,623 bytes, SHA-256 `746c07e7d10abf616f4205db05ce0c8428c3644329313d9082c5c30d1912bc0a` | 4, **0** rows, SHA-256 `74f5bd62748ff68c3479f85c2d1785b70b509d6d04c9ff95304d868c91f89180` | Page 3 repeated, same ordered content and SHA; `CONTROL 19 ... records-stable body-stable` |
| 21 `neveljavni-akti` | 507, **11** rows, 19,749 bytes, SHA-256 `92d7de284ea8eb05fd8364b160e080662f7763b2ca0098377fe0a16497e1c75d` | 508, **0** rows, SHA-256 `00b8d095437e7cc70ceb3086072c4ce982bb8572aaafe62744d8da19695231e4` | Page 507 repeated, same ordered content and SHA; `CONTROL 21 ... records-stable body-stable` |

The earlier first-page `totalCount=99819` on operations 19 and 21 **did not represent the actual observed terminal position**. Under the unverified assumption that pages are contiguous and stable, this would suggest **136** and **25,311** rows respectively; these are **not certified totals**. Only a full G3 sweep plus independent source-to-PG manifest/parity can certify them. The previously observed op 17 terminal pair remains valid as bounded evidence. This new execution had **0 POST, 0 embeddings, 0 source/DB writes**. Owner did not provide a formal issuer rate/standing authorization document.

Bisect the open interval at page size 50 until the bounds are adjacent. Use at most 11 search requests per endpoint and one fresh-page stability control per endpoint, with a combined ceiling of 24. Pages 1, 2 and 1997–1999 are excluded, including as controls. A control repeats a newly read boundary page, preferring the last nonempty page. Validate HTTP status, page echoes, envelope and row sizes, and int64 identities. Check uniqueness within a page and disjoint sampled identities across distinct pages of the same endpoint. Record SHA-256 of each received JSON body and compare ordered record content on the control, independently of diagnostic counter changes. Mark the affected operation NOT_VERIFIED on contradictory shape, overlap or changed records. Stop the pilot on auth, rate limit, redirect or TLS failure. A bounded pass records the sampled adjacent pair, subject to the archived bounds and stable sampled behavior. Full enumeration, source-to-PG parity and source-wide history remain G3 evidence.

**HISTORICAL REPRODUCTION ONLY — DO NOT RE-RUN.** This operator command was executed on PIKI with concealed existing token after owner confirmation for these bounded reads. It is preserved as provenance; any subsequent investigation requires a separately defined reason, request budget and authorized source scope.

```bash
python3 -c "$(awk '/^<!-- OLC91-BISECTION-BEGIN -->$/{p=1;next} /^<!-- OLC91-BISECTION-END -->$/{exit} p && !/^```/' /data/projects/pisrs-piki-staging-foundation/docs/PIKI-PISRS-API.md)"
```

<!-- OLC91-BISECTION-BEGIN -->
```python
import getpass
import hashlib
import json
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import requests

ORIGIN = "https://pisrs.si/extapi"
OPERATIONS = ((19, "/akt-ls/akti-v-pripravi"), (21, "/akt-ls/neveljavni-akti"))
OLD_PAGES = {1, 2, 1997, 1998, 1999}
PAGE_SIZE = 50

class Unverified(Exception):
    """A sampled source contract failed."""

class Stop(Unverified):
    """Stop the complete pilot after an access, rate, or budget failure."""

def unique_keys(pairs):
    values = dict(pairs)
    if len(values) != len(pairs):
        raise Unverified("duplicate-json-key")
    return values

def find_boundary(probe):
    lo, hi = 2, 1997
    for _ in range(11):
        if hi == lo + 1:
            break
        mid = (lo + hi) // 2
        if probe(mid):
            lo = mid
        else:
            hi = mid
    if hi != lo + 1:
        raise Unverified("bounds-not-adjacent")
    return lo, hi

def run(token):
    calls = 0
    print("PIKI_UTC", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with requests.Session() as session:
        session.headers.update({
            "Accept": "application/json, text/html",
            "Accept-Encoding": "identity",
            "User-Agent": "OpenLegalCore-pisrs-ingest/0.1.0",
            "X-API-KEY": token,
            "Authorization": f"Bearer {token}",
        })
        try:
            for op, path in OPERATIONS:
                samples = {}
                seen = set()
                op_calls = 0

                def probe(page, control=False):
                    nonlocal calls, op_calls
                    if page in OLD_PAGES or not 2 < page < 1997:
                        raise Stop("out-of-scope-page")
                    if calls >= 24 or op_calls >= (12 if control else 11):
                        raise Stop("request-budget")
                    calls += 1
                    op_calls += 1
                    deadline = time.monotonic() + 45
                    try:
                        with session.get(
                            ORIGIN + path, params={"page": page, "pageSize": PAGE_SIZE},
                            verify=True, allow_redirects=False, stream=True, timeout=(8, 25),
                        ) as response:
                            status = response.status_code
                            print("HTTP", op, page, status, "control" if control else "search")
                            if status in {401, 403, 407, 429, 498} or 300 <= status < 400:
                                raise Stop("auth-rate-or-redirect")
                            if status != 200:
                                raise Unverified("http-status")
                            mime = response.headers.get("Content-Type", "").partition(";")[0].strip().lower()
                            if mime != "application/json" or response.headers.get("Content-Encoding", "identity").lower() != "identity":
                                raise Unverified("response-media-or-encoding")
                            body = bytearray()
                            for chunk in response.iter_content(chunk_size=65536):
                                body.extend(chunk)
                                if len(body) > 4 * 1024 * 1024 or time.monotonic() > deadline:
                                    raise Unverified("body-bound")
                    except requests.exceptions.SSLError:
                        raise Stop("tls")
                    except requests.RequestException:
                        raise Unverified("transport") from None
                    sha = hashlib.sha256(body).hexdigest()
                    print("BODY", op, page, len(body), sha)
                    try:
                        payload = json.loads(body, object_pairs_hook=unique_keys)
                        if not isinstance(payload, dict) or payload.get("error"):
                            raise Unverified("wrapper")
                        rows = payload.get("data")
                        if not isinstance(rows, list) or not 0 <= len(rows) <= PAGE_SIZE:
                            raise Unverified("data-size")
                        if any(type(payload.get(k)) is not int or payload[k] != v for k, v in (
                            ("page", page), ("requestedPageSize", PAGE_SIZE), ("realPageSize", len(rows))
                        )):
                            raise Unverified("page-echo-or-size")
                        ids = [row.get("id") if isinstance(row, dict) else None for row in rows]
                        if any(type(i) is not int or not -(2**63) <= i < 2**63 for i in ids) or len(set(ids)) != len(ids):
                            raise Unverified("invalid-or-duplicate-id")
                        records_sha = hashlib.sha256(json.dumps(
                            rows, sort_keys=True, ensure_ascii=True, allow_nan=False,
                            separators=(",", ":")
                        ).encode()).hexdigest()
                    except (ValueError, UnicodeError, RecursionError):
                        raise Unverified("json-parse") from None
                    print("PAGE", op, page, "rows", len(rows), "requested", PAGE_SIZE)
                    if control:
                        if samples[page][2] != records_sha:
                            raise Unverified("control-records-changed")
                        print("CONTROL", op, page, "records-stable",
                              "body-stable" if samples[page][1] == sha else "wrapper-changed")
                    else:
                        if page in samples or seen.intersection(ids):
                            raise Unverified("no-progress-or-cross-page-id-overlap")
                        if any(
                            (ids and other < page and count < PAGE_SIZE)
                            or (len(ids) < PAGE_SIZE and other > page and count > 0)
                            for other, (count, _, _) in samples.items()
                        ):
                            raise Unverified("inconsistent-page-order-or-size")
                        seen.update(ids)
                        samples[page] = len(rows), sha, records_sha
                    return bool(rows)

                try:
                    last, successor = find_boundary(probe)
                    probe(last if last in samples else successor, control=True)
                    left = samples[last] if last in samples else (50, "PRIOR_17_GET", None)
                    right = samples[successor] if successor in samples else (0, "PRIOR_17_GET", None)
                    print("RESULT", op, "PASS_BOUNDED", last, left[0], left[1],
                          successor, right[0], right[1])
                except Stop:
                    raise
                except Unverified as err:
                    print("RESULT", op, "NOT_VERIFIED", str(err))
        except Stop as err:
            print("STOP", op, "NOT_VERIFIED", str(err))
        except KeyboardInterrupt:
            print("STOP", op, "NOT_VERIFIED", "interrupted")
        finally:
            print(f"NEW_GET_REQUESTS {calls}/24")

def main():
    if Path("/proc/sys/kernel/hostname").read_text().strip().split(".")[0] != "piki" or not sys.stdin.isatty():
        raise SystemExit("Run in a normal PIKI terminal. NEW_GET_REQUESTS 0/24")
    if input("Potrjen obseg in tempo za teh največ 24 bralnih zahtev [yes/skip]? ") != "yes":
        raise SystemExit("NOT_RUN; NEW_GET_REQUESTS 0/24")
    warnings.simplefilter("error", getpass.GetPassWarning)
    try:
        token = getpass.getpass("Obstoječi PISRS žeton (skriti vnos): ")
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        token = ""
    if not token or any(c.isspace() for c in token):
        raise SystemExit("NOT_RUN; NEW_GET_REQUESTS 0/24")
    run(token)

if __name__ == "__main__":
    main()
```
<!-- OLC91-BISECTION-END -->

### Remaining source identity controls

The three local terminal checks are **PASS_BOUNDED** as recorded above. That evidence and both owner-run pilots (17 + 24 GETs) are preserved. This cycle dispatched **0/3 new protected GETs** because the PIKI shell had no authorized credential context. References establish the expected identities independently of the protected responses.

| Control | Verified evidence | Remaining verification |
|---|---|---|
| ZDR-1 base, SOP `2013-01-0784` | Archived HTTP 200/MIME/length/hash above. The [original Uradni list RS 21/2013, act 784, p. 2793](https://pisrs.si/api/uradni-list/objava/u2013021.pdf) shows the December endpoint in Art. 162(4). [ZDR-1D, Uradni list RS 114/2023](https://www.uradni-list.si/_pdf/2023/Ur/u2023114.pdf), Arts. 20 and 23, adds Art. 142.a and changes that deadline. The amendment also adds a reference to Directive 2019/1152 in Art. 1. These are content discriminators beyond title equality. | **NOT_VERIFIED** for the archived HTML itself. The prior operator probe processed its bytes in memory; no matching saved body was found in known audit paths. Compare only already acquired bytes with the exact archived size/hash, the original Art. 162(4) passage and absence of later/consolidation markers. If the operator cannot recover the original bytes, obtain a separate owner decision for an equivalent issuer proof or a one-off reread. This handoff does not refetch the base or its catalogue lookup. |
| Known CELEX edge | **PASS_OFFICIAL** for ZVPot-1, SOP `2022-01-3083`, PISRS `ZAKO7054` → `32011L0083` (Directive 2011/83/EU). [Official national record, Art. 1](https://pisrs.si/Pis.web/pregledPredpisa?d-49685-p=1&d-49687-s=2&d-49688-o=2&d-49688-s=0&id=ZAKO7054) exposes the exact CELEX reference. [EUR-Lex](https://eur-lex.europa.eu/legal-content/sl/TXT/?uri=CELEX%3A32011L0083) identifies the target. | **NOT_RUN** for the integration API edge. A filtered state GET must return the exact SOP/MOPED ID and the CELEX inside `zveza[]`. Only then run a direct CELEX-target GET to establish the bounded link. No claim of reverse-edge or whole-corpus completeness. |
| Known code-list member | **PASS_OFFICIAL** for `13022` (Pravilnik) in `Vrsta akta RS` per the [API Guide, §4.2](https://pisrs.si/swagger/navodila). The earlier run confirmed scoped dictionary lookup behavior. | **NOT_RUN** for this exact scoped API lookup. Use the independent list ID from the operator's previously authorized dictionary catalogue evidence or SVZ. The member ID 13022 is not the list ID. If the list identifier is unavailable, the handoff skips the request. |

One operator run can verify the effective containerd root using a narrowly filtered live metadata DB descriptor, compare any retained ZDR-1 HTML offline, and execute at most **three new protected GETs** (two for the fixed CELEX pair and one scoped dictionary lookup). Confirm the allowed pilot scope and cadence first. The script uses the existing token via hidden terminal input, verified TLS, constrained targets, zero redirects, and no payload output. Paste only redacted status/count/size/hash lines into OLC-91. Full record-graph, versions and parity are G3 acceptance, independently of these three samples.

```bash
python3 -c "$(awk '/^<!-- OLC91-IDENTITY-BEGIN -->$/{p=1;next} /^<!-- OLC91-IDENTITY-END -->$/{exit} p && !/^```/' /data/projects/pisrs-piki-staging-foundation/docs/PIKI-PISRS-API.md)"
```

<!-- OLC91-IDENTITY-BEGIN -->
```python
import getpass
import hashlib
import json
import re
import subprocess
import sys
import time
import unicodedata
import warnings
from html.parser import HTMLParser
from pathlib import Path

import requests

BASE_SHA = "d7a47fcafcf3faed5b185088751a7af76c76c95db8eaf0b02b6b4876da04d2b8"
CELEX = "32011L0083"
SOP = "2022-01-3083"

def normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())

class Visible(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, _attrs):
        if tag in {"head", "script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"head", "script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

def base_markers(body):
    parser = Visible()
    parser.feed(body.decode("utf-8-sig"))
    text = normalize(" ".join(parser.parts))
    article = re.search(
        r"\b162\s*\.\s*člen\s*\(?izraba letnega dopusta\)?(.*?)\b163\s*\.\s*člen\b", text
    )
    return (
        bool(article and re.search(r"\(4\).*31\s*\.\s*decembra naslednjega leta", article[1]))
        and not re.search(r"\b142\s*\.\s*a\s*člen\b|pravica do odklopa|\b2019/1152\b", text)
        and not re.search(r"neuradno prečiščeno besedilo\s+(predpisa|zakona)", text)
    )

def compare_saved(path):
    if not path:
        return "NOT_RUN", "saved-body-unavailable"
    path = Path(path).expanduser()
    try:
        if not path.is_file():
            return "NOT_VERIFIED", "regular-file-required"
        with path.open("rb") as stream:
            body = stream.read(265559)
        if len(body) != 265558 or hashlib.sha256(body).hexdigest() != BASE_SHA:
            return "NOT_VERIFIED", "different-body"
        return ("PASS_BOUNDED", BASE_SHA) if base_markers(body) else ("NOT_VERIFIED", "source-markers")
    except (OSError, ValueError):
        return "NOT_VERIFIED", "cannot-read-or-decode"

def containerd():
    command = ["/usr/bin/systemctl", "show", "containerd.service", "-p", "MainPID", "--value"]
    try:
        pid = int(subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL).strip())
        if pid <= 0:
            return False
        result = subprocess.run([
            "/usr/bin/sudo", "--", "/usr/bin/find", f"/proc/{pid}/fd", "-maxdepth", "1",
            "-type", "l", "-lname", "/data/containerd/io.containerd.metadata.v1.bolt/meta.db",
            "-printf", "x",
        ], capture_output=True, check=False)
        return (result.returncode == 0 and b"x" in result.stdout
                and int(subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL)) == pid)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False

class Stop(Exception):
    pass

def api_controls(token, delay, dictionary_id):
    calls = 0
    last_start = None
    current = "CELEX_API"
    with requests.Session() as session:
        session.headers.update({
            "Accept": "application/json, text/html",
            "Accept-Encoding": "identity",
            "User-Agent": "OpenLegalCore-pisrs-ingest/0.1.0",
            "X-API-KEY": token,
            "Authorization": f"Bearer {token}",
        })

        def read(label, path, params=None):
            nonlocal calls, last_start
            if calls >= 3:
                raise Stop("request-budget")
            if last_start is not None:
                time.sleep(max(0, delay - (time.monotonic() - last_start)))
            last_start = time.monotonic()
            calls += 1
            with session.get("https://pisrs.si/extapi" + path, params=params,
                             verify=True, allow_redirects=False, stream=True, timeout=(8, 25)) as r:
                print(label, "HTTP", r.status_code)
                if r.status_code in {401,403,407,429,498} or 300 <= r.status_code < 400:
                    raise Stop("auth-rate-or-redirect")
                mime = r.headers.get("Content-Type", "").partition(";")[0].strip().lower()
                if r.status_code != 200 or mime != "application/json" or r.headers.get("Content-Encoding","identity").lower() != "identity":
                    return []
                body = bytearray()
                for chunk in r.iter_content(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > 4 * 1024 * 1024 or time.monotonic() - last_start > 45:
                        raise Stop("body-bound")
                print(label, "bytes", len(body), "sha256", hashlib.sha256(body).hexdigest())
                value = json.loads(body)
                if not isinstance(value,dict) or value.get("error"):
                    return []
                rows = value.get("data")
                return rows if isinstance(rows,list) and all(isinstance(row,dict) for row in rows) else []

        try:
            state = read("STATE", "/predpis/register-predpisov", {"sop": SOP, "page":1, "pageSize":2})
            source = [row for row in state if row.get("sop")==SOP and row.get("mopedId")=="ZAKO7054"]
            refs = source[0].get("zveza") if len(state)==len(source)==1 else None
            has_edge = isinstance(refs,list) and any(
                isinstance(ref,dict) and ref.get("celex")==CELEX for ref in refs
            )
            target = read("EU", "/predpis-eu", {"celex":CELEX, "page":1, "pageSize":2}) if has_edge else []
            matched = len(target)==1 and target[0].get("celex")==CELEX
            print("CELEX_API", "PASS_BOUNDED" if matched else "NOT_VERIFIED")
            current = "DICTIONARY_API"
            if dictionary_id:
                codes = read("DICTIONARY", "/sifranti/" + dictionary_id)
                entry = [row for row in codes if type(row.get("id")) is int and row["id"] == 13022]
                ok = len(entry)==1 and isinstance(entry[0].get("naziv"),str) and normalize(entry[0]["naziv"])=="pravilnik"
                print("DICTIONARY_API", "PASS_BOUNDED" if ok else "NOT_VERIFIED")
            else:
                print("DICTIONARY_API NOT_RUN known-list-id-required")
        except (requests.RequestException, Stop, ValueError, KeyboardInterrupt):
            print(current, "NOT_VERIFIED stopped")
        finally:
            print(f"NEW_GET_REQUESTS {calls}/3")

def main():
    if Path("/proc/sys/kernel/hostname").read_text().strip().split(".")[0] != "piki" or not sys.stdin.isatty():
        raise SystemExit("Use an ordinary PIKI terminal. NEW_GET_REQUESTS 0/3")
    if input("Izvedem ozko bralno potrditev containerd s sudo [yes/skip]? ") == "yes":
        print("CONTAINERD_RUNTIME", "PASS" if containerd() else "NOT_VERIFIED")
    print("ZDR_BASE", *compare_saved(input("Pot do ohranjenega API HTML ZDR-1 [Enter=preskoči]: ").strip()))
    if input("Dovoljen obseg in tempo za največ tri nove PIKI GET [yes/skip]? ") != "yes":
        raise SystemExit("API NOT_RUN; NEW_GET_REQUESTS 0/3")
    value = input("Najmanjši potrjeni razmik med zahtevki v sekundah [Enter=1, če dovoljeno]: ").strip() or "1"
    if not re.fullmatch(r"[1-9][0-9]{0,3}",value):
        raise SystemExit("API NOT_RUN; invalid cadence; NEW_GET_REQUESTS 0/3")
    dictionary = input("Že dokazani ID šifranta Vrsta akta RS [Enter=preskoči]: ").strip()
    if dictionary and not re.fullmatch(r"[0-9]{1,19}",dictionary):
        raise SystemExit("API NOT_RUN; unknown dictionary ID; NEW_GET_REQUESTS 0/3")
    warnings.simplefilter("error", getpass.GetPassWarning)
    try:
        token = getpass.getpass("Obstoječi PISRS žeton (skriti vnos): ")
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        token = ""
    if not token or any(c.isspace() for c in token):
        raise SystemExit("API NOT_RUN; NEW_GET_REQUESTS 0/3")
    api_controls(token, int(value), dictionary)

if __name__ == "__main__":
    main()
```
<!-- OLC91-IDENTITY-END -->
