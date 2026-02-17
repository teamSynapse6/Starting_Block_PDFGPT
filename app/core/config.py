import os
from pathlib import Path
from dotenv import load_dotenv


def _env_bool(name: str, default: bool) -> bool:
	value = os.getenv(name)
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "y", "on"}

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BASE_DIR / ".env")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "pdfai-startingblock")
MINIO_SERVICE_NAME = os.getenv("MINIO_SERVICE_NAME", "pdfgpt-minio")
MINIO_STORAGE_ROOT = os.getenv("MINIO_STORAGE_ROOT", "/data2/services/minio")

MINIO_PROCESSED_PREFIX = os.getenv("MINIO_PROCESSED_PREFIX", "processed")
MINIO_RAW_PREFIX = os.getenv("MINIO_RAW_PREFIX", "raw")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_FLASH_ATTENTION = _env_bool("OLLAMA_FLASH_ATTENTION", True)
OLLAMA_KV_CACHE_TYPE = os.getenv("OLLAMA_KV_CACHE_TYPE", "")
OLLAMA_NUM_PARALLEL = int(os.getenv("OLLAMA_NUM_PARALLEL", "1"))
OLLAMA_MAX_QUEUE = int(os.getenv("OLLAMA_MAX_QUEUE", "512"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "192"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.9"))
OLLAMA_TOP_K = int(os.getenv("OLLAMA_TOP_K", "40"))
OLLAMA_REPEAT_PENALTY = float(os.getenv("OLLAMA_REPEAT_PENALTY", "1.05"))
OLLAMA_MODEL_IDLE_SECONDS = int(os.getenv("OLLAMA_MODEL_IDLE_SECONDS", "180"))
OLLAMA_IDLE_SWEEP_INTERVAL_SECONDS = int(os.getenv("OLLAMA_IDLE_SWEEP_INTERVAL_SECONDS", "5"))

LLM_IDLE_ARCHIVE_SECONDS = int(os.getenv("LLM_IDLE_ARCHIVE_SECONDS", "1200"))
LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS = int(os.getenv("LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS", "60"))
LLM_HISTORY_MAX_TURNS = int(os.getenv("LLM_HISTORY_MAX_TURNS", "4"))
LLM_SUMMARY_TRIGGER_MESSAGES = int(os.getenv("LLM_SUMMARY_TRIGGER_MESSAGES", "16"))
LLM_SUMMARY_RECENT_MESSAGES = int(os.getenv("LLM_SUMMARY_RECENT_MESSAGES", "8"))
LLM_SUMMARY_MAX_CHARS = int(os.getenv("LLM_SUMMARY_MAX_CHARS", "3000"))

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB_NAME = os.getenv("MYSQL_DB_NAME", "pdfai_startingblock")
MYSQL_CHARSET = os.getenv("MYSQL_CHARSET", "utf8mb4")

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "announcement_chunks")
QDRANT_SERVICE_NAME = os.getenv("QDRANT_SERVICE_NAME", "pdfgpt-qdrant")
QDRANT_STORAGE_ROOT = os.getenv("QDRANT_STORAGE_ROOT", "/data2/qdrant")

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-large-instruct")
EMBEDDING_MODEL_REPO_ID = os.getenv("EMBEDDING_MODEL_REPO_ID", EMBEDDING_MODEL_NAME)
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
EMBEDDING_MODEL_LOCAL_PATH = os.getenv(
	"EMBEDDING_MODEL_LOCAL_PATH",
	str(BASE_DIR / "app" / "data" / "models" / "intfloat__multilingual-e5-large-instruct"),
)
RAG_CONTEXT_MAX_CHARS = int(os.getenv("RAG_CONTEXT_MAX_CHARS", "4000"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1000"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))

INDEXING_POLL_INTERVAL_SECONDS = int(os.getenv("INDEXING_POLL_INTERVAL_SECONDS", "2"))
INDEXING_BATCH_SIZE = int(os.getenv("INDEXING_BATCH_SIZE", "16"))
