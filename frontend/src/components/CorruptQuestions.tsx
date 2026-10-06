import { useCallback, useEffect, useState } from "react";
import { apiUrl, authHeaders, readApiError } from "../api";
import { RichText } from "../richText";

interface Item {
  id: number; major: string; grade: string; difficulty: string; note: string; status: string;
  content: { text: string; options: string[]; answer: number; explanation?: string; subject?: string; topic?: string; book?: string; page?: number };
  reports: { id: number; reason: string; mock_id: number; created_at: string }[];
}

export default function CorruptQuestions() {
  const [items, setItems] = useState<Item[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("corrupt");
  const [editing, setEditing] = useState<Item | null>(null);
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const res = await fetch(apiUrl(`/api/admin/questions/corrupt?offset=${offset}&limit=20&status=${status}`), { headers: authHeaders() });
      if (!res.ok) throw new Error(await readApiError(res, "بانک گزارش‌ها دریافت نشد"));
      const data = await res.json(); setItems(data.items); setTotal(data.total);
    } catch (e) { setError(e instanceof Error ? e.message : "خطای ارتباط"); }
  }, [offset, status]);
  useEffect(() => { load(); }, [load]);

  async function review(q: Item, action: string) {
    setBusy(true); setError("");
    try {
      const res = await fetch(apiUrl(`/api/admin/questions/${q.id}/review`), {
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ action, note: q.note,
          ...(action === "correct" ? { text: q.content.text, options: q.content.options,
            answer: q.content.answer, explanation: q.content.explanation ?? "" } : {}) }),
      });
      if (!res.ok) throw new Error(await readApiError(res, "بررسی ثبت نشد"));
      setEditing(null); setApproved(false); await load();
    } catch (e) { setError(e instanceof Error ? e.message : "خطای ارتباط"); }
    finally { setBusy(false); }
  }
  const field = "w-full bg-[var(--surface)] border-b border-[var(--border-strong)] p-2 text-sm text-[var(--text)]";

  return <section className="study-section p-5">
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-sm font-bold text-[var(--text)]">بانک سوال‌های گزارش‌شده ({total.toLocaleString("fa-IR")})</h2>
      <button type="button" onClick={load} disabled={busy} className="text-xs text-[var(--accent)]">تازه‌سازی</button>
    </div>
    <p className="text-xs text-[var(--muted)] mt-2 leading-relaxed">این سوال‌ها در هیچ دفترچه جدیدی استفاده نمی‌شوند. اصلاح، نسخه جدیدی می‌سازد و گزارش و نسخه قبلی را برای بررسی نگه می‌دارد.</p>
    <div className="flex gap-4 text-xs border-b border-[var(--border)] py-3">{[["corrupt", "در انتظار بررسی"], ["deleted", "بایگانی حذف و اصلاح"]].map(([v, label]) => <button key={v} onClick={() => { setStatus(v); setOffset(0); setEditing(null); }} className={status === v ? "text-[var(--accent)] font-bold" : "text-[var(--muted)]"}>{label}</button>)}</div>
    {error && <p role="alert" className="text-xs text-red-500 mt-3">{error}</p>}
    {!items.length && <p className="text-xs text-[var(--muted-2)] py-5">گزارش بررسی‌نشده‌ای وجود ندارد.</p>}
    {items.map(q => <article key={q.id} className="border-t border-[var(--border)] mt-5 pt-4 space-y-3">
      <p className="text-xs text-[var(--muted)]">#{q.id} · {q.content.subject} · {q.content.topic} · {q.major} {q.grade}</p>
      <div className="text-sm leading-relaxed text-[var(--text)]"><RichText text={q.content.text} /></div>
      <ol className="grid gap-2 text-sm text-[var(--text)]">{q.content.options.map((o, i) => <li key={i} className={i === q.content.answer ? "text-[var(--accent)] font-bold" : ""}>{i + 1}. <RichText text={o} /> {i === q.content.answer ? "← کلید ثبت‌شده" : ""}</li>)}</ol>
      {q.content.explanation && <div className="text-xs text-[var(--muted)]"><RichText text={q.content.explanation} /></div>}
      {q.content.book && <p className="text-xs text-[var(--muted)]">منبع: {q.content.book} {q.content.page ? `· صفحه ${q.content.page}` : ""}</p>}
      <ul className="space-y-2 text-xs text-[var(--muted)]">{q.reports.map(r => <li key={r.id} className="border-s-2 border-red-400 ps-3">{r.reason} <span className="block text-[10px] mt-1">دفترچه #{r.mock_id} · {new Date(r.created_at + (r.created_at.endsWith("Z") ? "" : "Z")).toLocaleString("fa-IR")}</span></li>)}</ul>
      {q.status === "corrupt" && <div className="flex flex-wrap gap-4 text-xs">
        <button type="button" disabled={busy} onClick={() => { setEditing({ ...q, content: { ...q.content, options: [...q.content.options] } }); setApproved(false); }} className="text-[var(--accent)]">بررسی و اصلاح</button>
        <button type="button" disabled={busy} onClick={() => review(q, "restore")} className="text-[var(--muted)]">سوال درست است؛ بازگردانی</button>
        <button type="button" disabled={busy} onClick={() => review(q, "delete")} className="text-red-500">حذف از چرخه سوال‌ها</button>
      </div>}
      {editing?.id === q.id && <form onSubmit={e => { e.preventDefault(); review(editing, "correct"); }} className="border-t border-[var(--border)] pt-4 space-y-3">
        <label className="block text-xs text-[var(--muted)]">متن سوال<textarea required rows={4} value={editing.content.text} onChange={e => setEditing({ ...editing, content: { ...editing.content, text: e.target.value } })} className={field} /></label>
        {editing.content.options.map((o, i) => <label key={i} className="block text-xs text-[var(--muted)]">گزینه {i + 1}<input required value={o} onChange={e => setEditing({ ...editing, content: { ...editing.content, options: editing.content.options.map((v, j) => i === j ? e.target.value : v) } })} className={field} /></label>)}
        <label className="block text-xs text-[var(--muted)]">پاسخ صحیح<select value={editing.content.answer} onChange={e => setEditing({ ...editing, content: { ...editing.content, answer: Number(e.target.value) } })} className={field}>{[0, 1, 2, 3].map(n => <option key={n} value={n}>گزینه {n + 1}</option>)}</select></label>
        <label className="block text-xs text-[var(--muted)]">توضیح پاسخ<textarea rows={3} value={editing.content.explanation ?? ""} onChange={e => setEditing({ ...editing, content: { ...editing.content, explanation: e.target.value } })} className={field} /></label>
        <label className="block text-xs text-[var(--muted)]">یادداشت بررسی<textarea value={editing.note} onChange={e => setEditing({ ...editing, note: e.target.value })} className={field} /></label>
        <label className="flex gap-2 text-xs text-[var(--muted)]"><input type="checkbox" checked={approved} onChange={e => setApproved(e.target.checked)} />پاسخ و چهار گزینه نسخه اصلاح‌شده را بررسی و تایید کردم.</label>
        <div className="flex gap-4 text-xs"><button type="submit" disabled={busy || !approved} className="text-[var(--accent)] font-bold disabled:opacity-40">ثبت نسخه تاییدشده</button><button type="button" onClick={() => review(editing, "note")} disabled={busy}>ذخیره یادداشت</button><button type="button" onClick={() => setEditing(null)}>بستن</button></div>
      </form>}
    </article>)}
    <div className="flex justify-between text-xs mt-5 text-[var(--muted)]"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))} className="disabled:opacity-40">قبلی</button><button disabled={offset + 20 >= total} onClick={() => setOffset(offset + 20)} className="disabled:opacity-40">بعدی</button></div>
  </section>;
}
