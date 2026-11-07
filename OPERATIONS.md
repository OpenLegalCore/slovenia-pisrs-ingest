# PISRS — operativno stanje v času RESET (8. 11. 2026)

**LASTNIKOV STOP.** Ne izvajati nadaljnjega razvoja, ponovnega kataloškega uvoza, besedilnega backfilla, embeddingov ali sprememb v produkciji. Aktualni mandat: [docs/PISRS-FULL-API-EXECUTION.md](docs/PISRS-FULL-API-EXECUTION.md); obvezna [AGENTS.md](AGENTS.md).

- Dejanska nameščena izdaja po poročilu 7. 11.: `84b72b19054c3482408e154fc85ca6be41e156db`; prejšnja izdaja `94c5b2a` je ohranjena. Ne zamenjuj `main`, razvojne veje in aktivne izdaje.
- Po poročilu je sistemski timer ACTIVE/enabled; novi urnik uporablja **`nightly --catalogs-only` ob 03:00 Europe/Ljubljana**. Ta način izvaja samo kataloge, **ne** besedil, embeddingov, Qdranta ali checkpointa. Prvi novi samodejni zagon ob zapisu še ni potrjen. Ne zaženi ročno namesto preverbe, če lastnik ni odobril.
- Zaščiten profil `pisrs-ingest` je 7. 11. dokazano omogočil 13-kataloški API popis. Javni direktni portalni URL-ji z Meda so 8. 11. vrnili HTTP 407 (proxy); to je drug dostop in iz njega ni mogoče sklepati, da avtorizirani integracijski API ne deluje.
- Pred kataloško migracijo je backup `/var/lib/pisrs-backups/backup-20261107T190129Z` prestal celotno zaporedno izolirano obnovo. **Ne razglašaj ga za postmigracijski backup.** Ohraniti dokaze in obnovitvene točke; ničesar ne brisati.
- `appdb.pisrs` in `pisrs_current` sta produktivni odvisnosti Engine. Nobenih novih PG/Qdrant zapisov, deploya, premikov checkpointa ali prekinitve servisa na podlagi tega dokumenta.
- Skrivnosti v `/etc/pisrs-ingest.env` ne kopirati v Git/Linear, ne spreminjati privilegijev ali obiti proxyja. `deploy/systemd/*.service` in `*.timer` sta **predlogi**, ne zanesljiv odčitek nameščene enote.
- Rezultati in zgodovinski izvajalski postopki so ohranjeni v Git zgodovini, predvsem mandat pred resetom na `8bfd8fc`. Pred novo izvedbo veljajo le zahteve uradni API → PG mapping → GAP → lastnikova odobritev.

**Dovoljena dejavnost v trenutnem režimu:** branje, preverjanje in konsolidacija obstoječih virov/dokumentacije, brez produkcijskih dejanj. Brez ponavljanja starih izvedbenih promptov.
