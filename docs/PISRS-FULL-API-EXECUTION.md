# PISRS — KONSOLIDACIJA IN RESET OSNOV (8. 11. 2026)

**STANJE: OWNER STOP / DESIGN RESET.** Lastnik je izrecno ustavil dotedanjo razvojno pot. Ta dokument je evidenca obstoječih dokazov in vrzeli, **ne** dovoljenje za izvajanje. Brez lastnikove nove izrecne odločitve: brez sprememb produkcije, kode, servisov, OpenAI klicev, besedilnega backfilla, novih Codex nalog ali samodejnega nadaljevanja predhodnih Linear nalog. Ohraniti obstoječo produkcijo in njene preverjene podatke. Zgodovinski dnevnik je v Git zgodovini do commita `8bfd8fc6759c558ac9f024097279faa97df08ea3` ter obstoječih Linear zapisih.

## 1. Cilj, obseg in razmejitev sistemov

**Lastnikov cilj:** popoln, dokazljiv inventar **dejansko dostopnega** uradnega PISRS API, njegova dokumentirana preslikava v obstoječi `appdb.pisrs`, najprej neodvisna hramba izvornih besedil in zgodovine v PostgreSQL, nato ločeno, merljivo in posebej odobreno ustvarjanje embeddingov v `pisrs_current`; varen nightly brez posega v OpenLegalCore Engine. Ne sklepati, da katalogni zapis že pomeni dostopno besedilo ali da spletni portal in uradni integracijski API ponujata enake storitve.

