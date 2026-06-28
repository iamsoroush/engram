# Aesthetics-Basic backend API (contracts)

> Stable request/response contracts for the deterministic, **zero-AI** aesthetics-Basic surfaces and
> the shared patient-facing surface. These are the contracts the frontend tracks build against — they
> are precise and meant to be stable. Story IDs reference
> [`docs/ux/aesthetics-stories.md`](../ux/aesthetics-stories.md). The backend OpenAPI schema
> (`/api/v1/openapi.json`) remains the machine source of truth; this file is the human contract for
> the build hand-off.

## Conventions

- **Base path:** all endpoints are under `/api/v1` unless noted. JSON bodies, **camelCase** keys.
- **Auth:** staff endpoints require a bearer token. Read endpoints accept `doctor | assistant | admin`
  (`staff_or_admin`); write endpoints require `doctor | assistant` (`staff`). The **public** patient
  surface endpoints (`/share/...`) take **no auth** — the token in the URL is the capability.
- **Tenant scope:** everything except the public endpoints is scoped to the caller's tenant.
- **Errors:** predictable `{"detail": "..."}` with conventional status codes — `400` invalid input,
  `403` insufficient role, `404` not found. Validation errors are FastAPI `422`.
- **Zero AI:** none of these endpoints run an AI job, enter a `processing` state, or depend on the
  gateway. They are deterministic and synchronous.

---

## AES-204 — Smart patient search

Deterministic, Persian-orthography-aware, multi-field, ranked. Reuses the confusable/transliteration
normalization in `patient_identity`.

### `GET /patients/search`
Query params: `q` (string, optional — name in any script / phone / national ID / alias; blank returns
recent patients), `limit` (int, default `20`, 1–100).

Response:
```jsonc
{
  "schemaVersion": "2026-06-12.patient-search.v1",
  "query": "قاسمی",
  "total": 3,                       // number of scored matches (may exceed items length)
  "items": [
    {
      // ...all standard patient fields (same shape as GET /patients/{id}):
      "id": "uuid", "tenantId": "uuid", "displayName": "ثریا قاسمی",
      "legalFirstName": null, "legalLastName": null, "nationalId": null,
      "dateOfBirth": null, "sex": null, "phone": "+98...", "email": null,
      "notes": null, "status": "active", "createdAt": "iso", "updatedAt": "iso",
      // ...plus search metadata:
      "score": 0.95,                // 0–1; null for the blank-query "recent" list
      "matchedOn": ["name"],        // national_id | phone | email | name | name_prefix | name_fuzzy | contact_partial
      "reason": "Exact name match (orthography-folded)."
    }
  ]
}
```
Items are sorted by `score` desc, then most-recently-updated. Ranking ladder (highest wins): exact
national ID (1.0) → exact phone (0.98) → exact email (0.97) → exact name alias (0.95) → name prefix
(0.85) → fuzzy name (≤0.84, first/last-name & transliteration variance) → partial contact digits (0.6).

---

## AES-205 — Duplicate-patient guard

Run at create time, before writing a new patient, to catch the split-into-many failure mode. Never
merges; only surfaces likely existing matches for a **Use existing / Create anyway** choice.

### `POST /patients/duplicate-check`
Body:
```jsonc
{ "displayName": "سروش معاضد", "nationalId": "0012345678", "phone": "0912...", "email": null }
```
All fields optional; pass whatever has been entered so far.

Response:
```jsonc
{
  "schemaVersion": "2026-06-12.duplicate-guard.v1",
  "hasLikelyDuplicate": true,       // true only when a STRONG signal matched (national_id/phone/email/exact-name)
  "candidates": [                   // sorted by confidence desc, capped at 5; fuzzy-name-only hits appear but do NOT raise the flag
    {
      "patientId": "uuid",
      "displayName": "سروش معاصد",
      "confidence": 1.0,
      "matchedOn": ["national_id"], // merged across signals for the same patient
      "reason": "An existing patient already has this national ID.",
      "risks": ["..."],             // human-readable cautions (may be empty)
      "evidence": { "identifierType": "national_id", "identifierValue": "...", "normalizedValue": "..." }
    }
  ]
}
```

