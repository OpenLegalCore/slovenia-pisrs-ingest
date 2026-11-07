# PISRS ingest — obvezna pravila izvajanja

**Avtoriteta:** zadnja izrecna odločitev lastnika > ta AGENTS.md > [enotni izvedbeni mandat](docs/PISRS-FULL-API-EXECUTION.md). Drugi dokumenti so tehnične reference, NE dovoljenje za nov obseg. Ob vsakem novem obratu preberi **najprej AGENTS.md in kratki razdelek "Trenutno stanje" v mandatu**.

## Cilj in stroga meja

Dokončati **en** obstoječi `slovenia-pisrs-ingest`: 100 % tistega, kar je dejansko uradno dostopno prek PISRS API (13 glavnih zbirk in relevantni podporni klici), celotna dosegljiva zgodovina/besedila v obstoječem PostgreSQL, pogodbena skladnost obstoječega Qdranta, zanesljiv nightly in tehnična predaja Engine seji. **Engine, case-law-ingest in druge repozitorije pusti pri miru.**

**BREZ DRIFTA.** Nobenih novih ciljev, repozitorijev, Linear projektov/nalog, vej, PR-jev, spremljevalnih aplikacij, testnih platform, splošnega refaktoriranja, neskončnih auditov ali infrastrukture, če lastnik tega **izrecno** ne naroči. Samostojni zgodovinski arhiv Uradnega lista in drugi zunanji sistemi **niso** samodejno razširitev PISRS API. Če je vir izven API, jasno označi omejitev, ne začni novega projekta.

**Najkrajša pot:** uporabi obstoječo kodo, skripte, teste, dokaze, dostopne servisne poti in delujoči nightly. Po preverbi zadnjega rezultata **opravi naslednji potreben izvedbeni korak**. Ne nadomeščaj izvajanja z dodatnim načrtom, ponovljenim preflightom, ritualom novih odobritev ali pripravo še enega handoffa. Ne ponavljaj uspešnih testov ali množičnih izvozov brez novega razloga; ciljni test ob spremembi je dovoljen. Časovni cilj 2–4 ure je operativna prioriteta, ne izmišljena garancija za velik zgodovinski prenos.

## Varovalke, ki so dejansko obvezne

- Pred **spremembo produkcije**: konkretna lastnikova odobritev spremembe, ustrezna aktualna obnovljiva PG+Qdrant+checkpoint točka ter preverjen povratek. Ne izvajaj produkcijskega SQL/Qdrant pisanja, deploymenta, posega v systemd/timer/checkpoint, plačljivih embeddingov ali brisanja brez izrecno določenega obsega odobritve.
- **Bralno delo ni deploy.** Za že izrecno dovoljeni bralni korak **ne zahtevaj ponovne odobritve**. Lastnik je 7. 11. 2026 odobril **enkratni** bralni zajem 13 katalogov z zaščitenim servisnim profilom `pisrs-ingest` (brez besedil, mutacij in izpisa/izvoza skrivnosti). Najprej preveri, ali je bil že opravljen; ne izvajaj drugič brez razloga.
- Nikoli ne izdajaj ali izpisuj skrivnosti, DSN, API tokenov ali zasebnih podatkov v Git/Linear/izpise. Privilegijev ne razširjaj na slepo. Če je za odobreno dejanje potreben interaktivni operater, vrni **en** točen, pregledan, najmanj privilegiran ukaz brez ponavljanja zahtev za odobritev; ob dokazani tehnični blokadi STOP z jasnim razlogom.
- Ohrani obstoječi produkcijski nightly, bazo, vektorje, backup in uporabnikov lokalni checkout. Nikoli ne uporabljaj `docker prune` ali brisanja neznanih artefaktov. Aktivna produkcija in razvojni checkout sta ločena; noben cloud checkout ni dokaz stanja Meda.

## Kontinuiteta brez birokracije

- **En** aktivni plan in status: `docs/PISRS-FULL-API-EXECUTION.md`. **En** nabor obstoječih Linear nalog OLC-77/79/80/85/82/83. `ACCEPTANCE_TESTS.md` določa končni sprejem A1–A9. Ne ustvarjaj drugega vira resnice.
- Po vsakem **vsebinskem** obratu na kratko popravi samo stanje, dokaze, blokado in naslednji korak v kanoničnem dokumentu ter ustrezni Linear nalogi. Brez dolgih dnevniških romanov in dokumentacijskih zank. Ohranitev zgodovine zagotavlja Git.
- V poročilu vedno loči `PASS`, `FAIL`, `UNKNOWN`, `NOT_RUN`; razvojni CI ni produkcijski PASS. Sporoči konkretno opravljeno delo, zaščitene spremembe (tudi 0) in **en** naslednji korak. Če ni ovire, nadaljuj izvajanje, ne ustavi se zgolj zaradi poročanja.
