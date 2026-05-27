# AesMem Engineering Docs

This folder is the starting point for future product and engineering work. The app-specific READMEs explain how to run services; these docs explain why the system is shaped the way it is and what constraints future changes must preserve.

## Documents

- [Product](product.md): product purpose, users, concepts, and high-level behavior.
- [Design principles](design-principles.md): durable UX/product principles.
- [UX docs](ux/overview.md): current user-facing screens, workflows, navigation, and shared state language.
- [Architecture](architecture.md): product architecture, data flow, storage model, and key principles.
- [Frontend docs](frontend/README.md): capture-first UX, login, local-first outbox, browser storage, and mobile testing notes.
- [Backend docs](backend/README.md): current backend, v2 design, auth, and storage.
- [AI engine docs](ai_engine/README.md): worker boundary, placeholder processors, job recovery, and replacement path.
- [Production](production.md): deployment model, volumes, networking, data safety, and operational concerns.

## Layering

- Product/design docs own intent and principles.
- UX docs own visible behavior and user-facing copy.
- Architecture docs own system boundaries and data flow.
- Frontend/backend docs own implementation mechanics.
- Backend OpenAPI remains the source of truth for exact API contracts.

## Core Principle

AesMem is a capture-first clinical memory tool. A doctor must never be forced to select a patient before capturing audio, photo, or text. Capture must remain available even when syncing, processing, patient assignment, or organization is delayed.
