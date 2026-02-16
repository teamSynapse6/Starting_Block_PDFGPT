import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import HTTPError

from app.api.llm.prompts import instructions
from app.core.config import RAG_TOP_K

router = APIRouter(prefix="/llm", tags=["LLM"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/start", summary="대화 UUID 생성")
async def start_conversation(request: Request):
    store = request.app.state.session_store
    ollama_client = request.app.state.ollama_client
    try:
        thread_id = await asyncio.to_thread(store.create_session)
        await ollama_client.ensure_model_loaded()
        return {"thread_id": thread_id}
    except HTTPError as error:
        if 'thread_id' in locals():
            await asyncio.to_thread(store.delete_session, thread_id)
        raise HTTPException(status_code=502, detail="Ollama 모델 로드 중 오류가 발생했습니다.") from error
    except Exception as error:
        if 'thread_id' in locals():
            await asyncio.to_thread(store.delete_session, thread_id)
        raise HTTPException(status_code=500, detail="세션을 생성하는 동안 오류가 발생했습니다.") from error


@router.post("/chat", summary="Ollama 채팅")
async def chat(request: Request):
    data = await request.json()
    thread_id = data.get("thread_id")
    message = data.get("message")
    announcement_id = data.get("announcement_id")

    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id가 없습니다")
    if not message:
        raise HTTPException(status_code=400, detail="message가 없습니다")
    if announcement_id is None:
        raise HTTPException(status_code=400, detail="announcement_id가 없습니다")

    store = request.app.state.session_store
    storage = request.app.state.storage
    ollama_client = request.app.state.ollama_client
    vector_indexer = request.app.state.vector_indexer

    session = await asyncio.to_thread(store.get_session, thread_id)
    if session is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    try:
        announcement_id = int(announcement_id)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail="announcement_id는 정수여야 합니다") from error

    if session.get("announcement_id") is not None and session.get("announcement_id") != announcement_id:
        raise HTTPException(status_code=400, detail="세션의 announcement_id와 요청값이 다릅니다")

    messages = session.get("messages", [])

    if not messages:
        chunks = await asyncio.to_thread(vector_indexer.search_chunks, announcement_id, message, RAG_TOP_K)

        if chunks:
            rag_context = "\n\n".join(chunk.page_content for chunk in chunks)
        else:
            announcement_text = await asyncio.to_thread(storage.get_processed_text, announcement_id)
            if announcement_text is None:
                raise HTTPException(status_code=404, detail="공고 파일을 찾을 수 없습니다")
            rag_context = announcement_text

        if not rag_context.strip():
            raise HTTPException(status_code=404, detail="공고 파일을 찾을 수 없습니다")

        system_context = (
            f"{instructions.strip()}\n\n"
            f"[공고 본문]\n{rag_context}\n"
        )
        messages.append({"role": "system", "content": system_context})

    messages.append({"role": "user", "content": message})

    try:
        await ollama_client.ensure_model_loaded()
        response_text = await ollama_client.chat(messages)
    except HTTPError as error:
        raise HTTPException(status_code=502, detail="Ollama 호출 중 오류가 발생했습니다.") from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail="Ollama 응답이 비어 있습니다.") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="채팅 처리 중 오류가 발생했습니다.") from error

    messages.append({"role": "assistant", "content": response_text})

    saved = await asyncio.to_thread(store.save_session, thread_id, messages, announcement_id)
    if not saved:
        raise HTTPException(status_code=404, detail="세션 저장에 실패했습니다")

    return JSONResponse(content={"response": response_text}, media_type="application/json; charset=utf-8")


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
