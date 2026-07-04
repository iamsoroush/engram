"""A minimal SQLAlchemy column type for pgvector, with no extra Python dependency.

The Q&A knowledge retrieval stores an embedding per exemplar in a native ``vector`` column (the
pgvector extension — decision-complete: pgvector inside the existing Postgres, no new infra). We keep
the ranking in Python over a tiny SQL-scoped candidate set, so we never need the ``<=>`` operator or
an ANN index here — only to store a vector and read it back. That means we can avoid the ``pgvector``
Python package entirely and define the type ourselves:

* **bind** a Python ``list[float]`` as the pgvector text form ``[0.1,0.2,...]`` (its input function
  parses it on assignment to a ``vector`` column), and
* **read** the column back (psycopg returns the unknown type as its text form) into a ``list[float]``.

The column is declared **dimensionless** (``vector`` with no ``(n)``): the corpus is tiny so we do an
exact in-memory scan rather than build an ivfflat/hnsw index (which would fix the dimension), which
also keeps the schema model-agnostic — swapping the embedding model never needs a migration.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    """A dimensionless pgvector ``vector`` column bound/read as a Python ``list[float]``."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:  # noqa: D102 (SQLAlchemy hook)
        return "vector"

    def bind_processor(self, dialect: Any):  # noqa: D102
        def process(value: list[float] | None) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(repr(float(component)) for component in value) + "]"

        return process

    def result_processor(self, dialect: Any, coltype: Any):  # noqa: D102
        def process(value: Any) -> list[float] | None:
            if value is None:
                return None
            # psycopg returns the vector as its text form, e.g. "[0.1,0.2]".
            if isinstance(value, (list, tuple)):
                return [float(component) for component in value]
            text = str(value).strip().lstrip("[").rstrip("]").strip()
            if not text:
                return []
            return [float(component) for component in text.split(",")]

        return process
