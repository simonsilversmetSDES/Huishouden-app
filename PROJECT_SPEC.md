# Persoonlijke Financiën App — Projectspecificatie

> **Doel van dit document:** volledige functionele en technische specificatie voor Claude Code om een self-hosted financiële webapp te bouwen die de bestaande Excel "Budget Tracker (Jozefien & Simon)" volledig vervangt, aangevuld met automatische CSV-import van bankrekeningen (KBC & BNP Paribas Fortis).

---

## 1. Context & doel

- Twee gebruikers: **Simon** en **Jozefien**. Drie financiële contexten: **Gemeenschappelijk**, **Simon**, **Jozefien**.
- De app vervangt een Excel-werkboek dat momenteel gebruikt wordt voor: budgetplanning per categorie, transactietracking, maandelijkse rekeningstatussen, beleggingsportefeuille, leningopvolging en vermogensbalans.
- Privacy is een harde eis: alle data blijft op de eigen server (mini-PC thuis). Geen cloud-databases, geen externe analytics, geen third-party trackers.
- De cijfers moeten exact overeenkomen met de Excel-berekeningen (zie §10 teststrategie).

## 2. Architectuur & hosting

```
┌─────────────────────────────── Mini-PC (thuis) ───────────────────────────────┐
│  Docker Compose                                                                │
│  ┌──────────────┐   ┌───────────────────┐   ┌────────────────────────┐        │
│  │  Frontend     │──▶│  Backend API      │──▶│  SQLite (volume mount) │        │
│  │  (static SPA) │   │  (REST + auth)    │   │  + nightly backup      │        │
│  └──────────────┘   └───────────────────┘   └────────────────────────┘        │
│          ▲                    ▲                                                │
└──────────┼────────────────────┼────────────────────────────────────────────────┘
           │   Tailscale (tailnet-only, HTTPS via Tailscale Serve)
     Simon (laptop/gsm)   Jozefien (gsm)
```

- **Toegang uitsluitend via Tailscale.** Geen poorten open naar het publieke internet. HTTPS via `tailscale serve` (of Caddy met Tailscale-certificaten) zodat de app als PWA op gsm installeerbaar is.
- **Database: SQLite** (één bestand, triviale backups, ruim voldoende voor 2 gebruikers). ORM met migraties verplicht.
- **Backend:** lichte REST API. Voorkeur: **Node.js + TypeScript (Fastify of Hono) + Drizzle ORM** of **Python + FastAPI + SQLAlchemy**. Kies één stack en blijf consistent.
- **Frontend:** **React + TypeScript + Vite**, Tailwind CSS, recharts (of chart.js) voor grafieken. Gebouwd als statische bundel, geserveerd door de backend of een aparte nginx-container.
- **Auth:** eenvoudige login met 2 accounts (Simon, Jozefien), sessie-cookies, bcrypt/argon2 gehashte wachtwoorden. Geen registratieflow.
- **Repo:** private GitHub-repository. Secrets (wachtwoord-hashes, API-keys) nooit in de repo — via `.env` + Docker secrets.
- Design-referentie: mockups uit Google Stitch worden als afbeeldingen/HTML aangeleverd; de frontend wordt daarop gebaseerd maar volledig in de eigen codebase gebouwd.

## 3. Datamodel

