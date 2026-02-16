import io
from minio import Minio
from minio.error import S3Error
from app.core.config import (
    MINIO_ENDPOINT,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    MINIO_BUCKET,
    MINIO_PROCESSED_PREFIX,
    MINIO_RAW_PREFIX,
)


class MinioStorage:
    def __init__(self):
        self.client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
        self.bucket = MINIO_BUCKET

    def ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def _processed_key(self, file_id: int | str) -> str:
        return f"{MINIO_PROCESSED_PREFIX}/{file_id}.txt"

    def _raw_key(self, file_id: int | str, file_format: str) -> str:
        return f"{MINIO_RAW_PREFIX}/{file_id}.{file_format}"

    def list_processed_ids(self) -> list[str]:
        objects = self.client.list_objects(self.bucket, prefix=f"{MINIO_PROCESSED_PREFIX}/", recursive=True)
        file_ids = []
        for obj in objects:
            name = obj.object_name.split("/")[-1]
            if name.endswith(".txt"):
                file_ids.append(name[:-4])
        numeric_ids = [file_id for file_id in file_ids if file_id.isdigit()]
        non_numeric_ids = [file_id for file_id in file_ids if not file_id.isdigit()]
        numeric_ids = sorted(numeric_ids, key=lambda value: int(value))
        non_numeric_ids = sorted(non_numeric_ids)
        return numeric_ids + non_numeric_ids

    def get_processed_text(self, file_id: int | str) -> str | None:
        key = self._processed_key(file_id)
        try:
            response = self.client.get_object(self.bucket, key)
            data = response.read().decode("utf-8")
            response.close()
            response.release_conn()
            return data
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return None
            raise

    def put_raw_bytes(self, file_id: int | str, file_format: str, content: bytes):
        key = self._raw_key(file_id, file_format)
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(content),
            length=len(content),
            content_type="application/octet-stream",
        )

    def put_processed_text(self, file_id: int | str, text: str):
        encoded = text.encode("utf-8")
        key = self._processed_key(file_id)
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(encoded),
            length=len(encoded),
            content_type="text/plain; charset=utf-8",
        )

    def delete_processed(self, file_id: int | str):
        key = self._processed_key(file_id)
        try:
            self.client.remove_object(self.bucket, key)
        except S3Error as error:
            if error.code not in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise
