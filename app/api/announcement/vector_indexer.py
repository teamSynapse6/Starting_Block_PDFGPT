import hashlib
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client import models

from app.core.config import (
    EMBEDDING_MODEL_LOCAL_PATH,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_REPO_ID,
    INDEXING_BATCH_SIZE,
    QDRANT_API_KEY,
    QDRANT_COLLECTION_NAME,
    QDRANT_URL,
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
)


class AnnouncementVectorIndexer:
    def __init__(self):
        self.collection_name = QDRANT_COLLECTION_NAME
        self.model_local_path = Path(EMBEDDING_MODEL_LOCAL_PATH)
        self._validate_local_model_path()
        self.embeddings = HuggingFaceEmbeddings(
            model_name=str(self.model_local_path),
            model_kwargs={"local_files_only": True},
            encode_kwargs={"normalize_embeddings": True},
        )
        self.client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY or None,
            timeout=60,
            check_compatibility=False,
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=RAG_CHUNK_SIZE,
            chunk_overlap=RAG_CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " "],
        )
        self.batch_size = INDEXING_BATCH_SIZE
        self.vector_store: QdrantVectorStore | None = None

    def _get_vector_store(self) -> QdrantVectorStore:
        if self.vector_store is None:
            self.vector_store = QdrantVectorStore(
                client=self.client,
                collection_name=self.collection_name,
                embedding=self.embeddings,
            )
        return self.vector_store

    def _validate_local_model_path(self):
        if not self.model_local_path.exists() or not self.model_local_path.is_dir():
            raise RuntimeError(
                "로컬 임베딩 모델 경로를 찾을 수 없습니다. "
                "`python -m app.scripts.download_embedding_model` 실행 후 다시 시작하세요. "
                f"(path={self.model_local_path})"
            )

        required_files = {"config.json", "modules.json"}
        missing = [name for name in required_files if not (self.model_local_path / name).exists()]
        if missing:
            raise RuntimeError(
                "로컬 임베딩 모델 파일이 누락되었습니다. "
                "`python -m app.scripts.download_embedding_model` 실행 후 다시 시작하세요. "
                f"(missing={', '.join(missing)})"
            )

    def _collection_exists(self) -> bool:
        existing_collections = self.client.get_collections().collections
        existing_names = {item.name for item in existing_collections}
        return self.collection_name in existing_names

    def _ensure_collection(self):
        if self._collection_exists():
            return

        sample_vector = self.embeddings.embed_query("벡터 차원 초기화")
        vector_size = len(sample_vector)
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )

    def _build_documents(self, announcement_id: int, text: str) -> tuple[list[Document], list[str]]:
        now = datetime.now(timezone.utc).isoformat()
        chunks = [chunk.strip() for chunk in self.splitter.split_text(text) if chunk and chunk.strip()]

        documents: list[Document] = []
        ids: list[str] = []
        for chunk_id, chunk in enumerate(chunks):
            content_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            point_id = f"{announcement_id}:{chunk_id}"
            metadata = {
                "announcement_id": announcement_id,
                "chunk_id": chunk_id,
                "chunk_uid": point_id,
                "source": "minio_processed",
                "content_hash": content_hash,
                "embedding_model": EMBEDDING_MODEL_REPO_ID,
                "created_at": now,
            }
            documents.append(Document(page_content=chunk, metadata=metadata))
            ids.append(point_id)

        return documents, ids

    def delete_announcement(self, announcement_id: int) -> None:
        if not self._collection_exists():
            return

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.announcement_id",
                            match=models.MatchValue(value=announcement_id),
                        )
                    ]
                )
            ),
        )

    def upsert_announcement(self, announcement_id: int, text: str) -> int:
        documents, ids = self._build_documents(announcement_id, text)

        self._ensure_collection()
        self.delete_announcement(announcement_id)
        if not documents:
            return 0

        vector_store = self._get_vector_store()
        vector_store.add_documents(documents=documents, ids=ids, batch_size=self.batch_size)
        return len(documents)

    def search_chunks(self, announcement_id: int, query: str, top_k: int) -> list[Document]:
        if not self._collection_exists():
            return []

        vector_store = self._get_vector_store()
        return vector_store.similarity_search(
            query=query,
            k=top_k,
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.announcement_id",
                        match=models.MatchValue(value=announcement_id),
                    )
                ]
            ),
        )
