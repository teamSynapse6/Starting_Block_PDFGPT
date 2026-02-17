import uuid
from datetime import datetime, timezone

from app.core.db_models import LLMMessage, LLMThread, get_db_session


class MySQLSessionStore:
    def __init__(self):
        pass

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_session(self) -> str:
        thread_id = str(uuid.uuid4())

        with get_db_session() as db:
            thread = LLMThread(
                thread_id=thread_id,
                announcement_id=None,
                status="active",
                created_at=datetime.now(timezone.utc),
                last_activity=datetime.now(timezone.utc),
            )
            db.add(thread)
            db.commit()

        return thread_id

    def get_session(self, thread_id: str) -> dict | None:
        with get_db_session() as db:
            thread = db.query(LLMThread).filter(LLMThread.thread_id == thread_id, LLMThread.status == "active").first()
            if thread is None:
                return None

            rows = (
                db.query(LLMMessage)
                .filter(LLMMessage.thread_id == thread_id)
                .order_by(LLMMessage.seq.asc())
                .all()
            )
            messages = [{"role": row.role, "content": row.content} for row in rows]

        return {
            "thread_id": thread.thread_id,
            "created_at": thread.created_at.isoformat() if thread.created_at else self._now(),
            "last_activity": thread.last_activity.isoformat() if thread.last_activity else self._now(),
            "announcement_id": thread.announcement_id,
            "summary_text": thread.summary_text or "",
            "messages": messages,
        }

    def save_session(self, thread_id: str, messages: list[dict], announcement_id: int | None):
        with get_db_session() as db:
            thread = db.query(LLMThread).filter(LLMThread.thread_id == thread_id, LLMThread.status == "active").first()
            if thread is None:
                return False

            thread.last_activity = datetime.now(timezone.utc)
            if thread.announcement_id is None:
                thread.announcement_id = announcement_id

            db.query(LLMMessage).filter(LLMMessage.thread_id == thread_id).delete(synchronize_session=False)

            seq = 1
            for message in messages:
                row = LLMMessage(
                    thread_id=thread_id,
                    seq=seq,
                    role=message.get("role", "user"),
                    content=message.get("content", ""),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(row)
                seq += 1

            db.commit()
            return True

    def delete_session(self, thread_id: str):
        with get_db_session() as db:
            db.query(LLMThread).filter(LLMThread.thread_id == thread_id).delete(synchronize_session=False)
            db.commit()

    def save_summary(self, thread_id: str, summary_text: str):
        with get_db_session() as db:
            thread = db.query(LLMThread).filter(LLMThread.thread_id == thread_id).first()
            if thread is None:
                return False

            thread.summary_text = summary_text
            thread.summary_updated_at = datetime.now(timezone.utc)
            db.commit()
            return True

    def list_session_ids(self) -> list[str]:
        with get_db_session() as db:
            rows = db.query(LLMThread.thread_id).filter(LLMThread.status == "active").all()
            return [row[0] for row in rows]
