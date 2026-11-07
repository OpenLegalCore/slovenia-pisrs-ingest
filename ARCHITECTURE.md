# PISRS — dejanska arhitektura in nedokazani deli (RESET 8. 11. 2026)

**STOP; dokumentirano dejansko stanje ni novo razvojno dovoljenje.** Avtoriteta: [kanonični reset in API matrika](docs/PISRS-FULL-API-EXECUTION.md). Ta dokument razlikuje nameščeno kodo, obstoječe podatke in še neodobreno ciljno zasnovo.

## Trenutna nameščena arhitektura

- Produkcija Medo: po dokumentirani izvedbi nameščena izdaja `84b72b19054c3482408e154fc85ca6be41e156db`; preverjeni podatkovni prehod 7. 11. 2026. Datoteke `deploy/systemd/` so vzorci in niso dokaz dejanske enote.
- Python `PisrsClient` uporablja `requests`, HTTPS in odobren PISRS API žeton. **Produkcijski ingest ne uporablja brskalnika ali Playwrighta.** Sedaj je urnik nastavljen kot `nightly --catalogs-only`: vseh 13 katalogov, brez besedil, OpenAI/Qdranta in checkpoint zapisa. Prvi novi avtomatski zagon ob zapisu še ni preverjen.
- Državne identitete: `register_id`/`moped_id` → `pisrs.acts`, `pisrs.act_sync_catalog`; izvorne variante po endpointu → `pisrs.state_raw_variants`. Državne NPB identitete `text_id` → `pisrs.npb_catalog`.
- Obstoječa državna besedila: `/besedilo/{text_id}` → `pisrs.act_text_versions` (HTML, navadni tekst in metadata) → `pisrs.act_text_blocks`; samo pogodbeno upravičeni `pisrs.embedding_chunks` so vir za `pisrs_current`.
- EU CELEX, lokalni aktni ID/`mopedPlusId`/EDA in lokalni NPB ID → `pisrs.source_catalog_items` s `namespace` = EU, LS_ACT ali LS_NPB ter izvirnim `raw_by_endpoint`. Med vsemi tremi skupinami je bilo 7. 11. uvoženih 300.875 identitet.
- `pisrs.source_text_versions` je nameščena, **prazna** in shematsko omejena na LS_NPB; hrani HTML/tekst/bloke/člene na `source_id`, **ne** originalnih datotečnih bajtov in **ne** besedil EU ali splošnih lokalnih aktov. Samodejna napačna LS pot prek državnega `/besedilo` je izključena.
- Obstoječi Qdrant: `pisrs_current`, vektorji 3072/Cosine, model `text-embedding-3-large`, ID določen iz kolekcije/text ID/chunk index. Po poročilu je bilo ob preklopu ohranjenih 281.338 točk. **Za EU in lokalne različice ne obstaja odobren indeksni kontrakt.**

## Nepravilno enačenje virov

`/npb-ls` vrača katalog lokalnih NPB, ne ID datoteke. Uradni `/besedilo/{idZbirkaElement}` je opisan za državna NPB. Portal PISRS pri pregledanih lokalnih primerih uporablja druge `/api/rezultat/...` in `/api/datoteke/integracije/...` klice; to je od uradnega integracijskega API-ja ločena, še nekvalificirana površina. Opazovana portalna pot ni dokaz njenega dovoljenega, avtenticiranega masovnega HTTP prenosa z Meda. Prav tako 407 javnega terminalskega dostopa ne zanika uspešnega zaščitenega kataloškega API dostopa.

## Zahtevana osnova pred novo zasnovo

1. Polna, izvorno preverjena pogodba API in vseh podatkovnih entitet, vključno z zgodovino, datotečnimi formati, šifranti in pogoji dostopa.
2. Dokazljiva matrika vsako izvorno polje/različica/datoteka → konkretni PG stolpci, izvorni bajti, hash in povezave.
3. Merljiva primerjava s produkcijsko PG shemo in Qdrant kontraktom, ločeno dokazljiva izguba/ni na voljo/ni še prevzeto.
4. Lastnikova nova odločitev. Pred tem brez razvoja ali sprememb produkcije.

**Ciljno načelo za oceno (ni implementacija):** PISRS → izvirniki in metapodatki v PostgreSQL; lokalno izračunan obseg tokenov; šele posebej odobreni OpenAI embeddingi → Qdrant.
