# Structured Report Model Owns Report Content (2026-05-22)

The backend stores generated report body content in `sessions.report_model`, a JSON model with report sections, paragraph/image/artifact blocks, extracted findings, and source capture references. The active-session frontend renders clinic and patient information from non-AI template/session context, then renders backend-owned body markdown from the session report contract.

The singleton `default` report template is centralized in backend reporting code and currently exposes clinic context and body rendering rules. Patient information is injected from the assigned database patient and identifiers at render time; AI-generated body text must not be treated as the source of truth for patient demographics.

TODO: Add tenant-aware multi-template selection when Engram supports more than the default clinic report layout.
