# Patient Surface (public token pages)

The clinic→patient channel: one primitive — a revocable tokenized link, no login, the token in the
URL is the capability — carrying two payloads ([foundation §4](../foundation.md)). Both pages render
in a **separate public area**: real paths (not hash routes), their own page bundle, no staff shell,
no clinic auth/state/stylesheet. Routes: [navigation.md](../navigation.md).

Both pages resolve an unknown, revoked, or expired token to one indistinguishable **"This link is no
longer available"** screen (no existence leak, AES-403). A network/server failure shows a retryable
"couldn't load" state instead — never a verdict on the link.

## Shared report — `/share/{token}`

A read-only, immutable **curated snapshot** of one visit (AES-401/303): the payload is copied at
share time, so later edits to the visit never leak. The snapshot is frozen, but the **link is
lifecycle-aware**: reassigning or de-effecting the source visit **auto-revokes** every active share
of it (so a token can never serve one patient's content under another's name), a media read
re-checks **patient ownership** (not just tenant) and 404s a reassigned/deleted photo, and archiving
a patient revokes its shares. A share whose source visit changed after it was frozen (a report
correction / safety-flag addition) is flagged `stale` in the staff share list (needs-attention —
review/re-share). Rendering:

- Warm clinic header — initials logo, clinic name, a first-name greeting, visit title + date.
- **Curated before/after photos** with their captions.
- The **curated sections**, an optional plain-words **"what we did"** list, and the **aftercare**
  checklist (bullet lines rendered as ticked items).
- The trust footer: `Private link · this is everything shared with you` (+ `Available until …` when
  an expiry is set).
- Page chrome localizes to the clinic's report language (fa/en); content renders with per-line
  direction (`dir="auto"`).
- Media loads **only** through the token-scoped endpoint (`GET /share/{token}/media/{captureId}`) —
  never a raw file URL; a failed image degrades to a labelled placeholder, never a broken image.

Created, previewed, and revoked from the clinic's share sheet
([session-review.md](session-review.md)).

### Shown vs withheld

The patient sees a curated subset of the clinic's **one** report — never a second document.
Withholding is enforced **server-side**: the share endpoint only stores and serves the curated
snapshot, so internals cannot appear through a UI bug.

| Element | Shared? |
| --- | --- |
| Visit summary · concern/goals · plan & follow-up · aftercare | default on (curated toggles) |
| Before/after media + captions | curated subset only |
| "What we did" treatment lines | opt-in; plain words — generic by default, brands only when the clinic's include-brands setting is on ([account.md](account.md)); **never the treatment table** |
| Assessment | opt-in, default **off** (clinician findings can alarm out of context) |
| Lot / batch numbers | **always withheld** — incl. lot/batch tokens filtered out of an AI-prefilled photo caption server-side at snapshot time |
| Confidence/uncertainty chips, carried-forward state, evidence/source links, corrections | **always withheld** |
| National ID / DOB / other visits / raw captures / internal notes | **always withheld** |
| Report status (`Complete`/`Updating`) | never — the patient gets a finished artifact |

## Post-session Q&A — `/qa/{token}` (Pro)

The patient's own Q&A thread (AES-402): a question composer plus the exchange history. Each
exchange shows the question, its status (`awaiting` / `answered` / `closed`), and — once a doctor
approves — the reply marked **doctor-verified** with a byline. A dismissed question shows closed,
with no reply. The AI draft, routing, internal status, and every other patient are never in this
payload, so they cannot appear here.

Clinic side: [qa-inbox.md](qa-inbox.md).

## Delivery

Copy-link / native-share / QR — the surface is channel-agnostic. Automated SMS/WhatsApp delivery is
deferred (AES-404).

## Main Components

- `PatientSharePage` + `shareApi` · `PatientQaPage` + `qaApi` (`features/patient-surface/`) —
  deliberately standalone modules that never depend on clinic auth or state.

## Related APIs

- Share payload + media: [aes-basic-api.md](../../backend/aes-basic-api.md) (`GET /share/{token}`,
  `GET /share/{token}/media/{captureId}`).
- Q&A thread: [aes-pro-qa-api.md](../../backend/aes-pro-qa-api.md) (`GET /qa/{token}`,
  `POST /qa/{token}/ask`).
