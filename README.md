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
- 공고 기능: `app/api/announcement/` (`router.py`, `storage.py`, `file_pipeline.py`)
- LLM 기능: `app/api/llm/` (`router.py`, `client.py`, `session_store.py`, `archive_store.py`, `prompts.py`)

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

REDIS_URL=redis://127.0.0.1:6379/0
LLM_SESSION_TTL_SECONDS=7200
LLM_IDLE_ARCHIVE_SECONDS=1200
LLM_ARCHIVE_SWEEP_INTERVAL_SECONDS=60

SQLITE_ARCHIVE_PATH=./llm_archive.db
```

## LLM API
- `POST /llm/start` : 대화 UUID 생성
- `POST /llm/chat` : Ollama 채팅 (`thread_id`, `message`, `announcement_id` 필요)
- `DELETE /llm/delete` : 대화 UUID 삭제 및 SQLite 아카이브

## Ollama 동작 정책
- 서버 시작 시 모델을 미리 실행하지 않습니다.
- 서버 시작 시 Ollama 서버가 실행 중인지 확인하고, 미실행이면 `ollama serve`를 시작합니다.
- `POST /llm/start`에서 UUID 발급 직후 모델을 로드합니다.
- Ollama 요청이 3분(`OLLAMA_MODEL_IDLE_SECONDS`) 이상 없으면 모델을 unload합니다. (Ollama 서버 프로세스는 유지)

## 실행
```bash
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 5001 --workers 2
```

## 기존 processed_file 데이터 1회 이전
기존 로컬 텍스트 파일을 MinIO로 이전하려면:

```bash
python -m app.scripts.migrate_processed_to_minio
```

기본 소스 디렉토리는 `./processed_file`이며 필요 시 `SOURCE_DIR` 환경 변수로 변경할 수 있습니다.