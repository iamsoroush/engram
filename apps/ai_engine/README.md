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
AI_ENGINE_BACKEND_INTERNAL_URL=http://localhost:8010 celery -A ai_engine.celery_app.celery_app worker --loglevel=INFO --queues=ai_jobs --beat --schedule=/tmp/aesmem-celerybeat-schedule
```

## Environment

```sh
AI_ENGINE_CELERY_BROKER_URL=redis://redis:6379/0
AI_ENGINE_CELERY_RESULT_BACKEND=redis://redis:6379/1
AI_ENGINE_BACKEND_INTERNAL_URL=http://backend:8000
AI_ENGINE_INTERNAL_TOKEN=dev-ai-engine-token
AI_ENGINE_JOB_MAX_RETRIES=3
AI_ENGINE_JOB_RETRY_DELAY_SECONDS=30
AI_ENGINE_RECOVERY_INTERVAL_SECONDS=60
AI_ENGINE_MOCK_STAGE_DELAY_SECONDS=1.25
AI_ENGINE_TRANSCRIPTION_BASE_URL=
AI_ENGINE_TRANSCRIPTION_API_KEY=unused
AI_ENGINE_TRANSCRIPTION_MODEL=gemini-3.1-flash-lite
```

When `AI_ENGINE_TRANSCRIPTION_BASE_URL` is set, audio capture jobs download the
source capture from the backend internal API, convert it to mono 16 kHz FLAC
with `ffmpeg`, and send it to the configured OpenAI-compatible chat completion
gateway as `input_audio`. When it is unset, non-fixture audio jobs fail through
the normal retryable job path instead of writing placeholder transcript text.
The Docker image installs `ffmpeg`; local Python development needs `ffmpeg`
available on `PATH`.
