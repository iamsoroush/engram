FROM python:3.12-slim

# Overridable pip index — default pypi.org; set PIP_INDEX_URL to an Iranian mirror for in-country builds.
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY ai_engine/requirements.txt /tmp/ai-engine-requirements.txt
# Retry the whole install: from Iran the pip index (pypi.org or a mirror) intermittently stalls
# mid-download, and a single read-timeout would otherwise fail the entire build.
RUN for i in 1 2 3 4 5; do \
        pip install --no-cache-dir --index-url "$PIP_INDEX_URL" --retries 5 --timeout 120 -r /tmp/ai-engine-requirements.txt && break; \
        [ "$i" = 5 ] && { echo "pip failed after 5 attempts" >&2; exit 1; }; \
        echo "pip attempt $i failed (flaky index); retrying in 5s..."; sleep 5; \
    done

COPY ai_engine /app

CMD ["celery", "-A", "ai_engine.celery_app.celery_app", "worker", "--loglevel=INFO", "--queues=ai_jobs", "--beat", "--schedule=/tmp/engram-celerybeat-schedule"]
