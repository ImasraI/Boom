import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavFn, SignupData, normalizeSignupData } from "../types";
import { pullServerProfile, pushProfile, toSignupData } from "../profileSync";
import { MAJORS, GRADES, STUDY_HOURS_OPTIONS, TEST_EXAM_OPTIONS, SUBJECTS_BY_MAJOR } from "../data";
import { PREFERENCES_CHANGED_EVENT, readPreferences, playFeedback, updatePreferences } from "../components/Experience";
import { apiJson } from "../api";
import PageHeading from "../components/PageHeading";
import { StudySymbol } from "../components/StudySymbols";

const SECTIONS = ["اطلاعات و تحصیل", "ارزیابی دروس", "تنظیمات"];
function Field({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return <label className={`profile-field ${wide ? "profile-wide" : ""}`}><span>{label}</span>{children}</label>;
}
function Switch({ label, description, checked, onClick }: { label: string; description: string; checked: boolean; onClick: () => void }) {
  return <div className="study-field flex items-center justify-between gap-4 py-5">
    <div><p className="font-semibold">{label}</p><p className="text-sm text-[var(--muted)] mt-1">{description}</p></div>
    <button type="button" className="boom-button boom-button-secondary" role="switch" aria-label={label} aria-checked={checked} onClick={onClick}>{checked ? "روشن" : "خاموش"}</button>
  </div>;
}
export default function Profile({ nav, userData, dark, toggleDark, onSave, logout, settingsRequest = 0 }: {
  nav: NavFn; userData: SignupData | null; dark: boolean; toggleDark: () => void;
  onSave: (data: SignupData) => void; logout: () => void; settingsRequest?: number;
}) {
  const [activeSection, setActiveSection] = useState(settingsRequest ? 2 : 0);
  const [draft, setDraft] = useState(() => normalizeSignupData(userData));
  const [savedData, setSavedData] = useState(() => normalizeSignupData(userData));
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [saveError, setSaveError] = useState("");
  const [customExam, setCustomExam] = useState("");
  const dirty = useRef(false);
  const [prefs, setPrefs] = useState(readPreferences);
  const [analytics, setAnalytics] = useState<Array<{ subject: string; minutes: number; accuracy: number | null; confidence: number | null }>>([]);
  const subjects = SUBJECTS_BY_MAJOR[draft.major] ?? [];
  const isChanged = JSON.stringify(draft) !== JSON.stringify(savedData);
  useEffect(() => { if (settingsRequest) setActiveSection(2); }, [settingsRequest]);
  useEffect(() => {
    if (!dirty.current) { const incoming = normalizeSignupData(userData); setDraft(incoming); setSavedData(incoming); }
  }, [userData]);
  useEffect(() => {
    const sync = () => setPrefs(readPreferences());
    window.addEventListener(PREFERENCES_CHANGED_EVENT, sync);
    return () => window.removeEventListener(PREFERENCES_CHANGED_EVENT, sync);
  }, []);
  useEffect(() => {
    if (activeSection !== 1) return;
    const controller = new AbortController();
    void apiJson<{ subjects: typeof analytics }>("/api/profile/analytics", { signal: controller.signal }, 10000)
      .then(data => setAnalytics(data.subjects || [])).catch(() => {});
    return () => controller.abort();
  }, [activeSection]);
  function update<K extends keyof SignupData>(key: K, value: SignupData[K]) {
    dirty.current = true; setDraft(old => ({ ...old, [key]: value })); setNotice(""); setSaveError("");
  }
  function toggleExam(exam: string) {
    update("testExams", draft.testExams.includes(exam) ? draft.testExams.filter(item => item !== exam) : [...draft.testExams, exam]);
  }
  function addExam() {
    const value = customExam.trim();
    if (value && !draft.testExams.includes(value)) update("testExams", [...draft.testExams, value]);
    setCustomExam("");
  }
  async function save() {
    if (!userData || saving) return;
    if (!draft.name.trim() || !MAJORS.includes(draft.major) || !GRADES.includes(draft.grade) || !draft.studyHours) {
      setSaveError("نام، رشته، پایه و زمان مطالعه را تکمیل کن."); return;
    }
    const token = localStorage.getItem("boom-token");
    const current = { ...draft, name: draft.name.trim(), phone: userData.phone };
    setSaving(true); setNotice(""); setSaveError("");
    try {
      const result = await pushProfile(current);
      if (localStorage.getItem("boom-token") !== token) return;
      if (result.conflict) {
        const server = result.profile ?? await pullServerProfile();
        if (localStorage.getItem("boom-token") !== token) return;
        if (server) {
          const fresh = toSignupData(server, savedData);
          dirty.current = false; setDraft(fresh); setSavedData(fresh); onSave(fresh);
        }
        setSaveError("اطلاعات روی دستگاه دیگری تغییر کرده بود؛ نسخهٔ جدید نمایش داده شد. تغییراتت را بررسی و دوباره ذخیره کن.");
        return;
      }
      if (!result.ok) {
        setSaveError("تغییرات روی سرور ذخیره نشد. اطلاعات این فرم حفظ شده؛ اتصال را بررسی کن و دوباره ذخیره کن."); return;
      }
      const accepted = toSignupData(result.profile ?? null, current);
      dirty.current = false; setDraft(accepted); setSavedData(accepted); onSave(accepted);
      setNotice("تغییرات در حساب ذخیره شد. آزمون‌ها و برنامه‌های بعدی از اطلاعات جدید استفاده می‌کنند.");
    } finally { setSaving(false); }
  }
  const form = <fieldset disabled={saving} className="profile-fields">
    <Field label="نام و نام خانوادگی" wide><input className="boom-field" autoComplete="name" value={draft.name} onChange={e => update("name", e.target.value)} /></Field>
    <Field label="رشتهٔ تحصیلی"><select className="boom-field" value={draft.major} onChange={e => update("major", e.target.value)}>
      <option value="" disabled>انتخاب رشته</option>{MAJORS.map(value => <option key={value}>{value}</option>)}
    </select></Field>
    <Field label="پایهٔ تحصیلی"><select className="boom-field" value={draft.grade} onChange={e => update("grade", e.target.value)}>
      <option value="" disabled>انتخاب پایه</option>{GRADES.map(value => <option key={value}>{value}</option>)}
    </select></Field>
    <Field label="زمان مطالعه در یک روز معمولی" wide><select className="boom-field" value={draft.studyHours} onChange={e => update("studyHours", e.target.value)}>
      <option value="" disabled>انتخاب زمان مطالعه</option>
      {draft.studyHours && !STUDY_HOURS_OPTIONS.includes(draft.studyHours) && <option>{draft.studyHours}</option>}
      {STUDY_HOURS_OPTIONS.map(value => <option key={value}>{value}</option>)}
    </select></Field>
    <div className="profile-field profile-wide"><span id="profile-exams-label">آزمون‌هایی که در آن‌ها شرکت می‌کنی</span>
      <div className="profile-options" role="group" aria-labelledby="profile-exams-label">
        {[...new Set([...TEST_EXAM_OPTIONS, ...draft.testExams])].map(exam => <button type="button" key={exam} aria-pressed={draft.testExams.includes(exam)} onClick={() => toggleExam(exam)}>
          {exam}{draft.testExams.includes(exam) && <span className="sr-only"> · انتخاب‌شده</span>}</button>)}
      </div>
      <div className="flex gap-2"><input aria-label="نام آزمون دیگر" maxLength={80} className="boom-field" value={customExam} onChange={e => setCustomExam(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addExam(); } }} placeholder="نام آزمون دیگر" />
        <button type="button" className="boom-button boom-button-secondary" disabled={!customExam.trim()} onClick={addExam}>افزودن</button></div>
      <small className="text-[var(--muted)]">اگر در آزمونی شرکت نمی‌کنی، همهٔ گزینه‌ها را غیرفعال بگذار.</small>
    </div>
    <Field label="سال کنکور (اختیاری)"><input className="boom-field" inputMode="numeric" value={draft.examYear} onChange={e => update("examYear", e.target.value)} placeholder="مثلاً ۱۴۰۶" /></Field>
    <Field label="رتبهٔ هدف (اختیاری)"><input className="boom-field" inputMode="numeric" value={draft.targetRank} onChange={e => update("targetRank", e.target.value)} /></Field>
    <Field label="تاریخ تولد (اختیاری)"><input type="date" className="boom-field" value={draft.birthday || ""} onChange={e => update("birthday", e.target.value)} /></Field>
    <Field label="شهر (اختیاری)"><input className="boom-field" value={draft.city || ""} onChange={e => update("city", e.target.value)} /></Field>
    <Field label="مدرسه (اختیاری)" wide><input className="boom-field" value={draft.school || ""} onChange={e => update("school", e.target.value)} /></Field>
  </fieldset>;
  return <div className="boom-page" dir="rtl">
    <PageHeading eyebrow="حساب من" title="پروفایل و مسیر تحصیل" icon={<StudySymbol kind="plan" size={32} />}
      description="رشته، پایه و زمان مطالعه‌ات را به‌روز نگه دار تا پیشنهادهای بوم با شرایط تو هماهنگ باشند."
      actions={<button className="boom-button boom-button-secondary" onClick={() => nav("home")}>بازگشت به خانه</button>} />
    <div className="profile-sections" role="tablist" aria-label="بخش‌های پروفایل">
      {SECTIONS.map((section, index) => <button key={section} id={`profile-tab-${index}`} type="button" role="tab" aria-selected={activeSection === index}
        aria-controls="profile-panel" onClick={() => setActiveSection(index)}>{section}</button>)}
    </div>
    <div className="profile-layout">
      <section id="profile-panel" role="tabpanel" aria-labelledby={`profile-tab-${activeSection}`} className="boom-panel">
        {activeSection === 0 && form}
        {activeSection === 1 && <>
          <p className="boom-page-description mb-5">ارزیابی شخصی تو از درس‌هاست؛ نتیجهٔ آزمون‌ها جداگانه ثبت می‌شود. تغییر رشته، ارزیابی قبلی درس‌ها را پاک نمی‌کند.</p>
          {!subjects.length && <p className="boom-notice">ابتدا رشتهٔ تحصیلی را در بخش اطلاعات انتخاب کن.</p>}
          {subjects.map(subject => <fieldset key={subject} disabled={saving} className="study-field py-5">
            <legend className="font-semibold">{subject}</legend>
            {(["completion", "confidence"] as const).map(key => <label className="profile-field mt-4" key={key}>
              <span>{key === "completion" ? "پیشرفت در کتاب" : "اعتماد به پاسخ‌گویی"} · {(draft[key]?.[subject] ?? 0).toLocaleString("fa-IR")}٪</span>
              <input aria-label={`${subject} ${key === "completion" ? "پیشرفت در کتاب" : "اعتماد به پاسخ‌گویی"}`} type="range" min={0} max={100} step={5}
                value={draft[key]?.[subject] ?? 0} onChange={e => update(key, { ...draft[key], [subject]: Number(e.target.value) })} />
            </label>)}
          </fieldset>)}
          {analytics.length > 0 && <section className="mt-6"><h2>عملکرد ثبت‌شده در ۳۰ روز اخیر</h2>
            {analytics.map(item => <p className="study-field py-3 text-sm" key={item.subject}>{item.subject} · {item.minutes} دقیقه مطالعه · {item.accuracy == null ? "هنوز نتیجهٔ آزمون ندارد" : `دقت ${item.accuracy}٪`}</p>)}
          </section>}
        </>}
        {activeSection === 2 && <>
          <Switch label="حالت تاریک" description="ظاهر روشن یا تاریک در همهٔ صفحه‌ها" checked={dark} onClick={toggleDark} />
          <Switch label="صدا" description="بازخورد کوتاه هنگام کار با برنامه" checked={prefs.sound} onClick={() => {
            const next = updatePreferences({ sound: !prefs.sound }); setPrefs(next); if (next.sound) playFeedback("success");
          }} />
          <Switch label="حرکت کمتر" description="کاهش پویانمایی برای تمرکز بیشتر" checked={prefs.calm} onClick={() => setPrefs(updatePreferences({ calm: !prefs.calm }))} />
          <div className="study-field py-5"><p className="mb-3 font-semibold">حال‌وهوای رنگی</p><div className="profile-options">
            {(["coral", "mint", "iris"] as const).map((palette, index) => <button type="button" key={palette} aria-pressed={prefs.palette === palette}
              onClick={() => setPrefs(updatePreferences({ palette }))}>{["غروب", "جنگل", "یاس"][index]}</button>)}
          </div></div>
          <div className="flex flex-wrap gap-3 mt-6">
            <button className="boom-button boom-button-secondary" onClick={() => { localStorage.setItem("boom-reset-phone", userData?.phone || ""); nav("signup"); }}>تغییر رمز عبور با تأیید پیامکی</button>
            <button className="boom-button boom-button-secondary" onClick={logout}>خروج از حساب</button>
          </div>
        </>}
        <div className="profile-save" aria-live="polite">
          {(isChanged || saving) && <button type="button" className="boom-button boom-button-primary" disabled={saving} onClick={() => void save()}>{saving ? "در حال ذخیره…" : "ذخیره تغییرات"}</button>}
          {saveError && <p role="alert" className="text-[var(--error-text)]">{saveError}</p>}
          {notice && <p role="status" className="text-[var(--success-text)]">{notice}</p>}
          {!isChanged && !notice && !saveError && <p className="text-[var(--muted)]">تغییر ذخیره‌نشده‌ای نداری.</p>}
        </div>
      </section>
      <aside className="boom-panel profile-side"><h2>اطلاعات حساب</h2>
        <label className="profile-field mt-4"><span>شمارهٔ موبایل تأییدشده</span><input className="boom-field" dir="ltr" readOnly value={userData?.phone || ""} /></label>
        <p className="mt-3">شمارهٔ موبایل در این بخش قابل تغییر نیست.</p>
        <p className="mt-4">{savedData.major || "رشته ثبت نشده"} · {savedData.grade || "پایه ثبت نشده"}</p>
        <p className="mt-3">تغییر رشته و پایه روی آزمون‌ها و برنامه‌های بعدی اثر می‌گذارد. سوابق قبلی حساب حفظ می‌شوند.</p>
      </aside>
    </div>
  </div>;
}
