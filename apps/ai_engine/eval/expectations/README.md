# AI eval — capture manifest

These are the **real recordings** the golden-set evals need. The other jobs (report-sections,
patient-memory, treatments, aftercare) run on synthetic text and need **no recordings**.

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

## 🎙️ transcription/ — audio → text  (5)

| File | Say |
|---|---|
| `t01-botox-forehead.m4a` | «بیست واحد بوتاکس روی پیشانی زدم.» |
| `t02-filler-brand.m4a` | «یک سی‌سی ژل ژوویدرم توی گونه چپ.» |
| `t03-spoken-lot.m4a` | «شماره لات ...» — read a real box's lot aloud (then fill `t03`'s `_todo`) |
| `t04-correction.m4a` | «دو سی‌سی... نه اشتباه گفتم، سه سی‌سی.» |
| `t05-noisy.m4a` | repeat **t01**, faster, with clinic background noise |

## 📷 caption/ — photo → text  (3)

| File | What |
|---|---|
| `p01-product-box.jpg` | a filler/botox **box with the lot/batch legible** (then fill `p01`'s `_todo`) |
| `p02-treatment-area.jpg` | a treatment-area photo (cheek / forehead) |
| `p03-injection-site.jpg` | a close-up of an injection site |

## 🎙️ matching/ — spoken patient name → extraction  (2)

| File | Say |
|---|---|
| `m01-exact-name.m4a` | «بیمار نگار محمدی.» (use a real existing patient's name) |
| `m02-near-miss.m4a` | a name **slightly wrong** vs an existing patient (one phoneme off — then fill `m02`'s `_todo`) |

---

The image extension can be `.jpg/.jpeg/.png/.heic`; audio `.m4a/.wav/.mp3/...`. If you rename a file,
rename its `.json` to match. Hand the `_todo` items to the agent and it finalizes the `.json`.
