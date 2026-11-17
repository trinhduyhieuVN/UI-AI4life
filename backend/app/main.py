from fastapi import FastAPI

from .routers import auth as auth_router


def create_app() -> FastAPI:
    app = FastAPI(title="Nasdaq Replay API")
    app.include_router(auth_router.router)
    return app