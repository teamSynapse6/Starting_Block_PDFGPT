import argparse
from pathlib import Path

from app.api.announcement.vector_indexer import AnnouncementVectorIndexer
from app.core.storage import MinioStorage


def parse_args():
    parser = argparse.ArgumentParser(description="기존 processed 파일을 Qdrant로 백필 임베딩합니다.")
    parser.add_argument("--ids", type=str, default="", help="쉼표 구분 announcement id 목록. 미지정 시 전체 처리")
    parser.add_argument("--limit", type=int, default=0, help="처리 최대 개수(0이면 전체)")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default="app/data/backfill_embeddings.done",
        help="완료 announcement_id를 저장하는 체크포인트 파일 경로",
    )
    parser.add_argument("--skip-existing", dest="skip_existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    parser.add_argument("--dry-run", action="store_true", help="실제 upsert 없이 대상만 출력")
    return parser.parse_args()


def select_target_ids(storage: MinioStorage, id_arg: str, limit: int) -> list[str]:
    if id_arg.strip():
        ids = [item.strip() for item in id_arg.split(",") if item.strip()]
    else:
        ids = storage.list_processed_ids()

    if limit > 0:
        return ids[:limit]
    return ids


def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()

    done_ids: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        token = line.strip()
        if token:
            done_ids.add(token)
    return done_ids


def append_checkpoint(path: Path, announcement_id: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{announcement_id}\n")


def process_one(
    storage: MinioStorage,
    indexer: AnnouncementVectorIndexer,
    raw_id: str,
    dry_run: bool,
    skip_existing: bool,
) -> tuple[str, int | str, int, str]:
    try:
        announcement_id = int(raw_id)
    except ValueError:
        return ("skipped", raw_id, 0, "non-numeric-id")

    text = storage.get_processed_text(announcement_id)
    if text is None:
        return ("skipped", announcement_id, 0, "missing-processed-text")

    if skip_existing and indexer.has_announcement_vectors(announcement_id):
        return ("skipped", announcement_id, 0, "already-indexed")

    if dry_run:
        return ("dry-run", announcement_id, len(text), "")

    try:
        chunk_count = indexer.upsert_announcement(announcement_id, text)
        return ("ok", announcement_id, chunk_count, "")
    except Exception as error:
        return ("fail", announcement_id, 0, str(error))


def main():
    args = parse_args()

    storage = MinioStorage()
    storage.ensure_bucket()
    indexer = AnnouncementVectorIndexer()

    checkpoint_path = Path(args.checkpoint)
    done_ids = load_checkpoint(checkpoint_path)

    target_ids = select_target_ids(storage, args.ids, args.limit)
    pending_ids = [item for item in target_ids if item not in done_ids]

    total = len(target_ids)
    pending_total = len(pending_ids)
    done = 0
    skipped = 0
    failed = 0

    print(f"total={total}, already_done={len(done_ids)}, pending={pending_total}")

    if pending_total == 0:
        print("--- Summary ---")
        print(f"target={total}, done={done}, skipped={skipped}, failed={failed}")
        return

    for raw_id in pending_ids:
        status, announcement_id, metric, detail = process_one(
            storage,
            indexer,
            raw_id,
            args.dry_run,
            args.skip_existing,
        )

        if status == "ok":
            done += 1
            append_checkpoint(checkpoint_path, int(announcement_id))
            print(f"[OK] announcement_id={announcement_id}, chunks={metric}")
        elif status == "dry-run":
            done += 1
            print(f"[DRY-RUN] announcement_id={announcement_id}, text_len={metric}")
        elif status == "skipped":
            skipped += 1
            if detail == "already-indexed" and isinstance(announcement_id, int):
                append_checkpoint(checkpoint_path, announcement_id)
            print(f"[SKIP] announcement_id={announcement_id}, reason={detail}")
        else:
            failed += 1
            print(f"[FAIL] announcement_id={announcement_id}, error={detail}")

    print("--- Summary ---")
    print(f"target={total}, done={done}, skipped={skipped}, failed={failed}")


if __name__ == "__main__":
    main()
