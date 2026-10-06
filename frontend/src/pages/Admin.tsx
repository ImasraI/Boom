import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl, authHeaders, readApiError } from "../api";
import type { NavFn } from "../types";
import CorruptQuestions from "../components/CorruptQuestions";

interface AllowEntry { id: number; phone: string; note: string; created_at: string | null }
interface Usage { features: Record<string, number>; tokens_used_today: number }
interface UserRow {
  id: number; username: string; phone: string | null;
  phone_verified: boolean; is_admin: boolean; created_at: string | null;
  usage: Usage;
}
interface UsersPayload { day: string; token_budget: number; limits: Record<string, number>; users: UserRow[] }
interface Shelf { major_key: string; major: string; difficulty: string; available: number }
interface PoolProgress {
  active: boolean; label: string; planned: number; produced: number;
  current: { major_key: string; major: string; difficulty: string } | null;
  elapsed_seconds: number;
  available: number; capacity: number; percent: number;
  duel_available: number; duel_capacity: number;
  // Question bookkeeping: a booklet is ~100 questions over several minutes,
  // so these move long before the booklet counters do.
  phase?: string;
  questions_planned: number; questions: number;
  current_target: number; current_questions: number; current_verified: number;
  failures: number; last_error: string;
}
interface PoolPayload {
  target: number; shelves: Shelf[]; running?: boolean;
  cancel_requested?: boolean; progress?: PoolProgress;
  provider_health?: { blocked: boolean; message?: string; retry_at?: string };
  question_bank?: Record<string, number>;
}
interface SmsCredit { credit: number; configured: boolean; detail: string; bypass_active: boolean }
interface SmsDelivery { message_id: number; send_at: number | null; delivery_at: number | null; delivery_state: number | null }

function formatElapsed(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  if (!minutes) return `${total} ثانیه`;
  return `${minutes}:${String(total % 60).padStart(2, "0")} دقیقه`;
}

const FEATURE_FA: Record<string, string> = {
  chat: "چت", study_plan: "برنامه درسی", weekly_plan: "برنامه هفتگی",
  today_tests: "آزمون امروز", mock_generate: "آزمون هوشمند", arena_join: "دوئل",
};
const DIFFICULTY_FA: Record<string, string> = {
  easy: "آسان", konkur: "کنکور", hard: "سخت",
};
const PHASE_FA: Record<string, string> = {
  generating: "تولید سوال", verifying: "راستی‌آزمایی پاسخ‌ها", saving: "ذخیره دفترچه",
};

