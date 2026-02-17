import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from ollama import RequestError, ResponseError

from app.api.announcement.vector_indexer import AnnouncementVectorIndexer
from app.core.config import (
    EMBEDDING_DEVICE,
    LLM_HISTORY_MAX_TURNS,
    LLM_SUMMARY_MAX_CHARS,
    LLM_SUMMARY_RECENT_MESSAGES,
    LLM_SUMMARY_TRIGGER_MESSAGES,
    RAG_CONTEXT_MAX_CHARS,
    RAG_TOP_K,
)
from app.schemas.llm import ChatRequest

router = APIRouter(prefix="/llm", tags=["LLM"])
logger = logging.getLogger(__name__)


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


def _safe_serialize(obj: any) -> any:
    """객체를 JSON 직렬화 가능한 형태로 변환합니다."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item) for item in obj]
    # datetime, bytes 등 변환 불가능한 객체는 문자열로
    try:
        return str(obj)
    except Exception:
        return None


def _get_ollama_server_log(lines: int = 50) -> list[str]:
    """Ollama 서버 로그에서 모델 로딩 관련 정보를 추출합니다."""
    try:
        result = subprocess.run(
            ["journalctl", "-u", "ollama", "--no-pager", "-n", str(lines)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        
        # FlashAttention, GPU offload, device 정보 등 필터링
        keywords = ["FlashAttention", "offload", "weight", "device=", "kv cache", 
                    "compute graph", "truncat", "runner started", "GPULayers"]
        
        filtered_lines = []
        for line in result.stdout.splitlines():
            if any(keyword in line for keyword in keywords):
                filtered_lines.append(line)
        
        return filtered_lines
    except Exception:
        return []


async def _get_vector_indexer(request: Request) -> AnnouncementVectorIndexer:
    """Pre-warmed vector indexer (initialized in lifespan)"""
    return request.app.state.vector_indexer


async def _search_rag_chunks(request: Request, announcement_id: int, message: str, top_k: int) -> list:
    """비동기 RAG 검색 헬퍼 함수"""
    try:
        vector_indexer = await _get_vector_indexer(request)
        chunks = await asyncio.to_thread(vector_indexer.search_chunks, announcement_id, message, top_k)
        return chunks or []
    except Exception as e:
        logger.warning(f"RAG search failed: {e}")
        return []


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
    thread_id = data.thread_id
    message = data.message
    announcement_id = data.announcement_id

    store = request.app.state.session_store
    storage = request.app.state.storage
    ollama_client = request.app.state.ollama_client

    def _sse(event: str, payload: dict) -> str:
        try:
            return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except (TypeError, ValueError) as e:
            logger.error(f"SSE JSON serialization error: {e}")
            # Fallback: 직렬화 가능한 기본 정보만 반환
            safe_payload = {"detail": str(payload.get("detail", "Serialization error"))}
            return f"event: error\ndata: {json.dumps(safe_payload)}\n\n"

    async def event_stream():
        started_at = time.perf_counter()
        checkpoints: list[tuple[str, float]] = [("request_received", started_at)]

        def mark(name: str):
            checkpoints.append((name, time.perf_counter()))

        def build_time_spend(ollama_internal: dict | None = None) -> dict:
            durations_ms: dict[str, int] = {}
            for index in range(1, len(checkpoints)):
                prev_name, prev_ts = checkpoints[index - 1]
                curr_name, curr_ts = checkpoints[index]
                key = f"{prev_name}->{curr_name}"
                durations_ms[key] = int((curr_ts - prev_ts) * 1000)

            durations_ms["total_ms"] = int((checkpoints[-1][1] - started_at) * 1000)
            if ollama_internal:
                durations_ms["ollama_internal"] = ollama_internal
            return durations_ms

        try:
            yield _sse("status", {"stage": "request_received"})

            # Phase 2: 병렬 처리 - session, ollama, rag 동시 시작
            session_task = asyncio.create_task(
                asyncio.to_thread(store.get_session, thread_id)
            )
            ollama_task = asyncio.create_task(
                ollama_client.ensure_model_loaded()
            )
            rag_task = asyncio.create_task(
                _search_rag_chunks(request, announcement_id, message, RAG_TOP_K)
            )

            # Session 완료 대기 (history 최적화에 필요)
            session = await session_task
            mark("session_loaded")
            if session is None:
                # 실행 중인 task 취소
                ollama_task.cancel()
                rag_task.cancel()
                yield _sse("error", {"detail": "세션을 찾을 수 없습니다"})
                return
            yield _sse("status", {"stage": "session_loaded"})

            if session.get("announcement_id") is not None and session.get("announcement_id") != announcement_id:
                ollama_task.cancel()
                rag_task.cancel()
                yield _sse("error", {"detail": "세션의 announcement_id와 요청값이 다릅니다"})
                return

            # History 최적화 (session 의존)
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
                    # summary 저장은 background로 실행 (비차단)
                    asyncio.create_task(
                        asyncio.to_thread(store.save_summary, thread_id, summary_text)
                    )
                context_history_messages = full_history_messages[-summary_recent_size:]

            mark("history_optimized")
            yield _sse("status", {"stage": "history_optimized"})

            # RAG, Ollama 완료 대기
            chunks, _ = await asyncio.gather(rag_task, ollama_task)
            mark("rag_searched")
            yield _sse("status", {"stage": "rag_searched", "chunk_count": len(chunks)})
            mark("ollama_model_ready")
            yield _sse("status", {"stage": "ollama_model_ready"})

            if chunks:
                rag_context = "\n\n".join(chunk.page_content for chunk in chunks)
                if len(rag_context) > RAG_CONTEXT_MAX_CHARS:
                    rag_context = rag_context[:RAG_CONTEXT_MAX_CHARS]
                mark("rag_context_prepared")
                yield _sse("status", {"stage": "rag_context_prepared"})
            else:
                announcement_text = await asyncio.to_thread(storage.get_processed_text, announcement_id)
                if announcement_text is None:
                    yield _sse("error", {"detail": "공고 파일을 찾을 수 없습니다"})
                    return
                rag_context = announcement_text
                if len(rag_context) > RAG_CONTEXT_MAX_CHARS:
                    rag_context = rag_context[:RAG_CONTEXT_MAX_CHARS]
                mark("fallback_context_loaded")
                yield _sse("status", {"stage": "fallback_context_loaded"})

            if not rag_context.strip():
                yield _sse("error", {"detail": "공고 파일을 찾을 수 없습니다"})
                return

            # Ollama는 이미 병렬로 준비됨 (ollama_task 완료)
            full_response = ""
            ollama_internal_timings: dict = {}
            ollama_log: dict = {}
            async for item in ollama_client.rag_chat_stream(
                question=message,
                context=rag_context,
                history=context_history_messages,
                summary_text=summary_text,
            ):
                item_type = item.get("type")
                if item_type == "token":
                    token = item.get("content", "")
                    full_response += token
                    yield _sse("token", {"text": token})
                elif item_type == "final":
                    full_response = item.get("content", "")
                    ollama_internal_timings = item.get("internal_timings", {})
                    ollama_log = item.get("raw_metadata", {})

            mark("ollama_response_generated")
            yield _sse("status", {"stage": "ollama_response_generated"})

            # Ollama 서버 로그 수집 (안전하게)
            try:
                server_log = await asyncio.to_thread(_get_ollama_server_log, 50)
                if server_log is None:
                    server_log = []
            except Exception as e:
                logger.warning(f"Failed to collect Ollama server log: {e}")
                server_log = []
            mark("server_log_collected")

            updated_messages = full_history_messages + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": full_response},
            ]

            saved = await asyncio.to_thread(store.save_session, thread_id, updated_messages, announcement_id)
            mark("session_saved")
            if not saved:
                yield _sse("error", {"detail": "세션 저장에 실패했습니다"})
                return
            yield _sse("status", {"stage": "session_saved"})

            mark("response_ready")
            
            # 로그 데이터를 안전하게 직렬화
            safe_log = {
                "metadata": _safe_serialize(ollama_log) if ollama_log else {},
                "server_log": server_log if isinstance(server_log, list) else [],
            }
            
            yield _sse(
                "done",
                {
                    "response": full_response,
                    "time_spend": build_time_spend(ollama_internal_timings),
                    "log": safe_log,
                },
            )
        except (RequestError, ResponseError) as e:
            logger.error(f"Ollama request/response error: {e}")
            yield _sse("error", {"detail": "Ollama 호출 중 오류가 발생했습니다."})
        except ValueError as e:
            logger.error(f"Ollama empty response: {e}")
            yield _sse("error", {"detail": "Ollama 응답이 비어 있습니다."})
        except Exception as e:
            logger.exception(f"Chat processing error: {e}")
            yield _sse("error", {"detail": "채팅 처리 중 오류가 발생했습니다."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
