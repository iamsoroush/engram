"""Q&A knowledge library + retrieval-grounded drafting (AES-410).

The clinic's own answers, made reusable. Two tiers of exemplars live in ``qa_knowledge_exemplars``:
curated **templates** and auto-indexed **doctor-approved sent replies** (per-tenant, never crossing
tenants). When a patient asks a between-visits question the backend retrieves the most relevant
exemplars — hybrid lexical + embedding, scoped in SQL — and grounds the ``qa_draft`` in them, so a
draft is prepared "based on how this clinic answers this kind of question" (the provenance chip).

The worker stays stateless (the boundary rule): the backend builds ``retrievedExemplars`` into the
job payload; the prompt keeps patient-specific context and the safety guardrails above any exemplar.

Modules:

* ``normalize`` — orthography-folding + language detection for the lexical match target.
* ``embeddings`` — the optional embeddings-gateway client (lexical-only when unconfigured).
* ``retrieval`` — hybrid retrieval (SQL-scoped candidates → reciprocal-rank fusion in Python).
* ``library`` — template CRUD, sent-reply auto-index + exclude, and provenance selection.
"""
