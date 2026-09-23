import { useCallback, useEffect, useState } from "react";
import { apiUrl, authHeaders, readApiError } from "../api";
import type { NavFn } from "../types";

interface AllowEntry { id: number; phone: string; note: string; created_at: string | null }
interface UserRow {
  id: number; username: string; phone: string | null;
  phone_verified: boolean; is_admin: boolean; created_at: string | null;
}

export default function Admin({ nav }: { nav: NavFn }) {
  const [entries, setEntries] = useState<AllowEntry[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, u] = await Promise.all([
        fetch(apiUrl("/api/admin/allowlist"), { headers: { ...authHeaders() } }),
        fetch(apiUrl("/api/admin/users"), { headers: { ...authHeaders() } }),
      ]);
      if (a.status === 403 || u.status === 403) { nav("home"); return; }
      setEntries(a.ok ? await a.json() : []);
      setUsers(u.ok ? await u.json() : []);
    } catch { setErr("خطا در دریافت اطلاعات"); }
  }, [nav]);

  useEffect(() => { load(); }, [load]);

  async function add() {
    setBusy(true); setErr(""); setMsg("");
    try {
      const res = await fetch(apiUrl("/api/admin/allowlist"), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ phone, note }),
      });
      if (!res.ok) throw new Error(await readApiError(res, "افزودن ناموفق بود"));
      setPhone(""); setNote("");
      setMsg("شماره اضافه شد - می‌تواند با کد ۱۱۱۱۱۱ ثبت‌نام کند");
      await load();
    } catch (e) { setErr(e instanceof Error ? e.message : "خطا"); }
    finally { setBusy(false); }
  }

  async function remove(id: number) {
    setBusy(true); setErr(""); setMsg("");
    try {
      const res = await fetch(apiUrl(`/api/admin/allowlist/${id}`), {
        method: "DELETE", headers: { ...authHeaders() },
      });
      if (!res.ok) throw new Error(await readApiError(res, "حذف ناموفق بود"));
      await load();
    } catch (e) { setErr(e instanceof Error ? e.message : "خطا"); }
    finally { setBusy(false); }
  }

  return (
    <div className="p-5 md:p-8 space-y-6 max-w-3xl">
      <div>
        <h1 className="font-display text-2xl text-[var(--text)]">پنل مدیریت</h1>
        <p className="text-xs text-[var(--muted-2)] mt-1">
          تا زمان تأیید قالب پیامک، شماره‌های این لیست می‌توانند با کد ثابت ثبت‌نام کنند.
        </p>
      </div>

      <section className="rounded-3xl bg-[var(--card)] border border-[var(--border)] p-5 space-y-3">
        <h2 className="font-bold text-[var(--text)] text-sm">افزودن شماره به لیست عبور</h2>
        <div className="flex flex-col sm:flex-row gap-2">
          <input value={phone} onChange={e => setPhone(e.target.value)}
            placeholder="۰۹۱۲۳۴۵۶۷۸۹" dir="ltr" inputMode="tel"
            className="flex-1 px-4 py-3 rounded-2xl bg-[var(--surface-2)] border border-[var(--border)] text-sm text-[var(--text)] outline-none focus:border-[var(--accent)]" />
          <input value={note} onChange={e => setNote(e.target.value)}
            placeholder="یادداشت (اختیاری)"
            className="flex-1 px-4 py-3 rounded-2xl bg-[var(--surface-2)] border border-[var(--border)] text-sm text-[var(--text)] outline-none focus:border-[var(--accent)]" />
          <button onClick={add} disabled={busy || !phone.trim()}
            className="px-5 py-3 rounded-2xl bg-[var(--accent)] text-[var(--surface)] font-bold text-sm disabled:opacity-40">
            افزودن
          </button>
        </div>
        {msg && <p className="text-xs text-emerald-400">{msg}</p>}
        {err && <p className="text-xs text-red-400">{err}</p>}
      </section>

      <section className="rounded-3xl bg-[var(--card)] border border-[var(--border)] p-5">
        <h2 className="font-bold text-[var(--text)] text-sm mb-3">
          لیست عبور ({entries.length})
        </h2>
        {entries.length === 0 ? (
          <p className="text-xs text-[var(--muted-2)]">خالی است</p>
        ) : (
          <ul className="space-y-2">
            {entries.map(e => (
              <li key={e.id}
                className="flex items-center gap-3 px-4 py-3 rounded-2xl bg-[var(--surface-2)]">
                <span dir="ltr" className="font-mono text-sm text-[var(--text)]">{e.phone}</span>
                {e.note && <span className="text-xs text-[var(--muted-2)] truncate">{e.note}</span>}
                <button onClick={() => remove(e.id)} disabled={busy}
                  className="ms-auto text-xs text-red-400 hover:text-red-300">حذف</button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-3xl bg-[var(--card)] border border-[var(--border)] p-5">
        <h2 className="font-bold text-[var(--text)] text-sm mb-3">
          کاربران ثبت‌نام‌شده ({users.length})
        </h2>
        <ul className="space-y-1.5">
          {users.map(u => (
            <li key={u.id} className="flex items-center gap-3 text-xs px-3 py-2 rounded-xl bg-[var(--surface-2)]">
              <span className="text-[var(--muted)]">#{u.id}</span>
              <span dir="ltr" className="text-[var(--text)]">{u.username}</span>
              {u.is_admin && <span className="text-[var(--accent)] font-bold">مدیر</span>}
              <span className="ms-auto text-[var(--muted-2)]">
                {u.created_at ? u.created_at.slice(0, 10) : ""}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
