# PISRS — en cilj, šest obstoječih nalog

**Edina aktualna avtoriteta za obseg, stanje in nadaljevanje:** [PISRS-FULL-API-EXECUTION.md](docs/PISRS-FULL-API-EXECUTION.md). Za omejitve in način dela glej [AGENTS.md](AGENTS.md). **Merila za DONE:** [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md).

**Cilj:** celovita, dokazljiva in samodejna uskladitev vseh uradno dostopnih PISRS API podatkov (vseh 13 katalogov, relevantnih identitet, besedil in zgodovinskih različic) z obstoječim PostgreSQL ter s pogodbeno izpeljanim Qdrantom; delujoči nightly in neprekinjeno delovanje Engine, brez sprememb Engine kode.

| Izvedbena faza | Obstoječi Linear zapis |
| --- | --- |
| F0 — dejanska produkcija in API vir | [OLC-77](https://linear.app/openlegalcore/issue/OLC-77) |
| F1 — državni/EU/lokalni katalogi | [OLC-79](https://linear.app/openlegalcore/issue/OLC-79), [OLC-80](https://linear.app/openlegalcore/issue/OLC-80) |
| F2 — besedila in vsa dostopna zgodovina | [OLC-82](https://linear.app/openlegalcore/issue/OLC-82) |
| F3 — povezave, integriteta in Qdrant | [OLC-85](https://linear.app/openlegalcore/issue/OLC-85) |
| F4 — odobrena produkcijska uskladitev in A1–A9 | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) |
| F5 — pospravljanje in tehnična predaja Engine | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) |

OLC-78/81/84 so zgodovinske, preklicane oziroma konsolidirane naloge. **Ne odpiraj novih issues ali projektov.** Zgodovinski rezultati se preverjajo v Git zgodovini in Linear, ne kopirajo v trenutna navodila.
