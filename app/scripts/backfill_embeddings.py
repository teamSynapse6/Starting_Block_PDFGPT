import argparse

from app.api.announcement.vector_indexer import AnnouncementVectorIndexer
from app.core.storage import MinioStorage


def parse_args():
    parser = argparse.ArgumentParser(description="기존 processed 파일을 Qdrant로 백필 임베딩합니다.")
    parser.add_argument("--ids", type=str, default="", help="쉼표 구분 announcement id 목록. 미지정 시 전체 처리")
    parser.add_argument("--limit", type=int, default=0, help="처리 최대 개수(0이면 전체)")
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


def main():
    args = parse_args()

    storage = MinioStorage()
    storage.ensure_bucket()
    indexer = AnnouncementVectorIndexer()

    target_ids = select_target_ids(storage, args.ids, args.limit)

    total = len(target_ids)
    done = 0
    skipped = 0
    failed = 0

    for raw_id in target_ids:
        try:
            announcement_id = int(raw_id)
        except ValueError:
            skipped += 1
            continue

        text = storage.get_processed_text(announcement_id)
        if text is None:
            skipped += 1
            continue

        if args.dry_run:
            print(f"[DRY-RUN] announcement_id={announcement_id}, text_len={len(text)}")
            done += 1
            continue

        try:
            chunk_count = indexer.upsert_announcement(announcement_id, text)
            print(f"[OK] announcement_id={announcement_id}, chunks={chunk_count}")
            done += 1
        except Exception as error:
            print(f"[FAIL] announcement_id={announcement_id}, error={error}")
            failed += 1

    print("--- Summary ---")
    print(f"target={total}, done={done}, skipped={skipped}, failed={failed}")


if __name__ == "__main__":
    main()
