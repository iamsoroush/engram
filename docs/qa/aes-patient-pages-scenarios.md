# Manual test script — public patient pages (AES-401 / AES-403)

A numbered, no-code script anyone can follow to test the **public, patient-facing share page** — the
tokenized, read-only page a patient opens from a link (no login) to see their curated before/after +
report sections + aftercare. It is a **separate area** from the clinic app and lives at
`/share/<token>`.

What this verifies:

- the curated report + aftercare render correctly and are **read-only**;
- raw clinic internals (internal notes, lots, national ID, other patients) are **not reachable**;
- a **revoked** link no longer opens;
- an **invalid / expired** token is handled gracefully.

Background spec: [redesign-aesthetics.md §6](../ux/redesign-aesthetics.md) ·
[aesthetics-stories.md AES-401/403](../ux/aesthetics-stories.md) ·
API contract: [aes-basic-api.md](../backend/aes-basic-api.md).

---

## 0 · Before you start — your two URLs

You need a running stack. Two web addresses matter; **write down the ones your stack prints** — the
defaults are:

| Thing | Default | What it is |
| --- | --- | --- |
| **App URL** | `http://localhost:5183` | where the patient page opens (the link the patient gets) |
| **API URL** | `http://localhost:8010/api/v1` | the backend, used here only to mint a test link |

> If you started an **isolated worktree stack** (`scripts/dev-stack.sh up`), it prints different
> ports — e.g. app `http://localhost:5185`, API `http://localhost:8012/api/v1`. Use **those** wherever
> this doc says `<APP>` and `<API>` below.

Throughout this doc:

- `<APP>` = your App URL (e.g. `http://localhost:5183`)
- `<API>` = your API URL (e.g. `http://localhost:8010/api/v1`)

The patient's link is always **`<APP>/share/<token>`** — note it is the **App** URL, *not* the API
URL. A common mistake is pasting the API address; the patient page only loads from the App URL.

---

## 1 · How to get a test share link

There are two ways. **Recipe A** (curl) works today and is the reliable way to mint links for these
tests. **Recipe B** (the clinic UI) is how staff will really do it, once that screen ships
(track ② — *Curate & Share*).

### Recipe A — mint a link with the API (works today)

Run these in a terminal, in order. Copy/paste each block and substitute `<API>` with your API URL.

**A1. Sign in as a clinician and grab a token.** This prints a big JSON blob — find the long
`"accessToken": "…"` value and copy it.

```sh
curl -s -X POST "<API>/auth/dev-login" \
  -H "Content-Type: application/json" \
  -d '{"persona":"doctor","tier":"basic"}'
```

For convenience, this one-liner stores the token in a shell variable `TOKEN` for the next steps
(macOS/Linux; needs `python3`, which is preinstalled on macOS):

```sh
TOKEN=$(curl -s -X POST "<API>/auth/dev-login" -H "Content-Type: application/json" \
  -d '{"persona":"doctor","tier":"basic"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")
echo "$TOKEN"
```

**A2. Get a patient to share with.** List patients and copy any patient's `id` (a long
`xxxxxxxx-xxxx-…` value):

```sh
curl -s "<API>/patients" -H "Authorization: Bearer $TOKEN"
```

If the list is empty, create one (then copy its `id` from the response):

```sh
curl -s -X POST "<API>/patients" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"displayName":"Sara Nazari"}'
```

Save the patient id:

```sh
PATIENT="<paste-the-patient-id-here>"
```

**A3. Create an aftercare template** (so the share has aftercare). Copy the returned `id`:

```sh
curl -s -X POST "<API>/aftercare-templates" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{
    "name":"Botox aftercare","procedureType":"botox",
    "body":"Stay upright for 4 hours — don'\''t lie down.\nDon'\''t rub or massage the treated area.\nSkip exercise, saunas, and alcohol for 24 hours.\nMild redness is normal and settles within hours."
  }'
```

```sh
TEMPLATE="<paste-the-template-id-here>"
```

**A4. (Optional) Find this patient's before/after photos.** Photos only appear in the share if the
patient already has photo captures from a visit. Check with:

```sh
curl -s "<API>/patients/$PATIENT/last-visit" -H "Authorization: Bearer $TOKEN"
```

In the response, under `visit.media`, copy any `captureId` values. If `media` is empty, that's fine —
skip the `"media"` line in the next step and you'll get a text-only share (still fully testable). To
populate photos with no extra tooling, use **Recipe B** once it ships, or have a developer capture a
photo for this patient in the clinic app.

