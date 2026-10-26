# PlanForge 백엔드 — API + 단일 워커(프로세스 내 asyncio) 하나의 컨테이너.
# build context는 저장소 루트다 (docker-compose.yml 참조) — 독립 CLI 패키지를 함께 복사한다.
FROM python:3.12-slim
WORKDIR /srv/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 독립 CLI 패키지(planforge 엔진) — backend는 이 패키지에 의존한다.
COPY packages/planforge-cli ./packages/planforge-cli
RUN pip install --no-cache-dir --no-build-isolation ./packages/planforge-cli

COPY backend/ .

ENV PYTHONUTF8=1
EXPOSE 8000
# 운영은 alembic으로 스키마를 올린다 — SQLite 파일(/srv/data)은 alembic이 생성한다
CMD ["sh", "-c", "mkdir -p /srv/data && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
