from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
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
from app.weekmenu import router as weekmenu


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Settings meteen laden: de secret-key-guard (config.Settings) moet de app
    # bij het opstarten laten crashen, niet pas bij het eerste request.
    get_settings()
    yield


app = FastAPI(
    title="Huishouden-app",
    docs_url=None,  # geen publieke API-docs: de app staat publiek bereikbaar
    redoc_url=None,  # via Cloudflare Tunnel — de login is de enige toegangslaag
    openapi_url=None,
    lifespan=lifespan,
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
app.include_router(weekmenu.router)