```sql
-- Contexten & gebruikers
users(id, name, email, password_hash)
contexts(id, name)                    -- 'Gemeenschappelijk', 'Simon', 'Jozefien'

-- Rekeningen
accounts(id, context_id, name, iban NULLABLE, bank ENUM('KBC','Fortis','Andere'),
         type ENUM('zicht','spaar','belegging','andere'), active BOOL)

-- Categorieën (per context, per type)
categories(id, context_id, name, type ENUM('Inkomen','Uitgaven','Sparen'),
           sort_order, active BOOL)

-- Budgetplanning: bedrag per categorie per maand
budgets(id, category_id, year, month, amount)          -- UNIQUE(category_id, year, month)

-- Transacties (manueel of via CSV-import)
transactions(id, context_id, account_id NULLABLE, category_id NULLABLE,
             date, amount,                              -- + = inkomen, − = uitgave
             type ENUM('Inkomen','Uitgaven','Sparen'),
             counterparty_name, counterparty_iban, description,
             source ENUM('manual','import_kbc','import_fortis'),
             import_id NULLABLE, import_hash UNIQUE NULLABLE,  -- dedupe
             categorization ENUM('auto','manual','uncategorized'),
             is_internal_transfer BOOL DEFAULT 0)

imports(id, filename, bank, imported_at, row_count, duplicate_count)

-- Categorisatieregels
categorization_rules(id, context_id, priority,
                     match_field ENUM('counterparty_name','counterparty_iban','description'),
                     match_type ENUM('contains','equals','regex'),
                     match_value, category_id, created_from_correction BOOL)

-- Maandelijkse rekeningstatus (snapshot per rekening)
account_snapshots(id, account_id, snapshot_date, balance)   -- UNIQUE(account_id, snapshot_date)

-- Beleggingen
securities(id, name, ticker, isin NULLABLE, currency DEFAULT 'EUR', owner_context_id)
security_transactions(id, security_id, date, side ENUM('buy','sell'),
                      shares DECIMAL, price_per_share, fee, tax,   -- beurstaks (TOB)
                      total)                                       -- shares*price + fee + tax
security_prices(id, security_id, date, price, source)              -- koershistoriek/cache

-- Lening
loans(id, context_id, name, principal, annual_rate, term_months,
      start_date, monthly_payment,
      property_value_paid NULLABLE, property_value_estimate NULLABLE)
loan_payments(id, loan_id, date, amount, interest_part, principal_part, balance_after)

-- Vermogensbalans (netto waarde per persoon per maand)
net_worth_snapshots(id, context_id, snapshot_date,
                    asset_class ENUM('contant','etf_fondsen','pensioensparen',
                                     'groepsverzekering','woning','aandelen'),
                    value)
```

**Seed-categorieën** (uit de bestaande Excel, context Gemeenschappelijk):
- *Inkomen:* Gemeenschappelijke bijdrage, Maaltijdcheques, Elektriciteit wagen, Terugbetalingen / Uitzonderlijk, Sparen reis
- *Uitgaven:* Lening, Energie en Water, Internet, Boodschappen, Restaurant / Café, Cadeaus, Verzekeringen / Belastingen, Huis & Wonen, Ontspanning/Sport/Boeken, Reizen / weekendje weg, Verzorging, Kadastraal inkomen, Andere, Katten
- *Sparen:* Spaarrekening, Beleggingen

Simon en Jozefien hebben elk hun eigen (gelijkaardige) categorielijst — categorieën zijn CRUD-beheerbaar per context.

## 4. Module: Budgetplanning

Vervangt sheets *Budget Planning*, *Tracking*, *Dashboard*.

- Per context, per jaar: budgetmatrix **categorieën × 12 maanden** met rijtotalen en jaartotaal, gegroepeerd per type (Inkomen / Uitgaven / Sparen).
- Snelle invoer: waarde naar rechts doortrekken ("vul rest van het jaar"), jaar kopiëren naar volgend jaar.
- **"To be allocated"** per maand = Σ Inkomen − Σ Uitgaven − Σ Sparen (zero-based budgeting indicator, mag negatief, kleurcodering).
- Dashboard per maand/jaar/custom periode: **budget vs. werkelijk** per categorie (uit transactions), met verschil en progressiebalk; drill-down naar de onderliggende transacties.
- Historiek blijft raadpleegbaar per jaar (zoals de jaartabbladen in Excel).

## 5. Module: Transacties & CSV-import

### 5.1 Manuele invoer
Snel formulier: datum, type, categorie, bedrag, omschrijving, context, rekening. Bewerken en verwijderen mogelijk. Lijstweergave met filters (periode, type, categorie, context, bron, ongecategoriseerd).

### 5.2 CSV-import — bankformaten

**BNP Paribas Fortis** (persoonlijke rekening Simon):
- Encoding UTF-8 **met BOM**, delimiter `;`, decimaal **komma**, datum `dd/mm/jjjj`.
- Kolommen: `Volgnummer; Uitvoeringsdatum; Valutadatum; Bedrag; Valuta rekening; Rekeningnummer; Type verrichting; Tegenpartij; Naam van de tegenpartij; Mededeling; Details; Status; Reden van weigering`
- Mapping: date ← Uitvoeringsdatum, amount ← Bedrag, counterparty_iban ← Tegenpartij, counterparty_name ← Naam van de tegenpartij, description ← Mededeling (fallback: Details). Rijen met Status ≠ "Geaccepteerd" overslaan.
- Dedupe-sleutel: `Volgnummer` + Rekeningnummer (bv. `2026-00186`), gehasht in `import_hash`.

