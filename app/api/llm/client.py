import asyncio
import subprocess
import time

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from app.api.llm.prompts import instructions
from app.core.config import OLLAMA_BASE_URL

OLLAMA_MODEL = "gemma3n:e4b"


class OllamaClient:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL.rstrip("/")
        self.model_loaded = False
        self.last_request_at = 0.0
        self._lock = asyncio.Lock()

    async def chat(self, messages: list[dict]) -> str:
        await self.ensure_model_loaded()

        url = f"{self.base_url}/api/chat"
        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "keep_alive": "10m",
        }

        timeout = httpx.Timeout(120.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            body = response.json()

        self.last_request_at = time.monotonic()
        self.model_loaded = True

        message = body.get("message", {})
        content = message.get("content", "")
        if not content:
            raise ValueError("OLLAMA_EMPTY_RESPONSE")
        return content

    async def rag_chat(self, question: str, context: str, history: list[dict] | None = None) -> str:
        await self.ensure_model_loaded()

        prompt_system = (
            f"{instructions.strip()}\n\n"
            f"[공고 본문]\n{context}\n"
        )

        lc_messages = [SystemMessage(content=prompt_system)]

        if history:
            for item in history:
                role = item.get("role")
                content = item.get("content", "")
                if role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))

        lc_messages.append(HumanMessage(content=question))

        llm = ChatOllama(
            base_url=self.base_url,
            model=OLLAMA_MODEL,
            temperature=0,
        )

        response = await llm.ainvoke(lc_messages)
        self.last_request_at = time.monotonic()
        self.model_loaded = True

        content = response.content
        if isinstance(content, list):
            content = "".join(str(part) for part in content)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("OLLAMA_EMPTY_RESPONSE")

        return content.strip()

    async def health(self) -> bool:
        url = f"{self.base_url}/api/tags"
        timeout = httpx.Timeout(5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception:
            return False

    async def ensure_server_running(self):
        if await self.health():
            return

        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as error:
            raise RuntimeError("Ollama 실행 파일을 찾을 수 없습니다.") from error

        for _ in range(30):
            if await self.health():
                return
            await asyncio.sleep(0.5)

        raise RuntimeError("Ollama 서버가 시작되지 않았습니다.")

    async def ensure_model_loaded(self):
        async with self._lock:
            await self.ensure_server_running()

            if self.model_loaded:
                self.last_request_at = time.monotonic()
                return

            url = f"{self.base_url}/api/generate"
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": " ",
                "stream": False,
                "keep_alive": "10m",
            }

            timeout = httpx.Timeout(120.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

            self.model_loaded = True
            self.last_request_at = time.monotonic()

    async def unload_model(self):
        async with self._lock:
            if not self.model_loaded:
                return

            url = f"{self.base_url}/api/generate"
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": "",
                "stream": False,
                "keep_alive": 0,
            }

            timeout = httpx.Timeout(30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

            self.model_loaded = False

    async def unload_if_idle(self, idle_seconds: int):
        if not self.model_loaded:
            return

        if self.last_request_at <= 0:
            return

        idle_for = time.monotonic() - self.last_request_at
        if idle_for >= idle_seconds:
            await self.unload_model()
