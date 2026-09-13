import { useState } from "react";
import { NavFn, SignupData } from "../types";
import { SUBJECTS_BY_MAJOR } from "../data";

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-9 h-9 rounded-xl bg-[var(--chip)] flex items-center justify-center text-[var(--muted)] hover:bg-[var(--chip-hover)] transition-colors">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
        <path d="M19 12H5M12 5l-7 7 7 7"/>
      </svg>
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-[var(--field)] rounded-xl px-4 py-3">
      <p className="text-[10px] font-bold text-[var(--muted-2)] mb-1.5 text-right">{label}</p>
      {children}
    </div>
  );
}

function Chips({ options, value, onChange }: { options: string[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5 justify-end">
      {options.map(o => (
        <button key={o} onClick={() => onChange(o)}
          className={`py-1.5 px-3 rounded-xl text-[12px] font-semibold transition-all ${
            value === o ? "bg-[var(--accent)] text-[var(--surface)]" : "bg-[var(--chip)] text-[var(--brown-text)] hover:bg-[var(--chip-hover)]"
          }`}
        >{o}</button>
      ))}
    </div>
  );
}

const DAYS_FA = ["شنبه", "یکشنبه", "دوشنبه", "سهشنبه", "چهارشنبه", "پنجشنبه", "جمعه"];
const SECTIONS = ["اطلاعات عمومی", "سبک زندگی", "ارزیابی دروس", "هوش مصنوعی", "تنظیمات"];

export default function Profile({ nav, userData, dark, toggleDark, onSave }: { 
  nav: NavFn; 
  userData: SignupData | null; 
  dark: boolean; 
  toggleDark: () => void;
  onSave: (data: SignupData) => void;
}) {
  const [activeSection, setActiveSection] = useState(0);
  const subjects = SUBJECTS_BY_MAJOR[userData?.major ?? "ریاضی فیزیک"] ?? [];

  // General
  const [firstName, setFirstName] = useState(userData?.name?.split(" ")[0] ?? "");
  const [lastName, setLastName] = useState(userData?.name?.split(" ").slice(1).join(" ") ?? "");
  const [phone, setPhone] = useState(userData?.phone ?? "");
  const [birthday, setBirthday] = useState(userData?.birthday ?? "");
  const [city, setCity] = useState(userData?.city ?? "");
  const [school, setSchool] = useState(userData?.school ?? "");

  // Lifestyle
  const [wakeTime, setWakeTime] = useState(userData?.wakeTime ?? "");
  const [dailyHours, setDailyHours] = useState<Record<string, number>>(() => userData?.dailyHours ?? Object.fromEntries(DAYS_FA.map(d => [d, 3])));
  const [maxConsec, setMaxConsec] = useState(userData?.maxConsec ?? 2);
  const [breakStyle, setBreakStyle] = useState(userData?.breakStyle ?? "");
  const [sleepHours, setSleepHours] = useState(userData?.sleepHours ?? 7);
  const [environment, setEnvironment] = useState(userData?.environment ?? "");
  const [phoneUsage, setPhoneUsage] = useState(userData?.phoneUsage ?? "");

  // Subjects
  const [completion, setCompletion] = useState<Record<string, number>>(() => userData?.completion ?? Object.fromEntries(subjects.map(s => [s, 40])));
  const [confidence, setConfidence] = useState<Record<string, number>>(() => userData?.confidence ?? Object.fromEntries(subjects.map(s => [s, 50])));

  // AI
  const [strictness, setStrictness] = useState(userData?.strictness ?? "");
  const [difficulty, setDifficulty] = useState(userData?.difficulty ?? "");
  const [studyStyle, setStudyStyle] = useState(userData?.studyStyle ?? "");
  const [reminderTime, setReminderTime] = useState(userData?.reminderTime ?? "07:30");
  const [notifs, setNotifs] = useState(userData?.notifs ?? true);

  const [saved, setSaved] = useState(false);

  function save() {
    if (!userData) return;
    onSave({
      ...userData,
      name: `${firstName} ${lastName}`.trim(),
      phone,
      birthday,
      city,
      school,
      wakeTime,
      dailyHours,
      maxConsec,
      breakStyle,
      sleepHours,
      environment,
      phoneUsage,
      completion,
      confidence,
      strictness,
      difficulty,
      studyStyle,
      reminderTime,
      notifs,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  }

  const sections = [
    // اطلاعات عمومی
    <div className="space-y-3" key="general">
      <div className="grid grid-cols-2 gap-2">
        <Field label="نام">
          <input value={firstName} onChange={e => setFirstName(e.target.value)} placeholder="پریسا"
            className="w-full bg-transparent outline-none text-[14px] font-semibold text-[var(--text)] placeholder:text-[var(--placeholder)] text-right" />
        </Field>
        <Field label="نام خانوادگی">
          <input value={lastName} onChange={e => setLastName(e.target.value)} placeholder="احمدی"
            className="w-full bg-transparent outline-none text-[14px] font-semibold text-[var(--text)] placeholder:text-[var(--placeholder)] text-right" />
        </Field>
      </div>
      <Field label="شماره موبایل">
        <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="۰۹۱۲۳۴۵۶۷۸۹" dir="ltr"
          className="w-full bg-transparent outline-none text-[14px] font-semibold text-[var(--text)] placeholder:text-[var(--placeholder)] text-left" />
      </Field>
      <Field label="تاریخ تولد">
        <input type="date" value={birthday} onChange={e => setBirthday(e.target.value)} dir="ltr"
          className="w-full bg-transparent outline-none text-[14px] font-semibold text-[var(--text)] text-left" />
      </Field>
      <Field label="شهر">
        <input value={city} onChange={e => setCity(e.target.value)} placeholder="تهران، اصفهان، شیراز..."
          className="w-full bg-transparent outline-none text-[14px] font-semibold text-[var(--text)] placeholder:text-[var(--placeholder)] text-right" />
      </Field>
      <Field label="نام مدرسه">
        <input value={school} onChange={e => setSchool(e.target.value)} placeholder="نام کامل مدرسهات"
          className="w-full bg-transparent outline-none text-[14px] font-semibold text-[var(--text)] placeholder:text-[var(--placeholder)] text-right" />
      </Field>
    </div>,

    // سبک زندگی
    <div className="space-y-3" key="lifestyle">
      <Field label="معمولاً چه ساعتی بیدار میشی؟">
        <input type="time" value={wakeTime} onChange={e => setWakeTime(e.target.value)} dir="ltr"
          className="w-full bg-transparent outline-none text-[14px] font-semibold text-[var(--text)]" />
      </Field>

      <div className="bg-[var(--field)] rounded-xl px-4 py-3">
        <p className="text-[10px] font-bold text-[var(--muted-2)] mb-3 text-right">ساعت مطالعه در هر روز هفته</p>
        <div className="space-y-3">
          {DAYS_FA.map(d => (
            <div key={d} className="flex items-center gap-3">
              <span className="text-[12px] font-bold text-[var(--accent)] w-8 text-left flex-shrink-0">{dailyHours[d]}س</span>
              <input type="range" min={0} max={12} step={0.5} value={dailyHours[d]}
                onChange={e => setDailyHours(h => ({ ...h, [d]: Number(e.target.value) }))}
                className="flex-1" />
              <span className="text-[12px] font-bold text-[var(--muted)] w-14 text-right flex-shrink-0">{d}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-[var(--field)] rounded-xl px-4 py-3">
        <p className="text-[10px] font-bold text-[var(--muted-2)] mb-2 text-right">حداکثر ساعت مطالعهی پشت سر هم</p>
        <div className="flex items-center gap-3">
          <span className="text-[13px] font-bold text-[var(--accent)] flex-shrink-0">{maxConsec} ساعت</span>
          <input type="range" min={0.5} max={5} step={0.5} value={maxConsec}
            onChange={e => setMaxConsec(Number(e.target.value))} className="flex-1" />
        </div>
      </div>

      <Field label="سبک استراحت مورد علاقهات">
        <div className="mt-1">
          <Chips options={["پومودورو ۲۵ دقیقه", "تمرکز ۴۵ دقیقه", "بلوکهای ۶۰ دقیقه", "خودم تصمیم میگیرم"]}
            value={breakStyle} onChange={setBreakStyle} />
        </div>
      </Field>

      <div className="bg-[var(--field)] rounded-xl px-4 py-3">
        <p className="text-[10px] font-bold text-[var(--muted-2)] mb-2 text-right">ساعت خواب شبانه</p>
        <div className="flex items-center gap-3">
          <span className="text-[13px] font-bold text-[var(--accent)] flex-shrink-0">{sleepHours} ساعت</span>
          <input type="range" min={3} max={12} step={0.5} value={sleepHours}
            onChange={e => setSleepHours(Number(e.target.value))} className="flex-1" />
        </div>
      </div>

      <Field label="محیط مطالعه">
        <div className="mt-1">
          <Chips options={["خانه", "کتابخانه", "کافه", "مدرسه", "متنوع"]}
            value={environment} onChange={setEnvironment} />
        </div>
      </Field>

      <Field label="استفاده از گوشی حین مطالعه">
        <div className="mt-1">
          <Chips options={["هیچوقت", "بهندرت", "گاهی", "زیاد"]}
            value={phoneUsage} onChange={setPhoneUsage} />
        </div>
      </Field>
    </div>,

    // ارزیابی دروس
    <div className="space-y-3" key="subjects">
      <p className="text-[12px] text-[var(--muted)] leading-relaxed text-right">
        صادقانه ارزیابی کن. هوش مصنوعی از این اطلاعات برای اولویتبندی ضعیفترین درساتت استفاده میکنه.
      </p>
      {subjects.map(s => (
        <div key={s} className="bg-[var(--field)] rounded-2xl p-4">
          <p className="text-[13px] font-bold text-[var(--text)] mb-3 text-right">{s}</p>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-[11px] font-bold text-[var(--accent)]">{completion[s]}%</span>
                <span className="text-[11px] font-bold text-[var(--muted-2)]">میزان پیشرفت در کتاب</span>
              </div>
              <input type="range" min={0} max={100} step={5} value={completion[s]}
                onChange={e => setCompletion(c => ({ ...c, [s]: Number(e.target.value) }))} className="w-full" />
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-[11px] font-bold text-[#5C8BA8]">{confidence[s]}%</span>
                <span className="text-[11px] font-bold text-[var(--muted-2)]">سطح اعتماد به نفس</span>
              </div>
              <input type="range" min={0} max={100} step={5} value={confidence[s]}
                onChange={e => setConfidence(c => ({ ...c, [s]: Number(e.target.value) }))}
                className="w-full" style={{ accentColor: "#5C8BA8" }} />
            </div>
          </div>
        </div>
      ))}
    </div>,

    // هوش مصنوعی و برنامهریزی
    <div className="space-y-3" key="ai">
      <Field label="سختگیری برنامه">
        <div className="mt-1">
          <Chips options={["انعطافپذیر", "متعادل", "سختگیر"]}
            value={strictness} onChange={setStrictness} />
        </div>
      </Field>

      <Field label="سرعت افزایش سختی">
        <div className="mt-1">
          <Chips options={["تدریجی", "متنوع", "از ابتدا سنگین"]}
            value={difficulty} onChange={setDifficulty} />
        </div>
      </Field>

      <Field label="سبک یادگیری مورد علاقه">
        <div className="mt-1">
          <Chips options={["بیشتر تمرین", "متعادل", "بیشتر مطالعه نظری"]}
            value={studyStyle} onChange={setStudyStyle} />
        </div>
      </Field>

      <Field label="ساعت یادآوری روزانه">
        <input type="time" value={reminderTime} onChange={e => setReminderTime(e.target.value)} dir="ltr"
          className="w-full bg-transparent outline-none text-[14px] font-semibold text-[var(--text)]" />
      </Field>

      <div className="bg-[var(--field)] rounded-xl px-4 py-3 flex items-center justify-between">
        <button
          onClick={() => setNotifs(n => !n)}
          className={`w-11 h-6 rounded-full transition-all relative flex-shrink-0 ${notifs ? "bg-[var(--accent)]" : "bg-[var(--toggle-off)]"}`}
        >
          <div className="bg-[var(--card)] rounded-full absolute top-0.5 transition-all"
            style={{ width: "18px", height: "18px", right: notifs ? "4px" : "20px" }} />
        </button>
        <div className="text-right">
          <p className="text-[13px] font-semibold text-[var(--text)]">اعلانهای هوشمند</p>
          <p className="text-[11px] text-[var(--muted-2)] font-medium mt-0.5">یادآوریها و آپدیت برنامه</p>
        </div>
      </div>
    </div>,

    // تنظیمات
    <div className="space-y-3" key="settings">
      <div className="bg-[var(--field)] rounded-xl px-4 py-3 flex items-center justify-between">
        <button onClick={toggleDark}
          className={`w-11 h-6 rounded-full transition-all relative flex-shrink-0 ${dark ? "bg-[var(--accent)]" : "bg-[var(--toggle-off)]"}`}
        >
          <div className="bg-[var(--card)] rounded-full absolute top-0.5 transition-all"
            style={{ width: "18px", height: "18px", right: dark ? "4px" : "20px" }} />
        </button>
        <div className="text-right">
          <p className="text-[13px] font-semibold text-[var(--text)]">حالت تاریک</p>
          <p className="text-[11px] text-[var(--muted-2)] font-medium mt-0.5">تغییر تم برنامه به حالت شب</p>
        </div>
      </div>
    </div>,
  ];

  return (
    <div className="min-h-screen bg-[var(--surface)] pb-10">
      <div className="px-5 pt-12 pb-4 flex items-center gap-4 sticky top-0 bg-[var(--surface)]/95 backdrop-blur-sm z-10 border-b border-[var(--border)]">
        <BackButton onClick={() => nav("home")} />
        <div className="text-right">
          <h1 className="font-display text-xl text-[var(--text)]">تکمیل پروفایل</h1>
          <p className="text-[12px] text-[var(--muted-2)] font-medium">به هوش مصنوعی کمک میکنه همه چیز رو شخصی کنه</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex overflow-x-auto px-5 py-3 gap-2 border-b border-[var(--border)]" style={{ scrollbarWidth: "none" }}>
        {SECTIONS.map((s, i) => (
          <button key={s} onClick={() => setActiveSection(i)}
            className={`flex-shrink-0 py-2 px-4 rounded-xl text-[12px] font-bold transition-all ${
              activeSection === i ? "bg-[var(--text)] text-[var(--surface)]" : "bg-[var(--chip)] text-[var(--muted)] hover:bg-[var(--chip-hover)]"
            }`}
          >{s}</button>
        ))}
      </div>

      <div className="px-5 pt-5 pb-6">{sections[activeSection]}</div>

      <div className="px-5">
        <button onClick={save}
          className={`w-full py-4 rounded-2xl font-bold text-[14px] transition-all active:scale-95 ${
            saved ? "bg-[var(--success-bg)] text-[var(--success-text)]" : "bg-[var(--accent)] text-[var(--surface)] hover:opacity-90"
          }`}
        >
          {saved ? "✓ ذخیره شد — هوش مصنوعی برنامهات رو آپدیت میکنه" : "ذخیره تغییرات"}
        </button>
      </div>
    </div>
  );
}

