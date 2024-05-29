# gunicorn_config.py

# Worker의 수 설정
workers = 2  # 싱글 코어 서버에서는 2 또는 1로 설정합니다.

# Uvicorn Worker 사용
worker_class = 'uvicorn.workers.UvicornWorker'

# 바인딩 설정
bind = '0.0.0.0:5001'

# 로그 레벨 설정
loglevel = 'info'
