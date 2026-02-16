import asyncio
import json

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import OPENAI_STATUS_URL
from app.api.gpt.pdf_source import information_from_pdf_server

router = APIRouter(prefix="/gpt", tags=["GPT"])


@router.get("/start", summary="쓰레드 생성")
async def start_conversation(request: Request):
    client = request.app.state.openai_client
    thread = await asyncio.to_thread(client.beta.threads.create)
    return {"thread_id": thread.id}


@router.post("/chat", summary="채팅 시작")
async def chat(request: Request):
    client = request.app.state.openai_client
    assistant_id = request.app.state.assistant_id

    data = await request.json()
    thread_id = data.get("thread_id")
    message = data.get("message")

    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id가 없습니다")

    await asyncio.to_thread(
        client.beta.threads.messages.create,
        thread_id=thread_id,
        role="user",
        content=message,
    )

    run = await asyncio.to_thread(
        client.beta.threads.runs.create,
        thread_id=thread_id,
        assistant_id=assistant_id,
    )

    while True:
        run_status = await asyncio.to_thread(
            client.beta.threads.runs.retrieve,
            thread_id=thread_id,
            run_id=run.id,
        )

        if run_status.status == "completed":
            break
        if run_status.status == "in_progress":
            await asyncio.sleep(0.1)
            continue
        if run_status.status == "requires_action":
            for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
                if tool_call.function.name == "information_from_pdf_server":
                    arguments = json.loads(tool_call.function.arguments)
                    output = information_from_pdf_server(arguments["announcement_id"])
                    await asyncio.to_thread(
                        client.beta.threads.runs.submit_tool_outputs,
                        thread_id=thread_id,
                        run_id=run.id,
                        tool_outputs=[
                            {
                                "tool_call_id": tool_call.id,
                                "output": json.dumps(output, ensure_ascii=False),
                            }
                        ],
                    )
            await asyncio.sleep(0.1)
            continue

        if run_status.status in {"failed", "expired", "cancelled"}:
            raise HTTPException(status_code=500, detail="어시스턴트 처리 중 오류가 발생했습니다.")

    messages = await asyncio.to_thread(client.beta.threads.messages.list, thread_id=thread_id)
    response = messages.data[0].content[0].text.value
    return JSONResponse(content={"response": response}, media_type="application/json; charset=utf-8")


@router.delete("/end", summary="쓰레드 삭제")
async def delete_thread(request: Request, thread_id: str):
    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id 파라미터가 필요합니다.")

    client = request.app.state.openai_client
    try:
        await asyncio.to_thread(client.beta.threads.delete, thread_id)
        return {"id": thread_id, "object": "thread.deleted", "deleted": True}
    except Exception as error:
        raise HTTPException(status_code=500, detail="스레드를 삭제하는 동안 오류가 발생했습니다.") from error


@router.get("/api_status", summary="API 상태 확인")
async def api_status():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(OPENAI_STATUS_URL)
            response.raise_for_status()
            status_data = response.json()
            indicator = status_data.get("status", {}).get("indicator", "unknown")

            if indicator in {"major", "critical"}:
                return {"status": "caution", "message": "OpenAI API에 문제가 있습니다. 현재 사용을 주의하세요."}
            if indicator in {"minor", "none"}:
                return {"status": "good", "message": "OpenAI API가 정상적으로 동작하고 있습니다."}
            return {"status": "unknown", "message": "상태를 확인할 수 없습니다."}
    except Exception as error:
        raise HTTPException(status_code=500, detail="API 호출 중 오류가 발생했습니다.") from error
