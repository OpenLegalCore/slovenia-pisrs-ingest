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
| F4 Izvedba in sprejem | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) | Svež usklajen PG+Qdrant+checkpoint backup 7. 11. PASS; izolirana obnova ustavljena zaradi dejanskega pomnilniškega pritiska, zato obnovljivost nove točke UNKNOWN in produkcijski zapis HOLD |
| F5 Čiščenje/predaja | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) | Po A1–A9; samo lastni odvečni artefakti + dokumentiran handoff ločeni Engine seji |

## Trenutno stanje — obvezno preberi pred vsakim obratom

**Razvojni repozitorij/veja:** `OpenLegalCore/slovenia-pisrs-ingest`, `codex/pisrs-state-catalogs-20261031`. Zadnji razvojni in dokumentacijski dokazi: [koda db0f969](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/db0f969e19c39fd4ce18599ad185f212b316cb6f), [F4 izmera 2a6ad19](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/2a6ad19aab7a2efbf32fdc3fd1fca81b0130a71f), [blokada 8511293](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/851129325e73eb2263b801631198a6cd9b5801ff). Vedno preberi dejanski HEAD, ne domnevaj.

**Produkcija:** Medo, stara izdaja `94c5b2a4182bd3f6b0c17ecf386defd4e464195f`. Zadnji potrjeni nightly **7. 11. 03:00:07–03:02:59 CET, exit 0**, naslednji načrtovan 8. 11. 03:00; timer ACTIVE ob F4 pregledu. PG 65.308 aktov, 71.649 državnih NPB, 281.338 državnih chunkov. Qdrant `pisrs_current`: green, 281.338 točk, 3072/Cosine. Števci in green niso polna skladnost. Tri nove PG tabele **ne obstajajo v produkciji**. Svež PG+Qdrant+checkpoint komplet 7. 11. ima preverjene hashe in izvorne prstne odtise, vendar njegova izolirana obnovljivost še ni dokazana. Star backup 31. 10. ostaja zgodovinsko preverjena obnovitvena točka. Nobena produkcijska podatkovna ali servisna sprememba razvojnih obratov ni izvedena.

**Sveži vir (7. 11., 13:39–13:44 CET):** 65.308 državnih aktov, 71.649 NPB, 80.128 EU CELEX, 125.012 LS aktov in 95.735 LS NPB. Proti produkcijskemu PG posnetku istega dne (12:45 CET): obe državni identitetni množici PASS (0 manjkajočih/odvečnih); **300.875 EU/LS kataloških identitet** nima ciljne tabele v produkciji; **31.785 parov državne provenience** manjka v obeh kataloških tabelah (ista množica, brez podvajanja). PG ima 352 NULL `act_id`; po svežih državnih identitetah ima vsak enega SOP kandidata. Pri LS NPB je 6.744 nerešenih povezav (937 več kandidatov, 5.390 brez kandidata, 417 brez SOP). Besedila, zgodovinska popolnost, Qdrant in potrebni embeddingi ostajajo UNKNOWN; kataloške identitete niso besedila.

**Razvojni dokazi:** 179 PASS / 3 SKIPPED v izoliranem PG; GitHub CI [42367397121](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/actions/runs/42367397121) in [42367525951](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/actions/runs/42367525951) PASS. Regresija ponovitve štirih kataloških transakcijskih mej PASS. Ni preizkusa dejanskega masovnega backfilla, ni nove produkcijske migracije.

**F4 dostop:** neprivilegirani kontekst je prej prejel HTTP 407; odobreni enkratni bralni zajem prek zaščitenega servisnega profila `pisrs-ingest` je 7. 11. uspel. Obstoječi razvojni `PisrsClient.discover_*` je zajel vseh 13 zbirk brez besedil in brez produkcijskih zapisov. Zasebni dokazni paket: `/tmp/pisrs-f4-live-20261107-wfVQjA/`; SHA-256 `SHA256SUMS` = `86eba81b0d677a652aab2caa4d383e67bcb676e4eb272f5b70f58fa2e8945434`.

**Naslednji EDINI operativni korak:** izolirano preveriti že izdelani sveži komplet z zaporedno obnovo, ko je mogoče ohraniti varnostno mejo PSI; ne ponavljati zajema in ne uporabljati kompleta za produkcijski povratek, dokler obnova ni PASS.

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

**7. 11. 2026, F4 povratna točka:** pred izvedbo `MemAvailable=6,51 GiB` (9,49 GiB pod obvezno mejo 16 GiB); swap praktično poln, PSI some/full avg10=0,68 %, avg60=0,31 %.
**Preflight:** disk 770,8 GB na voljo; PISRS servis inactive/dead, timer active/waiting, naslednji zagon 8. 11. ob 03:00 CET.
**Rezultat:** backup NOT_RUN, restore NOT_RUN, nova preverjena povratna točka UNKNOWN; obstoječi backup in produkcija nespremenjeni.
**Blokada:** obstoječi izvajalnik zahteva >=16 GiB `MemAvailable` in PSI avg10/avg60 <1 % pred avtentikacijo; varovalka ni bila sproščena.
**Naslednje:** eno mirno okno z >=16 GiB za obstoječi zaporedni backup/restore; brez samodejnega nadaljevanja.

