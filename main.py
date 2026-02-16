import asyncio
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api.announcement.router import router as announcements_router
from app.api.llm.router import router as llm_router, archive_idle_sessions
from app.api.llm.client import OllamaClient
from app.api.llm.session_store import MySQLSessionStore
from app.api.llm.archive_store import MySQLArchiveStore
from app.core.storage import MinioStorage
from app.core.db_models import ensure_database_and_tables
from app.api.announcement.index_job_store import AnnouncementIndexJobStore
from app.api.announcement.vector_indexer import AnnouncementVectorIndexer
from app.core.config import (
    INDEXING_POLL_INTERVAL_SECONDS,
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

async def announcement_index_loop(app: FastAPI):
    interval = app.state.indexing_poll_interval_seconds
    worker_id = app.state.index_worker_id
    job_store = app.state.index_job_store
    vector_indexer = app.state.vector_indexer
    storage = app.state.storage

    while True:
        job = await asyncio.to_thread(job_store.claim_next, worker_id)
        if job is None:
            await asyncio.sleep(interval)
            continue

        job_id = job["id"]
        action = job["action"]
        announcement_id = job["announcement_id"]

        try:
            if action == "delete":
                await asyncio.to_thread(vector_indexer.delete_announcement, announcement_id)
            else:
                text = await asyncio.to_thread(storage.get_processed_text, announcement_id)
                if text is None:
                    await asyncio.to_thread(vector_indexer.delete_announcement, announcement_id)
                else:
                    await asyncio.to_thread(vector_indexer.upsert_announcement, announcement_id, text)

            await asyncio.to_thread(job_store.mark_done, job_id)
        except Exception as error:
            await asyncio.to_thread(job_store.mark_failed, job_id, str(error))
            await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_database_and_tables()

    storage = MinioStorage()
    storage.ensure_bucket()
    app.state.storage = storage

    session_store = MySQLSessionStore()
    archive_store = MySQLArchiveStore()
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
    index_job_store = AnnouncementIndexJobStore()
    vector_indexer = AnnouncementVectorIndexer()
    app.state.indexing_poll_interval_seconds = INDEXING_POLL_INTERVAL_SECONDS
    app.state.index_worker_id = f"worker-{uuid.uuid4()}"
    app.state.index_job_store = index_job_store
    app.state.vector_indexer = vector_indexer

    app.state.archive_loop_task = asyncio.create_task(archive_loop(app))
    app.state.ollama_idle_loop_task = asyncio.create_task(ollama_idle_loop(app))
    app.state.announcement_index_loop_task = asyncio.create_task(announcement_index_loop(app))
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

    index_task = app.state.announcement_index_loop_task
    index_task.cancel()
    try:
        await index_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="PDFGPT_StartingBlock_Server", lifespan=lifespan)
app.include_router(announcements_router)
app.include_router(llm_router)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5001, timeout_keep_alive=60, workers=2)
