# PISRS — kanonični izvedbeni mandat in status

**v1.0 — 7. november 2026.** Namen: trajna enotna referenca za vsako naslednjo sejo in lokalni Codex. **Status: NAČRT POTRJEN, POPOLNA SINHRONIZACIJA NI IZVEDENA.** Dokument ni odobritev za produkcijski zapis, deployment, brisanje, spremembo urnika ali plačljive embeddinge.

## Obvezno ob odpiranju nove seje

1. Preberi ta dokument, [PROJECT_GOALS.md](../PROJECT_GOALS.md), [ACCEPTANCE_TESTS.md](../ACCEPTANCE_TESTS.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [OPERATIONS.md](../OPERATIONS.md) in AGENTS.md.
2. Preveri dejanski Git remote/branch/HEAD, zadnje datirane zapise **Stanje in predaja** spodaj, obstoječe Linear naloge in uporabnikov zadnji Codex rezultat. Ne zamenjaj pregleda oblaka z dostopom do Meda.
3. Nadaljuj neposredno od zadnje dokazano izvedene faze. Ne odpiraj dodatnih projektov, vej ali nalog; ne ponavljaj uspešnih testov ali obsežnih zajemov brez razloga.
4. Po **vsakem** zaključnem Codex obratu konsolidiraj **ta isti dokument**, relevantne obstoječe Linear naloge in GitHub readback. Ob prekinitvi povej, kaj ni bilo shranjeno. Osrednji cilj je dokončan ingest, ne dokumentacija.

## Končni cilj in sprejem

En sam majhen, varen, idempotenten ingest, ki zajame **vse podatke, ki jih uradni PISRS API dejansko nudi**, v obstoječi produkcijski PostgreSQL ter ustrezno izpeljani Qdrant; pravilno ohrani vse uradno dostopne zgodovinske različice in vsebine; dnevni nightly to stanje vzdržuje.

- **API:** sedem državnih katalogov, državni `/npb`, EU `/predpis-eu`, trije lokalni `/akt-ls/…`, lokalni `/npb-ls`: **13 glavnih zbirk**; dodatno relevantni `/seznam`, šifranti in `/besedilo/{id}`. Uradni list zunaj dokazano podprtih API klicev se popiše ločeno: ne inventiraj neobstoječih endpointov ali dostopnosti vsebine.
- **PG:** pravilne identitete po imenskem prostoru vira (državni register_id/text_id, lokalni EDA/LS, EU CELEX), provenienca, surovi izvor, zgodovina, HTML, členi/odstavki/priloge, pravilni datumi in zveze.
- **Qdrant:** obstoječi `pisrs_current`, 3072/Cosine, točke in dragi vektorji ostanejo; indeksira samo **izrecno definirane upravičene** verzije/chunke. Polna PG zgodovina ne pomeni avtomatsko vektoriziranja vseh verzij. Nove zbirke/embeddingi le po posebni odobritvi in merjenem strošku.
- **Nightly:** varni inkrementalni zajem + omejen, nadaljevalen in idempotenten backfill brez podvajanja prenosov ali embeddingov; checkpoint napreduje po uspešnem zaključku.
- **Integracija:** stare produkcijske PG/Qdrant povezave, porti, poverilnice in razpoložljivost za Engine nespremenjeni; v `olc-engine` in `case-law-ingest` ni posegov. Engine prejme samo ločen zaključni tehnični handoff.
- **DONE samo ob A1–A9 PASS** iz [ACCEPTANCE_TESTS.md](../ACCEPTANCE_TESTS.md), z dokazom za vsak vir in vsak nerazpoložljiv dokument (`NOT_AVAILABLE_FROM_API` ali drug izmerjeni razlog, nikoli izmišljena vsebina). Ne razglasi 100 % na podlagi CI, enakih števcev ali primerjave PG↔Qdrant brez uradnega vira.

## Produkcijska meja in izhodišče (7. 11. 2026)

Medo hrani edino živo kopijo. Stara produkcijska izdaja `94c5b2a4182bd3f6b0c17ecf386defd4e464195f` je bila obnovljena in nightly je po uporabnikovem poročilu stekel 6. in 7. novembra. Zadnji poročani dnevni zagon **7. 11. 03:00:06–03:02:59 CET**: `documents_failed=0`, 65.308 aktov, 71.649 NPB in 4 uvožene različice. Naknadna **polna** integriteta PG↔Qdrant in checkpoint po zagonu: **UNKNOWN** zaradi omejenega dostopa. Stanje timerja ob naknadnem pregledu: **UNKNOWN**, čeprav je zagon iz journala dokazan. Zgodovinska popolna izolirana obnova PG/Qdrant/checkpoint 31. 10.: **PASS za takratni zajem**, ne aktualna povratna točka.

Sedemkataloški kandidat `21f60ad607602e8e811ce6e5aaf10f60d320fe69` in ločeni `catalog-sync` `a537ce7530c75da2ffb419c1d14803248f4d5053` ostajata razvojna artefakta, **nista** dovoljenje za produkcijsko uporabo. Dry-run 5. 11. je bil BLOCKED, ker so tri uradne identitete manjkale v PG. Ne izvajaj še enega identičnega dry-runa; ta mehanizem ima strukturno omejitev za nove akte.

Datirane nepravilnosti: ~31.760 provenance povezav, 352 NULL `act_id`, 44 datumskih razlik, 14 neaktivnih chunkov z izvenmejnimi razponi, ~16.538 dodatnih državnih `/seznam` ID z nerazčiščeno semantiko. Zgodovinska količina EU/LS: ~80.098 CELEX, ~124.993 lokalnih aktov, ~95.682 lokalnih NPB (zajem 1. 11.). Ti števci niso svež dokaz besedilne popolnosti. Pri lokalnih katalogih je bil `totalCount` opaženo nezanesljiv; potrebna verifikacija zaključka strani in neodvisna kontrola množice.

**Prepovedano brez konkretne nove odobritve:** produkcijski SQL/Qdrant zapis, `catalog-sync --apply`, act-link apply/rollback, sprememba systemd/timerja, aktivacija izdaje, checkpoint, plačljivi embeddingi, podiranje ali brisanje podatkov. Ohraniti stari delujoči nightly med razvojem. Brez avtomatskega `docker prune` in brez brisanja neznanih artefaktov. RAM ~9 GiB pomeni majhne pretočne razvojne operacije; prag 16 GiB je dogovorjen za **hkratni** produkcijski backup+izolirano obnovo, ne za vso kodo.

## Faze — edina dovoljena hierarhija

| Faza | Obstoječi Linear zapis | Deliverable / merilo za PASS | Status 7. 11. |
|---|---|---|---|
| **F0** Produkcijska osnova in vir | [OLC-77](https://linear.app/openlegalcore/issue/OLC-77), [OLC-79](https://linear.app/openlegalcore/issue/OLC-79) | datum/revizija/kontrakt, zdrav nightly, izmerjena izhodiščna pokritost; brez posega | DELNO PASS; globalna integriteta UNKNOWN |
| **F1** Vseh 13 katalogov | [OLC-79](https://linear.app/openlegalcore/issue/OLC-79), [OLC-80](https://linear.app/openlegalcore/issue/OLC-80) | vse množice identitet in provenienca, ločeni RS/LS/EU ključi, paginacija, najmanjša aditivna PG shema, ciljni API+PG testi | IN PROGRESS; EU/LS ni implementirano |
| **F2** Besedila in zgodovina | [OLC-82](https://linear.app/openlegalcore/issue/OLC-82), [OLC-85](https://linear.app/openlegalcore/issue/OLC-85) | izvirno HTML/besedilo, členi/odstavki/priloge in vse razpoložljive verzije; parser fidelity; omejen obnovljiv backfill, vsak izostanek reason-coded | NOT STARTED za globalni obseg |
| **F3** Integriteta in Qdrant | [OLC-85](https://linear.app/openlegalcore/issue/OLC-85), [OLC-82](https://linear.app/openlegalcore/issue/OLC-82) | odprava dokazljivih razlik; brez spremembe nespremenljivih ID/vektorjev; PG↔Qdrant celovitost v definiranem indeksnem obsegu | DIFF, neodobreni podatkovni popravki |
| **F4** Uvedba in A1–A9 | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) | en preverjen kandidat, izmerjeni učinki/stroški, predhodne slike in rollback, ločena odobritev, dejanski postflight in timer-triggered nightly | NOT STARTED |
| **F5** Pospravljanje in handoff | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) | dokazano odstranitev samo nepotrebnih lastnih artefaktov, disk delta, seznam zaščitenih backupov, Engine handoff brez posega vanj | NOT STARTED |

V Linear obstajajo že vse potrebne naloge; **ne ustvarjaj** novih. [OLC-78](https://linear.app/openlegalcore/issue/OLC-78) in [OLC-81](https://linear.app/openlegalcore/issue/OLC-81) sta že preklicani in vključeni v OLC-79/80; OLC-84 je preklicana dokumentacijska naloga. Ohraniti zgodovino; ne označiti ničesar za DONE brez sprejemnih dokazov.

### Izvedbeni princip: največ dva glavna cikla

1. **Enotni razvojni cikel**: iz obstoječih modulov v obstoječem repozitoriju dodaj najmanjšo potrebno podporo F1–F3. Preveri uradni kontrakt, uporabi zajete API fixture, minimalne realne zahteve, zaščitene izolirane integracijske teste in nedupliran model; izmeri realni preostali prenos/stroške. Ne izumljaj release/test/monitoring platforme. Po dejanskem razvoju commit/push na obstoječo razvojno vejo, readback in posodobi ta dokument ter Linear.
2. **Ločeno odobren produkcijski cikel**: pred pisno odobritvijo pripravi konkreten diff podatkov, povratno zaščito, neregresijske kontrole in stroške; **STOP pred produkcijskim zapisom**. Po ločeni odobritvi paketno uvozi brez rušenja starega ingesta, primerjaj vir→PG→Qdrant in opazuj pravi nightly. Šele nato F5 in DONE.

**Cilj 2–4 ur je razvojni časovni proračun, ne zagotovilo popolnega zgodovinskega prenosa.** ~167.317 besedilnih NPB identitet bi za vse zahtevke v 4h zahtevalo ~11,6 uspešnih zahtev/s brez parserja in zapisov, kar ni izmerjena ali odobrena API prepustnost. Preostali zaostanek je treba najprej izračunati iz obstoječih podatkov. Če prenos preseže okno, mora biti idempotentno nadaljevalen, ne pa razbit na nove razvojne obrate.

## Obvezno: zapis po VSAKEM obratu

Pod naslovom **Stanje in predaja** ohrani log zaključnih dogodkov (najnovejši na vrhu), ne prepisuj starih dokazov. Po vsakem obratu v istem commitu/navedeni obstoječi veji zapiši:

- UTC/CET čas; Git commit/veja in produkcijska izdaja;
- faza + PASS/DIFF/BLOCKED/UNKNOWN (navedi obseg), konkretno izvedeno, natančne javne reference in **zasebne dokaze samo s sanitiziranim opisom/hashom**;
- produkcijski zapisi/servisne spremembe (tudi izrecno 0);
- ustvarjeni, odstranjeni, ohranjeni artefakti in disk delta; brez domnevnega čiščenja;
- odprta blokada, zahtevana dovoljenja, naslednji **en** najmanjši korak; stanje naloge v Linear;
- GitHub commit/push in readback; če ni mogoče, status **NOT_PERSISTED** in kompletna predaja v izpisu.

Ne more se zaključiti po dokumentaciji ali testih, če obstaja nadaljnje neodvisno dovoljeno delo. Nikoli pa ne more samodejno izvajati zaščitenega produkcijskega posega.

## Stanje in predaja

### 2026-11-07 — CONSOLIDATION v1.0

- **Vir:** predhodni potrjeni host Codex izpisi in pregledani GitHub/Linear dokumenti. To ni sveže merjenje Meda.
- **Stanje:** delujoči stari nightly po izpisu 7. 11.; popolna integriteta v tem trenutku UNKNOWN; razvojni sedemkataloški kandidat obstaja; EU/LS in poln history/text backfill niso zaključeni. A1–A9 še niso PASS.
- **Dovoljene spremembe s to konsolidacijo:** zgolj dokumentacija na obstoječi razvojni veji in datirane opombe na obstoječih Linear nalogah; brez produkcijskih sprememb.
- **Naslednji korak:** enoten razvoj F1–F3 v obstoječem repozitoriju na osnovi tega dokumenta, po samostojni preverbi trenutnega Git stanja in brez posega v produkcijo.
