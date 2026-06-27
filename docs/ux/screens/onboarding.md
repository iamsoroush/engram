# First-run Onboarding (Guided First Capture)

## Purpose

Capture-first is unfamiliar, so a freshly signed-up founder gets a short, skippable guided
"capture your first visit" the first time they enter the app — so they aren't lost.

## When it shows

- Only after **self-serve sign-up** (a brand-new founder). It is **not** shown on ordinary login.
- Triggered by a per-user `localStorage` flag set at registration (`markOnboardingPending`); cleared
  when the tour is finished or skipped. Survives a reload until then.

## Format

A short, animated, **show-don't-tell** tour (`OnboardingOverlay`) layered on the **live** Active
Session screen. It mixes two step kinds:

- **Modal steps** — a centered card (welcome by name → "it organizes itself" → finish).
- **A spotlight step** — dims the screen around the **real** capture bar, pulses a highlight ring on
  it, and floats a coachmark above. The bar stays clickable through the cut-out.
- **Live first capture** — on the spotlight step the founder taps a real capture action; the overlay
  hides while the capture sheet is open and **auto-advances** once the first capture lands (or they
  can choose *I'll try later*). This teaches capture-first by doing it.

**Tier-accurate content** (Basic is zero-AI — capture + deterministic organize only):

- **Basic:** the third step is "Saved & organized" (captures saved on-device, synced, grouped into
  the visit — **no AI report/summary claims**), followed by a **"Want AI on top?"** upsell step with a
  **See the Pro plan** link to the [Plan screen](plan.md).
- **Pro:** the third step is "It organizes itself" (AI report + summary), followed by a **"Your Pro
  tools"** step (patient memory + post-session Q&A).

Final step: **Start capturing**, plus (for owner/admin) an **Invite your team** link to the
[Team screen](team.md). **Skip the tour** is available throughout. Rendered in the founder's app
language (fa/en + RTL) from the tenant's `app_language`.

**Replay:** any user can re-open the guide via **Replay guide** in the account menu (re-arms the flag
and returns to Active Session). The replayed tour reflects the clinic's **current** tier.

## Main Components

- `OnboardingOverlay` (modal + spotlight rendering, `useTargetRect`), `onboardingState` (flag helpers).
- Anchored to the capture bar via `data-onboarding="capture-bar"` in `CaptureActions`.

## Known Gaps

- Client-side flag only (training UX, not security); not synced across devices.
