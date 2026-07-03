# AI Engine

Celery worker app for Engram AI processing jobs.

Detailed processing contracts live in [docs/ai_engine](../../docs/ai_engine/README.md).

The backend is the producer: it creates durable job rows and sends named Celery tasks. The AI engine is the consumer: it runs those task names against the configured OpenAI-compatible gateway (transcription, captions, report synthesis, patient memory, Q&A) and calls backend internal APIs to update job state and submit generated output. Gateway-less environments fall back deterministically per job (see [docs/ai_engine/processing.md](../../docs/ai_engine/processing.md)).

The AI engine does not import backend code or connect directly to the database. Its coupling points are Redis task names and backend `/internal/ai/jobs/...` endpoints authenticated with `AI_ENGINE_INTERNAL_TOKEN`.

**Jobs must be vertical-agnostic.** Never hardcode or assume a vertical (e.g. "aesthetics clinic" /
"psychotherapy practice", or domain vocabulary) in a prompt or processor. The backend passes a
`domain` descriptor in each job's context; prompts read it via `processing.domain_framing()` and fall
back to a neutral `"clinic"`. Vertical-specific wording is allowed only when it is optional and
data-driven through that descriptor — see [docs/ai_engine/README.md](../../docs/ai_engine/README.md#caution-ai-jobs-must-be-vertical-agnostic).

## Local Worker

From the repository root, Docker development starts the worker with:

```sh
docker compose up --build ai-engine
```

For local Python development:

```sh
cd apps/ai_engine
pip install -r requirements.txt
AI_ENGINE_BACKEND_INTERNAL_URL=http://localhost:8010 celery -A ai_engine.celery_app.celery_app worker --loglevel=INFO --queues=ai_jobs --beat --schedule=/tmp/engram-celerybeat-schedule
```

## Environment

Settings are `AI_ENGINE_`-prefixed env vars; the authoritative list (with defaults and per-task
gateway/model overrides) is [`ai_engine/config.py`](ai_engine/config.py) — read it rather than
relying on any enumeration here, which would go stale.

When `AI_ENGINE_TRANSCRIPTION_BASE_URL` is set, audio capture jobs download the
source capture from the backend internal API, convert it to mono 16 kHz FLAC
with `ffmpeg`, and send it to the configured OpenAI-compatible chat completion
gateway as `input_audio`. When it is unset, non-fixture audio jobs fail through
the normal retryable job path instead of writing placeholder transcript text.
The Docker image installs `ffmpeg`; local Python development needs `ffmpeg`
available on `PATH`.
