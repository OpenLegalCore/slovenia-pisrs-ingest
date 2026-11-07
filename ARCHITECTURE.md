# PISRS — dejanska arhitektura, brez nove platforme

Ta dokument je **tehnična referenca**, ne načrt dodatnega razvoja. Za trenutno stanje glej [kanonični mandat](docs/PISRS-FULL-API-EXECUTION.md). Obstoječa produkcija `94c5b2a4182bd3f6b0c17ecf386defd4e464195f` se razlikuje od razvojnega 13-zbirčnega kandidata; pred posegom preveri nameščeno izdajo.

## Obstoječi podatkovni tok

`PisrsClient` → katalogi in `/besedilo/{id}` → `PostgresBoundary` → različice/HTML/bloki/chunki → obstoječi `pisrs_current` v Qdrantu (le pogodbeno indeksirani chunki) → checkpoint po uspehu. `pipeline.run_nightly` ostaja enotna pot. Za podrobnosti se uporabi **koda**, ne prepis stare implementacije.

## Identitete in kompatibilnost

| Področje | Kontrakt |
| --- | --- |
| Državni akti | `register_id`, `moped_id`; SOP ni globalno enoličen ključ |
| Državne NPB | `text_id`; verzije v `pisrs.act_text_versions`, bloki v `pisrs.act_text_blocks` |
| EU | ločen prostor identitet `EU`, CELEX |
| Lokalni akti | ločen prostor `LS_ACT` (lokalni id / `mopedPlusId` / EDA) |
| Lokalna NPB | ločen prostor `LS_NPB`, dvoumne SOP zveze niso ugibane |
| Razvojna aditivna PG migracija | `docs/sql/001_source_catalog_items.sql`: `source_catalog_items`, `source_text_versions`, `state_raw_variants` — **še ni nameščena v produkciji** |
| Obstoječi Qdrant | `pisrs_current`, UUIDv5 po `(collection_name,text_id,chunk_index)`, `text-embedding-3-large`, 3072/Cosine |
| Izvor resnice | PostgreSQL; Qdrant je izvedeni indeks; polna zgodovina v PG ni avtomatično celoten Qdrant vektorski arhiv |

Razvojni `PisrsClient` pozna 7 državnih katalogov, `/npb`, `/predpis-eu`, tri `/akt-ls/*` in `/npb-ls`. `/seznam` je ločeno opažanje, ne samodejni nov akt. EU/lokalno besedilno in zgodovinsko popolnost je treba dokazati iz uradnega vira.

Stari nightly, obstoječi API token, Postgres/Qdrant in Engine so **delujoče produkcijske odvisnosti**; ničesar ne nadomestiš ali preusmeriš zaradi kandidatne kode. Za integriteto in sprejem glej [A1–A9](ACCEPTANCE_TESTS.md).
