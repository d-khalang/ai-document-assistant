# Project State Tracking — Modular Platform Architecture (v2.5)
- **Architecture Phase:** Phase 1 (Advanced/Feature-Complete MVP — Streamlit + SQLite + Local ChromaDB)
## Current Status
- **Current Milestone:** Step 8 Completed (Deterministic Auto-Routing, Batch Pipeline & Universal 4-Sheet Executive Report) 🟢
- **System Architecture:** Modular Multi-Tenant Document Intelligence & Compliance Platform
- **Stability Status:** 100% Operational, Zero-Hallucination Verified, Fully Backward Compatible.
- **Test Suite Status:** 18/18 Automated Pytest Test Suites Passing (100% Green).

---

## Completed Milestones:

### Phase 0–27 (Baseline MVP & Multimodal Core)
- پیاده‌سازی پایپ‌لاین RAG بدون فریم‌ورک‌های واسط (Framework-Free) با پایتون خالص، Google GenAI، ChromaDB و SQLite.
- پشتیبانی چندوجهی و چندفرمت: فایل‌های PDF دیجیتال و اسکن‌شده (PyMuPDF OCR)، اسناد Word (`.docx`)، تصاویر (Gemini Vision) و دفاتر کاری اکسل (`.xlsx`/`.xls`) با نگاشت ساختاریافته شیت‌ها و سطرها.
- استخراج داده‌های ممیزی سیستم مدیریت زیست‌محیطی ISO 14001 و تولید گزارش‌های سازمانی اکسل و ورد با امضاهای پویا و متادیتای شرکت.

### Step 1 — Modular Schema Registry
- انتقال کامل منطق دامنه به فایل‌های ساختاریافته در مسیر `schemas/*.json` (`iso_14001.json`, `energy_utility.json`, `hr_training.json`, `machinery_maintenance.json`, `fleet_fuel_expenses.json`, `general_documents.json`).
- پیاده‌سازی رجیستری در `app/extraction/registry.py` همراه با اعتبارسنجی نوع داده‌ها و محاسبات ریاضی قطعی در `app/extraction/calculators.py`.
- تبدیل `app/extraction/schemas.py` به یک Shim سازگار رو به عقب برای حفظ سلامت تست‌های قدیمی.

### Step 2 — UI Module Switcher & Review Roundtrip
- افزودن انتخابگر دامنه‌های عملیاتی در نوار کناری رابط کاربری (`🧩 Modulo / Standard Operativo`).
- پیاده‌سازی موتور چرخه بازبینی انسانی (`app/extraction/review.py`): ثبت ویرایش‌های دستی `st.data_editor` با وضعیت `EDITED` و محاسبه مجدد خودکار فرمول‌ها بدون ایجاد توهم.
- فیلتر بازیابی معنایی بر اساس اسناد سشن فعال و اعمال پاک‌سازی زباله‌های برداری.

### Step 3 — Scoped Exporters (Cross-Module Isolation)
- تفکیک قطعی ماژول‌ها در خروجی‌های رسمی اکسل و ورد از طریق `app/reporting/common.py` (`resolve_scope`).
- تضمین عدم نفوذ داده‌ها و شیت‌های ماژول‌های دیگر در گزارش نهایی (رفع آلودگی بین‌اسکیمایی).
- اعتبارسنجی ۱۰۰٪ موفق با تست اختصاصی `test_scoped_reports.py`.

### Step 4 — Deadline Alerts Engine & Monitoring
- راه‌اندازی موتور قطعی استخراج سررسیدهای قانونی و ممیزی (`app/alerts/deadlines.py`) با شناسه‌های یکتای UUID5.
- موتور اسکن زمان‌بندی‌شده و دسته‌بندی آستانه‌های بحرانی (`app/alerts/scanner.py`) بر اساس روزهای باقی‌مانده.
- لایه پایداری SQLite (`app/alerts/store.py`) با سازوکار ضدهرزنامه و جلوگیری از ارسال تکراری (Deduplication).
- دیسپچر اعلان‌ها و کلاینت‌های استاندارد SMTP Email و Twilio SMS (`app/alerts/dispatcher.py`, `app/alerts/notifiers.py`).
- اضافه شدن تب «⏰ Scadenze & Monitoraggio» در UI و نقطه ورود CLI مستقل `app/alerts/run.py`.

### Step 5 — Dynamic Schema Registry & Extensibility
- تعمیم عملگرهای محاسباتی قطعی پایتون در `calculators.py`: پشتیبانی کامل از عملگرهای `ratio`، `sum`، `diff` و `product` بدون ریسک توهم هوش مصنوعی.
- پیکربندی پویای مدل استخراج برای هر ماژول اسکیما (`ModuleDef.model`) با پیش‌فرض `gemini-3.6-flash`.
- افزودن مکانیزم بازخوانی زنده کش رجیستری (`reload_registry`).
- ارتقای نرمال‌ساز تاریخ (`normalizer.py`) برای پشتیبانی هم‌زمان از اسناد انگلیسی و ایتالیایی.

