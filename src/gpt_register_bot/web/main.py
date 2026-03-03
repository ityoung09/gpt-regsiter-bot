from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gpt_register_bot.web.api import build_api_router
from gpt_register_bot.web.config import STATIC_DIR, TEMPLATE_DIR
from gpt_register_bot.web.services.process_manager import ProcessManager


def create_app() -> FastAPI:
    app = FastAPI(title="GPT Register Bot Console", version="1.0.0")

    manager = ProcessManager()
    app.include_router(build_api_router(manager))

    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")

    index_file = TEMPLATE_DIR / "index.html"

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(index_file)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("gpt_register_bot.web.main:app", host="0.0.0.0", port=8000)
