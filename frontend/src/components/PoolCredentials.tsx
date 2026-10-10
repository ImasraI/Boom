import { useEffect, useState } from "react";
import { apiJson } from "../api";

interface CredentialGroup {
  provider: string;
  stage: string;
  active: boolean;
  total: number;
  available: number;
  daily_limited: number;
  access_denied: number;
  cooling_down: number;
}
interface CredentialStatus {
  groups: CredentialGroup[];
  added?: boolean;
}
const choices = [
  { value: "groq:generation", label: "Groq — تولید سؤال" },
  { value: "gemini:verification", label: "Gemini — بررسی پاسخ" },
  { value: "gemini:generation", label: "Gemini — تولید سؤال" },
];

export default function PoolCredentials({ onChanged }: { onChanged: () => void }) {
  const [status, setStatus] = useState<CredentialStatus | null>(null);
  const [choice, setChoice] = useState(choices[0].value);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function refresh() {
    setLoading(true); setError("");
    try { setStatus(await apiJson<CredentialStatus>("/api/admin/pool/credentials")); }
    catch { setError("وضعیت کلیدها دریافت نشد؛ دوباره تلاش کنید."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setMessage(""); setError("");
    const [provider, stage] = choice.split(":");
    try {
      const result = await apiJson<CredentialStatus>("/api/admin/pool/credentials", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, stage, key }),
      });
      setKey(""); setStatus(result);
      const active = result.groups.find(group => group.provider === provider && group.stage === stage)?.active;
      setMessage(result.added === false ? "این کلید قبلاً برای همین کاربرد ثبت شده است." :
        active ? "کلید ذخیره شد؛ تولیدهای بعدی بدون راه‌اندازی مجدد از آن استفاده می‌کنند." :
        "کلید ذخیره شد. این سرویس برای کاربرد انتخاب‌شده در تنظیمات سرور فعال نیست.");
      onChanged();
    } catch (err) { setError(err instanceof Error ? err.message : "ذخیرهٔ کلید انجام نشد."); }
    finally { setBusy(false); }
  }
  return <section className="study-section p-5 space-y-4" aria-labelledby="pool-keys-title">
    <div className="flex items-center justify-between gap-3">
      <h2 id="pool-keys-title" className="font-bold text-base">کلیدهای سرویس ساخت آزمون</h2>
      <button type="button" onClick={() => void refresh()} disabled={busy || loading}
        className="text-xs text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-50">تازه‌سازی وضعیت</button>
    </div>
    <p className="text-xs text-[var(--muted)] leading-relaxed">
      کلیدها فقط در تنظیمات خصوصی سرور ذخیره می‌شوند. کلید جدید به فهرست همان کاربرد اضافه می‌شود؛ کلیدهای چت و برنامه‌ریزی تغییر نمی‌کنند.
    </p>
    {loading && !status && <p className="text-xs text-[var(--muted)]">در حال دریافت وضعیت کلیدها…</p>}
    {status && <div className="divide-y divide-[var(--border)]">
      {status.groups.map(group => <div key={`${group.provider}:${group.stage}`} className="py-3 text-xs space-y-1">
        <div className="flex flex-wrap justify-between gap-2">
          <span className="font-bold">{group.provider === "groq" ? "Groq" : "Gemini"} · {group.stage === "verification" ? "بررسی پاسخ" : "تولید سؤال"}</span>
          <span className="text-[var(--muted)]">{group.total.toLocaleString("fa-IR")} کلید · {group.active ? "سرویس فعال" : "سرویس غیرفعال"}</span>
        </div>
        <p className="text-[var(--muted)] leading-relaxed">
          بدون محدودیت ثبت‌شده: {group.available.toLocaleString("fa-IR")} · سقف روزانه: {group.daily_limited.toLocaleString("fa-IR")} ·
          توقف موقت: {group.cooling_down.toLocaleString("fa-IR")} · بدون دسترسی: {group.access_denied.toLocaleString("fa-IR")}
        </p>
      </div>)}
    </div>}
    <form onSubmit={save} className="border-t border-[var(--border)] pt-4 space-y-3">
      <div className="flex flex-wrap gap-3 items-end">
        <label className="text-xs space-y-2 flex-1 min-w-48">
          <span className="block">سرویس و کاربرد کلید</span>
          <select value={choice} onChange={event => setChoice(event.target.value)} disabled={busy}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--field)] px-3 py-2">
            {choices.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label className="text-xs space-y-2 flex-[2] min-w-48">
          <span className="block">کلید API جدید</span>
          <input type="password" value={key} onChange={event => setKey(event.target.value)} required
            autoComplete="off" spellCheck={false} autoCapitalize="none" dir="ltr" maxLength={512} disabled={busy}
            placeholder="API key" className="w-full rounded-lg border border-[var(--border)] bg-[var(--field)] px-3 py-2" />
        </label>
        <button type="submit" disabled={busy || !key.trim()}
          className="rounded-lg bg-[var(--accent)] text-[var(--page-bg)] px-4 py-2 text-sm font-bold disabled:opacity-50">
          {busy ? "در حال ذخیره…" : "افزودن کلید"}
        </button>
      </div>
      <p className="text-xs text-[var(--muted)] leading-relaxed">
        وضعیت بر اساس خطاهای ثبت‌شدهٔ سرویس است و تأیید اعتبار کلید نیست. کلیدهای یک پروژه ممکن است سهمیهٔ مشترک داشته باشند؛ افزودن کلید سقف آن پروژه را افزایش نمی‌دهد.
      </p>
      {message && <p role="status" className="text-sm text-[var(--accent)]">{message}</p>}
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
    </form>
  </section>;
}