### Step 6 — Central Configuration & Hot Reload
- ایجاد ماژول تنظیمات متمرکز `app/config.py` جهت اتصال یکپارچه متغیرهای محیطی به هسته سیستم.
- انتقال تمام ثوابت هاردکدشده مدل‌ها، چانکر و آستانه‌ها به کانفیگ مرکزی.
- تعبیه دکمه بازخوانی زنده اسکیماها (`🔄 Ricarica Schemi (Hot Reload)`) در سایدبار رابط کاربری بدون نیاز به راه‌اندازی مجدد Streamlit.
- یکپارچه‌سازی کامل مسیر دیتابیس SQLite در تمام ماژول‌ها از طریق `get_db_path()`.

### Step 7 — Pytest Suite, Robust Excel Parsing & Dynamic Tenant Profile
- یکپارچه‌سازی تمامی آزمون‌های مستقل در قالب فریم‌ورک استاندارد `pytest` تحت پوشه `tests/` همراه با فیکسچر ایزوله‌سازی خودکار دیتابیس (`conftest.py`).
- پیاده‌سازی موتور هوشمند تشخیص سربرگ اکسل (`_parse_excel_sheet`) و یکتاسازی نام ستون‌های تکراری جهت جلوگیری از خطای `Series is ambiguous`.
- خوانش سطرهای اکسل با اندیس موقعیتی `.iloc` جهت تضمین دریافت مقادیر اسکالر.
- حذف کامل اطلاعات هاردکدشده شرکتی؛ شروع هر نشست با فیلدهای کاملاً خالی و ذخیره‌سازی پویا در گزارش‌های خروجی اکسل و ورد.

### Step 8 — Platform Batch Pipeline & 4-Sheet Enterprise Report (v2.5)
- **موتور روتینگ قطعی و بدون توهم (`app/extraction/pipeline.py`):** نگاشت خودکار فایل‌های آپلود شده به ماژول/اسکیماهای متناظر بر اساس وزن‌دهی کلمات کلیدی (`strong_keywords`, `keywords`) و نام فایل در `schemas/*.json` بدون نیاز به تغییر سایدبار.
- **بازبینی و تصحیح انسانی روتینگ (Human-in-the-Loop):** امکان بازبینی و تغییر دستی مقصد هر سند در جدول تعاملی پیش از شروع استخراج.
- **استخراج دسته‌ای غیرمسدودکننده (Batch Pipeline):** استخراج هم‌زمان فایل‌ها با `ThreadPoolExecutor` (با ۳ ورکر موازی) و نمایش زنده وضعیت پیشرفت با `st.status` و `st.progress`.
- **مدیریت چرخه حیات اسناد و سررسیدها:** پیاده‌سازی پاک‌سازی خودکار رکوردهای اسناد حذف‌شده (`evict_document`) و غیرفعال‌سازی سررسیدهای منسوخ یا ویرایش‌شده در دیتابیس (`deactivate_missing_deadlines`, `deactivate_deadlines_for_document`).
- **خروجی اکسل چندشیته جامع پلتفرم (`app/reporting/platform_excel_exporter.py`):**
  - شیت ۱: `Dashboard & KPI` (آمار اسناد، سررسیدها و درصد انطباق)
  - شیت ۲: `Registro Documenti` (دفتر ثبت اسناد سازمانی با ستون‌های استاندارد و علت عدم تحلیل فایل‌ها)
  - شیت ۳: `Scadenze & Azioni` (رادار سررسیدهای اولویت‌بندی‌شده، روزهای باقی‌مانده و اقدامات لازم)
  - شیت ۴+: `Dati <Schema>` (شیت‌های تحلیلی با فرمت‌دهی شرطی اکسل، تاریخ‌های نیتیو و استایل سلول‌های محاسباتی)
- **گاردریل هشدارهای شبیه‌سازی‌شده:** محافظت از ثبت لاگ `sent` در صورت عدم تنظیم کلاینت‌های واقعی SMTP/Twilio (`notifiers.configured`).
- **تضمین تست خودکار:** افزوده شدن آزمون‌های جامع در `tests/test_pipeline.py` و تثبیت پایداری ۱۸ تست سبز.

---

## Remaining Action Items & Next Milestones:

### Immediate Production Tuning:
- تنظیم اعتبارنامه‌های واقعی ارسال ایمیل/پیامک (SMTP/Twilio) در فایل `.env`.
- راه‌اندازی تسک خودکار زمان‌بندی‌شده روزانه (Cron Job / Windows Task Scheduler) برای اجرای خودکار `app/alerts/run.py`.
- تیونینگ تدریجی کلمات کلیدی روتینگ در `schemas/*.json` با دریافت نمونه‌های بیشتر از اسناد شرکتی.

### Step 9 — Production Hardening & Multi-Tenant Authentication:
- افزودن لایه احراز هویت سبک (Authentication) برای تفکیک امن نشست‌های کاربران سازمانی.
- آماده‌سازی کانتینر Docker و پایپ‌لاین CI برای ارزیابی مداوم کیفیت.