---

## AES-301 — Deterministic assign-later suggestion

Rule-based (NOT AI) "Assign to …?" for an unassigned visit. Capture-first never blocks; filing catches
up. The resolver still offers Assign / Keep unassigned / Create new — nothing is assigned silently.

### `GET /sessions/{session_id}/assignment-suggestion`
Response:
```jsonc
{
  "schemaVersion": "2026-06-12.assign-later-suggestion.v1",
  "sessionId": "uuid",
  "alreadyAssigned": false,         // true → suggestion null, candidates []
  "suggestion": {                   // the top candidate, or null
    "patientId": "uuid",
    "displayName": "Active Patient",
    "basis": "active_patient",      // active_patient (a visit open right now) | recent_patient (most recently seen)
    "reason": "This patient has a visit open right now.",
    "lastVisitAt": "iso"
  },
  "candidates": [ /* same shape, active patients first then most-recent, capped at 5 */ ]
}
```

---

## AES-106 / AES-203 — Last-visit fetch

How Basic answers "what did we use last time" — by retrieval. Returns the prior visit's free-text
note(s) and that visit's photos (before/after media; Basic does **not** tag them).

### `GET /patients/{patient_id}/last-visit`
Query params: `excludeSessionId` (uuid, optional — the current in-progress visit to skip, so a
returning patient gets the visit *before* the one being captured now).

Response:
```jsonc
{
  "schemaVersion": "2026-06-12.last-visit.v1",
  "patientId": "uuid",
  "hasPriorVisit": true,
  "visit": {                        // null when there is no prior visit with content
    "sessionId": "uuid",
    "title": "Visit",
    "status": "needs_review",
    "capturedAt": "iso",
    "updatedAt": "iso",
    "captureCount": 2,
    "note": "Forehead Botox, 20u Dysport.",  // concatenated typed note(s); null if none
    "noteSource": "captures",                // "captures" | null
    "media": [                               // the visit's photos (before/after; untagged in Basic)
      {
        "captureId": "uuid",
        "type": "photo",
        "fileEndpoint": "/api/v1/captures/{id}/file",          // authenticated; presigned-URL style
        "contentEndpoint": "/api/v1/captures/{id}/file-content", // authenticated; streamed bytes (range)
        "capturedAt": "iso",
        "caption": null                       // Pro caption when present, else null
      }
    ]
  },
  "sameAsLastTime": {               // deterministic "same as last time" pre-fill; null if the prior visit has no typed note
    "note": "Forehead Botox, 20u Dysport.",
    "fromSessionId": "uuid",
    "fromVisitAt": "iso",
    "label": "from last visit · 2026-06-12"
  }
}
```
The pre-fill is never auto-saved; the client seeds an editable note from `sameAsLastTime.note`.

---

## AES-702 — Aftercare templates

Per-procedure deterministic aftercare instruction templates, managed in Settings, attached to a
curated share (AES-304).

Template object:
```jsonc
{
  "id": "uuid", "tenantId": "uuid",
  "name": "Botox aftercare",
  "procedureType": "botox",         // free-form clinic label, lowercased; null = general
  "body": "Avoid lying down for 4 hours.",
  "isActive": true,
  "createdAt": "iso", "updatedAt": "iso"
}
```

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `GET` | `/aftercare-templates` | staff_or_admin | List, newest first. Query: `procedureType` (filter), `includeInactive` (bool, default false). Returns a JSON array. |
| `POST` | `/aftercare-templates` | staff | Body: `{ name, procedureType?, body, isActive? }` (`isActive` default true). Returns the template. |
| `GET` | `/aftercare-templates/{id}` | staff_or_admin | One template. |
| `PATCH` | `/aftercare-templates/{id}` | staff | Body: any subset of `{ name, procedureType, body, isActive }` (only provided keys change; `procedureType: null` clears it). |
| `DELETE` | `/aftercare-templates/{id}` | staff | Returns `{ "id": "uuid", "status": "deleted" }`. |

---

## AES-303 / AES-304 / AES-403 / AES-401 — Patient surface