**KBC** (gemeenschappelijke rekening):
- Delimiter `;`, decimaal **komma**, datum `dd/mm/jjjj`, velden bevatten veel padding-spaties (trimmen!), rijen gescheiden door `\r`.
- Kolommen: `Rekeningnummer; Rubrieknaam; Naam; Munt; Afschriftnummer; Datum; Omschrijving; Valuta; Bedrag; Saldo; credit; debet; rekeningnummer tegenpartij; BIC tegenpartij; Naam tegenpartij; Adres tegenpartij; gestructureerde mededeling; Vrije mededeling`
- Mapping: date ← Datum, amount ← Bedrag, counterparty_iban ← rekeningnummer tegenpartij, counterparty_name ← Naam tegenpartij, description ← Vrije mededeling (fallback: Omschrijving). Merchant bij kaartbetalingen zit **in de Omschrijving-tekst** (bv. "BETALING VIA BANCONTACT … COLRUYT SINT-AMAN …") — parse de handelaarsnaam eruit voor categorisatie.
- Dedupe-sleutel: hash van (Rekeningnummer, Afschriftnummer, Datum, Bedrag, Omschrijving).

Importflow: upload → parse & valideer → toon preview met voorgestelde categorieën → gebruiker bevestigt → opslaan. Duplicaten worden getoond maar niet opnieuw geïmporteerd (idempotent: zelfde bestand twee keer opladen = 0 nieuwe rijen).

### 5.3 Automatische categorisatie

