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

### 2026-11-07 12:13 CET / 11:13 UTC — regresija ponovnega zagona in CI popravek

- **Veja in meja:** `codex/pisrs-state-catalogs-20261031` je bila čista in varno fast-forward usklajena na `c88e47aae4d68d375ded0c83327c1927cb97a70f`. Korenski checkout z obstoječimi spremembami v `deploy/systemd/` je ostal nedotaknjen. Produkcijski PG/Qdrant/checkpoint/service/timer zapisi in zunanji PISRS/embedding klici: **0**.
- **CI vzrok in popravek:** GitHub run [42349871712](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/actions/runs/42349871712) in [42350119814](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/actions/runs/42350119814) sta padla pri `ruff format --check` v `tests/test_extended_pg.py`; testna datoteka je formatirana. Novi GitHub CI readback je ob pripravi tega zapisa še **PENDING**.
- **Regresija prekinitev:** v obstoječem socket-only izoliranem PG 18.6 testu so štirje dejanski commit mejni scenariji **PASS**: po `external.synchronize`, po `catalogs.synchronize`, po `external.synchronize_state_raw` in tik pred `checkpoint.advance` po koncu obdelave. Za vsak scenarij ponovitev istega vhoda konvergira v 3 EU/LS + 1 državni akt + 1 surovo varianto brez dvojnika; že zapisane vrstice imajo isti `xmin` in isti vsebinski readback, neodvisni `unrelated` stolpec ostane ohranjen. Checkpoint je ob prekinitvi odsoten in se po uspešni ponovitvi premakne na isti konec intervala. Embedder in Qdrant mutacije niso poklicani. Napaka v produkcijskem pipelineu ni bila odkrita, zato je spremenjen le test.
- **Preverjanje:** `ruff format --check .`, `ruff check .`, ciljni test (5 PASS), celotna zbirka z izoliranim PG (179 PASS, 3 SKIPPED) in lokalni wheel/sdist build: **PASS**. Build artefakti so ostali zasebni v `/tmp/pisrs-ci-build-20261107` (~0,18 MB), s SHA-256 wheel `24dcd9dddf1905f00415b3de091fb545bdfa1a352d2343e18b8fa65ef6e146e4`, sdist `25d6b2c6d0359f948f021eda5086f20eaa4a22449a41838557b44cc563cfb3ac`. En testni PG vsebnik brez omrežja/produkcijskih mountov (512 MB limit) in ena kratka cleanup instanca sta bila ustvarjena in odstranjena; lastna testna socket mapa je odstranjena. Razvojni worktree, uv cache, build artefakti in predhodni zasebni dokazi so ohranjeni. Ni izmerjene produkcijske diskovne delte.

| Preostanek F1–F3 | Dokazano stanje | Meja za sprejem |
|---|---|---|
| `/seznam` | Replay 1. 11.: RS 81.809 in LS 139.029 opaženih ID; identitete niso samodejno promovirane v akte. | Semantika dodatnih ID in aktualna popolnost uradnega vira **UNKNOWN**. |
| EU/lokalna besedila in zgodovina | Replay 1. 11.: EU 80.098 identitet, lokalni akti 124.993, lokalni NPB 95.682; sintetični parser/404 in PG perzistenca PASS. | Celotna dostopnost besedil, EU zgodovinska pot in dejanski backfill **UNKNOWN/NOT_RUN**. |
| Qdrant indeksni obseg | Obstoječi RS deterministični UUID, 3072/Cosine in pravila aktivnih različic niso spremenjeni; lokalni zajem ne vektorizira. | Natančna upravičenost EU/LS, strošek vektorjev in sveža PG↔Qdrant primerjava **UNKNOWN**. |
| Podatkovni zaostanek | Zgodovinskih 71.635 RS in 95.682 LS NPB identitet je obseg vira, **ne izmerjen zaostanek**; stare provenance/act-link razlike so datirani dokazi. | Sveže stanje produkcijskih vrstic in obseg manjkajočih besedil **UNKNOWN**; ni dovoljeno ugibati količin prenosov ali embedding stroška. |
| Migracija | Aditivni SQL `docs/sql/001_source_catalog_items.sql` je uspešno izveden samo v izoliranem PG. | Pregledana produkcijska migracija, sveža zaščita in ločena odobritev še manjkajo; F4 **HOLD**. |

