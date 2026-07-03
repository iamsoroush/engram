# UX Overview

## Summary

Engram is a capture-first clinical assistant for aesthetics and therapy clinics (dermatology next). The UX lets authenticated clinic staff capture audio, photo, or text immediately, keep those captures safe on the device when needed, progressively evolve session report output, and review memory through the Active Session, Clinical Memory, and Search shell.

The UX keeps capture first while moving long-term review toward Clinical Memory: a calm assistant surface that focuses on today's work, searchable patient memory, and only the items that need human judgment. Patient assignment remains non-blocking.

## Main Users

- Owner: the clinic's founding user from sign-up; a full superset of doctor + admin (captures and
  administers the tenant).
- Doctor: captures clinical material and reviews generated session output.
- Assistant: captures, assigns patients, and reviews session memory.
- Admin: can load staff-facing session lists, but cannot perform staff-only capture or assignment APIs.
- Patient preview: receives a limited-access screen only; staff tools are unavailable.

## Main Workflows

- [Capture a session](workflows/capture-session.md)
- [Clinical Memory workflow](workflows/review-and-assign-patients.md)

## Main Screens

- [Landing / Login / Sign-up](screens/login.md) (bilingual fa/en + RTL; self-serve clinic sign-up)
- [First-run onboarding](screens/onboarding.md)
- [Capture / Active Session](screens/capture.md)
- [Clinical Memory](screens/patients.md) — Today, Patients, and Needs input tabs; Pro adds a
  deterministic **Lists** tab (smart lists + lot/product recall)
- [Search](screens/search.md)
- [Session review](screens/session-review.md)
- Q&A inbox (Pro) — staff side of patient Q&A; see [navigation](navigation.md)
- [Insights (clinic analytics)](screens/insights.md) (owner/admin)
- [Account pages — Settings & Profile](screens/account.md) (+ Switch clinic for multi-clinic users)
- [Team (member management)](screens/team.md) (owner/admin)
- [Plan (Basic vs Pro)](screens/plan.md) (owner/admin)
- [Public patient surfaces](screens/patient-surface.md) — `/share/{token}` curated report + aftercare,
  `/qa/{token}` patient Q&A (Pro); token-capability pages outside the staff shell

## How To Read These Docs

- Start here for the current UX map and links.
- Use [navigation](navigation.md) for routes and cross-screen paths.
- Use [states](states.md) for shared loading, empty, offline, warning, and assistant-language rules.
- Use screen docs for layout and visible content on one screen.
- Use workflow docs for the user's path across screens.

## Navigation Summary

The frontend is a single React app with hash-based screen selection:

- Default: Active Session Workspace
- `#active-session`: current active session workspace
- `#patients`: Clinical Memory with Today, Patients, Needs input, and (Pro) Lists tabs
- `#search`: local memory search
- `#qa-inbox`: Q&A inbox (Pro; top-bar icon beside Search)
- `#settings`, `#profile`: account pages (account menu)
- `#insights`: clinic analytics (owner/admin; account menu)
- `#team`, `#plan`: member management and plan switch (owner/admin; account menu)
- `#switch-clinic`: switch the active clinic (multi-clinic users; account menu)

Two public, token-capability routes live outside the staff shell: `/share/{token}` (curated
patient report) and `/qa/{token}` (patient Q&A, Pro).

The shell keeps Active Session, Clinical Memory, and Search available from a compact top-left navigator after staff login. Capture actions are always available as a sticky bottom row for staff users.

See [navigation](navigation.md).

## Important UX Constraints

- Capture must not require selecting a patient.
- Local persistence happens before network upload.
- Generated capture/session output is shown as review material with lightweight confidence and state indicators.
- Technical AI and sync pipeline labels are hidden behind assistant-state language. See [states](states.md).
- Backend OpenAPI remains the source of truth for exact API contracts.
