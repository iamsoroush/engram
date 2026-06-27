// Lightweight bilingual catalog for the public / first-run surfaces (landing, login, sign-up,
// onboarding). The authenticated clinic app stays English-only for now; this seam is the incremental
// path to translating it later. Keys are flat + dotted; `{var}` placeholders are filled by translate().

export type Lang = "fa" | "en";

export const LANGS: readonly Lang[] = ["fa", "en"];

// Each language labels itself in its own script (shown on the language toggle).
export const LANG_LABEL: Record<Lang, string> = { fa: "فارسی", en: "English" };

type Dict = Record<string, string>;

const en: Dict = {
  "brand.name": "Engram",

  "lang.switchTo": "فارسی", // label of the OTHER language, to switch to it
  "lang.aria": "Switch language",

  "common.back": "Back",

  // Landing
  "landing.eyebrow": "Capture-first clinical memory",
  "landing.title": "Capture the visit. Engram organizes the memory.",
  "landing.subtitle":
    "Engram is a capture-first clinical record for aesthetics clinics. Record audio, snap a photo, or jot a note during the visit — and keep every patient's visits organized in one place.",
  "landing.cta.signup": "Create your clinic",
  "landing.cta.login": "Log in",
  "landing.proTag": "Pro",
  // Hero product preview (stylized phone)
  "landing.preview.session": "Today's visit",
  "landing.preview.unassigned": "Unassigned · assign later",
  "landing.preview.note": "Note",
  "landing.preview.photo": "Photo",
  "landing.preview.audio": "Audio",
  "landing.preview.caption": "Capture now — pick the patient later.",
  // How it works
  "landing.how.title": "How it works",
  "landing.how.step1.title": "Capture",
  "landing.how.step1.body": "Audio, photo, or a note — in seconds, even before you pick the patient.",
  "landing.how.step2.title": "It organizes",
  "landing.how.step2.body": "Every capture is grouped into the visit, ready to review when you have a moment.",
  "landing.how.step3.title": "It stays",
  "landing.how.step3.body": "Each visit is saved to the patient's history — nothing scattered across apps.",
  // Trust
  "landing.trust.title": "Built for clinics you can trust",
  "landing.trust.1.title": "Your records, your clinic",
  "landing.trust.1.body": "Patient records belong to your clinic and stay scoped to it.",
  "landing.trust.2.title": "Works on your device",
  "landing.trust.2.body": "Capture-first saves on the device first and syncs when you're online.",
  "landing.trust.3.title": "AI is opt-in",
  "landing.trust.3.body": "Basic does zero AI. Reports, patient memory, and Q&A come with Pro — only when you choose.",
  // Pricing (placeholder amounts — not final)
  "landing.pricing.title": "Plans",
  "landing.pricing.note": "Placeholder — pricing not final.",
  "landing.pricing.basic.name": "Basic",
  "landing.pricing.basic.price": "Free · early access",
  "landing.pricing.basic.f1": "Fast capture — audio, photo, note",
  "landing.pricing.basic.f2": "Saved on device, synced when online",
  "landing.pricing.basic.f3": "Organized into visit sessions",
  "landing.pricing.pro.name": "Pro",
  "landing.pricing.pro.price": "Coming soon",
  "landing.pricing.pro.f1": "Everything in Basic, plus the AI layer",
  "landing.pricing.pro.f2": "AI reports, summaries & patient matching",
  "landing.pricing.pro.f3": "Patient memory + post-session Q&A",
  "landing.footer": "Built for aesthetics clinics. Therapy and dermatology next.",

  // Shared auth fields
  "auth.email": "Email",
  "auth.password": "Password",

  // Login
  "login.title": "Welcome back",
  "login.subtitle": "Sign in to your clinic.",
  "login.submit": "Sign in",
  "login.submitting": "Signing in…",
  "login.error.invalid": "Invalid email or password.",
  "login.toSignup": "New clinic? Create an account",
  "login.devPersonas": "Developer sign-in",

  // Sign-up
  "signup.title": "Onboard your clinic",
  "signup.subtitle": "Create your clinic and your owner account in one step.",
  "signup.clinicName": "Clinic name",
  "signup.fullName": "Your name",
  "signup.password.hint": "At least 8 characters",
  "signup.submit": "Create clinic",
  "signup.submitting": "Creating…",
  "signup.toLogin": "Already have an account? Log in",
  "signup.error.emailTaken": "An account with this email already exists.",
  "signup.error.email": "Enter a valid email address.",
  "signup.error.password": "Password must be at least 8 characters.",
  "signup.error.generic": "Could not create your clinic. Please try again.",

  // Pending local captures notice (carried over from the old login screen)
  "pending.notice": "{n} capture(s) saved on this device — sign in and I'll organize them once you're online.",

  // Onboarding (guided first capture)
  "onboarding.welcome.title": "Welcome to Engram, {name}",
  "onboarding.welcome.body":
    "Engram is capture-first: record the visit now, organize later. Let's capture your first one together — it takes seconds.",
  "onboarding.capture.title": "Make your first capture",
  "onboarding.capture.body": "Tap any of these — audio, photo, or a note. No patient needed yet. Go ahead and try one now.",
  "onboarding.organizeBasic.title": "Saved & organized",
  "onboarding.organizeBasic.body":
    "Nice. Your captures are saved on this device, synced when you're online, and grouped into the visit — no setup, nothing to wait for. Assign a patient whenever it suits you.",
  "onboarding.organizePro.title": "It organizes itself",
  "onboarding.organizePro.body":
    "Nice. Engram turns your captures into a draft report and summary, and you can assign a patient anytime — review whenever you have a moment.",
  "onboarding.proCallout.title": "Want AI on top?",
  "onboarding.proCallout.body":
    "You're on Basic — fast, reliable capture. Pro adds AI-drafted reports, longitudinal patient memory, and doctor-verified patient Q&A.",
  "onboarding.proTools.title": "Your Pro tools",
  "onboarding.proTools.body":
    "Engram also builds longitudinal patient memory across visits and handles post-session patient Q&A you approve — they appear as you work.",
  "onboarding.done.title": "You're all set",
  "onboarding.done.body": "Capture freely — Engram keeps everything organized in the background. You can replay this guide anytime from the account menu.",
  "onboarding.progress": "Step {n} of {total}",
  "onboarding.next": "Next",
  "onboarding.later": "I'll try later",
  "onboarding.finish": "Start capturing",
  "onboarding.seePlan": "See the Pro plan",
  "onboarding.inviteTeam": "Invite your team",
  "onboarding.skip": "Skip the tour",

  // Clinical safety flags (authed app; English-only for now — see appT). The flag BODY is clinical
  // content in the report language and is never translated; only these labels are.
  "safety.kind.allergy": "Allergy",
  "safety.kind.contraindication": "Contraindication",
  "safety.kind.consent": "Consent",
  // Session-level safety panel (capture verify region; opt-out — auto-kept, reject if wrong)
  "capture.safety.label": "Safety flags · this visit",
  "capture.safety.hint": "Kept by default — reject any that's wrong.",
  "capture.safety.reject": "Reject this flag",
  // Cross-visit patient safety flags (session-context card + patient timeline) — prior visits / record
  "context.safety.label": "Safety · on record",
  "context.safety.aria": "Patient safety flags on record",
};

