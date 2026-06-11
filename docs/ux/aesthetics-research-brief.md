# Aesthetics — Comparable-Product Research Brief (Phase 0)

> Deliverable 1 of the aesthetics design track ([foundation §5–6](redesign-foundation.md)). A
> **lighter pass** ([foundation §5](redesign-foundation.md): the §3 feature set already frames it):
> med-spa / aesthetics tools + the behavioral reality of small Persian-speaking clinics. Feeds the
> journeys ([aesthetics-journeys.md](aesthetics-journeys.md)), stories
> ([aesthetics-stories.md](aesthetics-stories.md)), and spec
> ([redesign-aesthetics.md](redesign-aesthetics.md)). Candidate extensions surfaced here are flagged
> `⊕` and collected for human review in [redesign-aesthetics.md §10](redesign-aesthetics.md) — none
> replace or drop an agreed feature.

## 1. Landscape snapshot

The med-spa software market splits into three camps: **clinical EMRs** built for
documentation/compliance (Aesthetic Record, Nextech, Symplast, AestheticsPro/PatientNow, Pabau),
**business-management / front-desk platforms** that lead with booking + payments and treat charting as
secondary (Boulevard, Mangomint, Zenoti), and **single-purpose photo apps** (RxPhoto). Nearly all are
Western, English-first, HIPAA-framed, all-in-one, and priced $175–$400+/month — heavy suites a small
Iranian clinic neither needs nor can adopt. None target Persian-language capture-first workflows, and
the incumbents' "just start charting" experience is gated behind setup, templates, and structured-data
entry. That gap — **fast, mobile, Persian-first capture before any structure** — is the opening.

| Product | Center of gravity | Before/after photos | Consent | Injectable/lot tracking | Patient comms | Mobile capture | Position |
|---|---|---|---|---|---|---|---|
| **Aesthetic Record** | EMR | Strong (SmartMatch align, video) | e-sign forms | Inventory + UPC scan, expiry | 2-way text, portal | iOS app | Category leader |
| **Symplast** | Mobile EMR | Good, in-app media | Custom forms | Charting-level | HIPAA 2-way msg + patient app | Mobile-first | Plastics/med-spa |
| **PatientNow + RxPhoto** | PM + CRM/marketing | RxPhoto: ghost-overlay, standardized | e-forms | EMR-level | Heavy CRM/marketing | RxPhoto app | All-in-one, post-merger clutter |
| **Nextech** | EMR + PM | Overlay + markup | Forms | Implants/supplies inventory | Portal | Limited | Derm/plastics, enterprise |
| **Boulevard** | Booking/payments | Upload to profile | Collects in profile | No (retail POS only) | Text, memberships | App | Front-desk/business |
| **Pabau** | Medical-first PM | Yes | Built-in consent | Inventory mgmt | SMS/email | Yes | Multi-location clinical |
| **Mangomint / Zenoti** | Booking/biz ops | Light | Forms | Retail/inventory | Strong msg/automation | Yes | Beauty-led / enterprise |

## 2. Patterns worth adopting

