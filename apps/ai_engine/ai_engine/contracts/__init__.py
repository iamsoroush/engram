"""Typed output contracts for the worker's AI jobs (Axis-1 §2.2).

Each module here owns ONE payload family: the pydantic models that describe a job's validated output
plus its ``OUTPUT_VERSION`` string (``YYYY-MM-DD.<name>.vN``). The models replace the old ad-hoc
dict-shaping (``_clean_*`` / ``normalize_*`` / ``parse_*``) — the tolerant coercion now lives in the
model classmethods, and the job's ``parse_*`` entry points delegate here. Tolerance is preserved
byte-for-byte (a typed model must never silently tighten validation — see ``tests/test_contract_parity``).

Contracts stay **worker-local** (§2.2 decision): the backend validates its own side over JSON-HTTP;
these models are not shared across the deployable boundary. They import only ``core`` (never ``jobs``
or backend code), so any job may depend on them without an import cycle.
"""