- **Naslednji en korak:** po potrjenem CI PASS pripraviti omejeno, bralno meritev aktualnega podatkovnega zaostanka in identitet po odobreni dostopni poti; ne izvajati migracije ali podatkovnega backfilla brez ločene odobritve.

### 2026-11-07 — neodvisni GitHub code/CI readback po F1–F3

- Pregledana commita [fd83a690](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/fd83a69055b1084a3aa45d7f43cd5d7307ded7ee) (koda) in [d3d2162](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/d3d2162aed42efee20a4383e26e7514266077386) (predaja). Pregledana dejanska `pipeline.py`, `postgres_external.py`, `postgres_external_text.py`, migracija in novi testi. Novi PG katalogi niso nameščeni, stari nightly je ostal aktivna produkcija po zadnjem host poročilu. **Produkcijske spremembe tega pregleda: 0.**
- **Pomemben CI FAIL:** PR #13 merge-context GitHub Actions [run 42349871712](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/actions/runs/42349871712) in [run 42350119814](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/actions/runs/42350119814) sta `failure` na `Lint`: `ruff format --check` zahteva preformatiranje `tests/test_extended_pg.py` približno vrstice 121–126. Lokalni 175 PASS/3 SKIPPED ostajajo datirani lokalni dokaz, **ne CI PASS**. Potreben minimalen popravek formatiranja.
- **Odprta regresija:** `run_nightly()` zapisuje ločeno `external.synchronize(...)`, `catalogs.synchronize(...)` in `external.synchronize_state_raw(...)`; test potrjuje rollback **znotraj** transakcije, ne ponovitve po prekinitvi **med** njimi. Dokazati, da ponovni zagon po vsakem mejnem commitu konvergira, brez izgubljenih identitet, napačnega checkpointa in nepotrebnih embeddingov.
- **Dovoljeno nadaljevanje:** ciljni izolirani fault-injection + formatiranje testne datoteke, brez novega parserja/servisa, brez produkcijskih zapisov ali aktivacije; po uspehu GitHub CI readback in ista konsolidacija. Varen čistilni zaključek samo za lastne nove začasne artefakte. **F1–F3 še niso produkcijsko sprejeti, F4 HOLD.**
- **Artefakti:** ta pregled ni ustvaril lokalnih Medo artefaktov in ni ničesar brisal; diskovna delta na Medu ni bila merjena.


### 2026-11-07 08:04 CET / 07:04 UTC — F1–F3 razvojni kandidat (brez produkcijske aktivacije)