- **Ghost-overlay before/after capture** — overlay the prior baseline on-screen while shooting the
  "after" so angle/framing/lighting match (RxPhoto ships 450+ on-screen guides). Without it,
  comparisons vary by angle/light and lose credibility. ([RxPhoto](https://rxphoto.com/platform/clinical-photography))
- **Side-by-side + slider compare** generated instantly from paired photos — the core "show the patient
  their progress" moment. ([Aesthetic Record](https://www.aestheticrecord.com/complete-emr/))
- **Keep clinical photos out of the camera roll** — clinical apps store images encrypted, out of the
  device gallery: a privacy *and* clutter win. ([Moxie](https://www.joinmoxie.com/post/nurse-aesthetic-pictures-take-better-aesthetic-before-and-after-photos-with-our-7-tips))
- **Inventory with UPC/lot scan + expiry** — scan units in, track usage/transfer/expiry per unit;
  enables "what's on the shelf" and **recall lookups**. ([Aesthetic Record](https://www.aestheticrecord.com/complete-emr/))
- **E-sign consent attached to the chart, pre-filled before the visit** — patients complete
  consents/questionnaires in advance, auto-linked to the procedure. ([Aesthetic Record](https://www.aestheticrecord.com/complete-emr/))
- **Two-way in-app messaging timeline** — one searchable thread per patient instead of scattered DMs;
  the central fix incumbents pitch for the comms mess. ([Doximity/opmed](https://opmed.doximity.com/articles/navigating-communication-challenges-in-aesthetic-medicine))
- **Provider-customizable charting templates/macros** to cut documentation time — but a known source of
  bloat (see §4). ([Nextech](https://www.nextech.com/plastic-surgery/ehr-system))

## 3. The Apple-Notes reality (where Memara's tiers land)

Today the un-tooled clinic runs on **Apple Notes + camera roll + WhatsApp/Instagram DMs + a
spreadsheet**. Failure modes, mapped to the tier that resolves them:

- **Before/after photos lost in a 10,000-image camera roll**, unpaired, unlabeled, mixed with personal
  photos → **Basic kills it**: patient-filed capture + before/after pairing + ghost-overlay.
- **"What did I inject last time — product, units, lot?"** lives in a note or someone's memory →
  **Basic kills the lookup** (per-patient longitudinal log + lot field); **Pro adds** auto-extraction
  from voice/notes + cross-visit synthesis.
- **The WhatsApp question deluge** ("is this swelling normal?") scattered across DMs/SMS/IG; messages
  slip through (a real one-star-review failure mode). → **Basic** centralizes the thread + shareable
  aftercare; **Pro adds** post-session Q&A answered from the actual session record.
- **Duplicate / mismatched patient records** — one person, several spellings; acute for **Persian
  names** (no one-to-one Latin mapping → one Farsi name → many spellings), so a clerk who can't find a
  record creates a new one and splits the history. ([arXiv 2502.20047](https://arxiv.org/pdf/2502.20047),
  [NCBI PMC9513649](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9513649/)) → **Basic** Persian-first
  normalized search + **duplicate guard**; **Pro** strengthens fuzzy matching/merge.
- **Consent** as a paper form or unrecorded verbal → **Basic** can attach/store it (deterministic).
- **Inconsistent docs, per-provider workflows, a spreadsheet nobody updates** — the "doesn't scale"
  wall. ([Edvak](https://edvak.com/blogs/converting-medspa-charts-to-emr/),
  [PatientNow](https://www.patientnow.com/resources/blog/overcoming-challenges-in-transitioning-from-paper-records-to-emr/))
  → **Basic** gives structure-by-default without forcing data entry.

## 4. Gaps / where incumbents are heavy

- **Setup before value**: EMRs require templates, structured fields, and migration before you can
  usefully chart; staff resistance and migration pain are repeatedly cited.
  ([PatientNow](https://www.patientnow.com/resources/blog/overcoming-challenges-in-transitioning-from-paper-records-to-emr/))
- **Suite bloat / merged-product clutter**: PatientNow (ex-Envision) merged architectures, leaving
  clinical tools "buried under heavy marketing dashboards." ([mdware](https://mdware.com/top-5-aesthetic-clinic-software-solutions-2026-guide/))
- **Business-ops-first tools under-serve clinical capture**: Boulevard/Mangomint lead with
  booking/payments; charting is shallow, lot/injectable tracking essentially absent.
  ([Boulevard](https://www.joinblvd.com/medical-spa-software))
- **English/US/HIPAA-framed, desktop-leaning**, $175–$400+/mo — wrong fit for a small Iranian med-spa.
- **Capture friction**: photos, consent, and treatment notes are separate structured steps, not one
  fast flow — exactly where reception/injector friction lives.

## 5. Where Memara wins

**Thesis:** Memara is **capture-first** — capture never blocks reception or the injector; structure and
intelligence are derived *after*, not demanded up front.

- **Apple-Notes-simple Basic** that genuinely beats Notes at the four jobs clinics misuse it for
  (filing · photo pairing · treatment log · search) — *zero AI, deterministic, fast, offline*.
- **AI as the Pro upsell, not the price of entry**: transcription, structured reports, matching,
  cross-visit synthesis, lot tracking, post-session Q&A.
- **Persian-first**: name normalization/search + Persian UX — something no incumbent does.
- **Longitudinal memory**: "what we did last time" as a first-class, always-present surface.
- **Post-session Q&A grounded in the real session record** — directly attacks the WhatsApp deluge.

**Honest concessions (not competing in v1):** incumbents are genuinely ahead on **legally-robust
e-consent**, **deep inventory/POS**, **payments/financing**, **insurance/billing**, and
**marketing/CRM automation**. Memara should do *enough* consent + lot capture to be useful, and not try
to out-suite the suites.

## 6. Implications for the design

- **ADOPT — ghost-overlay before/after capture** + instant slider/side-by-side compare. The single
  highest-credibility, highest-delight feature; table stakes, done well. *(Basic, deterministic.)*
- **ADOPT — keep clinical photos out of the camera roll**, filed straight to the patient. Privacy +
  kills the "lost photos" pain. *(Basic.)*
- **ADOPT — one searchable per-patient comms/timeline** consolidating the DM mess. *(Basic thread;
  Pro Q&A drafting.)*
- **ADOPT — Persian-first normalized search + duplicate guard** in Basic. Prevents the record split
  unique to this market.
- **ADAPT — "what did we do last time" longitudinal log** as a glanceable patient header, with a
  structured **lot/product/units** field even in Basic (deterministic version is cheap; Pro
  auto-extracts).
- **⊕ consent capture, lightweight** (attach/sign + store) — useful without competing on compliance
  depth. *Candidate; legally sensitive — flag.*
- **⊕ face-map injection logging** (tap a face diagram → site/product/units/lot) — turns the treatment
  log into structured, recall-ready data; strong Pro hook. *Candidate.*
- **⊕ lot/expiry scan + recall lookup** ("find every patient who got lot X") — real safety need
  (counterfeit-Botox lot recalls are a live FDA issue). *Candidate.* ([FDA](https://www.fda.gov/drugs/drug-safety-and-availability/counterfeit-version-botox-found-multiple-states))
- **⊕ pre-visit consent/questionnaire link** auto-attached to the session — proven incumbent pattern,
  low effort, removes in-clinic friction. *Candidate.*
- **GUARDRAIL — never require setup/templates before first capture.** The whole wedge is "just start
  capturing"; structure is derived later.

## Research caveats

1. **Injector first-person voice is thin.** Reddit/forum threads (r/Injectables etc.) didn't surface
   usable public results; §3 behavioral claims lean on practice-management blogs, a Doximity clinician
   account, and academic transliteration/duplicate-record papers — solid but secondary. A manual Reddit
   pass would strengthen §3 if needed.
2. **Aesthetic Record's per-unit lot/expiry/UPC-scan recall** came from its EMR-features page + search
   snippets, not deeply verified on a live fetch — treat the recall-lookup capability as "advertised."

## Sources

[Aesthetic Record — Complete EMR](https://www.aestheticrecord.com/complete-emr/) ·
[Symplast](https://symplast.com/) · [Symplast media](https://symplast.com/media-management/) ·
[PatientNow](https://www.patientnow.com/medical-aesthetics/) ·
[RxPhoto clinical photography](https://rxphoto.com/platform/clinical-photography) ·
[Nextech plastic surgery EHR](https://www.nextech.com/plastic-surgery/ehr-system) ·
[Boulevard med-spa software](https://www.joinblvd.com/medical-spa-software) ·
[Pabau — Mangomint alternatives](https://pabau.com/blog/mangomint-alternatives) ·
[mdware — top aesthetic software 2026](https://mdware.com/top-5-aesthetic-clinic-software-solutions-2026-guide/) ·
[Doximity/opmed — comms challenges](https://opmed.doximity.com/articles/navigating-communication-challenges-in-aesthetic-medicine) ·
[Edvak — converting charts to EMR](https://edvak.com/blogs/converting-medspa-charts-to-emr/) ·
[PatientNow — paper-to-EMR](https://www.patientnow.com/resources/blog/overcoming-challenges-in-transitioning-from-paper-records-to-emr/) ·
[Moxie — before/after photo tips](https://www.joinmoxie.com/post/nurse-aesthetic-pictures-take-better-aesthetic-before-and-after-photos-with-our-7-tips) ·
[FDA — counterfeit Botox / lot recall](https://www.fda.gov/drugs/drug-safety-and-availability/counterfeit-version-botox-found-multiple-states) ·
[arXiv 2502.20047 — Persian transliteration](https://arxiv.org/pdf/2502.20047) ·
[NCBI PMC9513649 — duplicate EMR records](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9513649/)
