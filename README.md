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
- GPT 기능: `app/api/gpt/` (`router.py`, `assistant.py`, `pdf_source.py`, `prompts.py`)

## 환경 변수
`.env`에 아래 값을 설정하세요.

```env
OPENAI_API_KEY=...

MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET=pdfai-startingblock
MINIO_PROCESSED_PREFIX=processed
MINIO_RAW_PREFIX=raw
```

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