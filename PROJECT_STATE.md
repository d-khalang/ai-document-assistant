# Project State Tracking — Modular Platform Architecture (v2.5)
- **Architecture Phase:** Phase 1 (Advanced/Feature-Complete MVP — Streamlit + SQLite + Local ChromaDB)
## Current Status
- **Current Milestone:** Step 8 Completed (Deterministic Auto-Routing, Batch Pipeline & Universal 4-Sheet Executive Report) 🟢
- **System Architecture:** Modular Multi-Tenant Document Intelligence & Compliance Platform
- **Stability Status:** 100% Operational, Zero-Hallucination Verified, Fully Backward Compatible.
- **Test Suite Status:** 38/38 Automated Pytest Test Suites Passing (100% Green).

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

### Step 8.5 — Architectural Hardening & Governance (v2.6)
- **فیلترینگ هوشمند سررسیدهای کهنه (`app/alerts/scanner.py`):** اعمال شرط `days_left < -max_overdue_days` جهت جلوگیری از بارگذاری و بررسی سررسیدهای بسیار قدیمی.
- **رفع نشت کانکشن SQLite (`app/alerts/store.py`):** بازنویسی `get_connection()` به صورت کانتکست منیجر استاندارد `@contextmanager` با `timeout=30`، کامیت خودکار و بستن حتمی کانکشن در بلوک `finally`.
- **فعال‌سازی سراسری حالت WAL در SQLite:** اجرای دستور `PRAGMA journal_mode=WAL;` در [database.py](file:///d:/ai-document-assistant/app/database/database.py) و [store.py](file:///d:/ai-document-assistant/app/alerts/store.py) جهت ممانعت قطعی از خطای `database is locked`.
- **پشتیبانی دوگانه از پورت‌های امن ایمیل (`app/alerts/notifiers.py`):** پشتیبانی توأمان از پروتکل SSL مستقیم (پورت 465 با `SMTP_SSL`) و TLS (پورت 587 با `starttls`) با رعایت کامل گاردریل شبیه‌سازی در غیاب سرور واقعی.
- **اصلاح بازنویسی استخراج دستی در UI (`app/ui/streamlit_app.py`):** به‌کارگیری `merge_result` در تب استخراج دستی (`tab_extraction`) به جای بازنویسی کامل دیکشنری، جهت حفظ سوابق استخراج‌شده از اسناد قبلی در سشن فعال.
- **دکمه ارسال هشدارهای واقعی در UI (فاز ۲ - `streamlit_app.py`):** نمایش وضعیت پیکربندی SMTP/SMS و افزودن دکمه «Invia Allerte Reali» با غیرفعال‌سازی هوشمند در صورت عدم کانفیگ و گزارش دقیق آمار ارسال، شبیه‌سازی و خطاها.
- **پاکسازی فایل‌های منسوخ و زائد (فاز ۳):** حذف کامل فایل `app/ui/platform_panel.py` و پاکسازی ارجاعات آن در مستندات جهت جلوگیری از انحراف کانتکست و بارگذاری ماژول‌های استفاده‌نشده.
- **اعتبارسنجی ورودی گیرنده جدید در UI (`app/ui/streamlit_app.py`):** اعتبارسنجی فرمت ایمیل و شماره تلفن پیش از ثبت، بررسی خروجی تابع `add_recipient` و نمایش پیام‌های دقیق خطا و موفقیت.
- **همگام‌سازی مدل پیش‌فرض استخراج با تنظیمات متمرکز (`app/extraction/registry.py`):** اتصال `DEFAULT_EXTRACTION_MODEL` به `app.config.GEMINI_MODEL` جهت حذف هاردکدینگ و پشتیبانی یکپارچه از تنظیم متغیرهای محیطی در `.env`.
- **توسعه تست‌های واحد و ایزوله (Mock Notification):** افزوده شدن تست‌های `test_scan_deadlines_max_overdue_days` و `test_dispatch_alerts_configured_mock` به `tests/test_alerts.py` جهت سنجش شاخه‌های ارسال موفق نوتیفیکیشن با مانکی‌پچ آفلاین و تثبیت پایداری ۲۰/۲۰ تست ۱۰۰٪ سبز.
- **تثبیت پایداری اسناد در رابط کاربری (`app/ui/streamlit_app.py`):** رفع باگ حذف ناخواسته اسناد و رکوردهای برداری هنگام جابه‌جایی بین صفحات ۵‌گانه یا کلیک روی دکمه‌های دانلود؛ جداسازی کامل وضعیت پایدار `indexed_documents` از چرخه موقت `file_uploader` و افزودن کنترل‌های صریح حذف سند (`remove_single_document`) و پاکسازی کامل.
- **پاکسازی یک‌کلیکی سررسیدها (`app/alerts/store.py` + `app/ui/streamlit_app.py`):** افزودن تابع `deactivate_all_deadlines()` (غیرفعال‌سازی نرم `active = 0` با حفظ کامل `alert_log` برای ممیزی)، تست آفلاین `test_deactivate_all_deadlines_clears_registry` و دکمه «Svuota registro scadenze» زیر جدول صفحه Scadenze & Allerte. تعداد تست‌ها: ۲۱/۲۱ سبز.
- **مدیریت و حذف گیرندگان اعلان‌ها (`app/alerts/store.py` + `app/ui/streamlit_app.py`):** افزودن توابع `deactivate_recipient_by_id`, `deactivate_recipient` و `deactivate_all_recipients` برای حذف تکی و پاکسازی یکجای گیرندگان فعال، پیاده‌سازی کنترل‌های حذف و انتخابگر در رابط کاربری بخش Destinatari، پوشش تست جامع `test_recipient_deactivation_and_reactivation` در `tests/test_alerts.py`. مجموع تست‌های سیستم: ۲۲/۲۲ سبز (۱۰۰٪ پاس).
- **مدرن‌سازی بصری و ارگونومی ناوبری سایدبار (`app/ui/theme.py`):** بازطراحی کامل استایل‌های `st.radio` در سایدبار به سبک Pill Tabs مدرن؛ فونت درشت‌تر (`1.15rem`، وزن ۶۰۰ تا ۷۵۰)، حذف دایره‌های رادیویی پیش‌فرض، موشن و شیفت افقی نرم هنگام Hover (`translateX(6px)` با سایه و پس‌زمینه ارگانیک `#EEF7E3`)، بردر و پس‌زمینه سبز شاخص برای تب فعال (`#E2F1D2` / `#8CC63F`) به همراه خط نشانگر عمودی (Accent line) و تست بدون خطای جابه‌جایی بین تمامی صفحات ۵‌گانه.
- **ارتقای اسکیمای مجوزهای زیست‌محیطی (`regulatory_authorization`) و موتورهای گزارش‌گیری (`layout.sheet_title` & `layout.word_sections`):** افزودن فیلدهای ظرفیت (`quantitativi_movimentabili`, `quantitativi_deposito`) بلافاصله بعد از کدهای EER، تفکیک شروط به دو فیلد `prescrizioni_con_scadenza` و `prescrizioni_tecnico_gestionali`، قانون تجمیع کل صفحات سند در یک رکورد واحد (Consolidated Record)، پشتیبانی از `sheet_title` سفارشی (`Dettagli File`) در اکسل و بخش‌های پویای جدول ۴ ستونی (`||`) و لیست شماره‌دار در Word (`app/reporting/word_exporter.py`) به همراه دکمه دانلود مستقیم Word در کنار اکسل در صفحه اول. مجموع تست‌ها: ۲۵/۲۵ سبز (۱۰۰٪ پاس).
- **موتور محاسبه قطعی تاریخ انقضای دوره‌های آموزشی (Deterministic Derived Dates for Training Certifications):** پیاده‌سازی لایه محاسبات انقضا (`app/extraction/calculators.py` و `normalizer.py`) با پشتیبانی از سال‌های کبیسه (`relativedelta`)، تطبیق انعطاف‌پذیر کلمات کلیدی، اعتبارسنجی Fail-fast اسکیما (`derived_dates`) در `app/extraction/registry.py`، و اتصال خودکار فیلدهای `CALCULATED` به موتور هشدارهای تقویمی سررسیدها (`app/alerts/deadlines.py`) مطابق الزامات توافقنامه ایالت-مناطق ایتالیا (Accordo Stato-Regioni) و استانداردهای دوره‌های سرپرستی (۲۴ ماه)، مدیریتی (۶۰ ماه)، تجهیزات/لیفتراک (۶۰ ماه)، آتش‌نشانی (۶۰ ماه) و کمک‌های اولیه (۳۶ ماه) بر روی هر دو اسکیمای `personnel_training` (در ماژول `iso_14001`) و `training_certificate` (در ماژول `hr_training` با نام شیت سفارشی `Attestati Formazione`). مجموع تست‌ها: ۳۳/۳۳ سبز (۱۰۰٪ پاس).
- **تزریق کانتکست ساختاریافته و قوانین شفافیت منشأ به چت با اسناد (Document Chat Structured Context & Provenance):** پیاده‌سازی `build_document_structured_context` در `app/ai/prompts.py` با پیمایش پویا بر روی `schema.fields` و `schema.computed`، تزریق خودکار اطلاعات رکوردهای استخراج‌شده/محاسبه‌شده اسناد فعال در تب `Document Chat` به `build_rag_prompt` قبل از تکه‌های متنی، و درج راهنمای شفافیت ممیزی داده‌ها (Provenance Guideline) جهت تفکیک دقیق داده‌های متن سند (`EXTRACTED`) از محاسبات قطعی بدون توهم سیستم (`CALCULATED`). مجموع تست‌ها: ۳۸/۳۸ سبز (۱۰۰٪ پاس).

---

## Remaining Action Items & Next Milestones:

### Immediate Production Tuning:
- تنظیم اعتبارنامه‌های واقعی ارسال ایمیل/پیامک (SMTP/Twilio) در فایل `.env`.
- راه‌اندازی تسک خودکار زمان‌بندی‌شده روزانه (Cron Job / Windows Task Scheduler) برای اجرای خودکار `app/alerts/run.py`.
- تیونینگ تدریجی کلمات کلیدی روتینگ در `schemas/*.json` با دریافت نمونه‌های بیشتر از اسناد شرکتی.

### Step 9 — Production Hardening & Multi-Tenant Authentication:
- افزودن لایه احراز هویت سبک (Authentication) برای تفکیک امن نشست‌های کاربران سازمانی.
- آماده‌سازی کانتینر Docker و پایپ‌لاین CI برای ارزیابی مداوم کیفیت.
- [Phase 2 Architecture Task] ارتقای استخراج شروط دارای مهلت (prescrizioni_con_scadenza) از حالت تک‌رشته متنی به ساختار اسکیمای فرزند (Child Schema) با رکوردهای مجزا و فیلد تاریخ‌دار رسمی برای اتصال مستقیم به موتور هشدارهای تقویمی deadlines (نیازمند پشتیبانی چنداسکیمایی در build_routing_plan).
