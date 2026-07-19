# Weekmenu — Build Instructions (Claude Code)

> **Doel:** Een receptendatabase + weekmenuplanning + automatische boodschappenlijst
> toevoegen aan de bestaande Huishouden-app, **zonder** de bestaande Financiën-functie
> of productiedata te raken.

---

## 0. Vooraf — lees dit eerst

**Werk op een aparte branch:**
```bash
git checkout -b feature/weekmenu
```

**Scope-isolatie (belangrijk voor credits + geen conflicten):**

De grootste winst — zowel voor credits als om conflicten te vermijden — zit in
scope-isolatie. Weekmenu staat functioneel volledig los van Financiën. Beperk elke
sessie daarom expliciet tot de weekmenu-mappen en negeer de rest van de repo.

- Alle backend-code voor deze feature komt in `backend/app/weekmenu/`
- Alle frontend-code komt in `frontend/src/weekmenu/`
- Routers krijgen prefix `/api/weekmenu/...`
- **Raak geen enkele bestaande Financiën-tabel, -router of -component aan.**
- Lees of doorzoek de Financiën-code niet tenzij strikt noodzakelijk; als je een
  gedeelde utility of db-sessie nodig hebt, benoem expliciet welk bestand en waarom.

> Deze scope-regels staan ook in `CLAUDE.md` in de repo-root, zodat ze automatisch
> bij elke sessie gelden. Je hoeft ze dus niet telkens te herhalen.

**Deze feature is puur additief.** Alleen nieuwe tabellen. Geen bestaande schema's
wijzigen. Geen bestaande data migreren.

**Werk per fase in een aparte Claude Code-sessie.** Start elke fase schoon zodat
de context beperkt blijft. De fases hieronder zijn zo gekozen dat ze op zichzelf staan.

**Randvoorwaarde:** Alembic moet werkend zijn vóór Fase 1 (zie Fase 0).

---

## Fase 0 — Alembic + basisstructuur

1. Stel Alembic in (indien nog niet gedaan) tegen de huidige SQLite-db.
   - Configureer **batch mode** (`render_as_batch=True` in `env.py`) — SQLite
     ondersteunt beperkte `ALTER TABLE`; zonder batch mode falen latere migraties.
   - Genereer een baseline-migratie van het **huidige** schema (autogenerate).
   - Controleer dat de baseline de bestaande Financiën-tabellen exact reflecteert
     en **geen** data-verlies veroorzaakt.
   - Test op een **kopie** van de productie-db, nooit direct op productie.
   - **Let op voor later (deploy):** op ginnybeehome bestaan de tabellen al. Daar
     wordt de baseline dus NIET uitgevoerd maar gestempeld: `alembic stamp <baseline>`.
     Zie de deploysectie onderaan.
2. Maak de map `backend/app/weekmenu/` met `__init__.py`, `models.py`, `schemas.py`,
   `router.py`, `crud.py`.
3. Registreer de nieuwe router in de main app onder prefix `/api/weekmenu`.

**Stop hier. Commit. Test dat de bestaande app nog volledig werkt.**

---

## Fase 1 — Databaseschema

Maak de volgende tabellen in `backend/app/weekmenu/models.py`. Genereer daarna een
Alembic-migratie (`alembic revision --autogenerate -m "weekmenu schema"`).

### Attribuuttabellen (beheerbaar — géén hardcoded enums)
Deze bestaan zodat opties later via een beheerscherm te wijzigen zijn, net als de
categoriebeheer in Financiën.

- **`recipe_moments`** — id, naam, sort_order  (bv. Lunch, Diner, Beide)
- **`recipe_categories`** — id, naam, kleur, sort_order  (Vis, Vlees, Veggie, Pasta, Soep, Salade, Oven, Anders)
- **`recipe_times`** — id, naam, sort_order  (Snel, Gemiddeld, Lang)
- **`recipe_difficulties`** — id, naam, sort_order  (Makkelijk, Gemiddeld, Moeilijk)

