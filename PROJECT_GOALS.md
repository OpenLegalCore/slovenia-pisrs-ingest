# PISRS — cilj in status po lastnikovem resetu (8. 11. 2026)

**STATUS: OWNER STOP.** Dosedanje F0–F5 izvedbene naloge niso več veljaven razvojni mandat; ne nadaljuj jih samodejno. Osrednja konsolidacija z vsemi viri in dokazi: [PISRS-FULL-API-EXECUTION.md](docs/PISRS-FULL-API-EXECUTION.md). Pravila: [AGENTS.md](AGENTS.md).

**Nespremenjeni lastnikov cilj:** dokumentiran in preverjen uradni PISRS API ter vse dejansko dostopne vsebine → pregledna, trajna PostgreSQL baza izvirnikov/metapodatkov/različic; šele po brezplačni izmeri tokenov ločeno odobren Qdrant indeks. Nightly brez prekinitve Engine. Kaj je dejansko uradno dostopno, katere izvirne formate dobimo in kaj hranimo, mora biti dokazano *pred* razvojem.

**Obstoječi rezultat, ki ga ohranimo:** nameščena kataloška izdaja `84b72b1`; po poročilu izvršitve v PG 65.308 državnih aktov, 71.649 državnih NPB, 80.128 EU, 125.012 lokalnih aktov in 95.735 lokalnih NPB; Qdrant 281.338 starih točk ohranjen. **To ni dokaz popolnosti besedil/zgodovine.**

**Ponovni začetek ni razvojna naloga.** Pred prvo novo odobritvijo so potrebni: (A) uradni API register shem in funkcij, (B) točna matrika izvornega polja in dokumenta → PG tabela/stolpec/izvirnik, (C) dejanski GAP glede na obstoječo produkcijo, (D) lastnikova presoja zasnove. Glej mandat, razdelek 5.

**Zgodovinska evidenca (zamrznjena):** [OLC-77](https://linear.app/openlegalcore/issue/OLC-77), [OLC-79](https://linear.app/openlegalcore/issue/OLC-79), [OLC-80](https://linear.app/openlegalcore/issue/OLC-80), [OLC-82](https://linear.app/openlegalcore/issue/OLC-82), [OLC-85](https://linear.app/openlegalcore/issue/OLC-85), [OLC-83](https://linear.app/openlegalcore/issue/OLC-83). Ohraniti kot dokaze; brez njihove ponovne uporabe kot dovoljenja za izvedbo, brez novih projektov ali nalog. `ACCEPTANCE_TESTS.md` je pogojna referenca, ne dosežen PASS.
