# Boom — وضعیت آمادگی برای رشد (Growth Readiness)

بر اساس نقشهٔ ۱۰ پروژهٔ مستند شده در جلسهٔ راهبردی. این سند وضعیت واقعی هر پروژه در ریپو را نگه می‌دارد.

| # | پروژه | وضعیت | توضیح |
|---|-------|-------|-------|
| 1 | منبع حقیقت واحد (server-side profile) | 🟡 پایه‌ریزی شد | `StudentProfile` + `GET/PATCH /api/profile` با version/409؛ sync فرانت در `profileSync.ts`؛ *باقی‌مانده*: availability کامل (کلاس‌های ثابت)، API sync جامع، IndexedDB |
| 2 | موتور برنامه‌ریزی قطعی | 🟡 هستهٔ اولیه | `app/planner/engine.py`: اولویت مستندشده، slot fitting، جداسازی بلوک، validator قیود سخت؛ ۱۰ تست invariant؛ *باقی‌مانده*: اتصال به دادهٔ واقعی (StudySession/mastery به‌عنوان ورودی)، شرح دلیل فارسی غنی‌تر |
| 3 | بازبرنامه‌ریزی و عقب‌افتادگی | 🟡 پایه‌ریزی شد | `planner/replan.py`: طبقه‌بندی صادقانه (سکوت = missed، ۸۰٪+ = completed)، تصمیم قطعی keep/shrink/drop، backlog کران‌دار (سرریز صریحاً حذف می‌شود نه بی‌صدا جمع)، کاهش ظرفیت هفتهٔ ضعیف با کف ۵۰٪؛ ستون‌های وضعیت روی DailyTask + مهاجرت؛ `PATCH /api/tasks/daily/{id}/report`، `POST /api/tasks/replan`، `GET /api/tasks/backlog`؛ UI ثبت واقعی (دقیقه + کامل/ناقص/نشد) در TaskSheet؛ ۱۷+ تست invariant؛ *باقی‌مانده*: تقسیم تکلیق به دو قطعه (split)، صف تشخیصی بعد از ۲ بار عقب‌افتادن |
| 4 | ثبت Study Session واقعی | 🟡 پایه‌ریزی شد | ستون‌های کامل + `POST/GET/DELETE /api/profile/sessions` + ثبت سریع از TaskSheet (ReportActualBlock) + postpone به‌عنوان rescheduled در progressSync؛ *باقی‌مانده*: تایمر، فیلدهای عمیق اختیاری در UI |
| 5 | مدل تسلط مبحث‌محور | 🔴 شروع نشده | `TopicMastery` وجود ندارد؛ دادهٔ خام (WrongAnswer/Session) آمادهٔ مصرف است |
| 6 | ایجنت با tool-calling امن | 🔴 شروع نشده | چرخهٔ preview/confirm/undo/audit ساخته نشده |
| 7 | Postgres + Alembic + Job Queue | 🔴 شروع نشده | SQLite + `ensure_schema` فعلی برای توسعه؛ مهاجرت مستلزم پروژهٔ مستقل است |
| 8 | امنیت و حریم خصوصی | 🟡 بخشی انجام شد | fail-startup بدون secret در production، رفع کوری‌وابستگی SECRET_KEY، 409 account-exists، rate limit؛ *باقی‌مانده*: refresh token/Redis، CSP، صفحهٔ حذف حساب |
| 9 | مشاهده‌پذیری و کنترل هزینه | 🟡 بخشی انجام شد | سهمیهٔ اتمیک (`consume/release`) با تست هم‌روندی، بودجهٔ توکن؛ *باقی‌مانده*: متریک/داشبورد، cache، fallback |
| 10 | تست و Eval gate | 🟡 بخشی انجام شد | ۱۵۶ تست (planner invariant، concurrency، ownership)؛ *باقی‌مانده*: E2E، دیتاست eval فارسی |

## معیار «آماده برای رشد» — کدام‌ها برآورده شد
- ✅ یک کاربر نمی‌تواند داده/آزمون کاربر دیگر را ببیند (IDOR sweep + تست مالکیت)
- ✅ تعارض هم‌زمان پروفایل silently overwrite نمی‌شود (version + 409)
- ✅ سهمیهٔ AI با درخواست هم‌زمان قابل عبور نیست
- ✅ production با secret ضعیف بوت نمی‌شود
- ✅ عقب‌افتادگی برنامه را غیرممکن نمی‌کند (backlog کران‌دار؛ سرریز با دلیل قابل‌مشاهده حذف می‌شود)
- ✅ planner قطعی قابل تست و بدون نقض قیود سخت
- ⬜ بقیهٔ موارد (sync کامل، undo ایجنت، Postgres/backup، eval gate) طبق جدول بالا