### Kern
- **`recipes`**
  - id, titel, beschrijving/stappen (text), foto_pad (nullable), bron_url (nullable)
  - moment_id (FK, nullable), categorie_id (FK, nullable), tijd_id (FK, nullable), moeilijkheid_id (FK, nullable)
  - aangemaakt_op, gewijzigd_op
  - **Foto-opslag:** foto's worden weggeschreven naar `backend/data/recipe_photos/`
    (bestandsnaam = uuid). Deze map staat in `.gitignore` en wordt op de mini-PC
    als Docker-volume gemount — zelfde principe als de SQLite-db: data blijft
    lokaal en komt nooit in de repo. `foto_pad` bevat alleen de bestandsnaam.

- **`ingredients`** — canonieke ingrediëntenlijst (dedupe op genormaliseerde naam)
  - id, naam, genormaliseerde_naam (lowercase, trimmed — uniek)
  - `pantry_type` enum: `always_home` | `pantry` | `normal`
    - `always_home` = verschijnt NOOIT op de boodschappenlijst (peper, zout, olijfolie, boter)
    - `pantry` = verschijnt onder "Voorraadkast", afvinkbaar (pasta, parelcouscous, verse kruiden)
    - `normal` = gewone boodschap
  - `winkelcategorie_id` (FK → shopping_categories, nullable)

- **`recipe_ingredients`** — koppeltabel recept ↔ ingrediënt
  - id, recipe_id (FK), ingredient_id (FK), hoeveelheid (nullable), eenheid (nullable), notitie (nullable)

### Weekplanning
- **`week_plan_entries`**
  - id, datum (date), recipe_id (FK, nullable), vrije_tekst (nullable — bv. "Diepvries", "Frietjes", "Bbq Simon en Jozefien")
  - afgevinkt (bool — het vinkje in het weekmenu-screenshot)

> Een dag kan óf een recept óf vrije tekst hebben. Niet allebei verplicht.

### Boodschappenlijst
- **`shopping_categories`** — id, naam, kleur, sort_order
  - Seed: Groenten & Fruit, Vlees & Vis, Zuivel, Voorraadkast, Diepvries, Drank, Overig
- **`shopping_list_items`**
  - id, naam, categorie_id (FK), afgevinkt (bool), handmatig_toegevoegd (bool)
  - bron: nullable link naar recipe_id/ingredient_id (zodat je ziet dat het uit een menu komt — zie "MENU"-label in screenshot)

**Seed de attribuut- en winkelcategorietabellen idempotent** (net als de bestaande
seed-aanpak). Gebruikerswijzigingen mogen niet overschreven worden bij herstart.

**Stop hier. Commit. Migratie testen op kopie van productie-db.**

---

## Fase 2 — Recept parse-endpoint

Bouw één endpoint dat een bewerkbaar recept-object teruggeeft. **Nooit direct opslaan** —
de frontend toont altijd eerst een review-scherm.

`POST /api/weekmenu/recipes/parse`

Drie parsers achter dit endpoint:

1. **URL met schema.org** — gebruik de Python-library `recipe-scrapers`. Dekt de
   meeste sites (incl. veel Belgische) via JSON-LD `Recipe`-metadata. Geen AI nodig.
   Retourneert titel, ingrediënten, stappen, vaak een foto-URL.

2. **URL fallback (geen schema)** — HTML ophalen, tekst naar Claude API sturen met
   een prompt die **strikt JSON** teruggeeft.

3. **Afbeelding/screenshot** — afbeelding (base64) naar Claude API (vision) met een
   prompt die strikt JSON teruggeeft: titel, ingrediënten (met hoeveelheid + eenheid),
   stappen.

**Belangrijk:**
- **URL-validatie (SSRF):** de app is publiek bereikbaar. Sta alleen `http`/`https`
  toe en weiger interne adressen (localhost, 127.0.0.1, 192.168.x.x, 10.x.x.x,
  169.254.x.x). Eén validatiefunctie vóór elke fetch.
- De Anthropic API-call gebeurt **server-side** (Python). De API-key staat in
  `backend/.env`, komt NOOIT in de frontend.
- Gevraagd JSON-formaat (parser retourneert altijd deze structuur):
  ```json
  {
    "titel": "...",
    "beschrijving": "...",
    "foto_url": "... of null",
    "bron_url": "... of null",
    "ingredienten": [
      {"naam": "...", "hoeveelheid": "... of null", "eenheid": "... of null"}
    ]
  }
  ```
