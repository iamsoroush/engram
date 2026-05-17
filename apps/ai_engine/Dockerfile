FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY ai_engine/requirements.txt /tmp/ai-engine-requirements.txt
RUN pip install --no-cache-dir -r /tmp/ai-engine-requirements.txt

COPY ai_engine /app

CMD ["celery", "-A", "ai_engine.celery_app.celery_app", "worker", "--loglevel=INFO", "--queues=ai_jobs"]
