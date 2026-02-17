# Starting_Block_PDFGPT

## Convention
- [CHORE]: 프로덕션 코드가 바뀌지 않고 개발 로직과 상관 없는 가벼운 일들
- [DEPS]: Dependency와 관련 있는 내용
- [DOCS]: 도큐먼트/문서화 업데이트
- [FEAT]: 새로운 기능/특징
- [FIX]: 버그를 고침
- [HOTFIX]: 시급한 버그를 고침
- [REFACTOR]: production 코드를 리팩토링
- [STYLE]: Code의 스타일, 포맷 등이 바뀐 경우
- [TEST]: 테스트 코드 추가 및 업데이트

## 실행 구조
- 루트 엔트리포인트: `main.py`
- 앱 생성/라우팅/초기화: `main.py`
- 공고 기능: `app/api/announcement/` (`router.py`, `file_pipeline.py`)
- LLM 기능: `app/api/llm/` (`router.py`, `client.py`, `session_store.py`, `archive_store.py`, `prompts.py`)
- 공통 인프라: `app/core/` (`storage.py`, `db_models.py`, `config.py`)

## 환경 변수
`.env`에 아래 값을 설정하세요.

```env
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET=pdfai-startingblock
MINIO_PROCESSED_PREFIX=processed
MINIO_RAW_PREFIX=raw

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL_IDLE_SECONDS=180
OLLAMA_IDLE_SWEEP_INTERVAL_SECONDS=5

LLM_IDLE_ARCHIVE_SECONDS=1200
LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS=60

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DB_NAME=pdfai_startingblock
MYSQL_CHARSET=utf8mb4

QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=announcement_chunks
QDRANT_SERVICE_NAME=starting_block_pdfgpt
QDRANT_STORAGE_ROOT=/data2/qdrant

EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-large-instruct
EMBEDDING_MODEL_REPO_ID=intfloat/multilingual-e5-large-instruct
EMBEDDING_MODEL_LOCAL_PATH=app/data/models/intfloat__multilingual-e5-large-instruct
RAG_TOP_K=5
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=200

INDEXING_POLL_INTERVAL_SECONDS=2
INDEXING_BATCH_SIZE=16
```

## LLM API
- `POST /llm/start` : 대화 UUID 생성
- `POST /llm/chat` : Ollama 채팅 (`thread_id`, `message`, `announcement_id` 필요)
- `DELETE /llm/delete` : 대화 UUID 종료(스레드 상태 archived 전환)

## 대화 저장소
- 서버 시작 시 `app/core/db_models.py`에서 MySQL DB(`pdfai_startingblock`)와 테이블을 자동 생성합니다(없으면 생성).
- `llm_threads` + `llm_messages` 정규화 스키마로 thread_id별 대화 내역을 저장합니다.
- 상태 컬럼(`active`/`archived`)으로 활성 대화와 종료 대화를 구분 관리합니다.

## Ollama 동작 정책
- 서버 시작 시 모델을 미리 실행하지 않습니다.
- 서버 시작 시 Ollama 서버가 실행 중인지 확인하고, 미실행이면 `ollama serve`를 시작합니다.
- `POST /llm/start`에서 UUID 발급 직후 모델을 로드합니다.
- Ollama 요청이 3분(`OLLAMA_MODEL_IDLE_SECONDS`) 이상 없으면 모델을 unload합니다. (Ollama 서버 프로세스는 유지)

## 실행
```bash
source venv/bin/activate
pip install -r requirements.txt
python -m app.scripts.download_embedding_model
uvicorn main:app --host 0.0.0.0 --port 5001 --workers 2
```

`AnnouncementVectorIndexer`는 실행 시 HuggingFace 원격 다운로드를 하지 않고,
반드시 `EMBEDDING_MODEL_LOCAL_PATH` 경로의 로컬 모델만 사용합니다.

`main.py` 실행 시 MinIO/Qdrant 컨테이너를 자동으로 시작하고,
애플리케이션 종료 시 함께 중지합니다.

수동으로 컨테이너를 직접 관리하려면 아래 명령을 사용할 수 있습니다.

```bash
mkdir -p /data2/services/minio
docker rm -f pdfgpt-minio >/dev/null 2>&1 || true
docker run -d --name pdfgpt-minio \
	-p 9000:9000 -p 9001:9001 \
	-e MINIO_ROOT_USER=minioadmin \
	-e MINIO_ROOT_PASSWORD=minioadmin \
	-v /data2/services/minio:/data \
	quay.io/minio/minio server /data --console-address ':9001'
```

위 설정이면 버킷 `pdfai-startingblock` 데이터는 `/data2/services/minio/pdfai-startingblock/`에 저장됩니다.

```bash
mkdir -p ${QDRANT_STORAGE_ROOT}/${QDRANT_SERVICE_NAME}
docker rm -f pdfgpt-qdrant >/dev/null 2>&1 || true
docker run -d --name pdfgpt-qdrant \
	-p 6333:6333 -p 6334:6334 \
	-v ${QDRANT_STORAGE_ROOT}/${QDRANT_SERVICE_NAME}:/qdrant/storage \
	qdrant/qdrant
```

위 설정이면 Qdrant 데이터는 `/data2/qdrant/{서비스명}/` 형태로 영구 저장됩니다.

## 기존 processed_file 데이터 1회 이전
기존 로컬 텍스트 파일을 MinIO로 이전하려면:

```bash
python -m app.scripts.migrate_processed_to_minio
```

기본 소스 디렉토리는 `./processed_file`이며 필요 시 `SOURCE_DIR` 환경 변수로 변경할 수 있습니다.

## 기존 processed 데이터 임베딩 백필
```bash
python -m app.scripts.backfill_embeddings
```

체크포인트 파일(`app/data/backfill_embeddings.done`)에
완료된 `announcement_id`를 기록합니다. 재실행 시 해당 ID는 자동으로 건너뜁니다.

현재 백필은 단일 프로세스 순차 처리 방식입니다.

기본값으로 이미 벡터가 있는 공고도 건너뛰며 재시작합니다:

```bash
python -m app.scripts.backfill_embeddings
```

기존 벡터도 강제로 재생성하려면:

```bash
python -m app.scripts.backfill_embeddings --no-skip-existing
```

체크포인트 경로 지정:

```bash
python -m app.scripts.backfill_embeddings --checkpoint app/data/my_backfill.done --skip-existing
```

선택한 공고 ID만 처리:

```bash
python -m app.scripts.backfill_embeddings --ids 1,2,3
```

실제 upsert 없이 대상 확인:

```bash
python -m app.scripts.backfill_embeddings --dry-run
```