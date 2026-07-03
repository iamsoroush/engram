# Engram Engineering Docs

These docs explain why the system is shaped the way it is and what constraints future changes must
preserve. The app-specific READMEs explain how to run services.

**The single documentation index lives in [CLAUDE.md §2](../CLAUDE.md)** — start there. Do not
maintain a second doc map here.

## Layering

- Product/design docs own intent and principles.
- UX docs own visible behavior and user-facing copy.
- Architecture docs own system boundaries and data flow.
- Frontend/backend/AI-engine docs own implementation mechanics.
- Backend OpenAPI remains the source of truth for exact API contracts.
- Everything under `docs/` is **system-state** (always current, present tense) except
  `docs/work/` — the temporary workspace for process docs (epics, plans, design explorations),
  which are deleted after their essence is folded into system-state docs. Its README defines the
  lifecycle. System-state docs never link into it (CI enforces this).

## Core Principle

Engram is a capture-first clinical memory tool. A doctor must never be forced to select a patient
before capturing audio, photo, or text. Capture must remain available even when syncing, processing,
patient assignment, or organization is delayed.