- **Vir in identiteta:** obstoječa veja `codex/pisrs-state-catalogs-20261031`, izhodišče `bee66e92248d7d6bffcc3e1695505efe78bba737`; stara produkcijska izdaja po zadnjem potrjenem poročilu `94c5b2a4182bd3f6b0c17ecf386defd4e464195f`. Korenski lokalni `main` je ostal nedotaknjen; delo je v ločenem worktreeju `/tmp/pisrs-full-api-20261107`.
- **F1 — razvojni PASS za odjemalca in sintetično PG integracijo, produkcijski podatkovni PASS še ne:** obstoječi `PisrsClient` zdaj prebere vseh 13 glavnih zbirk in loči RS `register_id`/`text_id`, EU CELEX ter lokalni `id`/`mopedPlusId`/EDA. Lokalni katalogi se zaključijo ob prvi prazni strani, ker je bil njihov `totalCount` v zajemu nezanesljiv. `/seznam` je ločeno bralno opažanje; redkih vrstic ne pretvori v polne akte. Aditivna, **v produkciji neizvedena** migracija `docs/sql/001_source_catalog_items.sql` predvideva ločene imenske prostore, izvorne variante in lokalne povezave. Stari katalog in `catalog-sync` ne dobita novih polj. Sintetična integracija v izolirani PG 18.6 je PASS; poln zajem v PG ni izveden.
- **F2 — delno:** omejene skupine državnih in lokalnih NPB ohranjajo checkpoint do konca zaostanka; državne različice ostanejo v obstoječih tabelah, lokalni HTML/bloki/členi pa v predvideni novi tabeli brez vektorjev. Izmerjeni HTTP 404 dobi razlog `NOT_AVAILABLE_FROM_API:HTTP_404` in ponovno preverbo po dnevu; vsebina se ne izmisli. EU zgodovinski/besedilni endpoint v zajetem OpenAPI z dne 1. 11. ni bil naveden (le `/predpis-eu` in `/besedilo/{idZbirkaElement}`); današnja globalna dosegljivost besedil in popolnost parserja ostajata **UNKNOWN**. Lokalni NPB se povežejo le z enoličnim točnim SOP; dvoumni ostanejo brez povezave.
- **F3 — pogodba ohranjena, celovitost UNKNOWN:** `qdrant_point_id`, zbirka, dimenzija, metrika, obstoječa pravila za aktivne državne različice in dragi vektorji niso spremenjeni. Lokalni backfill ne kliče embedderja ali Qdranta. Sveža popolna primerjava PG↔Qdrant in popravek zgodovinskih `act_id` nista izvedena.
- **Dokazni replay brez omrežja:** zasebni datirani zajem z dne 1. 11., SHA-256 njegovega `SHA256SUMS=0de2d7da1cbeda2fbc998b66a9c86f6b34f29e1033fece23dfd6427fb609ce55`; preverjenih 512 odzivov glavnih zbirk, 500.870.974 bajtov. Rezultat: RS akti 65.271, RS NPB 71.635, EU CELEX 80.098, LS akti 124.993, LS NPB 95.682. Ločenih 10 `/seznam` odzivov, 52.784.468 bajtov: RS 81.809 in LS 139.029 opaženih ID. Državnih surovih endpoint variant 130.527. Lokalni NPB: 88.938 enolično povezanih po SOP, 937 dvoumnih, 5.390 brez SOP ujemanja, 417 brez razčlenljivega SOP. To je **datiran replay**, ne svež zajem vira ali produkcijski postflight.
- **Preverjanje:** celotna zbirka z opt-in testno vtičnico **175 PASS, 3 SKIPPED** (trije starejši izolirani PG testi brez svojega fixture); brez vtičnice 174 PASS, 4 SKIPPED. Novi izolirani PG 18.6 test je preveril izvedbo migracije, ponovljene UPSERT-e brez spremembe `xmin`, zavrnitev naknadno dvoumne povezave, rollback celotne transakcije ob napaki med serijami, parser/HTML in reason-coded 404 z readbackom, državni bounded pending ter collision guard. Lint PASS, wheel/sdist build PASS. Wheel SHA-256 `ef4ce5ac9e94b7f7f4d93c5785832cc7b4b0ba9ef4f4a1b2c26462d2e2c387de`. Produkcijski PG zapis, Qdrant integracijski test, masovni prenos besedil in A1–A9 **NOT_RUN**.
- **Produkcija:** SQL/Qdrant/checkpoint/service/timer spremembe **0**; zunanji PISRS in plačljivi embedding klici **0**. Ustvarjeni so ločen razvojni worktree, zaklenjeni lokalni `.venv` (~60,9 MB), lokalni uv cache (~58,4 MB) in dva build artefakta (~0,17 MB). Štirje lastni izolirani PG testni vsebniki (`network=none`, brez produkcijskih mountov, 512 MB limit) ter njihove testne vtičnice so bili odstranjeni; prva dva vsebnika sta obstala v inicializaciji, tretji in četrti sta uspešno izvedla integracijo. Nič obstoječega ni izbrisano. Disk delta produkcije ni merjena.
- **HOLD:** kandidat zahteva ločeno odobreno migracijo in uvedbo; datiran replay in sintetični PG test ne dokazujeta aktualne produkcijske popolnosti. `/seznam` dodatni ID ostajajo opažanja z nerazčiščeno semantiko; EU besedilna zgodovina, lokalna dostopnost besedil, 6.744 neenolično/nepovezljivih lokalnih NPB, dejanska Qdrant integriteta in prekinitev **med ločenimi** katalogskimi transakcijami ostajajo odprti. Naslednji en korak: **omejen razvojni preizkus nadaljevanja po prekinitvi med ločenimi kataloškimi transakcijami**, brez produkcijskih zapisov.
- **Objava in readback:** razvojna koda in ta zapis sta v commit-u [`fd83a69055b1084a3aa45d7f43cd5d7307ded7ee`](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/commit/fd83a69055b1084a3aa45d7f43cd5d7307ded7ee) na obstoječi veji; `git ls-remote` in GitHub readback dokumenta potrjujeta isti commit. Obstoječe naloge OLC-77/79/80/85/82/83 so dopolnjene z datiranimi opombami in povezavo na kodo, nato ponovno prebrane; statusi nalog so ohranjeni. Korenski lokalni checkout ima enake predhodne necommitane spremembe v `deploy/systemd/` in ni bil spreminjan.


