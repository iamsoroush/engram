# Pro pre-visit brief (Job-4 `sessionContext` extension)

**Fold destination:** `docs/ux/screens/capture.md` (session context card section) +
`docs/ai_engine/processing.md` (the patient-memory / Job-4 section) when built.

The un-built slice of the session patient-context work. **Already shipped** (documented in
[capture.md](../ux/screens/capture.md)): the deterministic context card in both tiers (last-visit
digest + cross-visit photo strip + key facts), the Pro lineup card layered on top, the
timeline round-trip ("Back to this visit"), and deterministic cross-visit safety flags. **This doc
covers what remains:** the assistant-grade **pre-visit brief** — a richer Job-4 synthesis surfaced
at the session.

## The idea

Pro has every prior capture, the structured `treatments[]` store, the synthesized reports, the
photos, and AI. The context window should feel like **a great human clinic assistant's pre-visit
brief** — one who reads the whole record, **predicts what matters for THIS patient at THIS
moment**, and surfaces just that, warmly and scannably. The intelligence is in the
**curation/prediction** (what's worth showing) and in **using everything, including the photos** —
never in clinical advice. The blocks below are the assistant's *palette*: it **chooses, orders,
and phrases what's salient** per patient (it won't show all of them every time):

| Block | What it shows | Source |
|---|---|---|
| **Brief / "story so far"** | ≤2-sentence who-they-are + journey + goals | Job 4 patient-memory summary (lineup card) — *shipped as the lineup card* |
| **Since last visit** | what changed since the last visit; elapsed time | Job 4 delta line |
| **Last-visit recap** | AI summary of the last session + what was done | last session's synthesis summary + `treatments[]` |
| **Treatment recall** | "what we've used": product · dose · area · lot · interval, across visits | **deterministic query** over `extracted_metadata.treatments` (no new AI) |
| **Before/after hero** | the hero photo + a journey before/after | Job 4 `heroCaptureId` + Job 2 pairing |
| **Suggested focus / "due for"** | what this visit is likely about; treatments due (e.g. "botox 10 wks ago, usually 12") | **NEW** — the brief itself |
| **Open items** | unconfirmed carried-forward dose, pending patient Q&A, missing consent | deterministic (needs-input / Q&A / flags) |

## Design decisions (agreed with the owner)

- **The pre-visit brief IS the centerpiece — a richer Job-4 synthesis** (`sessionContext`
  extension), not a due-for line. An assistant-grade pass that **predicts + curates**: the salient
  story, the most telling before/after, **visible progress read from the photos**, the patient's
  cadence (*due-for as a fact*), the doctor's own prior plan, and what needs attention. It may be
  **multimodal** (Job-2 captions/pairing + a vision read of progress where it adds value).
  Deterministic pieces stay deterministic (due-for intervals, open items, treatment recall); the
  **curation + phrasing is the AI**.
- **Extend Job 4** (add a `sessionContext` field to the memory projection), not a separate job —
  it shares Job 4's context + triggers. Schedule with or right after Job-4 work.
- **Guardrails — curate freely, never prescribe.** No clinical recommendation ever (no "you
  should", no suggested treatment/dose, no diagnosis, no "indicated/due" as a directive). Visual
  statements stay observational ("visible fullness up in the left cheek vs the Jan photo"), never
  diagnostic. Per-clinic suppressible.
- Read-triggered like Job 4 (no cost on un-opened patients); deterministic fallback (gateway-less
  Pro shows the deterministic digest + treatment recall, never blank).
- Everything **assistive + cited** (tap a claim → the source visit/capture); never authoritative.
- Vertical-agnostic via the domain descriptor (therapy/derma reuse the window, different content).
- New AI job/extension ⇒ **eval-gated**: consult the owner on golden-set scenarios first
  (CLAUDE.md §4), same scrutiny as extraction.

## Open questions

- Inline "peek" expansions on the card before a full timeline navigation, or full timeline only?
