# AGENTS.md

This repository is developed with AI coding agents.

This document explains how agents should gather context, implement tasks, follow coding conventions, validate changes, and update documentation.

Agents should not read the entire repository blindly. Start from the relevant development README and then read only the documentation and code needed for the task.

---

## 1. Start here

Before implementing any task, first identify the task type:

- Frontend
- Backend
- Full-stack
- Architecture
- Production/deployment
- Documentation-only

Then start with the relevant README:

### Frontend task

Start with:

- `apps/frontend/README.md`

Use it to understand:

- how to install dependencies
- how to run the frontend locally
- how to run tests
- how to run linting/type checks
- how environment variables are configured

### Backend task

Start with:

- `apps/backend/README.md`

Use it to understand:

- how to install dependencies
- how to run the backend locally
- how to run tests
- how to run linting/type checks
- how migrations work, if applicable
- how environment variables are configured

### Full-stack task

Start with both:

- `apps/frontend/README.md`
- `apps/backend/README.md`

Also check:

- `docker-compose.yml`

Use `docker-compose.yml` to understand the local development setup and how frontend/backend services are connected.

### Production/deployment task

Start with:

- `docs/production.md`
- `docker-compose.prod.yml`

Also check:

- `docs/architecture.md`
- `docker-compose.yml`, if comparing development and production behavior

---

## 2. Core documentation map

Use these documents as the lightweight source of truth.

### `docs/product.md`

Defines what the product is, who it is for, what problem it solves, current MVP scope, and current product behavior.

Important:

If your implementation changes product behavior, update this document.

---

### `docs/design-principles.md`

Purpose:

Defines the non-negotiable product and UX principles.

If a requested change conflicts with these principles, explain the conflict before implementing.

---

### `docs/architecture.md`

Purpose:

Explains the system architecture, main applications, major modules, data flow, and important system boundaries.

Important:

If your implementation changes architecture, update this document briefly.

---

### `docs/technical-decisions.md`

Purpose:

Briefly records important decisions and why they were made.

Important:

Keep this file short. Add only decisions that future developers or agents need to understand.

Examples of decisions worth documenting:

- Capture creation does not require patient ID.
- Backend owns active session fallback logic.
- A specific state management pattern is used for active session state.
- A module intentionally avoids direct API calls.
- A background job owns a specific responsibility.

Examples of decisions not worth documenting:

- Small refactors
- Renaming a local variable
- Obvious implementation details
- Temporary debugging choices

---

### `docs/production.md`

Purpose:

Explains how to run and operate the production version.

Important:

If production behavior changes, update this document.

---

## 3. Implementation rules

### General

- Keep changes focused on the requested task.
- Prefer modifying existing modules/components over creating duplicates.
- Preserve existing behavior unless the user explicitly asks to change it.
- Do not silently change product behavior.
- Keep code readable, typed, and maintainable.
- The backend OpenAPI schema is the single source of truth for exact API contracts

### Frontend

- Reuse existing components where reasonable.
- Keep presentational components separate from business/API orchestration when practical.

### Backend

- Keep business logic in services or appropriate domain modules, not directly inside route handlers/controllers.
- Keep route/controller layers thin.
- Keep schemas/models typed and explicit.
- Return predictable error responses.

---

## 4. Coding conventions

### Python

All Python modules, classes, and public functions should have appropriate docstrings, unless they are small and self-descriptive.

Use Google-style docstrings.

Use typing for function inputs and outputs.

Add clarifying comments if a logic might not seem obvious.
