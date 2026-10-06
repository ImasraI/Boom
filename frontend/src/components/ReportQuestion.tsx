import { useState } from "react";
import { apiUrl, authHeaders, readApiError } from "../api";

export default function ReportQuestion({ mockId, questionId, onReported }: {
  mockId: number; questionId: number; onReported?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [reported, setReported] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true); setError("");
    try {
      const res = await fetch(apiUrl(`/api/mocks/${mockId}/questions/${questionId}/report`), {
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ reason: reason.trim() }),
      });
      if (!res.ok) throw new Error(await readApiError(res, "گزارش ثبت نشد"));
      setReported(true); setOpen(false); onReported?.();
    } catch (e) { setError(e instanceof Error ? e.message : "خطای ارتباط"); }
    finally { setBusy(false); }
  }

  return <div className="mt-4 border-t border-[var(--border)] pt-3 text-right">
    {reported ? <p role="status" className="text-xs text-[var(--accent)]">گزارش ثبت شد؛ این سوال تا بررسی مدیر از بانک کنار گذاشته شد.</p>
      : <button type="button" onClick={() => setOpen(!open)} className="text-xs text-[var(--muted)] hover:text-red-500">⚑ گزارش اشکال در سوال</button>}
    {open && <div className="mt-2 space-y-2">
      <label className="block text-xs text-[var(--muted)]">اشکال متن، گزینه‌ها، تصویر یا پاسخ را توضیح بده
        <textarea value={reason} onChange={e => setReason(e.target.value)} maxLength={2000} rows={2}
          className="mt-2 block w-full bg-[var(--surface)] border border-[var(--border-strong)] p-3 text-sm text-[var(--text)]" />
      </label>
      <div className="flex gap-3">
        <button type="button" onClick={submit} disabled={busy || reason.trim().length < 5}
          className="text-xs font-bold text-[var(--accent)] disabled:opacity-40">{busy ? "در حال ثبت…" : "ثبت گزارش"}</button>
        <button type="button" onClick={() => setOpen(false)} disabled={busy} className="text-xs text-[var(--muted)]">انصراف</button>
      </div>
    </div>}
    {error && <p role="alert" className="text-xs text-red-500 mt-2">{error}</p>}
  </div>;
}
