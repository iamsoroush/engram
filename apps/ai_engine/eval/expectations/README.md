# AI eval — capture manifest

These are the **real recordings** the golden-set evals need. Report-sections and patient-memory run on
synthetic text and need no recordings; **full-visit synthesis** now has a fixture-driven path too (see
`synthesis/` below) that scores `treatments` + `aftercare` on real clips.

> **Status: 🎙️ audio batch-1 DONE — batch-2 + 📷 images TODO.** The 15 batch-1 audio clips (transcription
> `t01`–`t09`, matching `m01`–`m06`) are recorded, in object storage, and scored. **Outstanding** (drop
> them in the matching folder later, then `push` + `run` — no code change): the caption photos
> **`p01`–`p06`** (`p01`'s lot is **PS18025**), the transcription edge batch **`t10`–`t14`**, the
> full-visit synthesis clips **`s01`–`s04`**, and matching **`m07`–`m09`**.

Record each on your phone in **natural clinical Farsi**, name it exactly, and drop it in the matching
folder of your staging dir (created by `scripts/eval-fixtures.sh stage`, default
`~/notari-eval-fixtures/`). A sibling `<case>.json` (the expected facts) is already there as a template;
a few have a `_todo` you (or the agent) fill in after recording. Then:

```sh
scripts/eval-fixtures.sh push     # → object storage (never committed to git)
scripts/eval-fixtures.sh run      # score the suite against them
```

> Media live in the `notari-eval-fixtures` object-storage bucket, **not in git**. Keep clips short
> (5–15s). For "noisy", just record in a normal clinic, not silence.

> Each list has **core** (record these first) + **extended edge cases** (the high-value safety
> scenarios — allergy, negation, laterality, decimals, ambiguous names). Do the core set, then as many
> edge cases as you can.

## 🎙️ transcription/ — audio → text

**Core**

| File | Say |
|---|---|
| `t01-botox-forehead.m4a` | «بیست واحد بوتاکس روی پیشانی زدم.» |
| `t02-filler-brand.m4a` | «یک سی‌سی ژل ژوویدرم توی گونه چپ.» |
| `t03-spoken-lot.m4a` | «شماره لات ...» — read a real box's lot aloud (fill `t03`'s `_todo`) |
| `t04-correction.m4a` | «دو سی‌سی... نه اشتباه گفتم، سه سی‌سی.» |
| `t05-noisy.m4a` | repeat **t01**, faster, with clinic background noise |

**Extended (edge cases)**

| File | Say | Why |
|---|---|---|
| `t06-allergy.m4a` | «بیمار به لیدوکائین حساسیت داره، حتماً ثبت بشه.» | allergen captured verbatim |
| `t07-negation.m4a` | «امروز تزریق انجام نشد، فقط معاینه بود.» | **negation** not dropped/flipped |
| `t08-decimal.m4a` | «یک و نیم سی‌سی ژل توی لب.» | half/decimal dose |
| `t09-laterality.m4a` | «فقط گونه راست رو تزریق کردم، سمت چپ هیچی نزدم.» | left/right not swapped |

