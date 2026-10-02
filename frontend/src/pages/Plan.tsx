import { useEffect, useState } from "react";
import { celebrate } from "../components/Experience";
import { apiUrl, authHeaders, readApiError } from "../api";
import type { NavFn, SignupData } from "../types";
import { addDays, getWeekISO, loadWeekBlocks, toISO, fromISO } from "../scheduleStore";
import { flushProgress } from "../progressSync";

type Overview = {
  evidence: { subject: string; topic: string; attempted: number; correct: number; accuracy: number }[];
  exams: { title: string; date: string }[];
  completed: number; recorded: number; actual_minutes: number;
};
const faDate = (iso: string) => new Intl.DateTimeFormat("fa-IR", { dateStyle: "full" }).format(fromISO(iso));
const card = "plan-card bg-[var(--card)] rounded-2xl border border-[var(--border)] p-5";

export default function Plan({ nav, userData }: { nav: NavFn; userData: SignupData | null }) {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [week, setWeek] = useState(getWeekISO());
  const [title, setTitle] = useState("");
  const [examDate, setExamDate] = useState("");
  const [subjects, setSubjects] = useState("");
  const [saving, setSaving] = useState(false);
  const [revision, setRevision] = useState(0);
  const blocks = loadWeekBlocks(week);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const synced = await flushProgress();
        const res = await fetch(apiUrl("/api/boom/plan-overview"), { headers: authHeaders() });
        if (!res.ok) throw new Error(await readApiError(res, "دریافت اطلاعات ناموفق بود"));
        const body = await res.json();
        if (active) { setData(body); setError(synced ? "" : "بعضی فعالیت‌ها هنوز همگام نشده‌اند؛ پس از اتصال دوباره تلاش کن."); }
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "خطای ارتباط"); }
    })();
    return () => { active = false; };
  }, [revision]);
  async function addExam() {
    setSaving(true); setError("");
    try {
      const res = await fetch(apiUrl("/api/profile/exams"), {
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ title, date: examDate, subjects: subjects.split(/[,،]/).map(s => s.trim()).filter(Boolean) }),
      });
      if (!res.ok) throw new Error(await readApiError(res, "ثبت آزمون ناموفق بود"));
      setTitle(""); setRevision(n => n + 1);
      celebrate("آزمون به تقویمت اضافه شد.");
    } catch (e) { setError(e instanceof Error ? e.message : "خطای ارتباط"); }
    finally { setSaving(false); }
  }
  return <div className="min-h-screen p-5 md:p-8 space-y-5 max-w-5xl mx-auto text-right">
    <header className="plan-heading"><span className="eyebrow">مسیر یادگیری تو</span><h1 className="font-display text-2xl text-[var(--text)]">قدم‌های کوچک، پیشرفت ماندگار.</h1><p className="text-[var(--muted)] mt-3">هدف: {userData?.targetRank || "هنوز هدفی ثبت نشده"}</p></header>
    {data && <div className="plan-metrics"><div><span>زمان ثبت‌شده</span><strong>{data.actual_minutes.toLocaleString("fa-IR")} <small>دقیقه</small></strong></div><div><span>قدم‌های کامل</span><strong>{data.completed.toLocaleString("fa-IR")} <small>فعالیت</small></strong></div><div><span>آزمون پیش رو</span><strong>{data.exams.length.toLocaleString("fa-IR")} <small>آزمون</small></strong></div></div>}
    {error && <div role="alert" className={card}>{error}<button className="block text-[var(--accent)] mt-2" onClick={() => setRevision(n => n + 1)}>تلاش دوباره</button></div>}
    <div className={card}>
      <h2 className="font-bold mb-3">فعالیت ثبت‌شده در هفت روز اخیر</h2>
      {data ? <p>{data.completed.toLocaleString("fa-IR")} فعالیت کامل از {data.recorded.toLocaleString("fa-IR")} فعالیت ثبت‌شده · {data.actual_minutes.toLocaleString("fa-IR")} دقیقه</p> : <p>در حال دریافت...</p>}
      <button onClick={() => nav("home")} className="text-[var(--accent)] mt-3">ثبت انجام تکالیف</button>
    </div>
    <div className={card}>
      <h2 className="font-bold mb-3">عملکرد واقعی در آزمون‌ها</h2>
      {data?.evidence.length ? data.evidence.map(e => <div key={e.subject + e.topic} className="py-3 border-b border-[var(--border)]">
        <p>{e.subject} — {e.topic}</p>
        <p className="text-sm text-[var(--muted)]">{e.correct} پاسخ درست از {e.attempted} · دقت {Math.round(e.accuracy * 100)}٪</p>
        <div className="h-2 rounded bg-[var(--border)] mt-2"><div className="h-2 rounded bg-[var(--accent)]" style={{ width: `${e.accuracy * 100}%` }} /></div>
      </div>) : <p className="text-[var(--muted)]">هنوز نتیجه‌ای ثبت نشده است. یک آزمون انجام بده تا نقاط قوت و ضعف مشخص شوند.</p>}
      <button onClick={() => nav("mock")} className="text-[var(--accent)] mt-3">شروع آزمون</button>
    </div>
    <div className={card}>
      <div className="flex justify-between gap-3 items-center mb-4">
        <button aria-label="هفته قبل" onClick={() => setWeek(toISO(addDays(fromISO(week), -7)))}>هفته قبل</button>
        <h2 className="font-bold">{faDate(week)}</h2>
        <button aria-label="هفته بعد" onClick={() => setWeek(toISO(addDays(fromISO(week), 7)))}>هفته بعد</button>
      </div>
      {Array.from({ length: 7 }, (_, day) => <div key={day} className="py-3 border-b border-[var(--border)]">
        <p className="font-semibold">{faDate(toISO(addDays(fromISO(week), day)))}</p>
        {blocks.filter(b => b.day === day).map((b, i) => <p key={i} className="text-sm text-[var(--muted)] mt-1">{b.title} · {Math.round(b.duration * 60)} دقیقه</p>)}
        {!blocks.some(b => b.day === day) && <p className="text-sm text-[var(--muted)]">فعالیتی برنامه‌ریزی نشده</p>}
      </div>)}
      <button onClick={() => nav("schedule")} className="mt-4 bg-[var(--accent)] text-white rounded-xl px-5 py-3">ساخت یا بازبینی برنامه هفتگی</button>
    </div>
    <div className={card}>
      <h2 className="font-bold mb-3">آزمون‌های پیش رو</h2>
      {data?.exams.length ? data.exams.map((e, i) => <p key={i} className="py-2">{e.title} · {faDate(e.date)}</p>) : <p className="text-[var(--muted)]">آزمون آینده‌ای ثبت نشده است.</p>}
      <form className="mt-4 grid gap-3" onSubmit={e => { e.preventDefault(); void addExam(); }}>
        <label>عنوان آزمون<input required value={title} onChange={e => setTitle(e.target.value)} className="block w-full p-3 rounded-xl bg-[var(--field)]" /></label>
        <label>تاریخ آزمون<input required type="date" min={toISO(new Date())} value={examDate} onChange={e => setExamDate(e.target.value)} className="block w-full p-3 rounded-xl bg-[var(--field)]" /></label>
        <label>درس‌ها (با ویرگول جدا کن)<input required value={subjects} onChange={e => setSubjects(e.target.value)} className="block w-full p-3 rounded-xl bg-[var(--field)]" /></label>
        <button disabled={saving} className="rounded-xl bg-[var(--accent)] text-white p-3">{saving ? "در حال ثبت..." : "ثبت آزمون"}</button>
      </form>
    </div>
  </div>;
}
