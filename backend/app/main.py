from fastapi import FastAPI

from app.routes import (
    auth,
    budgets,
    categories,
    contexts,
    dashboard,
    health,
    imports,
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
app.include_router(transactions.router)
app.include_router(imports.router)
