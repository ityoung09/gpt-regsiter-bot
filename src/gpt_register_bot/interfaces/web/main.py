from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gpt_register_bot.config.settings import get_settings
from gpt_register_bot.container import get_container
from gpt_register_bot.interfaces.web.api import build_api_router
from gpt_register_bot.interfaces.web.config import STATIC_DIR, TEMPLATE_DIR

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="GPT Register Bot Console",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.include_router(build_api_router(get_container().job_manager()))
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")

    index_file = TEMPLATE_DIR / "index.html"
    if not index_file.is_file():
        logger.warning("index template not found at %s", index_file)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        if not index_file.is_file():
            raise HTTPException(
                status_code=503,
                detail=f"UI template missing: {index_file}. Reinstall with 'uv sync'.",
            )
        return FileResponse(index_file)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "gpt_register_bot.interfaces.web.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
