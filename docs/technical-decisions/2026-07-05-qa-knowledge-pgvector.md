# Q&A Knowledge Retrieval — pgvector in the Existing Postgres; ChromaDB Rejected (2026-07-05)

The Q&A knowledge library (AES-410) grounds `qa_draft` in the clinic's own approved answers (curated
templates + auto-indexed sent replies) via hybrid lexical + embedding retrieval. Store decision:

- **pgvector inside the existing Postgres** — the `vector` extension + a `qa_knowledge_exemplars` table
  (alembic), **not** a dedicated vector DB. **ChromaDB was evaluated and rejected**: it is another
  always-on service to deploy, monitor, and back up on the single alpha VPS, with its own persistence
  and app-side multi-tenancy anyway. The corpus is tiny (hundreds–low-thousands of short texts per
  clinic) and retrieval needs SQL-side tenant/language/tag filtering + transactional writes with the
  owning rows — exactly what pgvector gives for free (existing backups/restore + tenant isolation
  included). Chroma wins only at scales this feature won't reach.
- **Operational cost of the choice — the Postgres image swaps `postgres:16-alpine` →
  `pgvector/pgvector:pg16`** (Debian-based) across `docker-compose.yml`, `docker-compose.shared-infra.yml`,
  and `docker-compose.prod.yml`. The extension is created per-database (`CREATE EXTENSION IF NOT EXISTS
  vector`), idempotent on the canonical DB, every dev-stack clone, e2e, and prod. **On an existing data
  volume the alpine(musl)→debian(glibc) collation provider changes**, so a one-time `REINDEX DATABASE`
  is required after the swap — recorded in [production-alpha-tradeoffs.md](../production-alpha-tradeoffs.md).
- **Column is dimensionless `vector`** (exact in-memory scan over a tiny SQL-scoped candidate set — no
  ivfflat/hnsw index), so the schema is embedding-model-agnostic (a model swap needs no migration). A
  tiny custom SQLAlchemy `Vector` type (`app/db/pgvector.py`) binds/reads it as a `list[float]`, so **no
  `pgvector` Python dependency** is added. Tenant scoping is enforced in SQL; the lexical + embedding
  fusion (reciprocal of a term-cosine + an embedding cosine) is done in Python and unit-tested.
- **Backend embeds directly — the one place the backend calls an AI gateway.** Retrieval is
  backend-owned (the worker stays stateless), so the backend computes embeddings via an
  OpenAI-compatible `/embeddings` endpoint (`BACKEND_EMBEDDINGS_BASE_URL`, stdlib HTTP — no OpenAI SDK
  on the backend). Blank config ⇒ **lexical-only** deterministic retrieval, so dev/CI/e2e stay
  reproducible gateway-less. Secrets live in env only, like the worker's gateway config. The embedding
  cost is small + optional and is not yet metered through the worker's usage sink (alpha tradeoff).

See [backend/aes-pro-qa-api.md](../backend/aes-pro-qa-api.md) and
[ai_engine/processing.md](../ai_engine/processing.md) "Q&A draft".
