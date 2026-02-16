import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BASE_DIR / ".env")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "pdfai-startingblock")

MINIO_PROCESSED_PREFIX = os.getenv("MINIO_PROCESSED_PREFIX", "processed")
MINIO_RAW_PREFIX = os.getenv("MINIO_RAW_PREFIX", "raw")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL_IDLE_SECONDS = int(os.getenv("OLLAMA_MODEL_IDLE_SECONDS", "180"))
OLLAMA_IDLE_SWEEP_INTERVAL_SECONDS = int(os.getenv("OLLAMA_IDLE_SWEEP_INTERVAL_SECONDS", "5"))

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

LLM_SESSION_TTL_SECONDS = int(os.getenv("LLM_SESSION_TTL_SECONDS", "7200"))
LLM_IDLE_ARCHIVE_SECONDS = int(os.getenv("LLM_IDLE_ARCHIVE_SECONDS", "1200"))
LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS = int(os.getenv("LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS", "60"))

SQLITE_ARCHIVE_PATH = os.getenv("SQLITE_ARCHIVE_PATH", str(BASE_DIR / "llm_archive.db"))
