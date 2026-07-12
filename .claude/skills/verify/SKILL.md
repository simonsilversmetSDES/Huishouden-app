---
name: verify
description: Draai de app lokaal en verifieer een wijziging end-to-end (backend + frontend + Playwright).
---

# Huishouden-app end-to-end verifiëren (Windows-dev-laptop)

## Starten
- Backend: draait bij Simon meestal al als `uvicorn --reload` op poort 8000
  (poort bezet = die instantie gebruiken; `--reload` pikt codewijzigingen vanzelf op).
  Zelf starten: `cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`.
- Frontend: `cd frontend; npm run dev` — vite kiest 5174 als 5173 al draait
  (dev-proxy stuurt `/api` naar :8000, zie vite.config.ts).

## Inloggen & data
- Dev-login: `simon@dev.local` / `huishouden-dev` (zie backend/.env; POST `/api/auth/login`).
- Contexten: 1 = Gemeenschappelijk (léég, geen effecten), 2 = Simon (echte dev-data),
  3 = Jozefien. De app opent op context 1 — schakel via de pill-knoppen in de header
  (`header nav >> button:has-text("Simon")`), anders lijkt alles leeg.

## Browser driven (screenshots)
- Playwright is NIET in het project geïnstalleerd; wel bruikbaar via de npx-cache:
  `$env:NODE_PATH = 'C:\Users\simon\AppData\Local\npm-cache\_npx\e41f203b7505f1fb\node_modules'`
  en dan een node-script met `require('playwright')` (Chromium staat in
  `%LOCALAPPDATA%\ms-playwright`). Cache-pad weg? `npx playwright --version` herstelt het.
- Login-flow in het script: vul `input[type=email]` + `input[type=password]`,
  klik `button[type=submit]`, wacht met `page.waitForURL` tot je van /login weg bent.
- API-antwoorden checken met `page.evaluate(() => fetch('/api/...').then(r => r.json()))`
  (zelfde sessiecookie) — betrouwbaarder dan `waitForResponse`-sniffing.

## Gotchas
- Twee 401's in de browserconsole bij het opstarten zijn normaal (auth-check vóór login).
- De Beleggingen-tab doet bij openen automatisch een koersen-fetch (POST /api/prices/fetch)
  die de dev-db bijwerkt — totalen kunnen daardoor per run enkele centen verschuiven.
- Dit is de échte dev-db (kopie van echte data): niets muteren behalve wat de flow zelf doet.
