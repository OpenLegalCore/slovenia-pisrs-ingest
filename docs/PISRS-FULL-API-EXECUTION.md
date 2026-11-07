# PISRS — EDINI aktivni izvedbeni mandat in predaja

**Status: F4 HOLD — 7. 11. 2026.** Ta dokument je edina aktualna evidenca dejanskega napredka. Za stalne meje in protidrift pravila glej [AGENTS.md](../AGENTS.md); za rezultate končnega sprejema [A1–A9](../ACCEPTANCE_TESTS.md). **To ni odobritev produkcijskega pisanja.**

## Cilj (nespremenljiv brez izrecne odločitve lastnika)

Dokončati **en** obstoječi PISRS ingest: celoten uradno dostopen API (7 državnih katalogov, /npb, /predpis-eu, 3 lokalni /akt-ls/*, /npb-ls = **13 zbirk**, ustrezni /seznam, šifranti in besedila), vse dosegljive zgodovinske različice in izvirnike v obstoječem PostgreSQL ter pogodbeno pravilni Qdrant; zanesljiv nightly; neprekinjen Engine. Zunanji Uradni list/arhiv in dodatni sistemi niso avtomatičen obseg, če niso del PISRS API. Če API določene vsebine ne daje, označi dokazljivo omejitev namesto obljube 100 % izmišljenih besedil.

**Izvedbena zahteva:** najkrajša pot do dejanskega vira→PG→Qdrant sprejema, ne nove platforme. Ohrani stare vektorje, ne ustvarjaj novih embeddingov brez odobritve. 2–4 ure je prednostni izvedbeni čas, ne potrjena prepustnost več kot 167.000 besedilnih HTTP zahtev.

## Ena fazna tabela

| Faza | Obstoječe naloge | Stanje in prehod |
| --- | --- | --- |
| F0 Produkcija | [OLC-77](https://linear.app/openlegalcore/issue/OLC-77) | Stari nightly 7. 11. PASS; naknadna celovita integriteta ni dokazana |
| F1 Vsi katalogi | [OLC-79](https://linear.app/openlegalcore/issue/OLC-79), [OLC-80](https://linear.app/openlegalcore/issue/OLC-80) | Razvoj za 13 zbirk in aditivna shema pripravljen, trenutni uradni vir še UNKNOWN |
| F2 Besedila + zgodovina | [OLC-82](https://linear.app/openlegalcore/issue/OLC-82) | Pretočni RS/LS NPB kandidat in 404 obravnava preverjena; polni backfill NOT_RUN |
| F3 Integriteta/Qdrant | [OLC-85](https://linear.app/openlegalcore/issue/OLC-85) | Restart testi PASS; 352 NULL act_id, 44 starih datumskih razlik, provenienca in poln Qdrant parity še odprti |
| F4 Izvedba in sprejem | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) | HOLD pred produkcijskim zapisom; potrebno sveže uradno identitetno stanje + sveža povratna zaščita |
| F5 Čiščenje/predaja | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) | Po A1–A9; samo lastni odvečni artefakti + dokumentiran handoff ločeni Engine seji |

## Trenutno stanje — obvezno preberi pred vsakim obratom

**Razvojni repozitorij/veja:** `OpenLegalCore/slovenia-pisrs-ingest`, `codex/pisrs-state-catalogs-20261031`. Zadnji razvojni in dokumentacijski dokazi: [koda db0f969](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/db0f969e19c39fd4ce18599ad185f212b316cb6f), [F4 izmera 2a6ad19](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/2a6ad19aab7a2efbf32fdc3fd1fca81b0130a71f), [blokada 8511293](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/851129325e73eb2263b801631198a6cd9b5801ff). Vedno preberi dejanski HEAD, ne domnevaj.

**Produkcija:** Medo, stara izdaja `94c5b2a4182bd3f6b0c17ecf386defd4e464195f`. Zadnji potrjeni nightly **7. 11. 03:00:07–03:02:59 CET, exit 0**, naslednji načrtovan 8. 11. 03:00; timer ACTIVE ob F4 pregledu. PG 65.308 aktov, 71.649 državnih NPB, 281.338 državnih chunkov. Qdrant `pisrs_current`: green, 281.338 točk, 3072/Cosine. Števci in green niso polna skladnost. Tri nove PG tabele **ne obstajajo v produkciji**. Checkpoint in sveži backup iz neprivilegiranega konteksta **UNKNOWN**. Star backup 31. 10. je zgodovinski, ne sveža zaščita. Nobena produkcijska sprememba razvojnih obratov ni izvedena.

**Zgodovinski vir (1. 11., ne danes):** 65.271 državnih aktov, 71.635 NPB, 80.098 EU CELEX, 124.993 LS aktov, 95.682 LS NPB. V PG sta državni množici iz tega zajema v celoti prisotni, vendar **300.773 EU/LS identitet** še čaka na novo tabelo; 31.760 dokazanih zgodovinskih parov državne provenience manjka. Poleg tega 352 NULL `act_id`, 44 znanih datumskih razlik, 14 zgodovinskih chunkov in dodatni `/seznam` ID z UNKNOWN semantiko. Aktualni obseg API/število besedilnih GET/plačljivih embeddingov: **UNKNOWN**.

**Razvojni dokazi:** 179 PASS / 3 SKIPPED v izoliranem PG; GitHub CI [42367397121](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/actions/runs/42367397121) in [42367525951](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/actions/runs/42367525951) PASS. Regresija ponovitve štirih kataloških transakcijskih mej PASS. Ni preizkusa dejanskega masovnega backfilla, ni nove produkcijske migracije.

**F4 blokada:** neprivilegirani Codex kontekst ima `PISRS_API_TOKEN=UNSET`; en API poskus je dal HTTP **407 Proxy Authentication Required** (`Server: Apache`, identiteta posrednika neznana). To **ni** dokaz, da servis nima tokena: produkcijski `pisrs-ingest` dnevno uporablja varovano `/etc/pisrs-ingest.env`. Obstoječi CLI nima varnega `identity-only` podukaza za 13 zbirk; `catalog-sync --dry-run` obravnava le državne kataloge. **Odločitev lastnika 7. 11.: ODOBREN enkratni samo bralni zajem 13 zbirk pod obstoječim servisnim profilom, brez besedil/PG-Qdrant zapisov/embeddingov/izpisa poverilnic.** Zagon še ni potrjen kot izveden. **Ne sprašuj ponovno za isto odobritev.**

**Naslednji EDINI operativni korak:** z obstoječimi razvojno-klientskimi `PisrsClient.discover_*` metodami in pregledanim najmanjšim read-only izvajalnikom uporabi odobreni zaščiteni servisni profil za **en** svež identitetni popis 13 zbirk in časovno zapečaten diff proti PG. Brez nove infrastrukture. Če Codex privilegiranega zagona ne more opraviti, vrni **en konkreten najmanj privilegiran operaterski ukaz**, ne novo serijo auditov ali prošnjo za isto dovoljenje. Če ponovno 407, zabeleži tehnično blokado brez ugibanja tokena in STOP.

## Po zajemu: ena produkcijska pot

Po dejanskem izmerjenem viru in stroških pripravi **en** pregledan produkcijski korak: aktualen PG+Qdrant+checkpoint backup in izolirano obnovitev, aditivna migracija, usklajen preklop brez ponovnega zagona starega štirikataloškega nightlyja po podatkovnem zapisu, omejeni idempotentni RS/LS backfill, poln definiran vir→PG→Qdrant preizkus ter A1–A9. Produkcijski zapis, časovni posegi v servis in plačljivi embeddingi **še niso odobreni**. Zaključek šele po dejanskem timer-triggered nightlyju in tehničnem handoffu Engine seji.

## Kratka trajna predaja (ne dnevniški roman)

Na koncu vsebinskega obrata dodaj **eno največ 5-vrstično datirano posodobitev**: kaj je bilo izvedeno (dokaz), kaj se je spremenilo v produkciji, kaj ostaja UNKNOWN/BLOCKED in en naslednji korak. Obstoječi Linear issue posodobi samo za spremembo njegovega dejanskega statusa/ugotovitve. **Brez novega projekta, podvojene dokumentacije, novih nalog ali dodatnega pregleda zaradi samega pregleda.**

**Arhiv:** poln historični dnevnik in vse dotedanje odločitve ostajajo v nespremenljivi Git zgodovini pri [8511293](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/blob/851129325e73eb2263b801631198a6cd9b5801ff/docs/PISRS-FULL-API-EXECUTION.md) ter v že obstoječih Linear issues. Staro besedilo **ni** navodilo za ponovitev preteklih faz.
