# AI Engine

Celery worker app for AesMem AI processing jobs.

Detailed processing contracts and replacement boundaries live in [docs/ai_engine](../../docs/ai_engine/README.md).

The backend is the producer: it creates durable job rows and sends named Celery tasks. The AI engine is the consumer: it runs those task names, calls backend internal APIs to update job state, and submits placeholder generated metadata until real AI processors are implemented.

The AI engine does not import backend code or connect directly to the database. Its coupling points are Redis task names and backend `/internal/ai/jobs/...` endpoints authenticated with `AI_ENGINE_INTERNAL_TOKEN`.

## Local Worker

From the repository root, Docker development starts the worker with:

```sh
docker compose up --build ai-engine
```

For local Python development:

```sh
cd apps/ai_engine
pip install -r requirements.txt
AI_ENGINE_BACKEND_INTERNAL_URL=http://localhost:8000 celery -A ai_engine.celery_app.celery_app worker --loglevel=INFO --queues=ai_jobs
```

## Environment

```sh
AI_ENGINE_CELERY_BROKER_URL=redis://redis:6379/0
AI_ENGINE_CELERY_RESULT_BACKEND=redis://redis:6379/1
AI_ENGINE_BACKEND_INTERNAL_URL=http://backend:8000
AI_ENGINE_INTERNAL_TOKEN=dev-ai-engine-token
AI_ENGINE_JOB_MAX_RETRIES=3
AI_ENGINE_JOB_RETRY_DELAY_SECONDS=30
AI_ENGINE_MOCK_STAGE_DELAY_SECONDS=1.25
```
