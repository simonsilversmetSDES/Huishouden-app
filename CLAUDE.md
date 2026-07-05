# CLAUDE.md — Huishouden-app (Persoonlijke Financiën)

## Wat dit project is
Een self-hosted financiële webapp voor twee gebruikers (Simon & Jozefien) die een bestaand
Excel-werkboek vervangt. **`PROJECT_SPEC.md` in de root is de bron van waarheid** voor alle
functionaliteit, het datamodel en de teststrategie. Lees dat bestand vóór je aan een fase begint.
De planning en fasering staat los in de roadmap (Notion) — werk één fase per sessie.

## Stack (vast — niet wijzigen zonder overleg)
- **Backend:** Python + FastAPI + SQLAlchemy (+ Alembic voor migraties).
- **Database:** SQLite (één bestand, volume-mount in Docker).
- **Frontend:** React + TypeScript + Vite + Tailwind CSS; recharts voor grafieken.
- **Koersen:** `yfinance` achter een `PriceProvider`-abstractie, met manuele invoer als fallback.
- **Auth:** sessie-cookies, 2 vaste accounts, wachtwoorden gehasht met argon2. Geen registratie.
- **Deploy:** Docker Compose, bereikbaar via Tailscale. Eén `docker compose up -d` moet volstaan.

## Harde regels
- **Geen secrets in de repo.** Wachtwoord-hashes, keys en config via `.env` (met `.env.example` als sjabloon).
- **`/data` staat in `.gitignore` en mag NOOIT gecommit worden** — het bevat echte financiële data
  (Excel + bank-CSV's). Controleer dit vóór elke commit.
- **Tests eerst voor alle financiële berekeningen.** Schrijf de test met de referentiewaarden uit
  PROJECT_SPEC.md §10 (annuïteit, gemiddelde aankoopprijs, "to be allocated", wederbeleggingsvergoeding)
  vóór de implementatie. Cijfers moeten exact overeenkomen met de Excel.
- **Privacy:** geen telemetrie, geen externe calls behalve de koersen-fetch (die uitschakelbaar).
- Geld intern als integer-centen of Python `Decimal` — nooit als float — om afrondingsfouten te vermijden.

## Conventies
- **Locale nl-BE:** bedragen weergeven als `€ 1.234,56`, datums als `dd/mm/jjjj`. (Opslag intern:
  ISO-datums en Decimal; formattering enkel in de weergavelaag.)
- Python: type hints overal, `ruff` voor linting, `pytest` voor tests.
- TypeScript: strict mode aan.
- Commit per afgewerkte, werkende stap met een duidelijke message.

## Mapstructuur (richtlijn)
- `backend/` — FastAPI-app, modellen, routes, services, tests
- `frontend/` — React/Vite-app
- `scripts/` — eenmalige migratiescripts (Excel-import, CSV-backfill)
- `data/` — **git-ignored**; `data/excel/` en `data/csv/` met de echte bronbestanden
- `design/` — Google Stitch-mockups als referentie
- `PROJECT_SPEC.md`, `CLAUDE.md`, `docker-compose.yml`, `.env.example`

## Werkwijze
- Begin elke fase in **plan mode**: stel eerst een plan voor, wacht op akkoord, bouw dan.
- Draai migratiescripts eerst op een kopie van de database, nooit meteen op echte data.
- Als iets in PROJECT_SPEC.md onduidelijk of tegenstrijdig is: vraag het, raad niet.
