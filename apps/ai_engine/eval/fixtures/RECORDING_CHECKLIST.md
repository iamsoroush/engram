# Recording checklist — AI eval fixtures

Record each item on your phone in **natural clinical Farsi**, then drop the file at the path shown.
Sibling `.json` (expected facts) gets authored by the agent once the media is in. Tick as you go.

> Tip: keep clips short (5–15s). For "noisy" variants, just record in a normal clinic, not silence.

## 🎙️ Transcription (audio → text)  →  `transcription/`

- [ ] **t01** `t01-botox-forehead.m4a` — say: *"بیست واحد بوتاکس روی پیشانی زدم."*  (expect: بوتاکس · ۲۰ · واحد; no Latin letters)
- [ ] **t02** `t02-filler-brand.m4a` — *"یک سی‌سی ژل ژوویدرم توی گونه چپ."*  (expect: «ژوویدرم» verbatim · سی‌سی)
- [ ] **t03** `t03-spoken-lot.m4a` — *"شماره لات ا ب ث، یک دو سه."* (or read a real box's lot aloud)  (expect: the lot string verbatim)
- [ ] **t04** `t04-correction.m4a` — *"دو سی‌سی... نه اشتباه گفتم، سه سی‌سی."*  (expect: both «۲» and «۳» appear verbatim)
- [ ] **t05** `t05-noisy.m4a` — repeat **t01** fast, with clinic background noise  (expect: still accurate)

**Batch 2 — high-value edge conditions (Part-2 #1a).** The one-speaker core set never reaches a
confusable dose minimal pair, length, code-switch, or a second voice — these do.

- [ ] **t10** `t10-confusable-24-20.m4a` — say clearly: *"بیست و چهار واحد بوتاکس روی پیشانی زدم."*
      (the confusable minimal pair — must hear **۲۴**, never «۲۰»; expect: `numbers:[24]` **and**
      `numbersForbidden:[20]` — the gate fails in **both** directions)
- [ ] **t11** `t11-long-monologue.m4a` — a ~**60s** natural multi-treatment monologue in one take
      (forehead botox, both cheeks filler with a brand + spoken lot, and an aftercare instruction)
      (expect: every dose/brand/area present — completeness under length)
- [ ] **t12** `t12-english.m4a` — a short **English** clinical sentence (e.g. *"Twenty units of botox on
      the forehead, one cc of filler in the left cheek."*)  (expect: `language:"en"`, dose/brand kept)
- [ ] **t13** `t13-latin-brand-lot.m4a` — Farsi with a **Latin brand + spoken lot**: *"یک سی‌سی ژوویدرم،
      شماره لات ... را زدم."* read a real box's Latin lot aloud  (expect: brand + lot verbatim, Farsi native script)
- [ ] **t14** `t14-second-speaker.m4a` — **t01** recorded by a **different speaker**  (expect: same accuracy — not overfit to one voice)

## 📷 Image caption (photo → text)  →  `caption/`

> Sourcing (approved 2026-07-04): **none needs a patient.** p01/p04 are **product boxes** (photograph
> at the partner clinic during the Tehran wave); p02/p03/p06 use a **consenting staff volunteer** (a
> cheek photo, a pen-dot "injection site", a before/after area pair); p05 is any receipt/screenshot.
> One ~10-min phone session covers all six → `stage` → `push` → `run`.

- [ ] **p01** `p01-product-box.jpg` — a filler/botox **box where the lot/batch is legible** (known lot **PS18025**)  (expect: lot read verbatim, `isProductLabel`, no diagnosis)
- [ ] **p02** `p02-treatment-area.jpg` — a treatment-area photo (e.g. cheek/forehead)  (expect: neutral objective caption, **no diagnosis**)
- [ ] **p03** `p03-injection-site.jpg` — a close-up of an injection site (fresh marks/redness)  (expect: objective findings only, **no assessment**)
- [ ] **p04** `p04-unreadable-lot.jpg` — a product box with the lot **blurred / cut off**  (expect: must **NOT invent** a lot — deterministic `forbiddenPattern` gate + groundedNoInvention judge)
- [ ] **p05** `p05-out-of-context.jpg` — a **non-clinical** photo (screenshot / parking receipt)  (expect: `expectOutOfContext` flag set)
- [ ] **p06** `p06-before-after.jpg` — a **before/after** treatment-area pair (same volunteer)  (expect: `pairing.phase` labeled correctly; objective, no diagnosis)

## 🎙️ Full-visit synthesis (audio → report)  →  `synthesis/`

> **Now wired.** A fixture-driven synthesis path in `treatments_eval.py` consumes `synthesis/` (transcribe
> the clip → synthesize → gate treatments + aftercare). Recording any of s01–s04 scores it immediately —
> the "real noisy carried-forward session" lesson made permanent (synthetic text was too clean).

- [ ] **s01** `s01-botox-filler-sun.m4a` — *"بیست واحد بوتاکس پیشانی و یک سی‌سی فیلر لب. به بیمار گفتم تا یک هفته از آفتاب مستقیم پرهیز کنه."*
      (expect: treatments = botox + filler; aftercare **botox = conflicts** (sun 1wk vs 3d), **filler = applies**) — *the real-session case that mis-attributed before*
- [ ] **s02** `s02-carry-forward.m4a` — *"بوتاکس پیشانی مثل دفعه قبل، همون مقدار."*  (expect: carriedForward = true)
- [ ] **s03** `s03-own-aftercare.m4a` — *"بوتاکس پیشانی. مراقبت‌ها رو خودم کامل گفتم، محدودیت آفتاب نداره."*  (expect: aftercare = superseded)
- [ ] **s04** `s04-consult-only.m4a` — *"فقط مشاوره بود، امروز تزریقی انجام نشد."*  (expect: treatments = [])

## 🎙️ Patient name (audio → match)  →  `matching/`

- [ ] **m01** `m01-exact-name.m4a` — *"بیمار نگار محمدی."*  (expect: matches the existing نگار محمدی)
- [ ] **m02** `m02-near-miss.m4a` — say a name **slightly wrong** vs an existing patient  (expect: NOT silently auto-assigned — surfaces a candidate)

**Batch 2 — extraction faithfulness (Part-2 #9).**

- [ ] **m07** `m07-name-mid-dictation.m4a` — name spoken **mid-sentence**, not as the lead phrase:
      *"برای خانم محمدی امروز بیست واحد بوتاکس زدم."*  (expect: «محمدی» extracted, `basis` implicit)
- [ ] **m08** `m08-two-similar.m4a` — two **similar-sounding existing** patients, say only ONE:
      *"خانم محمودی امروز اومد، نه خانم محمدی."*  (expect: faithful «محمودی»; **not** auto-corrected to «محمدی»)
- [ ] **m09** `m09-near-miss-noisy.m4a` — re-record **m02** (the «نگار معمری» near-miss) **with clinic noise**  (expect: near-miss surname still NOT snapped to «محمدی»)

**Batch 3 — incident cluster (identity-correction / detach). Prefer the owner's OWN prod/dev clips
where they exist (approved reuse — his voice, no patient data): production session
`f3ee7cd5-3aa4-44cc-8d04-2897a3258b34` (audio 4 is the `درستش` correction) and dev sessions
`f681a5fb…` / `8b7ea6f8…`, from MinIO bucket `engram-captures` via `ssh engram`. Expectations for
these are already committed in `expectations/matching/i0*.json`.**

- [ ] **i01** `i01-correction-directive.m4a` — the prod audio-4 clip:
      *"اسم بیمار سروش معاضد هست درستش."*  (expect: `basis` **explicit**, «معاضد» extracted, NOT out_of_context)
- [ ] **i02** `i02-correction-only-in-context.m4a` — a correction-ONLY clip (no clinical content):
      *"اشتباهه، بیمار سارا هست."*  (expect: `basis` explicit, **out_of_context false** — an instruction is visit content)
- [ ] **i03** `i03-self-correction.m4a` — in-clip self-correction:
      *"برای سارا... نه، مریم."*  (expect: «مریم» extracted, «سارا» absent, `basis` explicit — knownGap on flash)
- [ ] **i04** `i04-detach.m4a` — negation with NO replacement name:
      *"این پرونده مال ایشون نیست."*  (expect: `intents.detach.present` true, no name extracted)

## 🎙️ Q&A reply voice-edit (voice note → revise/replace)  →  `qa_revise/`

> **Now wired.** `qa_revise_eval.py` consumes `qa_revise/`: each clip is the doctor's spoken edit of a
> **fixed `currentDraft`** (in the sibling `.json`); the eval runs the real job and gates the
> revise-vs-replace classification + numbers-preserved + escalation-survives + native script. The
> harness is green on parser + gate self-tests + judge smoke until clips land. **Record on a phone,
> natural clinical Farsi** (never auto-generated). The base draft to edit is:
> «سلام سارا، ورم خفیف بعد از بیست واحد بوتاکس در روزهای اول طبیعی است. لطفاً کمپرس یخ بگذارید. اگر بدتر شد با کلینیک تماس بگیرید. — دکتر دمو»

- [ ] **r01** `r01-warmer-shorter.m4a` — *«یکم گرم‌تر و کوتاه‌ترش کن»*  (expect: mode=revise; dose «۲۰» + clinic-contact kept)
- [ ] **r02** `r02-remove-ice.m4a` — *«اون قسمت کمپرس یخ رو حذف کن»*  (expect: revise; «کمپرس یخ» gone, everything else intact)
- [ ] **r03** `r03-add-sun.m4a` — *«اضافه کن که تا یک هفته آفتاب نره»*  (expect: revise; sun+«یک هفته» added, nothing invented)
- [ ] **r04** `r04-replace.m4a` — *«کلاً اینو ول کن، بنویس: سلام، لطفاً فردا برای معاینه به کلینیک بیاید. — دکتر دمو»*  (expect: mode=replace; old draft gone)
- [ ] **r05** `r05-reassure.m4a` — *«بگو نگران نباشه»*  (expect: revise; reassurance folded in, the **clinic-contact tail survives**)
- [ ] **r06** `r06-override-aftercare.m4a` — *«بگو سونا مشکلی نداره»* (over a draft variant that says avoid sauna)  (expect: follows the doctor)
- [ ] **r07** `r07-english-note-fa-draft.m4a` — English note *"make it friendlier"* over the fa draft  (expect: reply stays **fa**, no Latin)
- [ ] **r08** `r08-dictate-dose.m4a` — *«بگو بیست واحد بوتاکس بوده»*  (expect: «بیست»/«۲۰» present)
- [ ] **r09** `r09-signoff.m4a` — any revise note  (expect: the «— دکتر دمو» sign-off kept)
- [ ] **r10** `r10-noisy-warmer.m4a` — re-record **r01** with clinic background noise  (expect: same as r01 — robustness)

---

When you've recorded a batch, tell the agent which `tNN/pNN/sNN/mNN/rNN` are in — it authors the `.json`
expectations and wires each into its `*_eval.py`, then `run_all.py` scores them.
