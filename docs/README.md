# AesMem Engineering Docs

This folder is the starting point for future product and engineering work. The app-specific READMEs explain how to run services; these docs explain why the system is shaped the way it is and what constraints future changes must preserve.

## Documents

- [Architecture](architecture.md): product architecture, data flow, storage model, and key principles.
- [Frontend docs](frontend/README.md): capture-first UX, login, local-first outbox, browser storage, and mobile testing notes.
- [Backend docs](backend/README.md): current backend, v2 design, auth, storage, and fake processing.
- [Production](production.md): deployment model, volumes, networking, data safety, and operational concerns.

## Core Principle

AesMem is a capture-first clinical memory tool. A doctor must never be forced to select a patient before capturing audio, photo, or text. Capture must remain available even when syncing, processing, patient assignment, or organization is delayed.
