FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
COPY backend/requirements-db.txt ./backend/requirements-db.txt
COPY ai_pipeline/requirements.txt ./ai_pipeline/requirements.txt

RUN pip install --no-cache-dir -r backend/requirements.txt \
    && pip install --no-cache-dir -r backend/requirements-db.txt \
    && pip install --no-cache-dir -r ai_pipeline/requirements.txt

COPY backend ./backend
COPY ai_pipeline ./ai_pipeline

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
