import { useState, useEffect } from "react";
import { NavFn, SignupData } from "../types";
import { pullServerProfile, pushProfile, toSignupData as toSignupPatch } from "../profileSync";
import { SUBJECTS_BY_MAJOR } from "../data";
import { PREFERENCES_CHANGED_EVENT, readPreferences, playFeedback, updatePreferences, SoundIcon } from "../components/Experience";
import { apiUrl, authHeaders } from "../api";

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

export default function Profile({ nav, userData, dark, toggleDark, onSave, logout }: { 
  nav: NavFn; 
  userData: SignupData | null; 
  dark: boolean; 
  toggleDark: () => void;
  onSave: (data: SignupData) => void;
  logout: () => void;
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

  // Sound + appearance preferences live in the Experience storage; the
  // Settings tab is now the only surface exposing them.
  const [prefs, setPrefs] = useState(readPreferences);
  useEffect(() => {
    const sync = () => setPrefs(readPreferences());
    window.addEventListener(PREFERENCES_CHANGED_EVENT, sync);
    return () => window.removeEventListener(PREFERENCES_CHANGED_EVENT, sync);
  }, []);
  function toggleSound() {
    const next = updatePreferences({ sound: !prefs.sound });
    setPrefs(next);
    if (next.sound) playFeedback("success");
  }
  function setPalette(palette: "coral" | "mint" | "iris") {
    setPrefs(updatePreferences({ palette }));
  }
  function toggleCalm() {
    setPrefs(updatePreferences({ calm: !prefs.calm }));
  }

  const [savedData, setSavedData] = useState<SignupData | null>(userData);
  const [saved, setSaved] = useState(false);
  const [conflictNotice, setConflictNotice] = useState("");
  const [analytics, setAnalytics] = useState<Array<{ subject: string; minutes: number; accuracy: number | null; confidence: number | null }>>([]);
  const [reviewQueue, setReviewQueue] = useState<Array<{ subject: string; topic: string; due: boolean; due_date: string; repetitions: number }>>([]);

  async function completeReview(subject: string, topic: string) {
    try {
      const response = await fetch(apiUrl("/api/tasks/review-queue/complete"), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ subject, topic, rating: 4 }),
      });
      if (response.ok) setReviewQueue(items => items.filter(item => !(item.subject === subject && item.topic === topic)));
    } catch {
      // Offline review completion can be retried from the queue later.
    }
  }

  useEffect(() => {
    if (!userData || (activeSection !== 2 && activeSection !== 3)) return;
    const endpoint = activeSection === 2 ? "/api/profile/analytics" : "/api/tasks/review-queue";
    fetch(apiUrl(endpoint), { headers: authHeaders() })
      .then(response => response.ok ? response.json() : null)
      .then(data => {
        if (!data) return;
        if (activeSection === 2) setAnalytics(data.subjects || []);
        else setReviewQueue(data.items || []);
      })
      .catch(() => undefined);
  }, [activeSection, userData]);
  
  function getCurrentData(): SignupData {
    return {
      ...(userData || {} as SignupData),
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
    };
  }

  const isChanged = JSON.stringify(getCurrentData()) !== JSON.stringify(savedData);

  function save() {
    if (!userData) return;
    setConflictNotice("");
    const current = getCurrentData();
    onSave(current);
    setSavedData(current);
    setSaved(true);
    // Growth-readiness project 1: the server row is authoritative; local
    // save stays instant (offline-friendly), server sync follows.
    pushProfile(current).then(async res => {
      if (res.conflict) {
        // Another device won: adopt the server profile explicitly.
        const server = res.profile ?? (await pullServerProfile());
        if (server) {
          const merged = toSignupPatch(server, current);
          onSave(merged);
          setSavedData(merged);
          setSaved(false);
          setConflictNotice("این پروفایل روی دستگاه دیگری تغییر کرده بود؛ نسخه جدید دریافت شد.");
        }
      }
    });
  }

  useEffect(() => {
    if (isChanged) {
      setSaved(false);
    }
  }, [isChanged]);

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
      {analytics.length > 0 && (
        <div className="space-y-2 pt-2">
          <p className="text-right text-[12px] font-bold text-[var(--text)]">شواهد ثبت‌شده در ۳۰ روز اخیر</p>
          {analytics.map(item => (
            <div key={item.subject} className="flex items-center gap-3 rounded-xl bg-[var(--field)] px-4 py-3">
              <span className="text-[11px] font-bold text-[var(--accent)]">{item.confidence == null ? "بدون داده" : `${item.confidence}%`}</span>
              <div className="min-w-0 flex-1 text-right">
                <p className="text-[12px] font-bold text-[var(--text)]">{item.subject}</p>
                <p className="text-[10px] text-[var(--muted-2)]">{item.minutes} دقیقه مطالعه · {item.accuracy == null ? "دقت ثبت نشده" : `${Math.round(item.accuracy * 100)}٪ دقت`}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>,

    // هوش مصنوعی و برنامهریزی
    <div className="space-y-3" key="ai">
      {reviewQueue.length > 0 && (
        <div className="space-y-2 rounded-2xl bg-[var(--field)] p-4">
          <p className="text-right text-[12px] font-bold text-[var(--text)]">صف مرور فاصله‌دار</p>
          {reviewQueue.slice(0, 5).map(item => (
            <div key={`${item.subject}-${item.topic}`} className="flex items-center justify-between gap-3 text-[11px]">
              <button type="button" onClick={() => completeReview(item.subject, item.topic)} className="rounded-lg bg-[var(--accent-soft)] px-2 py-1 font-bold text-[var(--accent)]">مرور شد</button>
              <span className="text-right font-semibold text-[var(--text)]">{item.subject} · {item.topic}</span>
              <span className={item.due ? "font-bold text-red-500" : "text-[var(--muted-2)]"}>{item.due ? "امروز" : item.due_date}</span>
            </div>
          ))}
        </div>
      )}
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

    // تنظیمات — theme and sound first so they're the top controls.
    <div className="space-y-3" key="settings">
      <div className="bg-[var(--field)] rounded-xl px-4 py-3 flex items-center justify-between">
        <button onClick={toggleDark} role="switch" aria-label="حالت تاریک" aria-checked={dark}
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
      <div className="bg-[var(--field)] rounded-xl px-4 py-3 flex items-center justify-between">
        <button onClick={toggleSound} role="switch" aria-label="صدا" aria-checked={prefs.sound}
          className={`w-11 h-6 rounded-full transition-all relative flex-shrink-0 ${prefs.sound ? "bg-[var(--accent)]" : "bg-[var(--toggle-off)]"}`}
        >
          <div className="bg-[var(--card)] rounded-full absolute top-0.5 transition-all"
            style={{ width: "18px", height: "18px", right: prefs.sound ? "4px" : "20px" }} />
        </button>
        <div className="text-right flex items-center gap-2">
          <SoundIcon muted={!prefs.sound} />
          <div>
            <p className="text-[13px] font-semibold text-[var(--text)]">صداهای برنامه</p>
            <p className="text-[11px] text-[var(--muted-2)] font-medium mt-0.5">افکت لمسی هنگام کار با برنامه</p>
          </div>
        </div>
      </div>
      <div className="bg-[var(--field)] rounded-xl px-4 py-3">
        <p className="text-[13px] font-semibold text-[var(--text)] text-right">رنگ اصلی</p>
        <p className="text-[11px] text-[var(--muted-2)] font-medium mt-0.5 text-right">حال‌وهوای رنگی برنامه</p>
        <div className="flex gap-2 mt-3">
          {(["coral", "mint", "iris"] as const).map(id => {
            const color = id === "coral" ? "#c4714a" : id === "mint" ? "#278575" : "#8060c6";
            const label = id === "coral" ? "غروب" : id === "mint" ? "جنگل" : "یاس";
            return (
              <button key={id} onClick={() => setPalette(id)} aria-pressed={prefs.palette === id}
                className={`flex-1 py-2 rounded-xl text-[12px] font-bold transition-all flex items-center justify-center gap-1.5 ${
                  prefs.palette === id ? "ring-2 ring-[var(--accent)]" : "opacity-70 hover:opacity-100"
                }`}
                style={{ backgroundColor: "var(--chip)", color: "var(--text)" }}
              >
                <span className="w-3.5 h-3.5 rounded-full" style={{ backgroundColor: color }} />
                {label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="bg-[var(--field)] rounded-xl px-4 py-3 flex items-center justify-between">
        <button onClick={toggleCalm} role="switch" aria-label="حرکت کمتر" aria-checked={prefs.calm}
          className={`w-11 h-6 rounded-full transition-all relative flex-shrink-0 ${prefs.calm ? "bg-[var(--accent)]" : "bg-[var(--toggle-off)]"}`}
        >
          <div className="bg-[var(--card)] rounded-full absolute top-0.5 transition-all"
            style={{ width: "18px", height: "18px", right: prefs.calm ? "4px" : "20px" }} />
        </button>
        <div className="text-right">
          <p className="text-[13px] font-semibold text-[var(--text)]">حرکت کمتر</p>
          <p className="text-[11px] text-[var(--muted-2)] font-medium mt-0.5">فضایی آرام‌تر برای تمرکز</p>
        </div>
      </div>
      <div className="bg-[var(--field)] rounded-xl px-4 py-3 flex items-center justify-between">
        <button onClick={logout} aria-label="خروج از حساب"
          className="w-11 h-6 rounded-full bg-red-100 dark:bg-red-950 flex items-center justify-center"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-red-600 dark:text-red-400">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
        </button>
        <div className="text-right">
          <p className="text-[13px] font-semibold text-[var(--text)]">خروج از حساب</p>
          <p className="text-[11px] text-[var(--muted-2)] font-medium mt-0.5">خروج و حفظ اطلاعات همین حساب</p>
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
        {conflictNotice && (
          <p role="status" className="mb-3 rounded-xl bg-[var(--accent-soft)] px-4 py-3 text-right text-[12px] font-semibold text-[var(--accent)]">
            {conflictNotice}
          </p>
        )}
        {(isChanged || saved) && (
        <button onClick={save}
          className={`w-full py-4 rounded-2xl font-bold text-[14px] transition-all active:scale-95 ${
            saved ? "bg-[var(--success-bg)] text-[var(--success-text)]" : "bg-[var(--accent)] text-[var(--surface)] hover:opacity-90"
          }`}
          style={{ display: (isChanged || saved) ? 'block' : 'none' }}
        >
          {saved ? "✓ ذخیره شد — هوش مصنوعی برنامهات رو آپدیت میکنه" : "ذخیره تغییرات"}
        </button>

        )}
      </div>
    </div>
  );
}