- Bij het **opslaan** (apart endpoint `POST /api/weekmenu/recipes`): match elk
  ingrediënt op `genormaliseerde_naam` tegen de bestaande `ingredients`-tabel.
  Bestaat het al → hergebruik id (behoud `pantry_type`). Bestaat het niet →
  maak aan met default `pantry_type = normal`.

**Stop hier. Commit. Test elk van de drie parsers los.**

---

## Fase 3 — Recept-CRUD + beheerschermen (frontend)

- Receptenlijst + detailweergave (zoals screenshot 2: titel, moment/categorie/tijd
  als selecteerbare pills, ingrediëntenlijst met VOORRAAD-label).
- Recept aanmaken via het parse → review → opslaan-flow uit Fase 2.
- Recept handmatig bewerken.
- **Beheerscherm** voor de attribuuttabellen (moment/categorie/tijd/moeilijkheid)
  en voor `ingredients` (waar je `pantry_type` en winkelcategorie per ingrediënt zet).
- nl-BE formatting overal (consistent met de rest van de app).

**Stop hier. Commit.**

---

## Fase 4 — Weekmenuplanning (frontend + backend)

- Weekweergave met dagen (zoals screenshot 1): per dag een recept kiezen óf vrije
  tekst invullen.
- Weeknavigatie (vorige/volgende week).
- Afvink-toggle per dag.
- Optioneel: lunch-ideeën / notitieveld per week.

`GET/PUT /api/weekmenu/week?start=YYYY-MM-DD`

**Stop hier. Commit.**

---

## Fase 5 — Boodschappenlijst (afgeleid uit de week)

- Genereer de lijst uit alle recepten in de huidige week.
- Voor elk `recipe_ingredient`:
  - `pantry_type = always_home` → **overslaan** (nooit tonen).
  - `pantry_type = pantry` → toevoegen onder "Voorraadkast", afvinkbaar.
  - `pantry_type = normal` → toevoegen onder de juiste `winkelcategorie`.
- Dedupliceer identieke ingrediënten over meerdere recepten (bv. som hoeveelheden
  of toon los — kies één gedrag en documenteer het).
- Handmatige items toevoegen per categorie mogelijk (screenshot 3: "item toevoegen").
- Toon "MENU"-label bij items die uit een recept komen (screenshot 3).
- Afvinken van items.

`GET /api/weekmenu/shopping-list?start=YYYY-MM-DD`
`POST /api/weekmenu/shopping-list/items` (handmatige toevoeging)

**Stop hier. Commit.**

---

## Deployment (na alle fases werkend + getest lokaal)

1. Merge `feature/weekmenu` → main.
2. Op ginnybeehome: `git pull`.
3. **Alembic — let op de volgorde:**
   - De Financiën-tabellen bestaan al op deze db. Stempel eerst de baseline:
     `alembic stamp <baseline-revisie-id>` (voert niets uit, markeert alleen
     dat de db al op dit punt staat).
   - Daarna pas: `alembic upgrade head` (voert alleen de weekmenu-migratie uit).
   - NIET opnieuw seeden — de productie-db bevat echte financiëndata.
   - Maak vóór dit alles een backup-kopie van het db-bestand.
4. `docker compose up -d --build`.
5. Zet de Anthropic API-key en het foto-volume in de mini-PC's `backend/.env`
   en `docker-compose.yml`.

---

## Credits / context besparen tijdens de bouw

- Eén fase = één schone Claude Code-sessie.
- Verwijs expliciet naar `backend/app/weekmenu/` en `frontend/src/weekmenu/`;
  laat Claude Code niet de hele repo (incl. Financiën) doorzoeken.
- Gebruik plan mode vóór elke fase; keur het plan goed vóór je laat uitvoeren.
- Overweeg een `.claudeignore` voor `node_modules`, build-output en Financiën-mappen
  die niet relevant zijn voor deze feature.
- Commit per werkende stap, zodat je nooit een grote sessie hoeft te herhalen.