One tokenized, revocable clinic→patient share of a **curated content snapshot** (sections + media +
aftercare). The withholding contract is structural: only curated content is copied into the share at
create time, and the public read serves *that snapshot alone* — raw captures, internal notes, lots,
national ID, and other visits are never copied, so they cannot leak.

> The **Pro** payload on the same patient surface — the post-session patient↔clinic Q&A (AES-402) —
> has its own contract: [`aes-pro-qa-api.md`](aes-pro-qa-api.md).

### Staff endpoints

**`POST /patient-shares`** (staff) — create a curated share.
```jsonc
// Request
{
  "patientId": "uuid",                 // required
  "sessionId": "uuid",                 // optional source visit (its captured-at becomes visitDate)
  "title": "Your Botox visit",
  "sections": [ { "label": "Visit", "body": "Forehead Botox performed." } ],  // empty-body sections dropped
  "media": [ { "captureId": "uuid", "caption": "Before" } ],                  // must be THIS patient's photo captures
  "aftercare": { "templateId": "uuid" }  // OR inline { "name": "...", "body": "..." }; templateId snapshots the template
                                          // (optional name/body override its snapshot); omit for no aftercare
  ,"expiresInDays": 30                   // optional, 1–365; omit = no expiry
}
```
Validation: `404` if patient/session/template/media-capture not found; `400` if the session or a
selected photo belongs to a different patient. Returns the **staff share payload** (below) with the
token and `preview`.

Staff share payload:
```jsonc
{
  "id": "uuid", "tenantId": "uuid", "patientId": "uuid", "sessionId": "uuid|null",
  "token": "url-safe-token",
  "publicPath": "/share/{token}",      // the patient-facing path (host-relative)
  "payloadType": "report_aftercare",   // Basic payload (Pro Q&A later)
  "status": "active",                  // active | revoked | expired (derived)
  "title": "Your Botox visit",
  "mediaCount": 1,
  "createdAt": "iso", "updatedAt": "iso",
  "expiresAt": "iso|null", "revokedAt": "iso|null",
  "preview": { /* the exact public payload — see below — included on create + GET one (AES-403) */ }
}
```

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `GET` | `/patient-shares` | staff_or_admin | List shares, newest first. Query: `patientId` (filter). No `preview`. |
| `GET` | `/patient-shares/{id}` | staff_or_admin | One share **with** `preview` (per-share preview, AES-403). |
| `POST` | `/patient-shares/{id}/revoke` | staff | Revoke; idempotent. Returns the staff payload with `status: "revoked"`. |

### Public endpoints (no auth — the token is the capability)

**`GET /share/{token}`** — read-only curated payload (AES-401). `404` if the token is unknown,
revoked, or expired (no existence leak).
```jsonc
{
  "schemaVersion": "2026-06-12.patient-share.v1",
  "payloadType": "report_aftercare",
  "status": "active",
  "clinic": { "name": "Engram Demo Clinic" },
  "patientName": "Sara Nazari",
  "title": "Your Botox visit",
  "visitDate": "iso|null",
  "sections": [ { "label": "Visit", "body": "Forehead Botox performed." } ],
  "media": [ { "captureId": "uuid", "caption": "Before", "url": "/api/v1/share/{token}/media/{captureId}" } ],
  "aftercare": { "templateId": "uuid|null", "name": "Botox aftercare", "body": "..." },  // or null
  "createdAt": "iso", "expiresAt": "iso|null"
}
```

**`GET /share/{token}/media/{capture_id}`** — stream a curated photo (no auth). Serves the bytes only
if that capture is in the share's curated `media` list; `404` otherwise. Supports HTTP `Range` for
mobile. This is the only way a shared photo is exposed publicly — the authenticated capture endpoints
are never reachable from the patient surface.

---

## E9 — Multi-seat / multi-user (AES-901..906)

> Both tiers. The clinic is a shared workspace; a visit is **owned by its creator** and edits/curation
> are owner-only by default, with **tenant-configurable** per-role permission presets. Capture-first is
> never blocked. Details: [`docs/ux/redesign-foundation.md`](../ux/redesign-foundation.md) §7.

### Author attribution (AES-901) — additive fields, not new endpoints

