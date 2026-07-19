# Memory-surface refinements from owner testing (2026-07-12)

Three refinements to the Clinical-Memory surfaces (stories AES-1607–1610; as-built in
`docs/ux/screens/patients.md` and `capture.md`):

- **"Today" tab → "Recent", restructured into time buckets.** The day-scoped Today tab only ever showed
  the current calendar day. It is now **Recent** (tab value `recent`): a recent-activity list bucketed by
  recency into **Active visit / Today / Yesterday / This week**, newest first, empty buckets omitted;
  older-than-a-week is a quiet link into Patients (the finder is the deep-search surface). The separate
  "Needs your input" preview section is gone — a needs-input visit stays actionable **inline** (amber
  card + focused action) in its time bucket, and the aggregate lives only in the hero chip + Attention
  tab. **Refines AES-1007**: the Today preview's `See all N in Attention` pointer no longer exists.
- **Search scoped to the Patients tab.** The always-visible Clinical-Memory header search bar is removed
  (the top-bar [finder](../ux/screens/finder.md) is the app-wide retrieval surface). The Patients tab gains
  a **lighter local roster filter** that filters the loaded list live and does **not** search content;
  the old in-tab deterministic/Persian-aware "smart match" block was dropped (that depth is the finder's
  job now). Recent + Attention rely on the finder.
- **Guided attention review.** A **grouped** Close-the-day card (≥2 confirmations) now **names its
  target** — `Visit {patient} · {time}` / `Unassigned visit · {time}`, never a bare "This visit" — and
  opening it arms a **guided review state** on the capture screen: a progress banner (`N to confirm`,
  next/prev) that scrolls to and highlights each confirmation in place, dismissing when all resolve. It
  reuses the existing per-source resolvers (conflict band → AI-created-patient panel → dose rows) — pure
  orientation, no new resolver, no changed confirm semantics. **Refines AES-1008.**