export default function Admin({ nav }: { nav: NavFn }) {
  const [entries, setEntries] = useState<AllowEntry[]>([]);
  const [payload, setPayload] = useState<UsersPayload | null>(null);
  const [pool, setPool] = useState<PoolPayload | null>(null);
  const [sms, setSms] = useState<SmsCredit | null>(null);
  const [messageId, setMessageId] = useState("");
  const [delivery, setDelivery] = useState<SmsDelivery | null>(null);
  const [deliveryError, setDeliveryError] = useState("");
  const [checkingDelivery, setCheckingDelivery] = useState(false);
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [restocking, setRestocking] = useState(false);
  const [cancelRequested, setCancelRequested] = useState(false);
  const [poolKind, setPoolKind] = useState("mock");
  const [poolMajor, setPoolMajor] = useState("riazi");
  const [poolDifficulty, setPoolDifficulty] = useState("konkur");
  const [poolGrade, setPoolGrade] = useState("دوازدهم");
  const [poolCount, setPoolCount] = useState(0);
  const poolTimer = useRef<number | null>(null);
  async function checkDelivery() {
    setCheckingDelivery(true); setDelivery(null); setDeliveryError("");
    try {
      const response = await fetch(apiUrl(`/api/admin/sms-delivery/${messageId}`), { headers: authHeaders() });
      if (!response.ok) throw new Error(await readApiError(response, "گزارش پیامک دریافت نشد"));
      setDelivery(await response.json());
    } catch (error) { setDeliveryError(error instanceof Error ? error.message : "خطای ارتباط"); }
    finally { setCheckingDelivery(false); }
  }
  const smsTime = (timestamp: number | null) => timestamp == null ? "ثبت نشده" : new Date(timestamp * 1000).toLocaleString("fa-IR", { timeZone: "Asia/Tehran" });

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
  // The server flag drives the poll too, so opening the panel mid-run (or
  // refreshing) still animates the progress bar.
  const generating = restocking || Boolean(pool?.running);
  useEffect(() => {
    if (!generating) return;
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
  }, [generating]);

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
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ kind: poolKind, major: poolMajor, difficulty: poolDifficulty, grade: poolGrade, count: poolCount }),
      });
      if (!res.ok) throw new Error(await readApiError(res, "شروع restock ناموفق بود"));
      setRestocking(true);
      setCancelRequested(false);
      setMsg("restock شروع شد؛ قفسه‌ها همین‌جا پر می‌شوند...");
    } catch (e) { setErr(e instanceof Error ? e.message : "خطا"); }
    finally { setBusy(false); }
  }

  async function wipeUser(u: UserRow) {
    // Type-to-confirm: the admin must retype the user's username (phone).
    const typed = window.prompt(
      `حذف کامل داده‌های کاربر #${u.id} (${u.username})\n\n` +
      "همه گفتگوها، آزمون‌ها، آمار و فایل‌های این کاربر برای همیشه پاک می‌شوند و قابل بازگشت نیستند.\n" +
      `برای تایید، نام کاربری را تایپ کنید: ${u.username}`
    );
    if (typed === null) return; // canceled
    setBusy(true); setErr(""); setMsg("");
    try {
      const res = await fetch(apiUrl(`/api/admin/users/${u.id}/data`), {
        method: "DELETE",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ confirm: typed.trim() }),
      });
      if (!res.ok) throw new Error(await readApiError(res, "حذف کامل ناموفق بود"));
      setMsg(`همه داده‌های کاربر ${u.username} پاک شد`);
      await load();
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

  const progress = pool?.progress;
  const poolPercent = Math.min(100, Math.max(0, progress?.percent ?? 0));

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
      <section className="study-section p-4 flex items-center gap-3">
        <div>
          <div className="text-[10px] text-[var(--muted-2)]">اعتبار پیامک (sms.ir)</div>
          <div className={`font-display text-xl ${sms && sms.credit > 0 ? "text-[var(--text)]" : "text-red-400"}`} dir="ltr">
            {sms ? sms.credit.toLocaleString("fa-IR") : "—"}
          </div>
          <div className="text-[10px] text-[var(--muted-2)] mt-0.5">
            اعتبار از پنل پیامک خوانده می‌شود
            {sms?.bypass_active && " · ورود با کد پشتیبانی فعال است"}
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
      <section className="study-section px-4 py-5">
        <h2 className="font-bold text-sm mb-2">پیگیری زمان تحویل کد تأیید</h2>
        <p className="text-xs text-[var(--muted)] mb-3">شناسهٔ پیامک را از گزارش ارسال وارد کن. زمان‌ها به وقت تهران نمایش داده می‌شوند.</p>
        <div className="flex gap-3">
          <input aria-label="شناسه پیامک" inputMode="numeric" dir="ltr" value={messageId} disabled={checkingDelivery} onChange={event => { setMessageId(event.target.value.replace(/[^0-9]/g, "")); setDelivery(null); setDeliveryError(""); }} className="min-w-0 flex-1 border-b border-[var(--border-strong)] bg-transparent px-1 py-2 text-sm" />
          <button type="button" onClick={checkDelivery} disabled={checkingDelivery || !/^[1-9][0-9]*$/.test(messageId)} className="text-sm text-[var(--accent)] disabled:opacity-40">{checkingDelivery ? "در حال بررسی…" : "بررسی تحویل"}</button>
        </div>
        {deliveryError && <p role="alert" className="text-xs text-red-400 mt-3">{deliveryError}</p>}
        {delivery && <dl className="grid grid-cols-2 gap-3 mt-4 text-xs" role="status">
          <dt className="text-[var(--muted)]">زمان ارسال</dt><dd>{smsTime(delivery.send_at)}</dd>
          <dt className="text-[var(--muted)]">زمان تحویل</dt><dd>{smsTime(delivery.delivery_at)}</dd>
          <dt className="text-[var(--muted)]">کد وضعیت سرویس</dt><dd>{delivery.delivery_state ?? "ثبت نشده"}</dd>
        </dl>}
      </section>
      <section className="study-section p-5 space-y-3">
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
      <section className="study-section p-5">
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
                    {!u.is_admin && (
                      <button onClick={() => wipeUser(u)} disabled={busy}
                        className="text-[11px] px-2.5 py-1 rounded-lg border border-red-400/60 text-red-400 hover:bg-red-400/10 disabled:opacity-40">
                        حذف کامل
                      </button>
                    )}
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
      <section className="study-section p-5">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="font-bold text-[var(--text)] text-sm">
            موجودی آزمون‌های آماده
          </h2>
          <span className="text-[10px] text-[var(--muted-2)] ms-auto">
            ذخیره بدون سقف
          </span>
          <button onClick={restock} disabled={busy || generating || pool?.provider_health?.blocked}
            className="text-[11px] px-3 py-1.5 rounded-xl bg-[var(--accent)] text-[var(--surface)] font-bold disabled:opacity-40">
            {generating ? "در حال تولید..." : "تولید فوری"}
          </button>
          {generating && !cancelRequested && (
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
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 border-y border-[var(--border)] py-4 mb-4 text-xs text-[var(--muted)]">
          <label>نوع دفترچه<select aria-label="نوع دفترچه برای تولید" value={poolKind} onChange={e => setPoolKind(e.target.value)} disabled={generating} className="block w-full bg-[var(--surface)] border-b border-[var(--border-strong)] py-2 text-[var(--text)]"><option value="mock">آزمون و تمرین</option><option value="ranked">دوئل رنکینگ</option><option value="both">هر دو</option></select></label>
          <label>رشته<select aria-label="رشته برای تولید" value={poolMajor} onChange={e => setPoolMajor(e.target.value)} disabled={generating} className="block w-full bg-[var(--surface)] border-b border-[var(--border-strong)] py-2 text-[var(--text)]">{Object.entries({ riazi: "ریاضی", tajrobi: "تجربی", insani: "انسانی", honar: "هنر", zaban: "زبان", all: "همه رشته‌ها" }).map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
          <label>دشواری<select aria-label="دشواری برای تولید" value={poolDifficulty} onChange={e => setPoolDifficulty(e.target.value)} disabled={generating || poolKind === "ranked"} className="block w-full bg-[var(--surface)] border-b border-[var(--border-strong)] py-2 text-[var(--text)]">{Object.entries(DIFFICULTY_FA).map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
          <label>پایه<select value={poolGrade} onChange={e => setPoolGrade(e.target.value)} disabled={generating} className="block w-full bg-[var(--surface)] border-b border-[var(--border-strong)] py-2 text-[var(--text)]">{["دهم", "یازدهم", "دوازدهم"].map(g => <option key={g}>{g}</option>)}</select></label>
          <label>تعداد دفترچه؛ صفر = پیوسته<input aria-label="تعداد دفترچه" type="number" min={0} step={1} value={poolCount} onChange={e => setPoolCount(Math.max(0, Math.floor(Number(e.target.value))))} disabled={generating} className="block w-full bg-[var(--surface)] border-b border-[var(--border-strong)] py-2 text-[var(--text)]" /></label>
        </div>
        <p className="text-xs text-[var(--muted)] mb-4">فقط انتخاب‌های بالا تولید می‌شوند. حالت پیوسته تا لغو یا توقف سرویس ادامه دارد. بانک سوال: {(pool?.question_bank?.active ?? 0).toLocaleString("fa-IR")} فعال · {(pool?.question_bank?.corrupt ?? 0).toLocaleString("fa-IR")} گزارش‌شده</p>
        {/* Aggregate fill across every shelf. While a sweep is producing, the
            bar shimmers and the live run state (booklets done, shelf in
            flight, elapsed) sits right underneath it. */}
        <div className="mb-4">
          <div className="flex items-baseline justify-between text-[11px] text-[var(--muted)] mb-1.5">
            <span>
              {generating ? "در حال تولید دفترچه‌ها..." : "موجودی کل قفسه‌ها"}
            </span>
            <span className="font-bold text-[var(--text)]">
              {progress?.available ?? 0} دفترچه آماده
            </span>
          </div>
          <div
            className={`pool-bar ${generating ? "is-running" : ""}`}
            role="progressbar"
            aria-valuenow={poolPercent}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className="pool-bar-fill" style={{ width: `${poolPercent}%` }} />
          </div>
          <div className="flex items-baseline justify-between text-[10px] text-[var(--muted-2)] mt-1.5">
            <span>
              {generating && progress ? (
                <>
                  {progress.produced} دفترچه · {progress.questions} سوال ساخته شد
                  {progress.current
                    ? ` — قفسه فعلی: ${progress.current.major} · ${DIFFICULTY_FA[progress.current.difficulty] ?? progress.current.difficulty}`
                    : " — در حال بررسی قفسه‌ها"}
                  {progress.elapsed_seconds > 0 ? ` · ${formatElapsed(progress.elapsed_seconds)}` : ""}
                </>
              ) : (
                "آماده‌ی مصرف دانش‌آموزان"
              )}
            </span>
            <span>
              دوئل آماده: {progress?.duel_available ?? 0}
            </span>
          </div>
          {/* Question detail for the paper being written right now. */}
          {generating && progress && progress.current_target > 0 && (progress.current_questions > 0 || progress.current_verified > 0) && (
            <p className="text-[10px] text-[var(--muted-2)] mt-1">
              دفترچه فعلی: {progress.current_questions} سوال ساخته، {progress.current_verified} تاییدشده از {progress.current_target}
              {progress.phase ? ` · مرحله: ${PHASE_FA[progress.phase] ?? progress.phase}` : ""}
            </p>
          )}
          {(pool?.provider_health?.blocked || progress?.last_error) && (
            <p role="alert" className="text-[12px] text-red-400 mt-1.5 leading-relaxed">
              {pool?.provider_health?.blocked
                ? pool.provider_health.message
                : `تولید متوقف شد: ${progress?.last_error}`}
              {pool?.provider_health?.retry_at && (
                <> بازنشانی بعدی: {new Date(pool.provider_health.retry_at).toLocaleString("fa-IR", { timeZone: "Asia/Tehran" })}</>
              )}
            </p>
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
        {generating && (
          <p className="text-[11px] text-[var(--muted-2)] mt-3">
            تولید هر دفترچه چند دقیقه طول می‌کشد (یک فراخوان LLM برای هر درس + یک
            فراخوان راستی‌آزمایی برای هر سوال). صفحه را ببندید و برگردید - عدد‌ها
            همین‌جا بالا می‌روند.
          </p>
        )}
      </section>
      <CorruptQuestions />
    </div>
  );
}
