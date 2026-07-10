from fastapi import FastAPI

from app.routes import (
    accounts,
    auth,
    budgets,
    categories,
    contexts,
    dashboard,
    forecast,
    health,
    imports,
    loans,
    net_worth,
    prices,
    rules,
    securities,
    snapshots,
    transactions,
)

app = FastAPI(
    title="Huishouden-app",
    docs_url=None,  # geen publieke API-docs; alles zit achter Tailscale maar toch
    redoc_url=None,
    openapi_url=None,
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(contexts.router)
app.include_router(categories.router)
app.include_router(budgets.router)
app.include_router(dashboard.router)
app.include_router(forecast.router)
app.include_router(transactions.router)
app.include_router(imports.router)
app.include_router(rules.router)
app.include_router(accounts.router)
app.include_router(snapshots.router)
app.include_router(net_worth.router)
app.include_router(securities.router)
app.include_router(prices.router)
app.include_router(loans.router)
