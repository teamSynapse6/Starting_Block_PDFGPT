import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "pdfai-startingblock")

MINIO_PROCESSED_PREFIX = os.getenv("MINIO_PROCESSED_PREFIX", "processed")
MINIO_RAW_PREFIX = os.getenv("MINIO_RAW_PREFIX", "raw")

OPENAI_STATUS_URL = "https://status.openai.com/api/v2/status.json"
