import asyncio
import logging
import os
import signal
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

logger = logging.getLogger(__name__)

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
    EMBEDDING_DEVICE,
    INDEXING_POLL_INTERVAL_SECONDS,
    LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS,
    LLM_IDLE_ARCHIVE_SECONDS,
    MINIO_SERVICE_NAME,
    MINIO_STORAGE_ROOT,
    OLLAMA_MODEL_IDLE_SECONDS,
    OLLAMA_IDLE_SWEEP_INTERVAL_SECONDS,
    QDRANT_SERVICE_NAME,
    QDRANT_STORAGE_ROOT,
)


def _run_command(command: list[str], check: bool = True):
    result = subprocess.run(command, capture_output=True, text=True)
    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        message = stderr or stdout or "unknown error"
        raise RuntimeError(f"command failed: {' '.join(command)}\n{message}")
    return result


def _container_exists(container_name: str) -> bool:
    result = _run_command(["docker", "inspect", container_name], check=False)
    return result.returncode == 0


def _ensure_container_running(container_name: str, create_cmd: list[str]):
    if _container_exists(container_name):
        _run_command(["docker", "start", container_name], check=False)
        return

    _run_command(create_cmd, check=True)


def _start_external_services():
    os.makedirs(MINIO_STORAGE_ROOT, exist_ok=True)
    qdrant_host_path = os.path.join(QDRANT_STORAGE_ROOT, QDRANT_SERVICE_NAME)
    os.makedirs(qdrant_host_path, exist_ok=True)

    minio_create_cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        MINIO_SERVICE_NAME,
        "-p",
        "9000:9000",
        "-p",
        "9001:9001",
        "-e",
        "MINIO_ROOT_USER=minioadmin",
        "-e",
        "MINIO_ROOT_PASSWORD=minioadmin",
        "-v",
        f"{MINIO_STORAGE_ROOT}:/data",
        "quay.io/minio/minio",
        "server",
        "/data",
        "--console-address",
        ":9001",
    ]

    qdrant_create_cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        QDRANT_SERVICE_NAME,
        "-p",
        "6333:6333",
        "-p",
        "6334:6334",
        "-v",
        f"{qdrant_host_path}:/qdrant/storage",
        "qdrant/qdrant",
    ]

    _ensure_container_running(MINIO_SERVICE_NAME, minio_create_cmd)
    _ensure_container_running(QDRANT_SERVICE_NAME, qdrant_create_cmd)


def _stop_external_services():
    _run_command(["docker", "stop", MINIO_SERVICE_NAME], check=False)
    _run_command(["docker", "stop", QDRANT_SERVICE_NAME], check=False)


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


async def get_vector_indexer(app: FastAPI) -> AnnouncementVectorIndexer:
    """Pre-warmed vector indexer (initialized in lifespan)"""
    return app.state.vector_indexer

async def announcement_index_loop(app: FastAPI):
    interval = app.state.indexing_poll_interval_seconds
    worker_id = app.state.index_worker_id
    job_store = app.state.index_job_store
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
            vector_indexer = await get_vector_indexer(app)
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
    try:
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
        app.state.indexing_poll_interval_seconds = INDEXING_POLL_INTERVAL_SECONDS
        app.state.index_worker_id = f"worker-{uuid.uuid4()}"
        app.state.index_job_store = index_job_store

        # Phase 1: 임베딩 모델 pre-warming
        logger.info("Pre-warming embedding model...")
        vector_indexer = await asyncio.to_thread(AnnouncementVectorIndexer, EMBEDDING_DEVICE)
        app.state.vector_indexer = vector_indexer
        
        # Warm-up: 더미 검색으로 모델 메모리 로딩
        try:
            await asyncio.to_thread(vector_indexer.search_chunks, 1, "warmup", 1)
            logger.info("Embedding model warmed up successfully")
        except Exception as e:
            logger.warning(f"Embedding warm-up failed (non-critical): {e}")

        app.state.archive_loop_task = asyncio.create_task(archive_loop(app))
        app.state.ollama_idle_loop_task = asyncio.create_task(ollama_idle_loop(app))
        app.state.announcement_index_loop_task = asyncio.create_task(announcement_index_loop(app))
        yield
    finally:
        archive_task = getattr(app.state, "archive_loop_task", None)
        if archive_task is not None:
            archive_task.cancel()
            try:
                await archive_task
            except asyncio.CancelledError:
                pass

        ollama_idle_task = getattr(app.state, "ollama_idle_loop_task", None)
        if ollama_idle_task is not None:
            ollama_idle_task.cancel()
            try:
                await ollama_idle_task
            except asyncio.CancelledError:
                pass

        index_task = getattr(app.state, "announcement_index_loop_task", None)
        if index_task is not None:
            index_task.cancel()
            try:
                await index_task
            except asyncio.CancelledError:
                pass

        pass


app = FastAPI(title="PDFGPT_StartingBlock_Server", lifespan=lifespan)
app.include_router(announcements_router)
app.include_router(llm_router)


if __name__ == "__main__":
    def _graceful_shutdown(*_):
        _stop_external_services()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    try:
        _start_external_services()
        uvicorn.run("main:app", host="0.0.0.0", port=5001, timeout_keep_alive=60, workers=1)
    finally:
        _stop_external_services()
