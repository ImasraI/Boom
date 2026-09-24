import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl, authHeaders, readApiError } from "../api";
import type { NavFn } from "../types";

interface AllowEntry { id: number; phone: string; note: string; created_at: string | null }
interface Usage { features: Record<string, number>; tokens_used_today: number }
interface UserRow {
  id: number; username: string; phone: string | null;
  phone_verified: boolean; is_admin: boolean; created_at: string | null;
  usage: Usage;
}
interface UsersPayload { day: string; token_budget: number; limits: Record<string, number>; users: UserRow[] }
interface Shelf { major_key: string; major: string; difficulty: string; available: number }
interface PoolPayload { target: number; shelves: Shelf[]; running?: boolean; cancel_requested?: boolean }
interface SmsCredit { credit: number; configured: boolean; detail: string; bypass_active: boolean }

const FEATURE_FA: Record<string, string> = {
  chat: "چت", study_plan: "برنامه درسی", weekly_plan: "برنامه هفتگی",
  today_tests: "آزمون امروز", mock_generate: "آزمون هوشمند", arena_join: "دوئل",
};
const DIFFICULTY_FA: Record<string, string> = {
  easy: "آسان", konkur: "کنکور", hard: "سخت",
};

export default function Admin({ nav }: { nav: NavFn }) {
  const [entries, setEntries] = useState<AllowEntry[]>([]);
  const [payload, setPayload] = useState<UsersPayload | null>(null);
  const [pool, setPool] = useState<PoolPayload | null>(null);
  const [sms, setSms] = useState<SmsCredit | null>(null);
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [restocking, setRestocking] = useState(false);
  const [cancelRequested, setCancelRequested] = useState(false);
  const poolTimer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [a, u, p, s] = await Promise.all([
        fetch(apiUrl("/api/admin/allowlist"), { headers: { ...authHeaders() } }),
        fetch(apiUrl("/api/admin/users"), { headers: { ...authHeaders() } }),
        fetch(apiUrl("/api/admin/pool"), { headers: { ...authHeaders() } }),
        fetch(apiUrl("/api/admin/sms-credit"), { headers: { ...authHeaders() } }),
      ]);
      if (a.status === 403 || u.status === 403 || p.status === 403 || s.status === 403) { nav("home"); return; }
      setEntries(a.ok ? await a.json() : []);
      setPayload(u.ok ? await u.json() : null);
      setPool(p.ok ? await p.json() : null);
      setSms(s.ok ? await s.json() : null);
    } catch { setErr("خطا در دریافت اطلاعات"); }
  }, [nav]);

  useEffect(() => { load(); }, [load]);

  // While a restock is running, poll the shelves so the numbers move live.
  // The payload also carries the server's run state, so a cancel (or a
  // backend restart) flips the UI back to idle even if this tab missed it.
  useEffect(() => {
    if (!restocking) return;
    poolTimer.current = window.setInterval(async () => {
      try {
        const res = await fetch(apiUrl("/api/admin/pool"), { headers: { ...authHeaders() } });
        if (res.ok) {
          const data: PoolPayload = await res.json();
          setPool(data);
          if (data.running === false) {
            setRestocking(false);
            setCancelRequested(false);
          } else {
            setCancelRequested(Boolean(data.cancel_requested));
          }
        }
      } catch { /* keep polling */ }
    }, 3000);
    return () => { if (poolTimer.current) window.clearInterval(poolTimer.current); };
  }, [restocking]);

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

  async function resetQuota(userId: number, username: string) {
    setBusy(true); setErr(""); setMsg("");
    try {
      const res = await fetch(apiUrl(`/api/admin/users/${userId}/reset-quota`), {
        method: "POST", headers: { ...authHeaders() },
      });
      if (!res.ok) throw new Error(await readApiError(res, "ریست ناموفق بود"));
      setMsg(`سهمیه روزانه ${username} ریست شد`);
      await load();
    } catch (e) { setErr(e instanceof Error ? e.message : "خطا"); }
    finally { setBusy(false); }
  }

  async function restock() {
    setBusy(true); setErr(""); setMsg("");
    try {
      const res = await fetch(apiUrl("/api/admin/pool/restock"), {
        method: "POST", headers: { ...authHeaders() },
      });
      if (!res.ok) throw new Error(await readApiError(res, "شروع restock ناموفق بود"));
      setRestocking(true);
      setCancelRequested(false);
      setMsg("restock شروع شد؛ قفسه‌ها همین‌جا پر می‌شوند...");
    } catch (e) { setErr(e instanceof Error ? e.message : "خطا"); }
    finally { setBusy(false); }
  }

  async function cancelRestock() {
    setErr("");
    try {
      const res = await fetch(apiUrl("/api/admin/pool/cancel"), {
        method: "POST", headers: { ...authHeaders() },
      });
      if (!res.ok) throw new Error(await readApiError(res, "لغو ناموفق بود"));
      setCancelRequested(true);
      setMsg("لغو درخواست شد؛ دفترچه فعلی تمام می‌شود و بقیه تولید متوقف می‌شود...");
    } catch (e) { setErr(e instanceof Error ? e.message : "خطا"); }
  }

  // Stop the live poll once every shelf has reached the target again.
  useEffect(() => {
    if (restocking && pool && pool.shelves.every(s => s.available >= pool.target)) {
      setRestocking(false);
      setCancelRequested(false);
      setMsg("همه قفسه‌ها پر شد");
    }
  }, [pool, restocking]);

  const limits = payload?.limits ?? {};

  return (
    <div className="p-5 md:p-8 space-y-6 max-w-3xl">
      <div>
        <h1 className="font-display text-2xl text-[var(--text)]">پنل مدیریت</h1>
        <p className="text-xs text-[var(--muted-2)] mt-1">
          تا زمان تأیید قالب پیامک، شماره‌های این لیست می‌توانند با کد ثابت ثبت‌نام کنند.
        </p>
      </div>

      {msg && <p className="text-xs text-emerald-400">{msg}</p>}
      {err && <p className="text-xs text-red-400">{err}</p>}

      {/* ------------------------------------------------ sms credit ---- */}
      <section className="rounded-3xl bg-[var(--card)] border border-[var(--border)] p-4 flex items-center gap-3">
        <div>
          <div className="text-[10px] text-[var(--muted-2)]">اعتبار پیامک (sms.ir)</div>
          <div className={`font-display text-xl ${sms && sms.credit > 0 ? "text-[var(--text)]" : "text-red-400"}`} dir="ltr">
            {sms ? sms.credit.toLocaleString("fa-IR") : "—"}
          </div>
          <div className="text-[10px] text-[var(--muted-2)] mt-0.5">
            هر کد تأیید ≈ ۱ واحد
            {sms?.bypass_active && " · کد عبور ۱۱۱۱۱۱ فعال است"}
            {sms && !sms.configured && ` · ${sms.detail}`}
            {sms?.configured && sms.credit === 0 && sms.detail && ` · ${sms.detail}`}
          </div>
        </div>
        <button onClick={load} disabled={busy}
          className="ms-auto text-[11px] px-3 py-1.5 rounded-xl bg-[var(--surface-2)] border border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-40">
          به‌روزرسانی
        </button>
      </section>

      {/* ------------------------------------------------ allowlist ---- */}
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
        {entries.length === 0 ? (
          <p className="text-xs text-[var(--muted-2)]">لیست خالی است</p>
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

      {/* --------------------------------------- users + usage/reset ---- */}
      <section className="rounded-3xl bg-[var(--card)] border border-[var(--border)] p-5">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="font-bold text-[var(--text)] text-sm">
            کاربران و مصرف امروز ({payload?.users.length ?? 0})
          </h2>
          {payload && <span className="text-[10px] text-[var(--muted-2)] ms-auto">
            {payload.day} · سقف توکن: {payload.token_budget.toLocaleString("fa-IR")}
          </span>}
        </div>
        {payload?.users.length ? (
          <ul className="space-y-2">
            {payload.users.map(u => {
              const used = u.usage?.tokens_used_today ?? 0;
              return (
                <li key={u.id} className="px-4 py-3 rounded-2xl bg-[var(--surface-2)] space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[var(--muted)] text-xs">#{u.id}</span>
                    <span dir="ltr" className="text-sm text-[var(--text)]">{u.username}</span>
                    {u.is_admin && <span className="text-[10px] text-[var(--accent)] font-bold">مدیر</span>}
                    <span className="ms-auto text-[10px] text-[var(--muted-2)]" dir="ltr">
                      {used.toLocaleString("en-US")} tok
                    </span>
                    <button onClick={() => resetQuota(u.id, u.username)} disabled={busy}
                      className="text-[11px] px-2.5 py-1 rounded-lg bg-[var(--card)] border border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-40">
                      ریست سهمیه
                    </button>
                  </div>
                  {Object.keys(u.usage?.features ?? {}).length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(u.usage.features).map(([f, n]) => (
                        <span key={f}
                          className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--card)] border border-[var(--border)] text-[var(--muted)]"
                          title={limits[f] != null ? `محدودیت: ${limits[f]}` : ""}>
                          {FEATURE_FA[f] ?? f}: {n}{limits[f] != null ? `/${limits[f]}` : ""}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-xs text-[var(--muted-2)]">کاربری ثبت‌نام نکرده است</p>
        )}
      </section>

      {/* ------------------------------------------------ mock pool ---- */}
      <section className="rounded-3xl bg-[var(--card)] border border-[var(--border)] p-5">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="font-bold text-[var(--text)] text-sm">
            موجودی آزمون‌های آماده
          </h2>
          <span className="text-[10px] text-[var(--muted-2)] ms-auto">
            هدف هر قفسه: {pool?.target ?? "—"}
          </span>
          <button onClick={restock} disabled={busy || restocking}
            className="text-[11px] px-3 py-1.5 rounded-xl bg-[var(--accent)] text-[var(--surface)] font-bold disabled:opacity-40">
            {restocking ? "در حال تولید..." : "تولید فوری"}
          </button>
          {restocking && !cancelRequested && (
            <button onClick={cancelRestock}
              className="text-[11px] px-3 py-1.5 rounded-xl border border-red-400/60 text-red-400 font-bold hover:bg-red-400/10">
              لغو تولید
            </button>
          )}
          {cancelRequested && (
            <span className="text-[10px] text-[var(--muted-2)]">
              در حال توقف پس از دفترچه فعلی...
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {pool?.shelves.map(s => {
            const full = s.available >= (pool.target ?? 0);
            return (
              <div key={`${s.major_key}/${s.difficulty}`}
                className="px-3 py-2.5 rounded-2xl bg-[var(--surface-2)] border border-[var(--border)]">
                <div className="flex items-baseline gap-1.5">
                  <span className={`text-lg font-bold ${full ? "text-emerald-400" : s.available === 0 ? "text-red-400" : "text-[var(--text)]"}`}>
                    {s.available}
                  </span>
                  <span className="text-[10px] text-[var(--muted-2)]">/ {pool.target}</span>
                </div>
                <div className="text-[10px] text-[var(--muted)] mt-0.5">
                  {s.major} · {DIFFICULTY_FA[s.difficulty] ?? s.difficulty}
                </div>
              </div>
            );
          })}
        </div>
        {restocking && (
          <p className="text-[11px] text-[var(--muted-2)] mt-3">
            تولید هر دفترچه چند دقیقه طول می‌کشد (یک فراخوان LLM برای هر درس + یک
            فراخوان راستی‌آزمایی برای هر سوال). صفحه را ببندید و برگردید - عدد‌ها
            همین‌جا بالا می‌روند.
          </p>
        )}
      </section>
    </div>
  );
}