Session and capture payloads now carry, from `created_by_user_id` (deterministic, no AI):
`createdByUserId` and `createdBy: { userId, displayName }`; sessions additionally carry
`ownerUserId` (== creator). The patient-timeline sessions (`GET /patients/{id}/memory` →
`sessions[]` / `groups[].sessions[]`) carry the same `createdBy` / `createdByUserId`.

### Role permissions (AES-905) — on tenant settings

The tenant profile (in `auth/dev-login`, `POST /auth/login`, `GET /me`, `PATCH /tenant/settings`)
gains `rolePermissions: { <role>: "contribute" | "reassign" | "full" }` — the effective per
non-owner-role preset (defaults merged with stored overrides). Owner and `admin` are always `full`
and are not listed. Presets are ordered: `contribute` (append only) < `reassign` (+ change the
patient) < `full` (+ edit/curate the visit).

`PATCH /tenant/settings` accepts `rolePermissions` (a partial map, merged) **admin-only** (`403`
otherwise); only the configurable roles `assistant` / `doctor` and valid presets are accepted (`400`
otherwise). Permissive zero-config default: `{ "assistant": "reassign", "doctor": "contribute" }`.

### Ownership enforcement (AES-902)

- `PATCH /sessions/{id}` (edit/curate) requires the **edit** right: owner, or a role with the `full`
  preset (admins are blocked at the existing staff-only write gate). `403` otherwise.
- `POST /sessions/{id}/assign-patient` requires the **reassign** right *only when changing an
  already-assigned visit* to a different patient (or clearing it). Initial filing of an unassigned
  visit is the capture-first / assign-later floor — open to all staff. `403` otherwise.

### Policy-aware intent (AES-906, Pro)

In the capture-processing job, an **explicit reassignment** of an already-assigned visit auto-applies
only if the *capturer's* role may reassign (above); otherwise it is routed to the owner as a
suggestion (`patient_match_candidate.decision = "suggested_reassignment"`, `policyDeferred: true`) —
never applied silently, never blocked.

### Worklist + clinic directory (AES-903)

A soft "line a patient up for a clinician" lane (a list, **not** a scheduler). Capture-first is
unaffected. All `staff_or_admin` to read, `staff` to write; tenant-scoped. `status` ∈
`waiting | seen | cancelled`.

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `GET` | `/clinic/members` | staff_or_admin | Active staff: `{ items: [{ userId, displayName, role, isClinician }] }`. |
| `GET` | `/worklist` | staff_or_admin | Query: `scope` (`mine`\|`clinic`, default `mine`), `status` (default `waiting`), `clinicianId`. Oldest first. |
| `POST` | `/worklist` | staff | Body `{ patientId, clinicianUserId, note? }`. Idempotent per `(patient, clinician)` while waiting. |
| `POST` | `/worklist/{id}/seen` | staff | Body `{ sessionId? }` — clears as seen, optionally linking the started session. |
| `DELETE` | `/worklist/{id}` | staff | Cancels (removes) the entry. |

Worklist entry shape: `{ id, status, note, patientId, patientName, clinicianUserId, clinician,
linedUpBy, sessionId, createdAt, updatedAt, resolvedAt }` where `clinician` / `linedUpBy` are
`{ userId, displayName }` attribution objects.

### "Mine vs Clinic" (AES-904)

`GET /sessions` and `GET /patient-memory` accept `clinicianId` — pass the caller's own id for the
"Mine" view (sessions/patients they own), omit for "Clinic" (the whole shared base).

---

## Notes for the frontend tracks

- **Search vs. list:** `GET /patients/search` is the smart, ranked, match-annotated search for the
  receptionist/find surface. The existing `GET /patients` (flat list, recency-ordered) is unchanged.
- **Register flow:** call `POST /patients/duplicate-check` as the name/contact is entered, before
  `POST /patients`. `POST /patients` itself still returns an existing exact match on retry (unchanged).
- **Curation is explicit:** the share captures only what the client sends in `sections` / `media` /
  `aftercare`; nothing is auto-included. Build the curated set from what the chronological report
  already shows.
- **Share links are immutable:** editing a sent share is not supported by design — revoke and create a
  new one. Revocation takes effect immediately on the public endpoints.