- **Regelengine** op `categorization_rules`, geëvalueerd op prioriteit: match op tegenpartijnaam, IBAN of omschrijving (contains/equals/regex, case-insensitive).
- Elke transactie krijgt: categorie (auto) of status *ongecategoriseerd*. **Alles blijft achteraf manueel aanpasbaar.**
- **Leereffect:** wanneer de gebruiker een auto-categorie corrigeert, stel voor om een regel aan te maken op basis van de tegenpartij ("Altijd 'JUST RUSSEL' → Katten?").
- **Interne overschrijvingen** (tussen eigen rekeningen, herkenbaar aan eigen IBAN's als tegenpartij) worden gemarkeerd als `is_internal_transfer` en uitgesloten van budget vs. werkelijk. Eigen IBAN's komen uit `accounts.iban`.
- Seed-regels afgeleid uit de echte data:

| Match (contains) | Categorie |
|---|---|
| COLRUYT, ALDI, DELHAIZE, LIDL, CARREFOUR, BON'AP, OKAY, MUHSIN MARKET | Boodschappen |
| LUMINUS | Energie en Water |
| MOBILE VIKINGS, TELENET, PROXIMUS | Internet |
| KBC VERZEKERINGEN, WONINGPOLIS, GEZINSPOLIS | Verzekeringen / Belastingen |
| WONINGKREDIET (KBC "TERUGBETALING … WONINGKREDIET") | Lening |
| GAMMA, ACTION, IKEA, BRICO | Huis & Wonen |
| JUST RUSSEL | Katten |
| CINAIR, KANGOEROE | Ontspanning/Sport/Boeken |
| TANDARTS, APOTHEEK, A.S.Z. | Verzorging |
| LOON (mededeling, credit) | Inkomen: loon/bijdrage |
| MAALTIJDCHEQUES / MONIZZE / EDENRED / PLUXEE | Maaltijdcheques |
| AUTOMATISCH SPAREN, mededeling "sparen" | Sparen: Spaarrekening |

## 6. Module: Rekeningstatus

Vervangt sheet *Rekeningstatus*.

- Maandelijkse manuele snapshot per rekening (zicht, spaar, …) per context; datum default = 1e van de maand.
- Totaal per context per maand + **verandering t.o.v. vorige maand** (absoluut en %).
- Grafiek: evolutie totaal vermogen op rekeningen over tijd, gestapeld per rekening.
- Reminder-indicator op het dashboard wanneer de snapshot van de huidige maand ontbreekt.

## 7. Module: Beleggingen

Vervangt sheets *Beleggingstransacties S./J.*, deel van *Balans*.

- Transactielog per persoon: datum, effect, aantal (fractioneel! bv. 0,013013 BTC), prijs per stuk, transactiekost, **beurstaks (TOB)**, totaal.
- Per positie berekend: totaal aantal, **gemiddelde aankoopprijs** (kosten en taks inbegrepen: Σ totaal / Σ aantal), totale kostprijs, actuele waarde, winst/verlies in € en %.
- **Actuele koersen:** dagelijkse fetch per ticker via gratis bron (bv. Yahoo Finance endpoint) met cache in `security_prices`; manuele koersinvoer als fallback (belangrijk voor fondsen zonder ticker en voor de groepsverzekering).
- Portefeuilleoverzicht: totale waarde, totale inleg, totaal rendement, verdeling per positie (% portefeuille).
- **Meerwaardebelasting-ondersteuning:** bij verkopen gerealiseerde meerwaarde berekenen o.b.v. gemiddelde aankoopprijs; jaaroverzicht gerealiseerde meerwaarden (relevant voor de Belgische meerwaardebelasting vanaf 2026; toon berekening en jaartotaal, geen fiscaal advies).

## 8. Module: Lening & woning

Vervangt sheets *Lening*, *Hogere maandaflossing*, *Wederbelggings*.

- Leningparameters: bedrag (€ 245.000), looptijd (15 jaar), nettorente (2,51 %), startdatum, maandlast (€ 1.631,52 — manueel instelbaar of berekend via annuïteitenformule).
- **Aflossingstabel per maand**: intrest = saldo × (rente/12), kapitaal = maandlast − intrest, saldo. Jaaraggregatie zoals in Excel.
- KPI's: totaal afbetaald (maandlasten, kapitaal, intresten), **% kapitaal afgelost vs. openstaand**, resterende looptijd ("13 jaar en 3 maanden"), einddatum.
- **Scenario: hogere maandaflossing** — input nieuwe maandlast → nieuwe einddatum, tijdwinst in maanden, intrestbesparing, **wederbeleggingsvergoeding (3 maanden intrest op openstaand saldo)**, netto voordeel, terugverdientijd.
- Woningblok: betaalde prijs, actuele schatting, meerwaarde. Woningwaarde en afgelost kapitaal voeden de vermogensbalans.

## 9. Module: Vermogensbalans & dashboards

Vervangt sheets *Balans*, *Status balans*, *Dashboard*.

- **Nettowaarde per context** per maand: contant geld, beleggingsfondsen/ETF's, pensioensparen, groepsverzekering, woning(aandeel), aandelen. Deels automatisch gevoed (rekeningsnapshots, beleggingswaarde, lening/woning), deels manueel.
- Grafieken: nettowaarde-evolutie, verdeling activa (donut), budget vs. werkelijk, spaarratio per maand.
- Hoofddashboard = landingspagina: totaal vermogen, verandering deze maand, budget-status huidige maand, openstaand leningsaldo + % afgelost, portefeuillewinst/-verlies, ontbrekende snapshots.

## 10. Datamigratie & teststrategie

- **Eenmalige migratiescripts** (apart uitvoerbaar, in `/scripts`):
  1. Excel-import: categorieën, budgetten (alle jaren), alle trackingtransacties (Gem./S./J.), rekeningstatussen, beleggingstransacties (S. en J.), leningparameters + betaalhistoriek, vermogensbalans-historiek.
  2. CSV-backfill: historische KBC- en Fortis-exports.
- **Unit tests verplicht** voor alle financiële berekeningen. Referentiewaarden uit de Excel als fixtures, o.a.:
  - Annuïteit: jaar 1 → intrest € 5.993,93 / kapitaal € 13.584,31; saldo na jaar 1 = € 231.415,69.
  - Gemiddelde aankoopprijs positie 1 = € 98,240055 bij 25 stuks / € 2.456,00 totaal.
  - "To be allocated" jan 2025 (Gem.) = € 92,08.
  - Wederbeleggingsvergoeding bij saldo € 221.001,58 = € 1.386,78.
- Tests voor beide CSV-parsers met geanonimiseerde fixture-bestanden (delimiter, BOM, decimale komma, padding, dedupe, statusfilter).

## 11. Non-functionele eisen

- Volledig responsive (gsm-gebruik door beide gebruikers is het hoofdscenario voor invoer).
- Bedragen in **€ 1.234,56**-notatie, datums **dd/mm/jjjj** (nl-BE locale).
- Nachtelijke SQLite-backup (bv. `sqlite3 .backup` naar tweede volume, 30 dagen retentie).
- Docker Compose met health checks; één `docker compose up -d` volstaat.
- Geen telemetrie of externe calls behalve de koersen-fetch (uitschakelbaar).
- Codekwaliteit: TypeScript strict / Python typed, linting, CI-workflow (GitHub Actions: lint + tests).

## 12. Buiten scope (v1)

- Weekmenu/recepten (bestaande Mealie-instance op dezelfde server dekt dit; eventuele integratie is v2).
- Automatische bankkoppelingen (PSD2/Ponto e.d.) — import blijft via CSV.
- Multi-currency (alles EUR; crypto-aantallen wel fractioneel).
