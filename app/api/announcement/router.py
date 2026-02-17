import asyncio
import os
import tempfile
from typing import List

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.schemas.announcement import DeleteRequest, UploadRequest
from app.api.announcement.file_pipeline import (
    convert_hwp_path_to_text,
    convert_pdf_bytes_to_text,
    detect_file_format,
)

router = APIRouter(tags=["PDF"])


@router.get("/validation", summary="저장된 파일 리스트 반환")
def validate_files(request: Request):
    storage = request.app.state.storage
    return {"file_ids": storage.list_processed_ids()}


@router.get("/announcement", summary="특정 공고 정보 가져오기")
async def get_announcement(request: Request, id: str):
    if not id:
        raise HTTPException(status_code=400, detail="file_id가 없습니다")

    storage = request.app.state.storage
    content = storage.get_processed_text(id)
    if content is None:
        raise HTTPException(status_code=404, detail="파일이 없습니다")

    return PlainTextResponse(content=content, media_type="text/plain; charset=utf-8")


@router.delete("/announcement/delete", summary="저장된 파일 삭제")
async def delete_files(request: Request, data: DeleteRequest):
    if not data.id:
        return {"error": "No file ids provided"}

    storage = request.app.state.storage
    index_job_store = request.app.state.index_job_store
    deleted_items = []
    failed_items = []
    vector_delete_queued_items = []
    vector_delete_enqueue_failed_items = []

    for file_id in data.id:
        try:
            storage.delete_announcement(file_id)
            deleted_items.append(file_id)
        except Exception:
            failed_items.append(file_id)
            continue

        try:
            index_job_store.enqueue("delete", int(file_id))
        except Exception:
            vector_delete_enqueue_failed_items.append(file_id)
            continue

        vector_delete_queued_items.append(file_id)

    return {
        "status": "finished",
        "deleted_items": deleted_items,
        "failed_items": failed_items,
        "vector_delete_queued_items": vector_delete_queued_items,
        "vector_delete_enqueue_failed_items": vector_delete_enqueue_failed_items,
    }


@router.post("/announcement/upload", summary="파일 업로드")
async def upload_files(request: Request, data: List[UploadRequest]):
    storage = request.app.state.storage
    index_job_store = request.app.state.index_job_store
    stored_items = []
    storage_failed_items = []
    indexing_queued_items = []
    indexing_failed_items = []

    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for item in data:
            file_id = item.id
            file_format = item.format.lower()
            if file_format not in {"hwp", "pdf", "txt"}:
                storage_failed_items.append(file_id)
                continue

            temp_file_path = None
            try:
                response = await client.get(item.url)
                response.raise_for_status()
                file_bytes = response.content

                actual_format = detect_file_format(file_bytes)
                if actual_format != file_format:
                    raise ValueError(
                        f"Incorrect file format for file_id {file_id}: expected {file_format}, got {actual_format}"
                    )

                storage.put_raw_bytes(file_id, file_format, file_bytes)

                if actual_format == "pdf":
                    text = await asyncio.to_thread(convert_pdf_bytes_to_text, file_bytes)
                elif actual_format == "hwp":
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".hwp") as temp_file:
                        temp_file.write(file_bytes)
                        temp_file_path = temp_file.name
                    text = await asyncio.to_thread(convert_hwp_path_to_text, temp_file_path)
                else:
                    text = file_bytes.decode("utf-8", errors="replace")

                storage.put_processed_text(file_id, text)
                stored_items.append(file_id)

                try:
                    index_job_store.enqueue("upsert", int(file_id))
                except Exception:
                    indexing_failed_items.append(file_id)
                    continue

                indexing_queued_items.append(file_id)
            except Exception:
                storage_failed_items.append(file_id)
            finally:
                if temp_file_path and os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    return {
        "status": "finished",
        "success_items": stored_items,
        "failed_items": storage_failed_items,
        "indexing_queued_items": indexing_queued_items,
        "indexing_failed_items": indexing_failed_items,
    }