**7. 11. 2026, 17:12 CET, F4 ponovni poskus:** začetno `MemAvailable=19,37 GiB`, PSI avg10 0 %; odobreni enkratni izvajalnik je pridobil pravi lock in začel PG dump.
**Ustavitev:** po 20,6 s PSI avg10 some/full 1,60 % nad 1 % varovalko, RAM 18,87 GiB; PG dump delni, Qdrant snapshot in izolirana obnova NOT_RUN.
**Dokazi:** `/home/rajko/.local/state/pisrs-f4-recovery-20261107-Rt7t5H`, SHA-256 dokaznega `ROOT_SHA256SUMS` `17088e9fe2dd82043a8dfba3fa63d1bc2e2687cca0d40707961d4d5845c42eb2`; delni backup `/var/lib/pisrs-backups/backup-20261107T161235Z` NI obnovitvena točka.
**Produkcija:** 0 PG/Qdrant/checkpoint zapisov po izvajalniku, servis inactive, timer active; runtime imenik in pravi lock ustvarjena ter ohranjena, zaklep po prekinitvi prost. Celovitost novega kompleta UNKNOWN.
**Naslednje:** brez ponovitve v tem obratu; zagotoviti mirno PSI okno za en nov popoln zajem in zaporedno izolirano obnovo.

**7. 11. 2026, 17:15 CET, F4 drugi poskus:** `MemAvailable` in PSI pred izvedbo PASS, servis inactive, timer active; obstoječi izvajalnik se je dejansko zagnal kot root (dokaz `root-started.json`).
**Ustavitev:** pred backupom `other active PISRS query during preflight`; `capture=NOT_RUN`, `restore=NOT_RUN`, novi backup in obnovitvena točka nista nastala. Zaganjalnikov `BLOCKED_AUTHENTICATION_NO_ROOT_START` je časovna dirka; ni dejanski vzrok.
**Dokazi:** `/home/rajko/.local/state/pisrs-f4-recovery-20261107-LascSa`; SHA-256 dokaznega `ROOT_SHA256SUMS` `22e907bdc57ebba617c522a72213050edea55296b387fda18c994fe66d94fd61` (člani PASS, brez novega backup manifesta).
**Produkcija:** 0 PG/Qdrant/checkpoint zapisov, 0 sprememb servisa/timerja ali runtime locka; prejšnji delni komplet ostaja nepreverjena delna kopija.
**Naslednje:** brez ponovitve v tem obratu; za nov zajem zagotoviti okno brez drugih aktivnih PISRS poizvedb in miren PSI.

**7. 11. 2026, 19:03 CET, F4 predpogoj:** `MemAvailable=7,526 GiB`, primanjkljaj 8,474 GiB do nespremenjene 16 GiB meje; PSI avg10 0,05 %, avg60 0,02 %; disk 768,81 GB na voljo.
**Sistem:** `pisrs-ingest.service` inactive/dead, timer active/waiting, naslednji zagon 8. 11. ob 03:00 CET; v omejeni kontroli ni bilo najdenega servisnega zapisovalnega procesa.
**Rezultat:** RAM varovalka FAIL; backup in izolirana obnova NOT_RUN, novi identifikator in kontrolne vsote ne obstajajo.
**Produkcija:** 0 sprememb v tem obratu; stare delne kopije ostajajo nedotaknjene.
**Naslednje:** ob dejansko razpoložljivih >=16 GiB in brez sočasnih PISRS poizvedb enkrat izvesti obstoječi pregledani postopek.

**7. 11. 2026, 19:07 CET, F4 nizki RAM:** `MemAvailable=7,95 GiB`, `SwapFree≈67,8 MiB`, PSI avg10 0,09 %; disk 768,59 GB na voljo. Brez backup/restore zagona v tem obratu.
**Dokaz meje:** pregledani runbook ne zahteva 16 GiB za pretočni capture; ta prag je dodal zasebni supervisor. Pregledani restore hkrati ohranja PG (2 GiB cap) in zažene Qdrant (8 GiB cap).
**Neznanka:** uspešni restore 31. 10. je imel 22,58 GiB `MemAvailable` pred obnovo, vendar poročilo izrecno ne meri vršne porabe; iz kap ni mogoče sklepati o dejanski porabi.
**Produkcija:** 0 sprememb, brez novega backup manifesta ali obnovitvene točke; predhodni delni backup ostaja nedotaknjen.
**Naslednje:** dokazati varnost obstoječega restore pri trenutni kapaciteti, preden se spremeni samo numerični RAM guard ali začne nov zajem.

**7. 11. 2026, 20:01–20:26 CET, F4:** usklajen zajem produkcijskega PG, Qdranta in 62-bajtnega checkpointa pod pravim app zaklepom PASS; `/var/lib/pisrs-backups/backup-20261107T190129Z`, SHA-256 `SHA256SUMS` `939c350d8f11fbc0b087043d3cfecef663a3de3b3563587f0d793f6fa30cde3f`; vsi člani in ponovljeni izvorni prstni odtisi so se ujemali.
**Obnova:** izolirani PG se je začel, vendar ga je varovalo ustavilo ob `full PSI avg60=1,00 %`; PG rezultat FAIL/nedokazan, Qdrant NOT_RUN, checkpoint v zajemu PASS in izolirani odčitek NOT_RUN. Testni vsebnik je odstranjen; ponovitve ni bilo.
**Viri/dokazi:** najmanjši vzorčeni `MemAvailable=10,04 GiB`, izolirani PG vzorčno 229–244 MiB (vrh UNKNOWN); `/home/rajko/.local/state/pisrs-f4-recovery-20261107T190113Z`, SHA-256 `ROOT_SHA256SUMS` `d88b45b6b5795bce36d81a7a1343ea53747e5a49208fa8393a914d1d637f30b0`.
**Produkcija:** izvajalnik 0 zapisov v PG/Qdrant/checkpoint in 0 sprememb servisov; enoti pred/po bajtno enaki, servis inactive, timer active; končni polni izvorni fingerprint po prekinjeni obnovi NOT_RUN. Backup ohranjen, obnovljivost nove točke UNKNOWN, migracija HOLD.
**Naslednje:** samo izolirana zaporedna obnova ob varnem pomnilniškem pritisku, brez novega zajema ali produkcijskih sprememb.
