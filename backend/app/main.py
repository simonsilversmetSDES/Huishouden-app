from fastapi import FastAPI

from app.routes import auth, health

app = FastAPI(
    title="Huishouden-app",
    docs_url=None,  # geen publieke API-docs; alles zit achter Tailscale maar toch
    redoc_url=None,
    openapi_url=None,
)

app.include_router(health.router)
app.include_router(auth.router)
