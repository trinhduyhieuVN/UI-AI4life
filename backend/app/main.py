from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from . import seed
from .config import SETTINGS
from .db import SessionLocal, init_db
from .models import SymbolRow
from .routers import (
    audit as audit_router,
    auth as auth_router,
    data as data_router,
    export as export_router,
    market as market_router,
    prefs as prefs_router,
    reviews as reviews_router,
    signals as signals_router,
    views as views_router,
    watchlist as watch_router,
)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def create_app(seed_data: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if seed_data:
            init_db()
            with SessionLocal() as s:
                if s.scalar(select(func.count(SymbolRow.symbol))) == 0:
                    seed.load_manifest(s, SETTINGS.manifest_path)
                seed.ensure_demo(s)
        yield

    app = FastAPI(title="Nasdaq Replay API", lifespan=lifespan)
    app.include_router(auth_router.router)
    app.include_router(prefs_router.router)
    app.include_router(market_router.router)
    app.include_router(watch_router.router)
    app.include_router(views_router.router)
    app.include_router(signals_router.router)
    app.include_router(reviews_router.router)
    app.include_router(export_router.router)
    app.include_router(audit_router.router)
    app.include_router(data_router.router)
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()