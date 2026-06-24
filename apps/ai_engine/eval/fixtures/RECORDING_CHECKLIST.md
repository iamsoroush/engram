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

## 📷 Image caption (photo → text)  →  `caption/`

- [ ] **p01** `p01-product-box.jpg` — a filler/botox **box where the lot/batch is legible**  (expect: lot read; no diagnosis)
- [ ] **p02** `p02-treatment-area.jpg` — a treatment-area photo (e.g. cheek/forehead)  (expect: neutral objective caption, **no diagnosis**)
- [ ] **p03** `p03-injection-site.jpg` — a close-up of an injection site  (expect: objective description only)

## 🎙️ Full-visit synthesis (audio → report)  →  `synthesis/`

- [ ] **s01** `s01-botox-filler-sun.m4a` — *"بیست واحد بوتاکس پیشانی و یک سی‌سی فیلر لب. به بیمار گفتم تا یک هفته از آفتاب مستقیم پرهیز کنه."*
      (expect: treatments = botox + filler; aftercare **botox = conflicts** (sun 1wk vs 3d), **filler = applies**) — *the real-session case that mis-attributed before*
- [ ] **s02** `s02-carry-forward.m4a` — *"بوتاکس پیشانی مثل دفعه قبل، همون مقدار."*  (expect: carriedForward = true)
- [ ] **s03** `s03-own-aftercare.m4a` — *"بوتاکس پیشانی. مراقبت‌ها رو خودم کامل گفتم، محدودیت آفتاب نداره."*  (expect: aftercare = superseded)
- [ ] **s04** `s04-consult-only.m4a` — *"فقط مشاوره بود، امروز تزریقی انجام نشد."*  (expect: treatments = [])

## 🎙️ Patient name (audio → match)  →  `matching/`

- [ ] **m01** `m01-exact-name.m4a` — *"بیمار نگار محمدی."*  (expect: matches the existing نگار محمدی)
- [ ] **m02** `m02-near-miss.m4a` — say a name **slightly wrong** vs an existing patient  (expect: NOT silently auto-assigned — surfaces a candidate)

---

When you've recorded a batch, tell the agent which `tNN/pNN/sNN/mNN` are in — it authors the `.json`
expectations and wires each into its `*_eval.py`, then `run_all.py` scores them.
