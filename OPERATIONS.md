# PISRS — minimalna operativna pravila

To ni seznam razvojnih opravil. **Edino trenutno navodilo je [kanonični mandat](docs/PISRS-FULL-API-EXECUTION.md); [AGENTS.md](AGENTS.md) prepoveduje širjenje obsega.** Ne ponavljaj starega P1 pregleda zgolj zato, ker je naveden v dokumentaciji.

## Produkcija

- Dejanska namestitev je na Medu; datoteke pod `deploy/systemd/` so **predloge**, ne dokaz stanja. Stari nightly ob 03:00 Europe/Ljubljana ostaja aktiven, dokler ne bo ločeno odobren varen preklop. Neaktivni oneshot servis med zagoni je normalen.
- `/etc/pisrs-ingest.env` je zaščiten; skrivnosti se ne berejo v izpis ali shranjujejo v Git/Linear. Pregledani servisni uporabnik: `pisrs-ingest`. Za dovoljen enkratni bralni API korak glej mandat in veljavno odobritev.
- Ne uporabljaj `nightly`, `reconcile --apply`, `catalog-sync --apply` ali produkcijskega `systemctl start` kot diagnostike. `preflight` ni nadomestilo za polni katalog; `catalog-sync --dry-run` ni 13-zbirčni popis.
- **Za branje**: en namenski merjeni pregled, samo potrebne SELECT/API GET, brez nepotrebnih ponovitev, izvoza vsebine, velikih snapshotov in nove testne infrastrukture. `PASS` se nanaša samo na res izveden obseg.

## Edini produkcijski prehod (ločena odobritev)

Za odobreno kataloško nadgradnjo uporabi `catalog-import --apply --expect-identities SHA256`.
Privzeti `catalog-import` je dry-run; odtis vključuje identitete in provenienco vseh 13 zbirk.
`nightly --catalogs-only` uporablja iste adapterje in pravi aplikacijski zaklep, vendar ne
prenaša besedil, ne spreminja Qdranta ali checkpointa ter ne odpira embedding odjemalca.
Ta izrecni način je potreben za urnik pod mejo 0 embedding klicev; obdelava državnih besedil
se nadaljuje šele z ločeno odločitvijo za polni nightly. Samodejna lokalna besedilna pot je
izključena do potrditve uradne poti; lokalni HTTP 404 ni dokaz neobstoja dokumenta.

1. Pregledan nespremenljiv kandidat + aktualen vir→PG diff + izmerjena količina/stroški in združljivost s starim nightlyjem; brez tega HOLD.
2. Pred odobrenim zapisom: dejanski lock/odločitev o sočasnem nightlyju, sveža skupaj obnovljiva PG/Qdrant/checkpoint zaščita, preizkušen povratek in potrjeno izvajalno okno. Ne uporabljaj 16-GiB praga za običajne bralne operacije; ta meja izvira iz sočasnega backupa+izolirane obnove.
3. Po **posebni** odobritvi migracija in paketna sinhronizacija, brez prekinitve Engine povezljivosti; sledijo source→PG→Qdrant readback, checkpoint ter dejanski naslednji timer-triggered nightly.
4. Po prvem podatkovnem zapisu **ne** zaganjaj starega štirikataloškega nightlyja kot preprostega rollbacka: lahko odstrani novo provenienco. Povratek podatkov mora uporabiti združljivo povratno točko, ne samo stare kode.

**Prepovedano:** širitev privilegijev na slepo, `docker prune`, brisanje neznanih datotek, posegi v `olc-engine`/`case-law-ingest`, nova platforma za deployment/test/monitoring.
