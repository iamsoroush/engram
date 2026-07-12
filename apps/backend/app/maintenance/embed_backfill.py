"""Maintenance CLI: (re)embed Q&A knowledge exemplars with a NULL embedding (AES-1902).

Run after wiring the embeddings gateway so existing lexical-only rows gain semantic vectors:

    python -m app.maintenance.embed_backfill

No-op (prints 0) when no gateway is configured. Startup runs the same pass automatically.
"""
from __future__ import annotations

from app.db.session import SessionLocal
from app.services.qa_knowledge.backfill import backfill_missing_embeddings


def main() -> None:
    db = SessionLocal()
    try:
        embedded = backfill_missing_embeddings(db)
    finally:
        db.close()
    print(f"Embedded {embedded} Q&A exemplar(s) that had a NULL embedding.")


if __name__ == "__main__":
    main()