**Tri različne površine:**
1. **Uradni integracijski API-PISRS:** [Swagger](https://pisrs.si/swagger), [navodila](https://pisrs.si/swagger/navodila); zahteva odobren API žeton. V tem projektu se uporablja `PisrsClient` (`requests`), brez brskalnika/Playwrighta.
2. **Spletni portal PISRS:** uporabniška aplikacija in njeni opaženi `/api/rezultat/...`, `/api/datoteke/integracije/...` klici. Ti niso avtomatično del dokumentiranega integracijskega API-ja; njihove sheme, pogoji in programatska dosegljivost niso potrjeni.
3. **OpenLegalCore:** PostgreSQL je trajna baza podatkov in izvirnikov, Qdrant pa izvedeni vektorski indeks. EUR-Lex oziroma zunanji zgodovinski arhivi niso samodejno vključeni v obseg PISRS API.

**Temeljno pomanjkanje dosedanjega projekta:** pred implementacijo ni bila zaključena verzionirana matrika *endpoint → parametri/odziv/identitete → dostopnost besedila/zgodovine → konkretna PG tabela/stolpec → dokaz konsistence*. Obstaja preverjena implementacija dela kataloškega prenosa, ne pa dokazana popolnost vira→besedilo→zgodovina→shramba→indeks. Pri ponovnem začetku je treba to matriko dokazati **pred** nadaljnjim razvojem.

## 2. Inventar uradnega API-ja — kaj vemo in česa ne

Uradni [Swagger](https://pisrs.si/swagger) in [navodila](https://pisrs.si/swagger/navodila) navajajo **13 glavnih katalogov**. Pregled po skupinah (številke so uvožene kataloške identitete z dne 7. 11. 2026, ne število pridobljenih besedil):

| Uradni endpoint(i) | Vir/pomen | Identiteta v kodi | Produkcijski rezultat | Besedilna pogodba |
|---|---|---|---:|---|
| `/predpis/register-predpisov` | Državni register | `register_id`, `moped_id` | skupaj 65.308 enoličnih državnih aktov v 7 zbirkah | katalog; ne neposredni HTML |
| `/predpis/neveljavni-predpisi` | Neveljavni | ista državna identiteta | vključeno zgoraj | katalog |
| `/predpis/obsoletni-in-konzumirani-predpisi` | Obsoletni/konzumirani | ista | vključeno zgoraj | katalog |
| `/predpis/evidenca-normodajalcev` | Normodajalci | ista | vključeno zgoraj | katalog |
| `/predpis/predpisi-v-pripravi` | V pripravi | ista | vključeno zgoraj | katalog |
| `/predpis/drugi-splosni-in-posamicni-akti` | Drugi akti | ista | vključeno zgoraj | katalog |
| `/predpis/splosni-akti-za-izvrsevanje-javnih-pooblastil` | Javnopooblastilni akti | ista | vključeno zgoraj | katalog |
| `/npb` | Državne NPB različice | `text_id` | 71.649 | `/besedilo/{idZbirkaElement}` je dokumentiran za državna NPB |
| `/predpis-eu` | Povezani EU akti | CELEX | 80.128 | iz samega kataloga ni dokazan dostop do polnih EU besedil |
| `/akt-ls/veljavni-akti` | Lokalni veljavni | `LS_ACT` id, `mopedPlusId` | skupaj 125.012 lokalnih aktov v 3 zbirkah | katalog |
| `/akt-ls/neveljavni-akti` | Lokalni neveljavni | ista lokalna identiteta | vključeno zgoraj | katalog |
| `/akt-ls/akti-v-pripravi` | Lokalni v pripravi | ista | vključeno zgoraj | katalog |
| `/npb-ls` | Lokalna NPB | `LS_NPB` id | 95.735 | **uradni Swagger ne navaja enakovrednega lokalnega besedilnega endpointa** |

**Dodatne uradne operacije:** sedem `/predpis/.../seznam`, tri `/akt-ls/.../seznam`, `/sifranti`, `/sifranti/{id}`, `/besedilo/{idZbirkaElement}` in zahtevek za API dostop. `/seznam` ima v kodi status ločenih opažanj; semantika in dokaz popolnosti še nista zaključena. Šifranti in celotna polja/filtri/DTO, napake, paginacija, izvozi in osveževanje **niso dokumentirani v preverjeni projektni preslikovalni matriki**. Navodila opisujejo običajen prikaz največ 1.000 zadetkov na stran in dnevno osveževanje; dejanska implementirana paginacija je ločena stvar, ki zahteva dokaz.

**Ne mešati ID-jev:** državna `text_id`, lokalna `LS_NPB` identiteta, lokalni `MP_...` in datotečni `FILE_ID` niso enakovredne vrednosti. Posredovanje `LS_NPB_ID` v državne `/besedilo/{id}` je bila napačna predpostavka (60/60 preverjenih lokalnih zahtev HTTP 404, državni kontrolni 200).

**Portalno odkritje — kvalificiranost UNKNOWN:** Codex je prek portalnega/brskalniškega diagnostičnega branja opazil `/api/rezultat/zbirka/id/{MP_ID}`, `/api/rezultat/neuradno-precisceno-besedilo/{LS_NPB_ID}/details` in objavljene `/api/datoteke/integracije/{FILE_ID}`. Trije identitetno povezani HTML primeri so imeli 11.262, 1.150 in 78.539 znakov, vendar SHA-256 meri prebrani `document.body.innerText`, **ne izvornih bajtov**. Neposredni terminalski javni zahtevki na Medu za te naslove so vrnili **HTTP 407** (proxy), medtem ko je zaščiteni servisni profil že omogočil uradni kataloški API zajem. To **ne dokazuje** neuspeha vseh API operacij in **ne kvalificira** novega samodejnega portalnega adapterja. Brskalnik ni del produkcijskega ingesta. Glej dokazni paket `/tmp/pisrs-local-text-20261108/RESULT.json`, obstoječi Linear OLC-82.

## 3. Pregled dejanske implementacije in podatkovne preslikave

| Vir / korak | Dejanska implementacija in ciljna shramba | Ocena |
|---|---|---|
| Sedem državnih katalogov | `PisrsClient.discover_acts` → `pisrs.acts`, `pisrs.act_sync_catalog` (izvorni JSON), `pisrs.state_raw_variants` (po endpointu) | identitete/provenienca po 7. 11. **PASS**; polja/DTO in semantika popolnosti **ni celovito validirana** |
| Državni NPB seznam | `discover_npbs` → `pisrs.npb_catalog` (`raw_item`) | 71.649 identitet; sam katalog ne dokazuje besedil |
| Državno besedilo | `GET /besedilo/{text_id}` → `pisrs.act_text_versions` (`html`, `plain_text`, `raw_meta`), `pisrs.act_text_blocks`; `embedding_chunks` | stari podatki obstajajo; zgodovinska popolnost in tekstovna zvestoba niso dokazani |
| EU register | `discover_eu_acts` → `pisrs.source_catalog_items` (`namespace=EU`, CELEX, `raw_by_endpoint`) | 80.128 ID; EU besedila/izvirniki **niso shranjeni s tem uvozom** |
| Lokalni akti | `discover_local_acts` → `pisrs.source_catalog_items` (`LS_ACT`, `moped_plus_id`, EDA/SOP, JSON) | 125.012 ID; aktovih izvirnikov/zgodovine uvoz ne dokazuje |
| Lokalni NPB katalog | `discover_local_npbs` → `pisrs.source_catalog_items` (`LS_NPB` + status povezave) | 95.735 ID; 88.991 enoličnih SOP povezav, 6.744 nerešenih |
| Lokalni NPB besedilni kandidat | `pisrs.source_text_versions` (en zapis na `LS_NPB` id: HTML, plain text, blocks, articles) | tabela nameščena, **0 uvoženih besedil**; ne podpira EU/LS_ACT izvirnih datotek niti celovitega manifestiranja originalnih bajtov; napačen avtomatski lokalni `/besedilo` odstranjen |
| Semantični indeks | `pisrs.embedding_chunks` → OpenAI `text-embedding-3-large` 3072 → Qdrant `pisrs_current`; UUID po kolekciji/text ID/chunk indeksu | obstoječih 281.338 Qdrant točk ohranjenih; **lokalni/EU vektorji niso del sedanjega podatkovnega kontrakta** |
| Zagon | `nightly --catalogs-only` s sistemskim timerjem | aktiviran 7. 11.; prvi dejanski novi timer-triggered zagon ob zapisu tega reseta **NOT_VERIFIED** |

**Kritične omejitve obstoječe sheme:** ni potrjenega celotnega slovarja vseh PISRS polj → vseh PG stolpcev; ni pregledane strategije shranjevanja originalnih datotečnih bajtov, MIME/hash/povezave in različic za vse vrste; ni dokazanega vira in verzioniranja za celotno zgodovino. `source_text_versions` se po trenutni SQL omejitvi nanaša le na `LS_NPB`. PostgreSQL mora biti samostojen arhiv; Qdrant šele naknadno izpeljan indeks. Ta **ciljni dvostopenjski princip je odločitev za ponovno načrtovanje, ne že dokončana implementacija**.

## 4. Rezultati, ki ostanejo veljavni, in odprta vprašanja

**V dokumentiranem produkcijskem posegu 7. 11. 2026 (preverba dokazov iz lokalnega Codexa, ne neposreden dostop tega klepeta do Meda):**
- Aktivna izdaja `84b72b19054c3482408e154fc85ca6be41e156db`; aditivna migracija PASS; vseh **300.875 novih EU/LS kataloških identitet** in **31.785 državnih provenienčnih parov** (0 manjkajočih proti istodnevnemu popisu). `state_raw_variants` = 130.601.
- 65.308 državnih aktov, 71.649 državnih NPB. Vsa obstoječa 281.338 Qdrant ID/payload/vektor množica je po poročilu izvajalnika nespremenjena; 62-bajtni checkpoint nespremenjen; druge stare PG tabele prav tako. 0 novih besedilnih/embedding klicev, 0 USD embeddingov.
- Pred migracijo usklajen backup `/var/lib/pisrs-backups/backup-20261107T190129Z` in zaporedna izolirana obnova PASS (takratnih 11 tabel, 14.823.681 vrstic, 281.338 vektorjev, checkpoint); to **ni samodejen dokaz nove obnovljive točke po migraciji**.
- Kandidat je prestal lokalne teste in CI `42415254706`, vendar CI sam ne potrjuje celovitega PISRS podatkovnega kontrakta.

**Nedokazano ali odprto:** vsaka shema/parameter/DTO/izvoz/šifrant uradnega API; zakaj so različna polja/relacije izvirnika v PG ohranjena ali izpuščena; dejansko dostopna in zajeta besedila po virih; vsa zgodovina; 352 državnih `act_text_versions.act_id IS NULL`; 6.744 lokalnih NPB povezav; 44 starih datumskih razlik in 14 zgodovinskih chunk anomalij; celoten vir→PG→Qdrant sprejem A1–A9; prvi avtomatski zagon `nightly --catalogs-only`; veljaven način za programski lokalni prenos ob 407. **Ni dokazano**, da 300.875 identitet pomeni enako število besedil ali novih embeddingov. Skupna cena novih embeddingov je zato UNKNOWN; obstoječe ustrezne vektorje ni treba plačati ponovno.

**Meje dostopa:** GitHub in Linear hranita verzionirane rezultate in poročila Codexa. Ta dokument ne nadomešča dejanske live hostske kontrole; za gostiteljske trditve je izvor dokumentirano poročilo Codexa. Izven že odobrenega obsega se brez lastnika ne opravljajo novi zaščiteni API zajemi, podatkovni popravki ali prenosi.

## 5. RESET — pogoji pred kakršnokoli novo izvedbo

**Zaporedje za ponovno presojo, ne avtomatski seznam novih nalog:**

**A. Izvorna specifikacija.** Iz uradnega trenutnega OpenAPI in navodil zajeti celoten register operacij, vhodne parametre, načine avtorizacije, paginacijo/izvoz, DTO/JSON sheme, povezave, šifrante, vrsto besedil, formate, zgodovino in pogoje uporabe. Vsaki trditvi dodati uradni vir ali dejanski, posebej odobren odgovor z API. Ločeno opisati nedokumentirane portalne storitve in omejitve. Če PISRS API določene vsebine ne daje, to izrecno označiti, ne nadomestiti z domnevami.

**B. Podatkovna preslikava.** Za vsako izvorno polje/identiteto/različico iz A navesti točno PG tabelo in stolpec ter izvorni JSON/HTML/datotečni manifest; razmejiti normalizirane podatke od nespremenjenega izvirnika, ključev in sledljivosti. Izvesti popis dejanskega PG in Qdrant kontrakta ter primerjavo s ciljno shemo — brez poseganja v produkcijo.

**C. Objektivni GAP in odločitev.** Matriko `API ponuja / obstoječa baza hrani / manjka / ni dostopno / kaj je zaželeno v Qdrantu` podpreti z dokazi in šele nato lastniku predložiti odločitev, kaj ohraniti, popraviti, ponovno uporabiti ali izločiti. Oceniti stroške šele po znanem naboru besedil. Ni privzetega dodatnega reembeddinga.

**D. Nova izrecna lastnikova odobritev.** Šele po lastnikovem sprejemu A–C je dovoljeno določiti *nov* izvedbeni obseg. Starih F0–F5 oziroma Linear OLC-77/79/80/82/83/85 se ne izvaja kot odprtih mandatov. Brez novih projektov ali samostojnih razširitev. Vse zgodovinske evidence ohraniti.

**Zadnje stanje:** RESET / NO DEVELOPMENT AUTHORIZED. Produkcija ostane v obstoječem načinu; nadaljnjih ukazov za razvoj ali produkcijo ta dokument ne izdaja.
