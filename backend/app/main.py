from fastapi import FastAPI

from .routers import (
    auth as auth_router,
    market as market_router,
    prefs as prefs_router,
    views as views_router,
    watchlist as watchlist_router,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Nasdaq Replay API")
    app.include_router(auth_router.router)
    app.include_router(prefs_router.router)
    app.include_router(market_router.router)
    app.include_router(watchlist_router.router)
    app.include_router(views_router.router)
    return app