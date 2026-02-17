import asyncio
import time
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from ollama import RequestError, ResponseError

from app.api.announcement.vector_indexer import AnnouncementVectorIndexer
from app.core.config import (
    EMBEDDING_DEVICE,
    LLM_HISTORY_MAX_TURNS,
    LLM_SUMMARY_MAX_CHARS,
    LLM_SUMMARY_RECENT_MESSAGES,
    LLM_SUMMARY_TRIGGER_MESSAGES,
    RAG_TOP_K,
)
from app.schemas.llm import ChatRequest

router = APIRouter(prefix="/llm", tags=["LLM"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clip_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def _build_history_summary(messages: list[dict], max_chars: int) -> str:
    lines: list[str] = []
    for item in messages:
        role = item.get("role")
        content = (item.get("content") or "").replace("\n", " ").strip()
        if not content:
            continue
        tag = "U" if role == "user" else "A"
        lines.append(f"{tag}: {content}")

    return _clip_text("\n".join(lines), max_chars)


def _merge_summary(existing: str, latest: str, max_chars: int) -> str:
    merged = "\n".join(part for part in [existing.strip(), latest.strip()] if part and part.strip())
    return _clip_text(merged, max_chars)


async def _get_vector_indexer(request: Request) -> AnnouncementVectorIndexer:
    existing = getattr(request.app.state, "vector_indexer", None)
    if existing is not None:
        return existing

    async with request.app.state.vector_indexer_lock:
        existing = getattr(request.app.state, "vector_indexer", None)
        if existing is None:
            existing = await asyncio.to_thread(AnnouncementVectorIndexer, EMBEDDING_DEVICE)
            request.app.state.vector_indexer = existing
        return existing


@router.post("/start", summary="대화 UUID 생성")
async def start_conversation(request: Request):
    store = request.app.state.session_store
    try:
        thread_id = await asyncio.to_thread(store.create_session)
        return {"thread_id": thread_id}
    except Exception as error:
        if 'thread_id' in locals():
            await asyncio.to_thread(store.delete_session, thread_id)
        raise HTTPException(status_code=500, detail="세션을 생성하는 동안 오류가 발생했습니다.") from error


@router.post("/chat", summary="Ollama 채팅")
async def chat(request: Request, data: ChatRequest):
    started_at = time.perf_counter()
    checkpoints: list[tuple[str, float]] = [("request_received", started_at)]

    def mark(name: str):
        checkpoints.append((name, time.perf_counter()))

    def build_time_spend() -> dict:
        durations_ms: dict[str, int] = {}
        for index in range(1, len(checkpoints)):
            prev_name, prev_ts = checkpoints[index - 1]
            curr_name, curr_ts = checkpoints[index]
            key = f"{prev_name}->{curr_name}"
            durations_ms[key] = int((curr_ts - prev_ts) * 1000)

        durations_ms["total_ms"] = int((checkpoints[-1][1] - started_at) * 1000)
        return durations_ms

    thread_id = data.thread_id
    message = data.message
    announcement_id = data.announcement_id

    store = request.app.state.session_store
    storage = request.app.state.storage
    ollama_client = request.app.state.ollama_client

    session = await asyncio.to_thread(store.get_session, thread_id)
    mark("session_loaded")
    if session is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    if session.get("announcement_id") is not None and session.get("announcement_id") != announcement_id:
        raise HTTPException(status_code=400, detail="세션의 announcement_id와 요청값이 다릅니다")

    full_history_messages = session.get("messages", [])
    full_history_messages = [
        item for item in full_history_messages
        if item.get("role") in {"user", "assistant"}
    ]

    summary_text = (session.get("summary_text") or "").strip()
    recent_window_size = max(LLM_HISTORY_MAX_TURNS * 2, 2)
    summary_recent_size = max(LLM_SUMMARY_RECENT_MESSAGES, recent_window_size)

    context_history_messages = full_history_messages[-recent_window_size:]
    if len(full_history_messages) > LLM_SUMMARY_TRIGGER_MESSAGES:
        old_messages = full_history_messages[:-summary_recent_size]
        latest_summary = _build_history_summary(old_messages, LLM_SUMMARY_MAX_CHARS)
        if latest_summary:
            summary_text = _merge_summary(summary_text, latest_summary, LLM_SUMMARY_MAX_CHARS)
            await asyncio.to_thread(store.save_summary, thread_id, summary_text)
        context_history_messages = full_history_messages[-summary_recent_size:]

    mark("history_optimized")

    chunks = []
    try:
        vector_indexer = await _get_vector_indexer(request)
        chunks = await asyncio.to_thread(vector_indexer.search_chunks, announcement_id, message, RAG_TOP_K)
    except Exception:
        chunks = []
    mark("rag_searched")

    if chunks:
        rag_context = "\n\n".join(chunk.page_content for chunk in chunks)
        mark("rag_context_prepared")
    else:
        announcement_text = await asyncio.to_thread(storage.get_processed_text, announcement_id)
        if announcement_text is None:
            raise HTTPException(status_code=404, detail="공고 파일을 찾을 수 없습니다")
        rag_context = announcement_text
        mark("fallback_context_loaded")

    if not rag_context.strip():
        raise HTTPException(status_code=404, detail="공고 파일을 찾을 수 없습니다")

    try:
        await ollama_client.ensure_model_loaded()
        mark("ollama_model_ready")
        response_text, ollama_internal_timings = await ollama_client.rag_chat(
            question=message,
            context=rag_context,
            history=context_history_messages,
            summary_text=summary_text,
        )
        mark("ollama_response_generated")
    except (RequestError, ResponseError) as error:
        raise HTTPException(status_code=502, detail="Ollama 호출 중 오류가 발생했습니다.") from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail="Ollama 응답이 비어 있습니다.") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="채팅 처리 중 오류가 발생했습니다.") from error

    updated_messages = full_history_messages + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": response_text},
    ]

    saved = await asyncio.to_thread(store.save_session, thread_id, updated_messages, announcement_id)
    mark("session_saved")
    if not saved:
        raise HTTPException(status_code=404, detail="세션 저장에 실패했습니다")

    mark("response_ready")
    return JSONResponse(
        content={
            "response": response_text,
            "time_spend": {
                **build_time_spend(),
                "ollama_internal": ollama_internal_timings,
            },
        },
        media_type="application/json; charset=utf-8",
    )


@router.delete("/delete", summary="대화 UUID 삭제")
async def delete_session(request: Request, thread_id: str):
    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id 파라미터가 필요합니다.")

    store = request.app.state.session_store
    archive_store = request.app.state.archive_store

    session = await asyncio.to_thread(store.get_session, thread_id)
    if session is None:
        return {"id": thread_id, "deleted": False}

    try:
        await asyncio.to_thread(archive_store.archive_session, session)
        return {"id": thread_id, "deleted": True}
    except Exception as error:
        raise HTTPException(status_code=500, detail="세션 삭제 중 오류가 발생했습니다.") from error


async def archive_idle_sessions(app):
    store = app.state.session_store
    archive_store = app.state.archive_store
    idle_seconds = app.state.llm_idle_archive_seconds

    session_ids = await asyncio.to_thread(store.list_session_ids)
    now = _utc_now()

    for thread_id in session_ids:
        session = await asyncio.to_thread(store.get_session, thread_id)
        if session is None:
            continue

        last_activity = session.get("last_activity")
        try:
            last_dt = datetime.fromisoformat(last_activity)
        except Exception:
            continue

        idle_time = (now - last_dt).total_seconds()
        if idle_time >= idle_seconds:
            await asyncio.to_thread(archive_store.archive_session, session)
