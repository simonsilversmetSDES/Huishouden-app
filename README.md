# Huishouden-app

Een webapp voor de gezinsfinanciën van Simon & Jozefien. Ze vervangt de Excel
"Budget Tracker": budgetplanning, transacties (met CSV-import van KBC en Fortis),
rekeningstatussen, beleggingen, de lening en de vermogensbalans — allemaal op de
eigen mini-PC, bereikbaar via Tailscale. Niets staat in de cloud.

> **Stand van zaken:** Fase 1 (fundament) is klaar — inloggen werkt en de database
> staat volledig klaar. De modules zelf (budget, transacties, …) volgen per fase.

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
app op **http://localhost:8080** — of op de mini-PC via het Tailscale-adres.
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

- Backend: `cd backend`, venv activeren, `pip install -e .[dev]`, dan
  `pytest` (tests), `ruff check .` (linting), `uvicorn app.main:app --reload` (dev-server).
- Frontend: `cd frontend`, `npm install`, `npm run dev` (dev-server met proxy
  naar de backend op poort 8000), `npm run build` (typecheck + productie-build).
- De volledige functionele specificatie staat in `PROJECT_SPEC.md`;
  afspraken voor Claude Code in `CLAUDE.md`.
