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
| Local acts in preparation, op 19 | Page 1/2: 50/50 rows; pages 1997/1998/1999: empty. All HTTP 200. First-page `totalCount=99819` is not an independently proven terminal bound. | **NOT_VERIFIED**: last nonempty page was not found. |
| Local invalid acts, op 21 | Page 1/2: 50/50 rows; pages 1997/1998/1999: empty. All HTTP 200. The repeated 99,819 hint is not an accepted record-count assertion. | **NOT_VERIFIED**: last nonempty page was not found. |
| State ZDR-1 `sop=2013-01-0784` | One state catalog response 200/JSON, 14,859 bytes, SHA-256 `7dfd6437cfcbccbfcd0145dde5bc7195bab72ff18d502bb0f2f82787f86e2711`. State base `/besedilo/{id}`: 200/`text/html`, 265,558 bytes, SHA-256 `d7a47fcafcf3faed5b185088751a7af76c76c95db8eaf0b02b6b4876da04d2b8`. | **PASS for retrieval/MIME/hash; content-to-base identity NOT_VERIFIED** because the entered comparison marker was not independently known. No evidence of wrong text. |
| CELEX edge and dictionary lookup | The optional terminal prompts received prompt text instead of an independently verified marker/numeric dictionary pair; no qualifying downstream GET was sent. | **NOT_VERIFIED / NOT_RUN** for those optional proof checks; do not report negative link/dictionary findings. |

**Targeted continuation only (not yet run, subject to an explicit new bounded read budget):** For each of ops 19 and 21, keep page size 50 and reuse **page 2 nonempty** and **page 1997 empty** as known bounds. Locate an *adjacent* nonempty/empty page boundary by integer bisection; up to 11 new GETs per operation if the source remains stable and page behavior stays monotone. Optionally confirm the empty successor and cross-page IDs within a combined **maximum 24 GETs** for both endpoints. Log page, size, status and SHA-256 only; stop if the source changes, responses are inconsistent, or authorization fails. No re-GET of pages 1, 2, 1997–1999 unless justified by observed drift. This bounded boundary check does **not** establish full source-to-PG parity; that is G3. State base-text content marker must be verified against an independent authoritative reference (not an invented phrase), and optional CELEX/dictionary controls require independently known IDs. No full catalog scan, no POST or paid calls.

| Evidence needed | Smallest approved continuation | Pass condition and decision |
|---|---|---|
| Unfiltered local pagination | For operations 17, 19 and 21, choose one allowed fixed size (pilot 50 when permitted). Read page 1 and page 2, then use existing or current count evidence only to nominate a tail pair. Request the adjacent nonempty/empty pair when the nomination is usable and at most one adjacent control. Maximum five GETs per operation with no scan toward the end. If the nomination cannot bracket a terminal boundary, request an issuer-documented boundary or an authorized reference export, and keep this item open. | Prove forward progress and no overlap in the early pair, record response page echoes, requested and delivered sizes, then observe a nonempty page and its empty successor with corroboration that this signals termination. A short or empty page with contradictory shape or ordering leaves the profile unverified. The total may change. Record endpoint, request pages, signed or redacted digest, status and counts. No record-wide parity claim. |
| State base text identity | Use one known state base catalogue ID whose act identity is independently confirmed and one issuer-sanctioned absence control only if necessary to classify non-availability. Reuse existing state NPB positive and historic body evidence. If a base ID is missing from the private evidence, allow one filtered state catalogue lookup. | Confirm correct scope, MIME and match to the intended act from the base response. Keep base and NPB locator classes separate. An unverifiable absence does not become a terminal unavailable disposition. |
| Historical and relation links | Reuse recorded ZDR-1 and Ljubljana positive associations. Use at most two targeted filtered GETs for a known populated state/CELEX pair if a private evidence pair is unavailable. Confirm relevant code-list scope from fixture or issuer; at most one additional dictionary lookup on a known ID if required for a particular mapping. | Compare exact source references and scoped targets, record evidence for resolved paths and an explicit unresolved/ambiguous rule for everything else. One success establishes the rule for that fixture. Whole-corpus lineage and temporal coverage are G3 evidence. |

Use the earlier granted request profile, verified TLS, no redirects and bounded bytes/time. Limit this continuation to 21 GETs total, and stop authentication attempts at the first rejection. Retain only sanitized case identifiers, counts, classifications and allowed hashes in OLC-91. If an issuer statement supplies equivalent scope/terminal semantics, use it in place of redundant requests. Unknown optional qualifiers remain archived with explicit unresolved status. Missing required stop behavior or inability to identify a required text locator keeps G1 open.

**G1** accepts a bounded, reproducible enumeration method, identity rules and a documented source envelope. **G3** proves complete enumeration, catalogue/list set parity, retrieved original bytes and source-wide history against PostgreSQL. G1 does not require the full scan or ingest. [Acceptance](PIKI-PISRS-ACCEPTANCE.md)
