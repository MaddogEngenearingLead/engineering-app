from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name,
                  description="P&ID dashboard and pipeline engineering API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(router, prefix=settings.api_prefix)
    from app.services.ollama_runtime import prepare_local_fallback
    app.add_event_handler("startup", prepare_local_fallback)
    return app


# Install the same persisted fallback policy for the optional API as for the GUI.
from app.gui.feature_controls import install as _install_feature_controls
_install_feature_controls()

app = create_app()


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Engineering App API is running"}