**A5. Create the share.** This returns the share. Copy the `"token"` value.

```sh
curl -s -X POST "<API>/patient-shares" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{
    "patientId":"'"$PATIENT"'",
    "title":"Your forehead treatment",
    "sections":[
      {"label":"Visit","body":"Forehead Botox performed — 20 units across the forehead lines."},
      {"label":"What to expect","body":"Results settle over the next 7–14 days. Book a review in two weeks if you'\''d like a touch-up."}
    ],
    "media":[{"captureId":"<paste-a-captureId-from-A4>","caption":"Before"},{"captureId":"<another-captureId>","caption":"After"}],
    "aftercare":{"templateId":"'"$TEMPLATE"'"},
    "expiresInDays":30
  }'
```

> Leave out the whole `"media":[…],` line if the patient has no photos.

In the response, the `token` is your link. The patient's page is:

```
<APP>/share/<token>
```

Keep the response handy — you'll also see `"id"` (the share id, used for the revoke test) and
`"publicPath"` (which is exactly `/share/<token>`).

### Recipe B — via the clinic Curate & Share screen (when track ② ships)

This is the real staff path; the screen is being built separately. When available, the flow will be:

1. Sign in to the clinic app at `<APP>` as a doctor or assistant.
2. Open the patient, open the visit, choose **Share** / **Curate & Share**.
3. Tick the before/after photos and report sections to include, pick an **aftercare template**, set an
   optional expiry, and review the **preview** of exactly what the patient will see.
4. Confirm to create the link, then **Copy link**. That copied link is `<APP>/share/<token>`.

Use that link in the scenarios below exactly as you'd use the Recipe-A link.

---

## How to "open on mobile width"

Every scenario says to open the link on mobile width. Any one of these is fine:

- **Easiest:** open the link in Chrome, press `F12` (or `Cmd+Option+I`), then click the
  **device toolbar** icon (`Cmd+Shift+M`) and pick a phone like *iPhone 12* (~390 px wide).
