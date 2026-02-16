import json
import uuid
from datetime import datetime, timezone
from redis import Redis
from app.core.config import REDIS_URL, LLM_SESSION_TTL_SECONDS


class RedisSessionStore:
    def __init__(self):
        self.client = Redis.from_url(REDIS_URL, decode_responses=True)

    def _session_key(self, thread_id: str) -> str:
        return f"llm:session:{thread_id}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_session(self) -> str:
        thread_id = str(uuid.uuid4())
        key = self._session_key(thread_id)
        now = self._now()
        payload = {
            "thread_id": thread_id,
            "created_at": now,
            "last_activity": now,
            "announcement_id": "",
            "messages": "[]",
        }
        self.client.hset(key, mapping=payload)
        self.client.expire(key, LLM_SESSION_TTL_SECONDS)
        return thread_id

    def get_session(self, thread_id: str) -> dict | None:
        key = self._session_key(thread_id)
        if not self.client.exists(key):
            return None

        data = self.client.hgetall(key)
        messages = json.loads(data.get("messages", "[]"))
        announcement_raw = data.get("announcement_id")
        announcement_id = int(announcement_raw) if announcement_raw else None
        return {
            "thread_id": data.get("thread_id", thread_id),
            "created_at": data.get("created_at", self._now()),
            "last_activity": data.get("last_activity", self._now()),
            "announcement_id": announcement_id,
            "messages": messages,
        }

    def save_session(self, thread_id: str, messages: list[dict], announcement_id: int | None):
        key = self._session_key(thread_id)
        if not self.client.exists(key):
            return False

        mapping = {
            "last_activity": self._now(),
            "messages": json.dumps(messages, ensure_ascii=False),
            "announcement_id": "" if announcement_id is None else str(announcement_id),
        }
        self.client.hset(key, mapping=mapping)
        self.client.expire(key, LLM_SESSION_TTL_SECONDS)
        return True

    def delete_session(self, thread_id: str):
        key = self._session_key(thread_id)
        self.client.delete(key)

    def list_session_ids(self) -> list[str]:
        ids = []
        for key in self.client.scan_iter(match="llm:session:*"):
            ids.append(key.replace("llm:session:", ""))
        return ids
