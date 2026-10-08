import { useState } from "react";
import { apiUrl, authHeaders } from "../api";
import { acceptServerCalendar, calendarVersion, calendarSyncError, flushCalendar, pullCalendar } from "../calendarSync";

export interface HomeworkDraft {
  id: string;
  status: string;
  details: Record<string, string | number>;
}

export default function HomeworkIntake({ draft, onScheduled, onDismiss }: {
  draft: HomeworkDraft; onScheduled: (answer: string) => void; onDismiss: () => void;
}) {
  const [fields, setFields] = useState<Record<string, string>>(() => Object.fromEntries(
    Object.entries({ ...draft.details, minutes: draft.details.minutes || draft.details.suggested_minutes || "", due_time: draft.details.due_time || "23:59", placement: "add" })
      .map(([key, value]) => [key, String(value)])));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const change = (key: string, value: string) => setFields(old => ({ ...old, [key]: value }));
  const inputStyle = "w-full bg-[var(--surface)] border-b border-[var(--border-strong)] px-2 py-2 outline-none focus:border-[var(--accent)]";

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const token = localStorage.getItem("boom-token");
    if (!token || pending) return;
    setPending(true); setError("");
    try {
      if (!await flushCalendar(token) || !await pullCalendar(token)) throw new Error(calendarSyncError() || "برنامه همگام نشد.");
      if (localStorage.getItem("boom-token") !== token) return;
      const response = await fetch(apiUrl(`/api/boom/homework/${draft.id}/schedule`), {
        method: "POST", headers: { ...authHeaders(token), "Content-Type": "application/json" },
        body: JSON.stringify({ ...fields, minutes: Number(fields.minutes),
          preparation_minutes: fields.activity === "practice" && fields.familiarity === "new" ? Number(fields.preparation_minutes || 0) : 0,
          calendar_version: calendarVersion() }),
      });
      const data = await response.json();
      if (localStorage.getItem("boom-token") !== token) return;
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "درس، مبحث، حجم، زمان و مهلت تکلیف را کامل کن.");
      let notice = "";
      try { acceptServerCalendar(token, data.calendar); }
      catch (cause) { notice = `\n\n${cause instanceof Error ? cause.message : "برنامه را دوباره همگام کن."}`; }
      onScheduled((data.answer || "این تکلیف قبلاً در برنامه ثبت شده است.") + notice);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "ثبت تکلیف انجام نشد."); }
    finally { setPending(false); }
  }
  return <form onSubmit={save} aria-label="جزئیات تکلیف" className="mt-4 border-y border-[var(--border-strong)] py-4 space-y-3 text-[12px]">
    <h3 className="font-bold text-[14px]">اول تکلیف را بشناسیم</h3>
    <p className="text-[var(--muted)]">هر بار یک تکلیف؛ زمان را بر اساس حجم و سرعت خودت تخمین بزن. برنامه پس از ثبت به‌روزرسانی می‌شود.</p>
    {!!draft.details.student_message && <p className="text-[var(--muted)]">توضیح تو: {draft.details.student_message}</p>}
    {!!draft.details.suggested_minutes && <p className="text-[var(--muted)]">پیشنهاد حدودی مدل: {draft.details.suggested_minutes} دقیقه؛ {draft.details.estimate_reason}. زمان را متناسب با خودت اصلاح کن.</p>}
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {[["subject", "درس", "مثلاً فیزیک"], ["topic", "مبحث", "مثلاً میدان الکتریکی"], ["title", "عنوان تکلیف", "تمرین‌های معلم"]].map(([key, label, placeholder]) =>
        <label key={key}>{label}<input required maxLength={key === "subject" ? 100 : 200} value={fields[key] || ""} onChange={e => change(key, e.target.value)} placeholder={placeholder} className={inputStyle} /></label>)}
      <label>زمان لازم (دقیقه)<input required type="number" min="15" max="2520" step="1" value={fields.minutes || ""} onChange={e => change("minutes", e.target.value)} placeholder="مثلاً ۹۰" className={inputStyle} /></label>
      <label>تاریخ تحویل (میلادی)<input required type="date" value={fields.due_date || ""} onChange={e => change("due_date", e.target.value)} className={inputStyle} /></label>
      <label>ساعت تحویل<input required type="time" value={fields.due_time || "23:59"} onChange={e => change("due_time", e.target.value)} className={inputStyle} /></label>
    </div>
    <label className="block">حجم دقیق و منبع<textarea required rows={2} maxLength={1000} value={fields.workload || ""} onChange={e => change("workload", e.target.value)} placeholder="مثلاً سؤال‌های ۳۰ تا ۵۰ کتاب خیلی سبز شیمی؛ حدود ۲۰ سؤال" className={inputStyle} /></label>
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <label>هدف تکلیف<select required value={fields.activity || ""} onChange={e => change("activity", e.target.value)} className={inputStyle}>
        <option value="">انتخاب کن</option><option value="practice">حل سؤال و تمرین</option><option value="study">مطالعه و یادگیری</option>
      </select></label>
      <label>این مبحث را چقدر بلدی؟<select required value={fields.familiarity || ""} onChange={e => change("familiarity", e.target.value)} className={inputStyle}>
        <option value="">انتخاب کن</option><option value="new">هنوز نخوانده‌ام</option><option value="learning">خوانده‌ام، نیاز به تمرین دارم</option><option value="confident">بلدم؛ برای مرور است</option>
      </select></label>
    </div>
    {fields.activity === "practice" && fields.familiarity === "new" &&
      <label className="block">از زمان کل، چند دقیقه برای مطالعهٔ پیش‌نیاز لازم داری؟
        <input required type="number" min="15" max={Math.max(15, Number(fields.minutes || 0) - 15)} value={fields.preparation_minutes || ""}
          onChange={e => change("preparation_minutes", e.target.value)} className={inputStyle} />
        <span className="text-[var(--muted)]">اول مطالعهٔ مبحث و سپس حل تمرین جا می‌گیرد؛ زمان را به مجموع تکلیف اضافه نمی‌کنیم.</span>
      </label>}
    <label className="block">جای تکلیف در برنامه<select value={fields.placement} onChange={e => change("placement", e.target.value)} className={inputStyle}>
      <option value="add">فقط در زمان آزاد اضافه کن</option>
      <option value="replace_matching">اگر جا نشد، جلسهٔ تولیدشدهٔ هم‌درس و هم‌مبحث را جایگزین کن</option>
    </select></label>
    <p className="text-[11px] text-[var(--muted)]">زمان روزانه و فعالیت‌های دستی حفظ می‌شوند. حل تمرین جای یادگیری اولیه را نمی‌گیرد؛ درصد تسلط با نتیجهٔ پاسخ‌ها سنجیده می‌شود.</p>
    {error && <p role="alert" className="text-[var(--danger)]">{error}</p>}
    <div className="flex gap-3"><button disabled={pending} className="press px-4 py-2 bg-[var(--accent)] text-[var(--surface)] font-bold disabled:opacity-50">{pending ? "در حال جا دادن…" : "ثبت در برنامه"}</button>
      <button type="button" disabled={pending} onClick={onDismiss} className="px-3 py-2 text-[var(--muted)]">فعلاً ثبت نکن</button></div>
  </form>;
}