- **Or** just narrow your browser window to roughly a phone width (~390–430 px).
- **Or** open it on a real phone (you'll need the stack reachable from the phone — see the frontend
  README's *HTTPS tunnel for phone testing* note).

---

## 2 · Scenarios

Each scenario: **Setup → Steps → Expected.** Use the link from §1.

### Scenario 1 — The curated report + aftercare render correctly

- **Setup:** A share created per §1 (with photos if you have them, plus the two sections and the
  aftercare template).
- **Steps:**
  1. Open `<APP>/share/<token>` on mobile width.
- **Expected:**
  - A blue header shows the **clinic name**, "Your care summary", a greeting with the patient's first
    name and a 👋, and a line with the **title** and **visit date**.
  - If photos were included: a **"Your before / after"** section shows the photos side-by-side, each
    with its caption (e.g. *Before*, *After*).
  - The report **sections** appear (e.g. *Visit*, *What to expect*) with their text.
  - An **aftercare** block appears with the template's name as a heading and each instruction as a
    green-checkmark checklist item.
  - A footer reads **"Private link for <name> · this is everything shared with you."** and, because we
    set a 30-day expiry, **"Available until <date>."**
  - The whole page is comfortably readable at phone width — nothing is cut off or overlapping.

### Scenario 2 — The page is read-only

- **Setup:** The same open share page from Scenario 1.
- **Steps:**
  1. Scan the whole page top to bottom.
  2. Try to tap/click on the text, the photos, and the aftercare items.
  3. Try to find any button, text box, menu, edit pencil, or "reply" field.
- **Expected:**
  - There is **nothing to fill in or submit** — no text inputs, no buttons that change anything, no
    edit controls, no comment/reply box. (The Q&A composer is a separate Pro payload, not part of this
    Basic report page.)
  - Tapping text or photos does not open an editor. The page only displays information.

### Scenario 3 — Raw clinic internals are NOT reachable

This is the withholding guarantee (AES-403): the patient sees only the curated snapshot.

- **Setup:** When you created the patient in §1, you could include a national ID and internal notes.
  For a stronger test, create one that has them, then create a share for that patient that includes
  **only** the curated sections/aftercare (do not put internal notes into a section):
  ```sh
  curl -s -X POST "<API>/patients" -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"displayName":"Test Withhold","nationalId":"0012345678","notes":"INTERNAL: VIP, comp the next visit"}'
  ```
  Use that patient's id for a fresh share (§1 A5).
- **Steps:**
  1. Open the share page and read every word shown.
  2. In the browser, open **View Source** or DevTools (`F12`) and use **Find** (`Cmd+F`) to search the
     page for: the national ID digits (`0012345678`), the word `INTERNAL`, the word `lot`, and the
     name of any **other** patient you know exists in the clinic.
- **Expected:**
  - **None** of those appear anywhere — not on screen and not in the page's underlying data.
  - The page shows only: clinic name, the patient's display name, the chosen title/date, the curated
    sections you wrote, the chosen photos, and the aftercare text. Nothing else from the clinic file.
  - (Optional deeper check, for a developer: requesting the raw capture file URL
    `<API>/captures/<captureId>/file` **without** a login token returns **401 Unauthorized** — the
    patient surface never exposes the authenticated capture endpoints. Photos are only reachable through
    the share's own `<API>/share/<token>/media/<captureId>` path.)

### Scenario 4 — A revoked link no longer opens

- **Setup:** A working share (note its `id` from the §1 A5 response) that you have confirmed opens.
- **Steps:**
  1. Open the link once to confirm it works.
  2. Revoke it (staff action):
     ```sh
     curl -s -X POST "<API>/patient-shares/<share-id>/revoke" -H "Authorization: Bearer $TOKEN"
     ```
  3. Refresh the patient page (or open `<APP>/share/<token>` again).
- **Expected:**
  - The report is **gone**. The page now shows a lock icon and **"This link is no longer available"**
    with a short message suggesting the patient contact the clinic for a new link.
  - Any photo that was in the report also stops loading (the media link returns nothing).
  - Revocation is **immediate** — no need to wait.

### Scenario 5 — An expired link no longer opens

- **Setup:** Create a share with the **shortest** expiry (1 day) — or, to see expiry now, ask a
  developer to set an expiry in the past. With `expiresInDays:1` you can verify the *"available until"*
  footer today and re-check after the date passes.
- **Steps:**
  1. Create a share with `"expiresInDays":1` (§1 A5) and confirm it opens; note the **"Available
     until …"** date in the footer.
  2. After the expiry date passes (or using a developer-set past expiry), open the link again.
- **Expected:**
  - Before expiry: the page renders normally and the footer shows the **"Available until <date>"**
    line.
  - After expiry: the page shows the same graceful **"This link is no longer available"** screen as a
    revoked link — a patient can't tell *why* it closed (by design, no information is leaked).

### Scenario 6 — An invalid / unknown token is handled gracefully

- **Setup:** None.
- **Steps:**
  1. Open `<APP>/share/this-is-not-a-real-token` on mobile width.
  2. Also try a link with a slightly altered token (change one character of a real token).
- **Expected:**
  - No crash, no blank page, no scary error. You see the same calm **"This link is no longer
    available"** screen with the lock icon and guidance to contact the clinic.
  - A revoked link, an expired link, and a made-up link all look **identical** — the page never reveals
    whether a token "exists".

### Scenario 7 — A connection problem is handled gracefully

- **Setup:** A working share link.
- **Steps:**
  1. In DevTools → **Network**, set throttling to **Offline** (or stop the backend).
  2. Open or refresh the share link.
  3. Restore the connection (set back to **Online** / restart the backend) and tap **Try again**.
- **Expected:**
  - While offline, the page shows a **"Couldn't load your visit"** message with a **Try again** button
    (it does **not** wrongly say the link is unavailable — a network glitch is not a closed link).
  - After restoring the connection and tapping **Try again**, the report loads normally.

---

## 3 · Quick pass/fail checklist

| # | Check | Pass? |
| --- | --- | --- |
| 1 | Header, before/after, sections, aftercare, footer all render on phone width | ☐ |
| 2 | Page is read-only — no inputs, buttons, or edit controls | ☐ |
| 3 | No national ID / internal notes / lots / other patients anywhere | ☐ |
| 4 | Unauthenticated raw capture URL returns 401 (developer check) | ☐ |
| 5 | Revoked link shows "no longer available" immediately | ☐ |
| 6 | Expired link shows "no longer available" | ☐ |
| 7 | Invalid/unknown token shows the same graceful screen (no leak) | ☐ |
| 8 | Offline shows "Couldn't load … Try again"; recovers on retry | ☐ |
