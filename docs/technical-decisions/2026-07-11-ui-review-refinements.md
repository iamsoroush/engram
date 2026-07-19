# UI-review refinements: one 24h clock + one attention count (2026-07-11)

From the 2026-07-10 UI expert review (process doc folded; stories E15/E16), shipped as AES-1007/1008
+ AES-1601–1604 (and AES-1501–1505 for the screens/router slice). Two decisions worth recording:

- **En clock convention = 24-hour.** Clock times across the memory surfaces were split — the visit
  card rendered `Visit: … 17:43` (24h, from the precomputed `session.time`) directly above
  `Updated: 5:43 PM` (12h). Rather than pick 12h, we standardised on **24h everywhere** so fa and en
  share one `Intl` format (only the locale differs — `fa-IR` adds Persian digits + Jalali): one shared
  `shared/lib/datetime.formatTime` now drives every clock label (visit card, timeline, patient-card
  "Latest visit", capture labels). The `Visit:` line derives from the visit timestamp, which also
  localizes its date (`Today` → «امروز», previously an un-localized English literal under fa).
- **One attention count feeds the bell + the Today chip.** The top-bar bell, the Clinical-Memory hero
  chip, and the Today "Needs your input" section were three counters computed from different sources
  (the chip counted a backend needs-input fetch; the bell counted the `/attention` roll-up). They now
  all read the **single** `attentionBadgeCount` (confirm + messages) from `GET /attention`; the chip is
  surface-by-exception (hidden at 0), and the redundant needs-input fetch in `PatientsHome` was removed.
  — **Partially superseded (2026-07-12, AES-1901):** the bell keeps its merged Messages count, but Q&A
  regains its **own** glanceable pending-thread badge on the inbox icon (see [the 2026-07-12 Q&A entry](2026-07-12-qa-owner-testing-gaps.md)).
