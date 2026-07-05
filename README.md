# Huishouden-app

Een webapp voor de gezinsfinanciën van Simon & Jozefien. Ze vervangt de Excel
"Budget Tracker": budgetplanning, transacties (met CSV-import van KBC en Fortis),
rekeningstatussen, beleggingen, de lening en de vermogensbalans — allemaal op de
eigen mini-PC, bereikbaar via Tailscale. Niets staat in de cloud.

> **Stand van zaken:** Fase 1 (fundament) en Fase 2 (budgetmodule) zijn klaar —
> inloggen, het dashboard met "te verdelen" en budget vs. werkelijk, de budgetmatrix
> per jaar, en de eenmalige import uit de oude Excel. De volgende modules
> (transacties met CSV-import, beleggingen, lening, balans) volgen per fase.

## Wat heb je nodig?

- **Docker** (Docker Desktop op Windows/Mac, of gewoon Docker op de mini-PC).
- Verder niets. Python en Node zijn alleen nodig als je aan de code wil werken.

## Eerste keer instellen (eenmalig, ± 10 minuten)

**Stap 1 — Maak je instellingenbestand.**
Kopieer het voorbeeldbestand naar een echt instellingenbestand:

```
copy .env.example .env        (Windows)
cp .env.example .env          (Linux/Mac)
```

Het bestand `.env` bevat jullie geheimen en blijft altijd op deze computer —
het wordt nooit meegestuurd naar GitHub.

**Stap 2 — Verzin een geheime sleutel.**
De app gebruikt die om login-sessies te beveiligen. Genereer er één:

```
docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_hex(32))"
```

Kopieer de lange reeks tekens die verschijnt en plak ze in `.env` achter `SECRET_KEY=`.

**Stap 3 — Maak voor elk van jullie een wachtwoord-"hash".**
Een hash is een versleutelde versie van je wachtwoord: de app kan ermee controleren
of je wachtwoord juist is, zonder het wachtwoord zelf ergens op te slaan.

```
docker compose build backend
docker compose run --rm backend python /scripts/hash_password.py
```

Typ een wachtwoord (je ziet niets verschijnen tijdens het typen — dat hoort zo)
en druk op Enter. Kopieer de regel die met `$argon2id$` begint en plak die in
`.env` achter `SIMON_PASSWORD_HASH=`. Doe hetzelfde nog een keer voor Jozefien.

**Stap 4 — Vul de e-mailadressen in.**
Zet in `.env` achter `SIMON_EMAIL=` en `JOZEFIEN_EMAIL=` de adressen waarmee
jullie willen inloggen.

## Opstarten

```
docker compose up -d
```

De eerste keer duurt dit enkele minuten (alles wordt gebouwd). Daarna staat de
app op **http://localhost:8081** — of op de mini-PC via het Tailscale-adres.
Log in met je e-mailadres en het wachtwoord uit stap 3.

## Handige commando's

| Wat wil je doen? | Commando |
|---|---|
| App starten | `docker compose up -d` |
| App stoppen | `docker compose down` |
| Kijken of alles draait | `docker compose ps` |
| Logboek bekijken (bij problemen) | `docker compose logs -f` |
| Updaten na nieuwe code | `git pull` en dan `docker compose up -d --build` |
| Wachtwoord wijzigen | Stap 3 opnieuw, nieuwe hash in `.env`, dan `docker compose up -d --force-recreate backend` |

## Waar staat mijn data?

Alles staat in de map **`data/`** naast dit bestand:

- `data/db/` — de database zelf (één bestand);
- `data/backups/` — automatische dagelijkse backups, 30 dagen bewaard;
- `data/excel/` en `data/csv/` — hier zet je straks de oude Excel en de
  bank-exports voor de eenmalige import.

De map `data/` wordt **nooit** naar GitHub gestuurd (net als `.env`). Wil je een
externe backup, kopieer dan af en toe de hele `data/`-map naar een USB-stick of
een andere schijf.

## Voor wie aan de code werkt

### Lokaal draaien zonder Docker (dev-omgeving op de laptop)

Eenmalig instellen — alles gebeurt vanuit de map `backend/`:

1. Maak `backend/.env` (staat in `.gitignore`) met minstens:

   ```
   APP_ENV=development
   SECRET_KEY=<lange random string>
   DATABASE_URL=sqlite:///../data/db/huishouden-dev.db
   SIMON_EMAIL=simon@dev.local
   SIMON_PASSWORD_HASH=<argon2-hash, zie scripts/hash_password.py>
   SESSION_COOKIE_SECURE=false
   ```

   **Let op:** de database-URL is relatief aan de map waaruit je de backend start
   (dus `../data/db/...` vanuit `backend/`). Een verkeerd pad geeft de fout
   *"unable to open database file"*. Anders dan in Docker Compose hoef je de
   `$`-tekens in de hash hier **niet** te verdubbelen.

2. Maak de database aan en vul de basisgegevens:

   ```
   cd backend
   .venv\Scripts\python -m alembic upgrade head
   .venv\Scripts\python -m app.seed
   ```

Daarna, telkens je wil werken (twee terminals):

```
cd backend  → .venv\Scripts\python -m uvicorn app.main:app --reload
cd frontend → npm run dev
```

De app staat dan op **http://localhost:5173** (Vite stuurt `/api` door naar de
backend op poort 8000). Gewijzigde `.env`? Herstart de backend — `--reload` ziet
alleen codewijzigingen.

### Overige commando's

- Backend: `pytest` (tests), `ruff check .` (linting) — vanuit `backend/`.
- Frontend: `npm run build` (typecheck + productie-build), `npm run lint`.
- Excel-import (eenmalig, altijd op een **kopie** van de database):
  `backend\.venv\Scripts\python scripts\import_excel.py --inspect` om te verkennen,
  daarna met `--db sqlite:///pad/naar/kopie.db` om echt te importeren.
- De volledige functionele specificatie staat in `PROJECT_SPEC.md`;
  afspraken voor Claude Code in `CLAUDE.md`.
