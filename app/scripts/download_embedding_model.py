from pathlib import Path

from huggingface_hub import snapshot_download

from app.core.config import EMBEDDING_MODEL_LOCAL_PATH, EMBEDDING_MODEL_REPO_ID


def main():
    target_path = Path(EMBEDDING_MODEL_LOCAL_PATH)
    target_path.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] repo_id={EMBEDDING_MODEL_REPO_ID}")
    print(f"[INFO] target={target_path}")

    snapshot_download(
        repo_id=EMBEDDING_MODEL_REPO_ID,
        local_dir=str(target_path),
    )

    print("[DONE] embedding model downloaded")


if __name__ == "__main__":
    main()