**Batch 2 (Part-2 #1a — record these next)**

| File | Say | Why |
|---|---|---|
| `t10-confusable-24-20.m4a` | «بیست و چهار واحد بوتاکس روی پیشانی زدم.» | confusable dose **minimal pair** — must hear ۲۴, never ۲۰ (gated both ways: `numbers:[24]`, `numbersForbidden:[20]`) |
| `t11-long-monologue.m4a` | ~60s multi-treatment monologue (botox + both-cheek filler w/ brand + spoken lot + aftercare) | completeness **under length** |
| `t12-english.m4a` | «Twenty units of botox on the forehead, one cc of filler in the left cheek.» | **English / code-switch** (`language:"en"`) |
| `t13-latin-brand-lot.m4a` | «یک سی‌سی ژوویدرم، شماره لات ... را زدم.» (read a real Latin lot aloud) | Latin brand + lot verbatim, Farsi stays native |
| `t14-second-speaker.m4a` | repeat **t01** in a **different voice** | not overfit to one speaker |

## 📷 caption/ — photo → text

> Sourcing (approved 2026-07-04): none needs a patient — p01/p04 are **product boxes**, p02/p03/p06 a
> **consenting staff volunteer**, p05 any receipt/screenshot. One ~10-min phone session covers all six.

**Core**

| File | What |
|---|---|
| `p01-product-box.jpg` | a filler/botox **box with the lot/batch legible** (fill `p01`'s `_todo`) |
| `p02-treatment-area.jpg` | a treatment-area photo (cheek / forehead) |
| `p03-injection-site.jpg` | a close-up of an injection site |

**Extended (edge cases)**

| File | What | Why |
|---|---|---|
| `p04-unreadable-lot.jpg` | a box where the **lot is blurry / cut off** | must NOT invent a lot (`forbiddenPattern` gate) |
| `p05-out-of-context.jpg` | a **non-clinical** photo (screenshot / receipt) | flagged out-of-context |
| `p06-before-after.jpg` | a **before/after** treatment-area pair (same volunteer) | `pairing.phase` labeled correctly |

## 🎙️ synthesis/ — full-visit audio → report (treatments + aftercare)

Now consumed by the fixture-driven path in `treatments_eval.py` (transcribe → synthesize → gate). Drop a
clip and it scores end-to-end — the real noisy carried-forward session synthetic text can't reproduce.

| File | Say | Expect |
|---|---|---|
| `s01-botox-filler-sun.m4a` | «بیست واحد بوتاکس پیشانی و یک سی‌سی فیلر لب. به بیمار گفتم تا یک هفته از آفتاب مستقیم پرهیز کنه.» | treatments = botox + filler; aftercare **botox = conflicts** (sun 1wk vs 3d), **filler = applies** |
| `s02-carry-forward.m4a` | «بوتاکس پیشانی مثل دفعه قبل، همون مقدار.» | `carriedForward = true` |
| `s03-own-aftercare.m4a` | «بوتاکس پیشانی. مراقبت‌ها رو خودم کامل گفتم، محدودیت آفتاب نداره.» | aftercare = superseded |
| `s04-consult-only.m4a` | «فقط مشاوره بود، امروز تزریقی انجام نشد.» | treatments = [] |

## 🎙️ matching/ — spoken patient name → extraction

**Core**

| File | Say |
|---|---|
| `m01-exact-name.m4a` | «بیمار نگار محمدی.» (use a real existing patient's name) |
| `m02-near-miss.m4a` | a name **slightly wrong** vs an existing patient (fill `m02`'s `_todo`) |

**Extended (edge cases)**

| File | Say | Why |
|---|---|---|
| `m03-first-name.m4a` | «بیمار سارا.» | partial name → surface, don't auto-assign |
| `m04-two-patients.m4a` | «بعد از خانم احمدی، نوبت خانم محمدیه.» | **ambiguous** → don't auto-assign (fill `_todo`) |
| `m05-reassign.m4a` | «بیمار رو عوض کن به نگار محمدی.» | explicit reassignment (basis=explicit) |
| `m06-national-id.m4a` | «کد ملی صفر صفر یک دو سه ...» digit-by-digit | ID normalized to digits (fill `_todo`) |

**Batch 2 (Part-2 #9 — extraction faithfulness)**

| File | Say | Why |
|---|---|---|
| `m07-name-mid-dictation.m4a` | «برای خانم محمدی امروز بیست واحد بوتاکس زدم.» | name spoken **mid-sentence** → still extracted, `basis` implicit |
| `m08-two-similar.m4a` | «خانم محمودی امروز اومد، نه خانم محمدی.» | two **similar-sounding existing** patients → faithful «محمودی», not corrected to «محمدی» |
| `m09-near-miss-noisy.m4a` | re-record **m02** («نگار معمری») with clinic noise | near-miss surname still not snapped to «محمدی» under noise |

## 🎙️ qa_revise/ — Q&A reply voice-edit (voice note → revise/replace)

Consumed by `qa_revise_eval.py`. Each clip is the doctor's spoken edit of a **fixed `currentDraft`** (in
the `.json`); the eval gates the revise-vs-replace classification + numbers-preserved + escalation-survives
+ native script. Base draft to edit: «سلام سارا، ورم خفیف بعد از بیست واحد بوتاکس در روزهای اول طبیعی است.
لطفاً کمپرس یخ بگذارید. اگر بدتر شد با کلینیک تماس بگیرید. — دکتر دمو».

| File | Say | Expect |
|---|---|---|
| `r01-warmer-shorter.m4a` | «یکم گرم‌تر و کوتاه‌ترش کن» | mode=revise; dose «۲۰» + clinic-contact kept |
| `r02-remove-ice.m4a` | «اون قسمت کمپرس یخ رو حذف کن» | revise; «کمپرس یخ» gone, rest intact |
| `r03-add-sun.m4a` | «اضافه کن که تا یک هفته آفتاب نره» | revise; sun+«یک هفته» added |
| `r04-replace.m4a` | «کلاً اینو ول کن، بنویس: سلام، لطفاً فردا برای معاینه به کلینیک بیاید. — دکتر دمو» | mode=replace; old draft gone |
| `r05-reassure.m4a` | «بگو نگران نباشه» | revise; **clinic-contact tail survives** |
| `r06-override-aftercare.m4a` | «بگو سونا مشکلی نداره» (draft variant says avoid sauna) | follows the doctor |
| `r07-english-note-fa-draft.m4a` | English *"make it friendlier"* | reply stays **fa**, no Latin |
| `r08-dictate-dose.m4a` | «بگو بیست واحد بوتاکس بوده» | «بیست»/«۲۰» present |
| `r09-signoff.m4a` | any revise note | «— دکتر دمو» sign-off kept |
| `r10-noisy-warmer.m4a` | re-record r01 with clinic noise | same as r01 (robustness) |

---

The image extension can be `.jpg/.jpeg/.png/.heic`; audio `.m4a/.wav/.mp3/...`. If you rename a file,
rename its `.json` to match. Hand the `_todo` items to the agent and it finalizes the `.json`.
