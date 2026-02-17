import asyncio
import os
import subprocess
import time
from typing import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from ollama import AsyncClient

from app.api.llm.prompts import instructions
from app.core.config import (
    OLLAMA_BASE_URL,
    OLLAMA_FLASH_ATTENTION,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_KV_CACHE_TYPE,
    OLLAMA_MAX_QUEUE,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_PARALLEL,
    OLLAMA_NUM_PREDICT,
    OLLAMA_REPEAT_PENALTY,
    OLLAMA_TOP_K,
    OLLAMA_TOP_P,
)


class OllamaClient:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL.rstrip("/")
        self.client = AsyncClient(host=self.base_url)
        self.model_loaded = False
        self.last_request_at = 0.0
        self._lock = asyncio.Lock()

    async def chat(self, messages: list[dict]) -> str:
        await self.ensure_model_loaded()

        response = await self.client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            stream=False,
            keep_alive=OLLAMA_KEEP_ALIVE,
            options={
                "num_predict": OLLAMA_NUM_PREDICT,
                "num_ctx": OLLAMA_NUM_CTX,
                "top_p": OLLAMA_TOP_P,
                "top_k": OLLAMA_TOP_K,
                "repeat_penalty": OLLAMA_REPEAT_PENALTY,
            },
        )

        self.last_request_at = time.monotonic()
        self.model_loaded = True

        content = (response.message.content if response.message else "") or ""
        if not content:
            raise ValueError("OLLAMA_EMPTY_RESPONSE")
        return content

    def _extract_ollama_timings_ms(self, response_metadata: dict | None) -> dict[str, int]:
        if not response_metadata:
            return {}

        timings: dict[str, int] = {}
        for key in ["total_duration", "load_duration", "prompt_eval_duration", "eval_duration"]:
            value = response_metadata.get(key)
            if isinstance(value, (int, float)):
                timings[f"{key}_ms"] = int(value / 1_000_000)

        for key in ["prompt_eval_count", "eval_count"]:
            value = response_metadata.get(key)
            if isinstance(value, int):
                timings[key] = value

        return timings

    async def rag_chat(
        self,
        question: str,
        context: str,
        history: list[dict] | None = None,
        summary_text: str | None = None,
    ) -> tuple[str, dict[str, int]]:
        await self.ensure_model_loaded()

        prompt_system = (
            f"{instructions.strip()}\n\n"
            f"[공고 본문]\n{context}\n"
        )

        lc_messages = [SystemMessage(content=prompt_system)]
        if summary_text and summary_text.strip():
            lc_messages.append(SystemMessage(content=f"[이전 대화 요약]\n{summary_text.strip()}"))

        if history:
            for item in history:
                role = item.get("role")
                content = (item.get("content") or "").strip()
                if not content:
                    continue
                if role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))

        lc_messages.append(HumanMessage(content=question))

        llm = ChatOllama(
            base_url=self.base_url,
            model=OLLAMA_MODEL,
            temperature=0,
            keep_alive=OLLAMA_KEEP_ALIVE,
            num_predict=OLLAMA_NUM_PREDICT,
            num_ctx=OLLAMA_NUM_CTX,
            top_p=OLLAMA_TOP_P,
            top_k=OLLAMA_TOP_K,
            repeat_penalty=OLLAMA_REPEAT_PENALTY,
        )

        response = await llm.ainvoke(lc_messages)
        self.last_request_at = time.monotonic()
        self.model_loaded = True

        content = response.content
        if isinstance(content, list):
            content = "".join(str(part) for part in content)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("OLLAMA_EMPTY_RESPONSE")

        internal_timings = self._extract_ollama_timings_ms(getattr(response, "response_metadata", None))
        return content.strip(), internal_timings

    async def rag_chat_stream(
        self,
        question: str,
        context: str,
        history: list[dict] | None = None,
        summary_text: str | None = None,
    ) -> AsyncIterator[dict]:
        await self.ensure_model_loaded()

        prompt_system = (
            f"{instructions.strip()}\n\n"
            f"[공고 본문]\n{context}\n"
        )

        lc_messages = [SystemMessage(content=prompt_system)]
        if summary_text and summary_text.strip():
            lc_messages.append(SystemMessage(content=f"[이전 대화 요약]\n{summary_text.strip()}"))

        if history:
            for item in history:
                role = item.get("role")
                content = (item.get("content") or "").strip()
                if not content:
                    continue
                if role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))

        lc_messages.append(HumanMessage(content=question))

        llm = ChatOllama(
            base_url=self.base_url,
            model=OLLAMA_MODEL,
            temperature=0,
            keep_alive=OLLAMA_KEEP_ALIVE,
            num_predict=OLLAMA_NUM_PREDICT,
            num_ctx=OLLAMA_NUM_CTX,
            top_p=OLLAMA_TOP_P,
            top_k=OLLAMA_TOP_K,
            repeat_penalty=OLLAMA_REPEAT_PENALTY,
        )

        full_parts: list[str] = []
        internal_timings: dict[str, int] = {}
        raw_metadata: dict = {}

        async for chunk in llm.astream(lc_messages):
            chunk_content = chunk.content
            if isinstance(chunk_content, list):
                chunk_content = "".join(str(part) for part in chunk_content)
            if isinstance(chunk_content, str) and chunk_content:
                full_parts.append(chunk_content)
                yield {"type": "token", "content": chunk_content}

            metadata = getattr(chunk, "response_metadata", None)
            if isinstance(metadata, dict) and metadata.get("done"):
                internal_timings = self._extract_ollama_timings_ms(metadata)
                raw_metadata = metadata

        self.last_request_at = time.monotonic()
        self.model_loaded = True

        full_text = "".join(full_parts).strip()
        if not full_text:
            raise ValueError("OLLAMA_EMPTY_RESPONSE")

        yield {
            "type": "final",
            "content": full_text,
            "internal_timings": internal_timings,
            "raw_metadata": raw_metadata,
        }

    async def health(self) -> bool:
        try:
            await self.client.list()
            return True
        except Exception:
            return False

    async def ensure_server_running(self):
        if await self.health():
            return

        try:
            env = os.environ.copy()
            env["OLLAMA_FLASH_ATTENTION"] = "1" if OLLAMA_FLASH_ATTENTION else "0"
            env["OLLAMA_NUM_PARALLEL"] = str(OLLAMA_NUM_PARALLEL)
            env["OLLAMA_MAX_QUEUE"] = str(OLLAMA_MAX_QUEUE)
            if OLLAMA_KV_CACHE_TYPE:
                env["OLLAMA_KV_CACHE_TYPE"] = OLLAMA_KV_CACHE_TYPE

            subprocess.Popen(
                ["ollama", "serve"],
                env=env,
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

            await self.client.generate(
                model=OLLAMA_MODEL,
                prompt=" ",
                stream=False,
                keep_alive=OLLAMA_KEEP_ALIVE,
                options={
                    "num_ctx": OLLAMA_NUM_CTX,
                    "num_predict": 1,
                },
            )

            self.model_loaded = True
            self.last_request_at = time.monotonic()

    async def unload_model(self):
        async with self._lock:
            if not self.model_loaded:
                return

            await self.client.generate(
                model=OLLAMA_MODEL,
                prompt="",
                stream=False,
                keep_alive=0,
            )

            self.model_loaded = False

    async def unload_if_idle(self, idle_seconds: int):
        if not self.model_loaded:
            return

        if self.last_request_at <= 0:
            return

        idle_for = time.monotonic() - self.last_request_at
        if idle_for >= idle_seconds:
            await self.unload_model()
