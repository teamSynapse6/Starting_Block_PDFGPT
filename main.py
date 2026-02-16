import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api.announcement.router import router as announcements_router
from app.api.llm.router import router as llm_router, archive_idle_sessions
from app.api.llm.client import OllamaClient
from app.api.llm.session_store import RedisSessionStore
from app.api.llm.archive_store import SQLiteArchiveStore
from app.api.announcement.storage import MinioStorage
from app.core.config import (
    LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS,
    LLM_IDLE_ARCHIVE_SECONDS,
    OLLAMA_MODEL_IDLE_SECONDS,
    OLLAMA_IDLE_SWEEP_INTERVAL_SECONDS,
)


async def archive_loop(app: FastAPI):
    interval = app.state.llm_archive_sweep_interval_seconds
    while True:
        await archive_idle_sessions(app)
        await asyncio.sleep(interval)


async def ollama_idle_loop(app: FastAPI):
    interval = app.state.ollama_idle_sweep_interval_seconds
    idle_seconds = app.state.ollama_model_idle_seconds
    client = app.state.ollama_client

    while True:
        await client.unload_if_idle(idle_seconds)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = MinioStorage()
    storage.ensure_bucket()
    app.state.storage = storage

    session_store = RedisSessionStore()
    archive_store = SQLiteArchiveStore()
    archive_store.initialize()
    ollama_client = OllamaClient()
    await ollama_client.ensure_server_running()

    app.state.session_store = session_store
    app.state.archive_store = archive_store
    app.state.ollama_client = ollama_client
    app.state.llm_idle_archive_seconds = LLM_IDLE_ARCHIVE_SECONDS
    app.state.llm_archive_sweep_interval_seconds = LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS
    app.state.ollama_model_idle_seconds = OLLAMA_MODEL_IDLE_SECONDS
    app.state.ollama_idle_sweep_interval_seconds = OLLAMA_IDLE_SWEEP_INTERVAL_SECONDS

    app.state.archive_loop_task = asyncio.create_task(archive_loop(app))
    app.state.ollama_idle_loop_task = asyncio.create_task(ollama_idle_loop(app))
    yield

    archive_task = app.state.archive_loop_task
    archive_task.cancel()
    try:
        await archive_task
    except asyncio.CancelledError:
        pass

    ollama_idle_task = app.state.ollama_idle_loop_task
    ollama_idle_task.cancel()
    try:
        await ollama_idle_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="PDFGPT_StartingBlock_Server", lifespan=lifespan)
app.include_router(announcements_router)
app.include_router(llm_router)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5001, timeout_keep_alive=60, workers=2)
