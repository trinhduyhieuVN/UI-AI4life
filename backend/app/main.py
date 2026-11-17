from fastapi import FastAPI

from .routers import auth as auth_router, market as market_router, prefs as prefs_router


def create_app() -> FastAPI:
    app = FastAPI(title="Nasdaq Replay API")
    app.include_router(auth_router.router)
    app.include_router(prefs_router.router)
    app.include_router(market_router.router)
    return app