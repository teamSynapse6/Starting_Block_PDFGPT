from datetime import datetime, timezone

from app.core.db_models import AnnouncementIndexJob, get_db_session


class AnnouncementIndexJobStore:
    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def enqueue(self, action: str, announcement_id: int) -> None:
        normalized_action = action.strip().lower()
        if normalized_action not in {"upsert", "delete"}:
            raise ValueError("지원하지 않는 인덱싱 작업입니다.")

        with get_db_session() as db:
            existing = (
                db.query(AnnouncementIndexJob)
                .filter(
                    AnnouncementIndexJob.action == normalized_action,
                    AnnouncementIndexJob.announcement_id == announcement_id,
                    AnnouncementIndexJob.status.in_(["queued", "processing"]),
                )
                .order_by(AnnouncementIndexJob.id.desc())
                .first()
            )
            if existing is not None:
                return

            db.add(
                AnnouncementIndexJob(
                    action=normalized_action,
                    announcement_id=announcement_id,
                    status="queued",
                    attempts=0,
                    created_at=self._now(),
                )
            )
            db.commit()

    def claim_next(self, worker_id: str) -> dict | None:
        with get_db_session() as db:
            row = (
                db.query(AnnouncementIndexJob)
                .filter(AnnouncementIndexJob.status == "queued")
                .order_by(AnnouncementIndexJob.id.asc())
                .with_for_update(skip_locked=True)
                .first()
            )
            if row is None:
                return None

            row.status = "processing"
            row.worker_id = worker_id
            row.started_at = self._now()
            row.attempts = (row.attempts or 0) + 1
            db.commit()

            return {
                "id": row.id,
                "action": row.action,
                "announcement_id": row.announcement_id,
                "attempts": row.attempts,
            }

    def mark_done(self, job_id: int) -> None:
        with get_db_session() as db:
            row = db.query(AnnouncementIndexJob).filter(AnnouncementIndexJob.id == job_id).first()
            if row is None:
                return

            row.status = "done"
            row.last_error = None
            row.finished_at = self._now()
            db.commit()

    def mark_failed(self, job_id: int, error_message: str) -> None:
        with get_db_session() as db:
            row = db.query(AnnouncementIndexJob).filter(AnnouncementIndexJob.id == job_id).first()
            if row is None:
                return

            row.status = "failed"
            row.last_error = error_message[:2000]
            row.finished_at = self._now()
            db.commit()
