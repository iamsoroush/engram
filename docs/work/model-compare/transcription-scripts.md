# Transcription test scripts — owner-recorded (T01–T12)

Owner-designed scripts for the transcription bracket (`gemini-3.1-flash-lite` vs
`gemini-3.5-flash`). **Recorded 2026-07-10 as session `ab64916e-928f-4150-a874-f671f8f45325`** on
the main dev stack (5183) — 12 audio captures, one per script, captured in script order T01 → T12.
Pull each capture's source audio via `GET /api/v1/captures/{id}/file-content` **against the MAIN
stack's backend (`http://localhost:8010`, dev-login token)** — a worktree dev stack's cloned
database has the session's rows, but its per-worktree MinIO bucket does NOT have the audio objects,
so pulling from a worktree stack 404s. The script text IS the reference transcript.

**Scoring** (agent implements, independent of `apps/ai_engine/eval/`): CER/WER against the script
after NFC normalization (`ی/ي`, `ک/ك`, ZWNJ/space tolerant), plus clinical-token accuracy — every
number, drug/product name, brand, and lot digit sequence. Numbers count as correct in digit OR
word form (value equivalence: «بیست» = «۲۰» = «20» — the production transcriber itself normalizes
to digits); a WRONG value is the failure. Romanizing Persian words into Latin script = fail; T08's
English terms must stay Latin. Compute CER/WER on a number-normalized variant of both sides so the
digit/word choice doesn't dominate the error rate. 3 transcription samples per clip per model;
majority verdict.

What each script stresses:

| Id | Stress |
| --- | --- |
| T01 | baseline doses: number words + units |
| T02 | decimals and fractional doses |
| T03 | Latin brand + letter-digit lot, spoken digit-by-digit |
| T04 | drug names (allergy/contraindication vocabulary) |
| T05 | fast colloquial register («پیشونیش», «یه», «واسه») |
| T06 | inline self-correction with disfluency |
| T07 | administrative/meta speech |
| T08 | fa/en code-switching (English terms stay Latin) |
| T09 | person name + age + device attributes |
| T10 | long multi-treatment dictation (~45s) |
| T11 | negation + hypothetical (safety-critical wording) |
| T12 | ordinals + session counts + consent |

---

## T01

امروز بیست واحد بوتاکس روی پیشانی تزریق شد و نیم سی‌سی فیلر برای خط خنده چپ.

## T02

یک و نیم سی‌سی ژل برای گونه راست و دو دهم سی‌سی برای زیر چشم چپ تزریق کردم.

## T03

فیلر جوویدرم ولوما برای گونه چپ استفاده شد، لات وی ال ام دو دو نه یک.

## T04

بیمار به پنی‌سیلین حساسیت دارد و سابقه مصرف ایزوترتینوئین در شش ماه گذشته را هم دارد، بنابراین از لیدوکائین استفاده نشد.

## T05

بیست و چهار واحد بوتاکس زدم رو پیشونیش، ژلم یه سی‌سی واسه لبش.

## T06

یک سی‌سی ژل توی لب تزریق شد... نه ببخشید، منظورم یک و نیم سی‌سی بود.

## T07

این گزارش رو برای منشی بفرست و بگو نوبت بعدی رو دو هفته دیگه ثبت کنه.

## T08

برای جلسه بعد micro-needling برنامه‌ریزی شد و به بیمار گفتم sunscreen یادش نره.

## T09

خانم مریم رضایی، سی و پنج ساله، جلسه دوم مزوتراپی مو، سوزن سی و دو، عمق چهار میلی‌متر.

## T10

ویزیت امروز: بیست واحد بوتاکس پیشانی، ده واحد بین ابروها، یک سی‌سی ژل گونه چپ، نیم سی‌سی خط خنده راست و نیم سی‌سی لب پایین. مراقبت بعد از درمان: تا بیست و چهار ساعت دراز نکشد، ناحیه‌های تزریق را ماساژ ندهد و تا سه روز از سونا و ورزش سنگین پرهیز کند. نوبت بررسی نتیجه، دو هفته دیگر.

## T11

اگر باردار بود بوتاکس نمی‌زدیم، ولی باردار نیست. قبلاً به سولفانامید حساسیت داشت اما تست جدید منفی بود.

## T12

جلسه سوم از شش جلسه لیزر موهای زائد انجام شد و رضایت‌نامه لیزر امضا شد.