### 2026-11-07 — CONSOLIDATION v1.0

- **Vir:** predhodni potrjeni host Codex izpisi in pregledani GitHub/Linear dokumenti. To ni sveže merjenje Meda.
- **Stanje:** delujoči stari nightly po izpisu 7. 11.; popolna integriteta v tem trenutku UNKNOWN; razvojni sedemkataloški kandidat obstaja; EU/LS in poln history/text backfill niso zaključeni. A1–A9 še niso PASS.
- **Dovoljene spremembe s to konsolidacijo:** zgolj dokumentacija na obstoječi razvojni veji in datirane opombe na obstoječih Linear nalogah; brez produkcijskih sprememb.
- **Naslednji korak:** enoten razvoj F1–F3 v obstoječem repozitoriju na osnovi tega dokumenta, po samostojni preverbi trenutnega Git stanja in brez posega v produkcijo.


### 2026-11-07 — CONSOLIDATION readback

- **Dokumentacija:** kanonični dokument objavljen na obstoječi razvojni veji (prvi docs commit `4fd8de5991e6348a38b6c40d84a23e8869459ac2`); `PROJECT_GOALS.md` povezan (commit `ee1f00dd57ede91193ebdd2e799b3fe09593beb6`); GitHub readback dokumenta in povezave PASS.
- **Linear:** opisi **OLC-77, OLC-79, OLC-80, OLC-85, OLC-82 in OLC-83** dopolnjeni z datirano fazo in povezavo; zgodovina in obstoječi statusi ohranjeni. Projektni status update [7. 11. 2026](https://linear.app/openlegalcore/project/pisrs-complete-source-to-index-synchronization-b47e7deb7c78/activity#project-update-44fd3ace) označen **atRisk** (podatkovna sinhronizacija ni dokončana).
- **Dejanske produkcijske spremembe:** **0**; GitHub spremembe samo dokumentacija, Linear samo evidence. Lokalno na Medu nič ustvarjeno ali odstranjeno, disk delta **ni merjena**.
- **Naslednja odobrena naloga:** obstoječi lokalni Codex po potrebi prejme **en** razvojni mandat za faze F1–F3 po tej specifikaciji; pred kakršnimkoli produkcijskim pisanjem, aktivacijo, embedingi ali posegom v druge repozitorije mora obstajati ločena odobritev. Novi agent začne z branjem tega dokumenta in relevantnega zadnjega Codex izpisa.
