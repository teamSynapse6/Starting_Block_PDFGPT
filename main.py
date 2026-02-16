from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from openai import OpenAI

from app.api.announcement.router import router as announcements_router
from app.api.gpt.router import router as gpt_router
from app.core.config import OPENAI_API_KEY
from app.api.gpt.assistant import create_or_sync_assistant
from app.api.announcement.storage import MinioStorage


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = MinioStorage()
    storage.ensure_bucket()
    app.state.storage = storage

    openai_client = OpenAI(api_key=OPENAI_API_KEY, default_headers={"OpenAI-Beta": "assistants=v2"})
    assistant_id = create_or_sync_assistant(openai_client)

    app.state.openai_client = openai_client
    app.state.assistant_id = assistant_id
    yield


app = FastAPI(title="PDFGPT_StartingBlock_Server", lifespan=lifespan)
app.include_router(announcements_router)
app.include_router(gpt_router)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5001, timeout_keep_alive=60, workers=2)