const fa: Dict = {
  "brand.name": "Engram",

  "lang.switchTo": "English",
  "lang.aria": "تغییر زبان",

  "common.back": "بازگشت",

  // Landing
  "landing.eyebrow": "حافظهٔ بالینیِ «اول‌ ثبت»",
  "landing.title": "ویزیت را ثبت کنید؛ نظم‌دادن به حافظه با مَمرا.",
  "landing.subtitle":
    "مَمرا یک سابقهٔ بالینیِ «اول‌ ثبت» برای کلینیک‌های زیبایی است. حین ویزیت صدا، عکس یا یادداشت ثبت کنید و ویزیت‌های هر بیمار را یک‌جا و منظم نگه دارید.",
  "landing.cta.signup": "ساخت کلینیک",
  "landing.cta.login": "ورود",
  "landing.proTag": "Pro",
  // Hero product preview
  "landing.preview.session": "ویزیت امروز",
  "landing.preview.unassigned": "بدون بیمار · بعداً تخصیص دهید",
  "landing.preview.note": "یادداشت",
  "landing.preview.photo": "عکس",
  "landing.preview.audio": "صدا",
  "landing.preview.caption": "همین حالا ثبت کنید — بیمار را بعداً انتخاب کنید.",
  // How it works
  "landing.how.title": "چطور کار می‌کند",
  "landing.how.step1.title": "ثبت کنید",
  "landing.how.step1.body": "صدا، عکس یا یادداشت — در چند ثانیه، حتی پیش از انتخاب بیمار.",
  "landing.how.step2.title": "منظم می‌شود",
  "landing.how.step2.body": "هر ثبت در ویزیت گروه‌بندی می‌شود و هر وقت فرصت داشتید آمادهٔ بازبینی است.",
  "landing.how.step3.title": "می‌ماند",
  "landing.how.step3.body": "هر ویزیت در سابقهٔ بیمار ذخیره می‌شود — نه پراکنده در چند برنامه.",
  // Trust
  "landing.trust.title": "ساخته‌شده برای اعتماد کلینیک‌ها",
  "landing.trust.1.title": "سوابق شما، کلینیک شما",
  "landing.trust.1.body": "سوابق بیمار متعلق به کلینیک شماست و محدود به همان می‌ماند.",
  "landing.trust.2.title": "روی دستگاه شما کار می‌کند",
  "landing.trust.2.body": "«اول‌ ثبت» ابتدا روی دستگاه ذخیره می‌کند و هنگام اتصال هم‌گام می‌شود.",
  "landing.trust.3.title": "هوش مصنوعی اختیاری است",
  "landing.trust.3.body": "Basic هیچ هوش مصنوعی ندارد. گزارش‌ها، حافظهٔ بیمار و پرسش‌وپاسخ با Pro می‌آیند — فقط اگر بخواهید.",
  // Pricing (placeholder)
  "landing.pricing.title": "پلن‌ها",
  "landing.pricing.note": "نمونه — قیمت‌گذاری نهایی نیست.",
  "landing.pricing.basic.name": "Basic",
  "landing.pricing.basic.price": "رایگان · دسترسی اولیه",
  "landing.pricing.basic.f1": "ثبت سریع — صدا، عکس، یادداشت",
  "landing.pricing.basic.f2": "ذخیره روی دستگاه، هم‌گام هنگام اتصال",
  "landing.pricing.basic.f3": "منظم‌شده در جلسات ویزیت",
  "landing.pricing.pro.name": "Pro",
  "landing.pricing.pro.price": "به‌زودی",
  "landing.pricing.pro.f1": "همهٔ امکانات Basic، به‌علاوهٔ لایهٔ هوش مصنوعی",
  "landing.pricing.pro.f2": "گزارش و خلاصهٔ هوش مصنوعی و تطبیق بیمار",
  "landing.pricing.pro.f3": "حافظهٔ بیمار + پرسش‌وپاسخ پس از ویزیت",
  "landing.footer": "ساخته‌شده برای کلینیک‌های زیبایی. روان‌درمانی و پوست در گام‌های بعدی.",

  // Shared auth fields
  "auth.email": "ایمیل",
  "auth.password": "گذرواژه",

  // Login
  "login.title": "خوش آمدید",
  "login.subtitle": "به کلینیک خود وارد شوید.",
  "login.submit": "ورود",
  "login.submitting": "در حال ورود…",
  "login.error.invalid": "ایمیل یا گذرواژه نادرست است.",
  "login.toSignup": "کلینیک جدید؟ ثبت‌نام کنید",
  "login.devPersonas": "ورود توسعه‌دهنده",

  // Sign-up
  "signup.title": "راه‌اندازی کلینیک",
  "signup.subtitle": "کلینیک و حساب مدیر آن را در یک مرحله بسازید.",
  "signup.clinicName": "نام کلینیک",
  "signup.fullName": "نام شما",
  "signup.password.hint": "حداقل ۸ کاراکتر",
  "signup.submit": "ساخت کلینیک",
  "signup.submitting": "در حال ساخت…",
  "signup.toLogin": "حساب دارید؟ وارد شوید",
  "signup.error.emailTaken": "حسابی با این ایمیل از قبل وجود دارد.",
  "signup.error.email": "یک ایمیل معتبر وارد کنید.",
  "signup.error.password": "گذرواژه باید حداقل ۸ کاراکتر باشد.",
  "signup.error.generic": "ساخت کلینیک ممکن نشد. دوباره تلاش کنید.",

  // Pending local captures notice
  "pending.notice": "{n} ثبت روی این دستگاه ذخیره شده — وارد شوید تا پس از اتصال آن‌ها را منظم کنم.",

  // Onboarding
  "onboarding.welcome.title": "{name} عزیز، به مَمرا خوش آمدید",
  "onboarding.welcome.body": "مَمرا «اول‌ ثبت» است: ویزیت را همین حالا ثبت کنید، بعداً منظمش کنید. بیایید اولین ویزیت‌تان را با هم ثبت کنیم — فقط چند ثانیه است.",
  "onboarding.capture.title": "اولین ثبت‌تان را انجام دهید",
  "onboarding.capture.body": "روی هرکدام بزنید — صدا، عکس یا یادداشت. هنوز نیازی به انتخاب بیمار نیست. همین حالا یکی را امتحان کنید.",
  "onboarding.organizeBasic.title": "ذخیره و منظم شد",
  "onboarding.organizeBasic.body":
    "عالی شد. ثبت‌های شما روی این دستگاه ذخیره می‌شود، هنگام اتصال هم‌گام‌سازی می‌شود و در ویزیت گروه‌بندی می‌شود — بدون تنظیمات و بدون انتظار. هر وقت خواستید بیمار را تخصیص دهید.",
  "onboarding.organizePro.title": "خودش منظم می‌شود",
  "onboarding.organizePro.body":
    "عالی شد. مَمرا ثبت‌های شما را به پیش‌نویس گزارش و خلاصه تبدیل می‌کند و هر زمان می‌توانید بیمار را تخصیص دهید — هر وقت فرصت داشتید بازبینی کنید.",
  "onboarding.proCallout.title": "هوش مصنوعی هم می‌خواهید؟",
  "onboarding.proCallout.body":
    "شما روی نسخهٔ Basic هستید — ثبت سریع و مطمئن. نسخهٔ Pro گزارش‌های تهیه‌شده با هوش مصنوعی، حافظهٔ بلندمدت بیمار و پرسش‌وپاسخ تأییدشدهٔ پزشک را اضافه می‌کند.",
  "onboarding.proTools.title": "ابزارهای نسخهٔ Pro شما",
  "onboarding.proTools.body":
    "مَمرا همچنین حافظهٔ بلندمدت بیمار را در طول ویزیت‌ها می‌سازد و پرسش‌وپاسخ پس از ویزیت بیمار را — با تأیید شما — مدیریت می‌کند. این‌ها در حین کار ظاهر می‌شوند.",
  "onboarding.done.title": "همه‌چیز آماده است",
  "onboarding.done.body": "آزادانه ثبت کنید — مَمرا همه‌چیز را در پس‌زمینه منظم نگه می‌دارد. هر زمان می‌توانید این راهنما را از منوی حساب دوباره ببینید.",
  "onboarding.progress": "گام {n} از {total}",
  "onboarding.next": "بعدی",
  "onboarding.later": "بعداً امتحان می‌کنم",
  "onboarding.finish": "شروع ثبت",
  "onboarding.seePlan": "مشاهدهٔ نسخهٔ Pro",
  "onboarding.inviteTeam": "دعوت هم‌تیمی‌ها",
  "onboarding.skip": "رد کردن راهنما",

  // Clinical safety flags — only these labels are translated; the flag body is report-language content.
  "safety.kind.allergy": "حساسیت",
  "safety.kind.contraindication": "منع مصرف",
  "safety.kind.consent": "رضایت",
  // Session-level safety panel (opt-out — auto-kept, reject if wrong)
  "capture.safety.label": "هشدارهای ایمنی · این ویزیت",
  "capture.safety.hint": "به‌صورت پیش‌فرض نگه داشته می‌شود — موارد نادرست را رد کنید.",
  "capture.safety.reject": "رد این مورد",
  // Cross-visit patient safety flags — prior visits / record
  "context.safety.label": "ایمنی · در سوابق",
  "context.safety.aria": "هشدارهای ایمنی بیمار در سوابق",
};

export const MESSAGES: Record<Lang, Dict> = { en, fa };
