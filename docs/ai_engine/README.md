# AI Engine Docs

AI engine docs describe the Celery worker boundary, placeholder processors, job recovery behavior, and future replacement path for real AI processors.

## Documents

- [Processing](processing.md): current AI engine placeholder capture and session processors.

## Direction

The backend owns API contracts, database schema, tenant scoping, and job rows. The AI engine consumes named Celery tasks and reports lifecycle state through protected backend internal endpoints. Real AI processors should replace placeholder job bodies without moving backend ownership into the worker.
