# AI eval — capture manifest

These are the **real recordings** the golden-set evals need. The other jobs (report-sections,
patient-memory, treatments, aftercare) run on synthetic text and need **no recordings**.

> **Status (2026-06): 🎙️ audio DONE — 📷 images TODO (deferred).** All 15 audio clips (transcription
> `t01`–`t09`, matching `m01`–`m06`) are recorded, persisted in object storage, and scored. The **5
> caption photos (`p01`–`p05`) are postponed** — drop them in `caption/` later and `push` + `run`; no
> code change. `p01`'s lot is **PS18025**.

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

## 📷 caption/ — photo → text

**Core**

| File | What |
|---|---|
| `p01-product-box.jpg` | a filler/botox **box with the lot/batch legible** (fill `p01`'s `_todo`) |
| `p02-treatment-area.jpg` | a treatment-area photo (cheek / forehead) |
| `p03-injection-site.jpg` | a close-up of an injection site |

**Extended (edge cases)**

| File | What | Why |
|---|---|---|
| `p04-unreadable-lot.jpg` | a box where the **lot is blurry / cut off** | must NOT invent a lot |
| `p05-out-of-context.jpg` | a **non-clinical** photo (screenshot / receipt) | flagged out-of-context |

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

---

The image extension can be `.jpg/.jpeg/.png/.heic`; audio `.m4a/.wav/.mp3/...`. If you rename a file,
rename its `.json` to match. Hand the `_todo` items to the agent and it finalizes the `.json`.
