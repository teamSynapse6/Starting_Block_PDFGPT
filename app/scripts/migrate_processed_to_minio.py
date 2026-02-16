import os
from pathlib import Path

from app.core.storage import MinioStorage


def migrate(source_dir: Path):
    storage = MinioStorage()
    storage.ensure_bucket()

    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"source directory not found: {source_dir}")

    success_count = 0
    failed_files = []

    for file_path in source_dir.glob("*.txt"):
        file_id = file_path.stem
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            storage.put_processed_text(file_id, content)
            success_count += 1
        except Exception:
            failed_files.append(file_path.name)

    print(f"migrated: {success_count}")
    print(f"failed: {len(failed_files)}")
    if failed_files:
        print("failed_files:")
        for name in failed_files:
            print(f"- {name}")


if __name__ == "__main__":
    source = os.getenv("SOURCE_DIR", "processed_file")
    migrate(Path(source))
