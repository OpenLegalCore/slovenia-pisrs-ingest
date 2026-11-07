# PISRS — EDINI aktivni izvedbeni mandat in predaja

**Status: F4 HOLD — 7. 11. 2026.** Ta dokument je edina aktualna evidenca dejanskega napredka. Za stalne meje in protidrift pravila glej [AGENTS.md](../AGENTS.md); za rezultate končnega sprejema [A1–A9](../ACCEPTANCE_TESTS.md). **To ni odobritev produkcijskega pisanja.**

## Cilj (nespremenljiv brez izrecne odločitve lastnika)

Dokončati **en** obstoječi PISRS ingest: celoten uradno dostopen API (7 državnih katalogov, /npb, /predpis-eu, 3 lokalni /akt-ls/*, /npb-ls = **13 zbirk**, ustrezni /seznam, šifranti in besedila), vse dosegljive zgodovinske različice in izvirnike v obstoječem PostgreSQL ter pogodbeno pravilni Qdrant; zanesljiv nightly; neprekinjen Engine. Zunanji Uradni list/arhiv in dodatni sistemi niso avtomatičen obseg, če niso del PISRS API. Če API določene vsebine ne daje, označi dokazljivo omejitev namesto obljube 100 % izmišljenih besedil.

**Izvedbena zahteva:** najkrajša pot do dejanskega vira→PG→Qdrant sprejema, ne nove platforme. Ohrani stare vektorje, ne ustvarjaj novih embeddingov brez odobritve. 2–4 ure je prednostni izvedbeni čas, ne potrjena prepustnost več kot 167.000 besedilnih HTTP zahtev.

## Ena fazna tabela

| Faza | Obstoječe naloge | Stanje in prehod |
| --- | --- | --- |
| F0 Produkcija | [OLC-77](https://linear.app/openlegalcore/issue/OLC-77) | Stari nightly 7. 11. PASS; naknadna celovita integriteta ni dokazana |
| F1 Vsi katalogi | [OLC-79](https://linear.app/openlegalcore/issue/OLC-79), [OLC-80](https://linear.app/openlegalcore/issue/OLC-80) | Razvoj za 13 zbirk in aditivna shema pripravljen; uradne identitete 7. 11. zajete, diff proti PG izmerjen |
| F2 Besedila + zgodovina | [OLC-82](https://linear.app/openlegalcore/issue/OLC-82) | Pretočni RS/LS NPB kandidat in 404 obravnava preverjena; polni backfill NOT_RUN |
| F3 Integriteta/Qdrant | [OLC-85](https://linear.app/openlegalcore/issue/OLC-85) | Restart testi PASS; 352 NULL act_id, 44 starih datumskih razlik, provenienca in poln Qdrant parity še odprti |
| F4 Izvedba in sprejem | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) | HOLD pred produkcijskim zapisom; uradne identitete izmerjene, potrebna sveža povratna zaščita |
| F5 Čiščenje/predaja | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) | Po A1–A9; samo lastni odvečni artefakti + dokumentiran handoff ločeni Engine seji |

## Trenutno stanje — obvezno preberi pred vsakim obratom

**Razvojni repozitorij/veja:** `OpenLegalCore/slovenia-pisrs-ingest`, `codex/pisrs-state-catalogs-20261031`. Zadnji razvojni in dokumentacijski dokazi: [koda db0f969](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/db0f969e19c39fd4ce18599ad185f212b316cb6f), [F4 izmera 2a6ad19](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/2a6ad19aab7a2efbf32fdc3fd1fca81b0130a71f), [blokada 8511293](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/851129325e73eb2263b801631198a6cd9b5801ff). Vedno preberi dejanski HEAD, ne domnevaj.

**Produkcija:** Medo, stara izdaja `94c5b2a4182bd3f6b0c17ecf386defd4e464195f`. Zadnji potrjeni nightly **7. 11. 03:00:07–03:02:59 CET, exit 0**, naslednji načrtovan 8. 11. 03:00; timer ACTIVE ob F4 pregledu. PG 65.308 aktov, 71.649 državnih NPB, 281.338 državnih chunkov. Qdrant `pisrs_current`: green, 281.338 točk, 3072/Cosine. Števci in green niso polna skladnost. Tri nove PG tabele **ne obstajajo v produkciji**. Checkpoint in sveži backup iz neprivilegiranega konteksta **UNKNOWN**. Star backup 31. 10. je zgodovinski, ne sveža zaščita. Nobena produkcijska sprememba razvojnih obratov ni izvedena.

**Sveži vir (7. 11., 13:39–13:44 CET):** 65.308 državnih aktov, 71.649 NPB, 80.128 EU CELEX, 125.012 LS aktov in 95.735 LS NPB. Proti produkcijskemu PG posnetku istega dne (12:45 CET): obe državni identitetni množici PASS (0 manjkajočih/odvečnih); **300.875 EU/LS kataloških identitet** nima ciljne tabele v produkciji; **31.785 parov državne provenience** manjka v obeh kataloških tabelah (ista množica, brez podvajanja). PG ima 352 NULL `act_id`; po svežih državnih identitetah ima vsak enega SOP kandidata. Pri LS NPB je 6.744 nerešenih povezav (937 več kandidatov, 5.390 brez kandidata, 417 brez SOP). Besedila, zgodovinska popolnost, Qdrant in potrebni embeddingi ostajajo UNKNOWN; kataloške identitete niso besedila.

**Razvojni dokazi:** 179 PASS / 3 SKIPPED v izoliranem PG; GitHub CI [42367397121](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/actions/runs/42367397121) in [42367525951](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/actions/runs/42367525951) PASS. Regresija ponovitve štirih kataloških transakcijskih mej PASS. Ni preizkusa dejanskega masovnega backfilla, ni nove produkcijske migracije.

**F4 dostop:** neprivilegirani kontekst je prej prejel HTTP 407; odobreni enkratni bralni zajem prek zaščitenega servisnega profila `pisrs-ingest` je 7. 11. uspel. Obstoječi razvojni `PisrsClient.discover_*` je zajel vseh 13 zbirk brez besedil in brez produkcijskih zapisov. Zasebni dokazni paket: `/tmp/pisrs-f4-live-20261107-wfVQjA/`; SHA-256 `SHA256SUMS` = `86eba81b0d677a652aab2caa4d383e67bcb676e4eb272f5b70f58fa2e8945434`.

**Naslednji EDINI operativni korak:** pred odobritvijo produkcijskih podatkovnih sprememb pripraviti svežo, preverjeno PG+Qdrant+checkpoint povratno točko za točno izmerjen obseg. Brez samodejnega zapisa ali aktivacije.

## Po zajemu: ena produkcijska pot

Po dejanskem izmerjenem viru in stroških pripravi **en** pregledan produkcijski korak: aktualen PG+Qdrant+checkpoint backup in izolirano obnovitev, aditivna migracija, usklajen preklop brez ponovnega zagona starega štirikataloškega nightlyja po podatkovnem zapisu, omejeni idempotentni RS/LS backfill, poln definiran vir→PG→Qdrant preizkus ter A1–A9. Produkcijski zapis, časovni posegi v servis in plačljivi embeddingi **še niso odobreni**. Zaključek šele po dejanskem timer-triggered nightlyju in tehničnem handoffu Engine seji.

## Kratka trajna predaja (ne dnevniški roman)

Na koncu vsebinskega obrata dodaj **eno največ 5-vrstično datirano posodobitev**: kaj je bilo izvedeno (dokaz), kaj se je spremenilo v produkciji, kaj ostaja UNKNOWN/BLOCKED in en naslednji korak. Obstoječi Linear issue posodobi samo za spremembo njegovega dejanskega statusa/ugotovitve. **Brez novega projekta, podvojene dokumentacije, novih nalog ali dodatnega pregleda zaradi samega pregleda.**

**Arhiv:** poln historični dnevnik in vse dotedanje odločitve ostajajo v nespremenljivi Git zgodovini pri [8511293](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/blob/851129325e73eb2263b801631198a6cd9b5801ff/docs/PISRS-FULL-API-EXECUTION.md) ter v že obstoječih Linear issues. Staro besedilo **ni** navodilo za ponovitev preteklih faz.

**7. 11. 2026, F4:** odobreni bralni zajem 13 zbirk in točen API↔PG diff PASS; dokazni SHA-256 `86eba81b0d677a652aab2caa4d383e67bcb676e4eb272f5b70f58fa2e8945434`.
**Razlike:** 0 državnih identitet, 300.875 EU/LS kataloških identitet brez ciljne tabele, 31.785 manjkajočih parov državne provenience; 352 NULL `act_id`, 6.744 nerešenih LS NPB povezav.
**Produkcija:** 0 zapisov, stari nightly/timer nespremenjena.
**UNKNOWN:** popolnost besedil/zgodovine/Qdranta, dejanski obseg embeddingov in sveža povratna točka.
**Naslednje:** sveža preverjena povratna točka pred ločeno odobrenim podatkovnim posegom.
