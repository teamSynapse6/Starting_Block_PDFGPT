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

LLM_IDLE_ARCHIVE_SECONDS = int(os.getenv("LLM_IDLE_ARCHIVE_SECONDS", "1200"))
LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS = int(os.getenv("LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS", "60"))

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB_NAME = os.getenv("MYSQL_DB_NAME", "pdfai_startingblock")
MYSQL_CHARSET = os.getenv("MYSQL_CHARSET", "utf8mb4")

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "announcement_chunks")

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-large-instruct")
EMBEDDING_MODEL_REPO_ID = os.getenv("EMBEDDING_MODEL_REPO_ID", EMBEDDING_MODEL_NAME)
EMBEDDING_MODEL_LOCAL_PATH = os.getenv(
	"EMBEDDING_MODEL_LOCAL_PATH",
	str(BASE_DIR / "app" / "data" / "models" / "intfloat__multilingual-e5-large-instruct"),
)
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1000"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))

INDEXING_POLL_INTERVAL_SECONDS = int(os.getenv("INDEXING_POLL_INTERVAL_SECONDS", "2"))
INDEXING_BATCH_SIZE = int(os.getenv("INDEXING_BATCH_SIZE", "16"))
