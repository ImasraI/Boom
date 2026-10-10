import { useCallback, useEffect, useRef, useState } from "react"
import { NavFn, SignupData } from "../types"
import { apiUrl, apiJson, authHeaders, readApiError } from "../api"
import { RichText } from "../richText"
import ReportQuestion from "../components/ReportQuestion"
import QuestionFigure from "../components/QuestionFigure"
import type { QuestionFigureData } from "../questionFigures"

type Phase = "lobby" | "queued" | "playing" | "finished" | "board" | "scheduled"

interface MeInfo {
  elo: number
  title: { name: string; color: string }
  wins: number
  losses: number
  matches: number
}

interface LeaderRow {
  user_id: number
  username: string
  elo: number
  rank: number
  title: string
  color: string
  is_you: boolean
}

interface MatchInfo {
  generation_error?: string | null
  match_id: number
  status: string
  opponent: string
  opponent_elo: number
  opponent_delta: number | null
  your_elo: number
  your_delta: number | null
  your_score: number | null
  opponent_score: number | null
  won: boolean
  mock_id: number | null
  mock: { duration_minutes: number | null } | null
  // Shared knowledge base the booklet was generated from (the INTERSECTION of
  // both players' subjects for a cross-major duel).
  subjects?: string[] | null
}

/** GET /api/arena/filters — the server-owned duel filter checkboxes. */
interface FilterOptions {
  // every study subject the app knows
  all: string[]
  // the ones THIS player studies (the tickable set)
  mine: string[]
  // tickable subjects that can also appear in the duel booklet
  addressable: string[]
  booklet_of: Record<string, string>
  // subject -> majors whose students study it (who a tick restricts you to)
  majors_with: Record<string, string[]>
  major: string
  grade: string
}

interface AQ {
  id: number
  subject: string
  text: string
  options: string[]
  figure?: QuestionFigureData
}

/* ---------------- Scheduled duels ---------------- */

interface ScheduledOpen {
  id: number
  host: string
  host_elo: number
  starts_at: string
  seconds_until: number
  major: string | null
  wanted: string[]
  is_mine: boolean
  can_accept: boolean
  accepted: boolean
}

interface ScheduledMine {
  match_id: number
  invite_id: number
  opponent: string
  opponent_elo: number
  starts_at: string
  seconds_until: number
  status: string
  you_booked: boolean
}

interface ScheduledQuota {
  used: number
  limit: number
  remaining: number | null  // null = unlimited
}

// The backend stores naive UTC datetimes; its ISO strings carry no offset,
// so tag them before handing them to Date.
function utcDate(iso: string): Date {
  return new Date(/Z|[+]-\d\d:?\d\d$/.test(iso) ? iso : iso + "Z")
}

function faNum(n: number | string): string {
  return String(n).replace(/\d/g, d => "۰۱۲۳۴۵۶۷۸۹"[+d])
}

function fmtWhen(iso: string): string {
  return utcDate(iso).toLocaleString("fa-IR", {
    weekday: "long", day: "numeric", month: "long",
    hour: "2-digit", minute: "2-digit",
  })
}

function countdown(seconds: number): string {
  if (seconds <= 0) return "همین حالا"
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (d) return `${faNum(d)} روز و ${faNum(h)} ساعت`
  if (h) return `${faNum(h)} ساعت و ${faNum(m)} دقیقه`
  if (m) return `${faNum(m)} دقیقه`
  return `${faNum(s)} ثانیه`
}

// Value for <input type="datetime-local"> in the LOCAL zone.
function localInputValue(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

// A local wall-clock date N days from today at a fixed hour. If that
// moment is already too close (backend wants >= 5 min ahead), roll it a
// day forward so "امشب ۲۱" clicked at 22:00 becomes tomorrow 21:00.
function dayAt(daysFromToday: number, hour: number): Date {
  const d = new Date()
  d.setDate(d.getDate() + daysFromToday)
  d.setHours(hour, 0, 0, 0)
  if (d.getTime() < Date.now() + 10 * 60e3) d.setDate(d.getDate() + 1)
  return d
}

// One-tap kickoff choices so nobody has to type a datetime. Computed at
// CLICK time, never at render, so "۱ ساعت دیگر" is always fresh.
const QUICK_SLOTS: { key: string; label: string; at: () => Date }[] = [
  { key: "h1", label: `۱ ساعت دیگر`, at: () => new Date(Date.now() + 3600e3) },
  { key: "h3", label: `۳ ساعت دیگر`, at: () => new Date(Date.now() + 3 * 3600e3) },
  { key: "tonight", label: `امشب ${faNum(21)}:${faNum("00")}`, at: () => dayAt(0, 21) },
  { key: "tomorrow-am", label: `فردا ${faNum(10)} صبح`, at: () => dayAt(1, 10) },
  { key: "tomorrow-pm", label: `فردا ${faNum(16)}`, at: () => dayAt(1, 16) },
  { key: "next-week", label: "هفتهٔ دیگر", at: () => dayAt(7, 10) },
]

const LABELS = ["الف", "ب", "ج", "د"]

function fmt(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
}

function EloBadge({ elo, title, color, size = "md" }: { elo: number; title?: string; color?: string; size?: "sm" | "md" | "lg" }) {
  const pad = size === "lg" ? "px-4 py-2" : size === "sm" ? "px-2 py-0.5" : "px-3 py-1"
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-xl font-bold ${pad}`}
      style={{ background: (color ?? "#9CA3AF") + "22", color: color ?? "#9CA3AF" }}>
      {title && <span className="text-[11px]">{title}</span>}
      <span className={size === "lg" ? "text-[20px]" : "text-[13px]"}>{elo}</span>
    </span>
  )
}

/* ---------------- Lobby ---------------- */

function Lobby({ me, onJoin, onBoard, onScheduled, busy, filters, wanted, onToggle, onClear, error }: {
  me: MeInfo | null
  onJoin: () => void
  onBoard: () => void
  onScheduled: () => void
  busy: boolean
  filters: FilterOptions | null
  wanted: string[]
  onToggle: (subject: string) => void
  onClear: () => void
  error?: string
}) {
  return (
    <div className="min-h-screen bg-[var(--surface)]">
      <div className="bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-5 text-center">
        <p className="text-[11px] font-bold text-[var(--muted-2)] mb-1">دوئل رنکینگ بوم</p>
        <h1 className="font-bold text-xl text-[var(--text)] mb-3">آرنا</h1>
        {me && <EloBadge elo={me.elo} title={me.title.name} color={me.title.color} size="lg" />}
        {me && (
          <p className="text-[12px] text-[var(--muted-2)] mt-2 font-bold">
            {me.wins} برد · {me.losses} باخت از {me.matches} مسابقه
          </p>
        )}
      </div>

      <div className="px-4 mt-5 max-w-[430px] mx-auto space-y-4">
        <div className="study-section p-5 text-right">
          <p className="text-[13px] font-bold text-[var(--text)] mb-2">چطور کار می‌کند؟</p>
          <ul className="text-[12px] text-[var(--muted-2)] leading-relaxed space-y-1.5">
            <li>• وارد صف شو؛ تا وقتی حریف هم‌سطح پیدا نشود در صف می‌مانی — بدون ربات.</li>
            <li>• هر دو یک دفترچه آزمون یکسان و کوتاه می‌گیرید، با زمان واقعی.</li>
            <li>• دفترچه از دانش مشترک شما ساخته می‌شود: رشته‌های مختلف فقط روی درس‌های مشترک مسابقه می‌دهند.</li>
            <li>• پایه تحصیلی کوچک‌تر تعیین می‌شود؛ سوال از مطالبی که هنوز نخوانده‌ای پرسیده نمی‌شود.</li>
            <li>• تصحیح با نمره منفی کنکور؛ امتیاز بیشتری بگیری، Elo بیشتری می‌گیری.</li>
            <li>• برنده‌ها بالا می‌روند: تازه‌کار → رنک C → رنک B → حرفه‌ای → نابغه → استاد → اسطوره.</li>
          </ul>
        </div>

        <div className="study-section p-4 text-right">
          <div className="flex items-center justify-between mb-1.5">
            <p className="text-[13px] font-bold text-[var(--text)]">فیلتر دروس (اختیاری)</p>
            {wanted.length > 0 && (
              <button onClick={onClear} className="text-[11px] font-bold text-[var(--accent)]">پاک کردن</button>
            )}
          </div>
          <p className="text-[11px] text-[var(--muted-2)] leading-relaxed mb-3">
            هر تیک یک شرط حریف است: فقط با کسانی وصل می‌شوی که آن درس را خوانده‌اند.
            {filters?.major ? ` (رشته تو: ${filters.major}${filters.grade ? ` — پایه ${filters.grade}` : ""})` : ""}
          </p>

          {!filters ? (
            <p className="text-[11px] text-[var(--muted-2)]">در حال بارگذاری دروس...</p>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {(filters.all || []).map(subject => {
                const mine = (filters.mine || []).includes(subject)
                const on = wanted.includes(subject)
                return (
                  <label key={subject}
                    className={`flex items-center gap-2 px-2.5 py-2 rounded-xl border text-[11px] font-bold transition-all ${
                      !mine ? "border-[var(--border)] text-[var(--muted-2)] opacity-45"
                        : on ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                        : "border-[var(--border)] text-[var(--muted)]"
                    }`}>
                    <input type="checkbox" checked={on} disabled={!mine}
                      onChange={() => onToggle(subject)}
                      className="w-3.5 h-3.5 accent-[var(--accent)] flex-shrink-0" />
                    <span className="truncate">{subject}</span>
                  </label>
                )
              })}
            </div>
          )}

          {wanted.length > 0 && filters && (
            <div className="mt-3 pt-3 border-t border-[var(--border)] space-y-1">
              {wanted.map(subject => (
                <p key={subject} className="text-[11px] text-[var(--muted-2)] leading-relaxed">
                  <span className="font-bold text-[var(--muted)]">{subject}</span>{" → "}
                  حریف: {((filters.majors_with || {})[subject] || []).join("، ") || "—"}
                  {!(filters.addressable || []).includes(subject) && (
                    <span className="text-[10px]"> (درس آزمونی نیست؛ فقط حریف را محدود می‌کند)</span>
                  )}
                </p>
              ))}
              <p className="text-[10px] text-[var(--muted-2)] pt-1">
                هر تیک صف را محدودتر می‌کند، پس پیدا شدن حریف می‌تواند بیشتر طول بکشد.
              </p>
            </div>
          )}
        </div>

        {!!error && (
          <p className="text-[12px] font-bold text-red-500 text-center leading-relaxed">{error}</p>
        )}

        <button onClick={onJoin} disabled={busy}
          className="w-full py-4 rounded-2xl bg-[var(--accent)] text-white font-bold text-[14px] hover:brightness-110 active:scale-[0.99] transition-all disabled:opacity-50">
          {busy ? "در حال دریافت اطلاعات آرنا..." : "جستجوی حریف"}
        </button>
        <button onClick={onScheduled}
          className="w-full py-3.5 rounded-2xl border border-[var(--border-strong)] text-[13px] font-bold text-[var(--text)] flex items-center justify-center gap-2">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          مسابقه زمان‌دار (حریف آنلاین نیست؟)
        </button>
        <button onClick={onBoard}
          className="w-full py-3.5 rounded-2xl border border-[var(--border-strong)] text-[13px] font-bold text-[var(--muted)]">
          جدول امتیازات
        </button>
      </div>
    </div>
  )
}

/* ---------------- Queue ---------------- */

function Queue({ waited, onCancel, wanted, grade }: {
  waited: number
  onCancel: () => void
  wanted: string[]
  grade?: string
}) {
  const mins = Math.floor(waited / 60)
  const secs = waited % 60
  return (
    <div className="min-h-screen bg-[var(--surface)] flex flex-col items-center justify-center gap-5 px-6">
      <div className="relative w-24 h-24">
        <div className="absolute inset-0 rounded-full border-4 border-[var(--border)]" />
        <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-[var(--accent)] animate-spin" />
        <div className="absolute inset-0 flex items-center justify-center font-bold text-[var(--text)] tabular-nums" dir="ltr">
          {mins > 0 ? `${mins}:${String(secs).padStart(2, "0")}` : `${secs}s`}
        </div>
      </div>
      <div className="text-center space-y-2">
        <p className="text-[14px] font-bold text-[var(--text)]">در حال پیدا کردن حریف هم‌سطح...</p>
        <p className="text-[12px] text-[var(--muted-2)] text-center leading-relaxed">
          تا وقتی حریفی از سطح خودت که دانش مشترکی با تو داشته باشد در صف نباشد صبر می‌کنیم — مسابقه با ربات انجام نمی‌شود؛ هر چقدر طول بکشد.
        </p>
        {wanted.length > 0 && (
          <p className="text-[11px] font-bold text-[var(--accent)] leading-relaxed">
            فیلتر فعال: {wanted.join("، ")}
          </p>
        )}
        {grade && (
          <p className="text-[11px] text-[var(--muted-2)] font-bold">پایه دوئل: {grade}</p>
        )}
      </div>
      <button onClick={onCancel} className="px-6 py-2.5 rounded-xl border border-red-300 text-red-500 text-[12px] font-bold">
        انصراف
      </button>
    </div>
  )
}

/* ---------------- Duel runner ---------------- */

function DuelRunner({ match, onDone, onExit }: {
  match: MatchInfo
  onDone: (answers: Record<string, number | "">, seconds: number) => void
  onExit: () => void
}) {
  const [questions, setQuestions] = useState<AQ[]>([])
  const [current, setCurrent] = useState(0)
  const [answers, setAnswers] = useState<Record<string, number | "">>({})
  const [elapsed, setElapsed] = useState(0)
  const [bookletError, setBookletError] = useState("")
  const totalSec = (match.mock?.duration_minutes ?? 10) * 60
  const submittedRef = useRef(false)
  const answersRef = useRef(answers)
  answersRef.current = answers

  // The duel booklet is AI-generated right after the match is reserved, so
  // it can take a couple of minutes; poll until real questions arrive.
  useEffect(() => {
    let alive = true
    let loading = false
    const load = async () => {
      if (loading) return
      loading = true
      try {
        const d = await apiJson<{ questions: AQ[] }>(`/api/mocks/${match.mock_id}`)
        if (alive && d.questions?.length) { setQuestions(d.questions); setBookletError("") }
      } catch (e) {
        if (alive) setBookletError(e instanceof Error ? e.message : "دریافت سوال‌ها ناموفق بود.")
      } finally { loading = false }
    }
    load()
    const t = setInterval(load, 5000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [match.mock_id])

  useEffect(() => {
    if (!questions.length) return
    const t = setInterval(() => setElapsed(e => e + 1), 1000)
    return () => clearInterval(t)
  }, [questions.length])

  const submit = useCallback(() => {
    if (submittedRef.current) return
    submittedRef.current = true
    onDone(answersRef.current, elapsed)
  }, [elapsed, onDone])

  useEffect(() => {
    if (elapsed >= totalSec) submit()
  }, [elapsed, totalSec, submit])

  const q = questions[Math.min(current, questions.length - 1)]

  if (!questions.length) {
    return (
      <div className="min-h-screen bg-[var(--surface)] flex flex-col gap-4 items-center justify-center px-5">
        <div className="w-9 h-9 border-3 border-[var(--accent)] border-t-transparent rounded-full animate-spin" style={{ borderWidth: 3 }} />
        <p className="text-sm text-[var(--muted)]">در حال دریافت دفترچه مسابقه… زمان آزمون پس از دریافت سوال‌ها شروع می‌شود.</p>
        {bookletError && <p role="alert" className="text-sm text-red-500">{bookletError}</p>}
        <button onClick={onExit} className="text-sm text-[var(--accent)]">بازگشت به آرنا</button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--surface)] flex flex-col">
      <div className="bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-3">
        <div className="flex items-center gap-3">
          <div className="flex-1 text-right">
            <p className="text-[13px] font-bold text-[var(--text)]">{match.opponent}</p>
            <EloBadge elo={match.opponent_elo} size="sm" />
          </div>
          <div className={`px-3 py-1.5 rounded-xl font-bold text-[15px] tabular-nums ${totalSec - elapsed <= 60 ? "bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400" : "bg-[var(--accent-soft)] text-[var(--accent)]"}`}>
            {fmt(Math.max(0, totalSec - elapsed))}
          </div>
          <div className="text-left">
            <p className="text-[13px] font-bold text-[var(--text)]">تو</p>
            <EloBadge elo={match.your_elo} size="sm" />
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto px-4 py-5">
        <div className="max-w-[560px] mx-auto">
          <p className="text-[11px] font-bold text-[var(--muted-2)] mb-2">سوال {current + 1} از {questions.length} — {q.subject}</p>
          <p className="text-[15px] font-bold text-[var(--text)] leading-relaxed mb-5 text-right whitespace-pre-wrap"><RichText text={q.text} /></p>
          <QuestionFigure figure={q.figure} />
          {match.mock_id && <ReportQuestion key={q.id} mockId={match.mock_id} questionId={q.id} />}
          <div className="space-y-2.5">
            {q.options.map((opt, i) => {
              const sel = answers[String(q.id)] === i
              return (
                <button key={i} onClick={() => setAnswers(a => ({ ...a, [String(q.id)]: a[String(q.id)] === i ? "" : i }))}
                  className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-xl border text-right transition-all ${
                    sel ? "bg-[var(--accent-soft)] border-[var(--accent)] text-[var(--accent)]" : "bg-[var(--card)] border-[var(--border)] text-[var(--text)]"
                  }`}>
                  <span className="w-7 h-7 rounded-lg bg-[var(--chip)] flex items-center justify-center text-[11px] font-bold flex-shrink-0">{LABELS[i]}</span>
                  <span className="flex-1 text-[14px] font-medium"><RichText text={opt} /></span>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <div className="border-t border-[var(--border)] bg-[var(--card)] px-4 py-3">
        <div className="max-w-[560px] mx-auto flex items-center gap-2">
          <button onClick={() => setCurrent(c => Math.max(0, c - 1))} disabled={current === 0}
            className="px-4 h-10 rounded-xl border border-[var(--border-strong)] text-[13px] font-bold text-[var(--muted)] disabled:opacity-35">قبلی</button>
          <div className="flex-1 text-center text-[11px] text-[var(--muted-2)] font-bold">
            {Object.values(answers).filter(v => v !== "").length} پاسخ داده‌شده
          </div>
          {current < questions.length - 1 ? (
            <button onClick={() => setCurrent(c => c + 1)}
              className="px-6 h-10 rounded-xl bg-[var(--accent)] text-white text-[13px] font-bold">بعدی</button>
          ) : (
            <button onClick={submit}
              className="px-6 h-10 rounded-xl bg-[var(--accent)] text-white text-[13px] font-bold">پایان دوئل</button>
          )}
        </div>
      </div>
    </div>
  )
}

/* ---------------- Match result ---------------- */

function MatchResult({ match, onHome, onBoard }: { match: MatchInfo; onHome: () => void; onBoard: () => void }) {
  const delta = match.your_delta ?? 0
  return (
    <div className="min-h-screen bg-[var(--surface)] flex flex-col">
      <div className="px-4 pt-16 pb-6 text-center">
        <p className={`font-bold text-3xl mb-2 ${match.won ? "text-green-500" : match.your_score === match.opponent_score ? "text-[var(--muted)]" : "text-red-500"}`}>
          {match.won ? "🏆 بردی!" : match.your_score === match.opponent_score ? "مساوی" : "باختی"}
        </p>
        <p className="text-[13px] text-[var(--muted-2)] mb-1">حریف: {match.opponent}</p>
        {!!match.subjects?.length && (
          <p className="text-[11px] text-[var(--muted-2)]">دانش مشترک دوئل: {match.subjects.join("، ")}</p>
        )}
        <div className="h-5" />

        <div className="flex items-center justify-center gap-6 mb-6">
          <div>
            <p className="text-[34px] font-bold text-[var(--text)] tabular-nums">{match.your_score ?? 0}٪</p>
            <p className="text-[10px] text-[var(--muted-2)] font-bold">امتیاز تو</p>
          </div>
          <span className="text-[var(--muted-2)] font-bold">vs</span>
          <div>
            <p className="text-[34px] font-bold text-[var(--text)] tabular-nums">{match.opponent_score ?? 0}٪</p>
            <p className="text-[10px] text-[var(--muted-2)] font-bold">حریف</p>
          </div>
        </div>

        <div className="flex items-center justify-center gap-3">
          <EloBadge elo={match.your_elo} size="lg" />
          <span className={`text-[18px] font-bold tabular-nums ${delta >= 0 ? "text-green-500" : "text-red-500"}`} dir="ltr">
            {delta >= 0 ? "+" : ""}{delta}
          </span>
        </div>
      </div>

      <div className="px-4 max-w-[430px] mx-auto w-full space-y-3">
        <button onClick={onHome} className="w-full py-3.5 rounded-2xl bg-[var(--accent)] text-white font-bold text-[13px]">
          بازگشت به آرنا
        </button>
        <button onClick={onBoard} className="w-full py-3.5 rounded-2xl border border-[var(--border-strong)] text-[13px] font-bold text-[var(--muted)]">
          جدول امتیازات
        </button>
      </div>
    </div>
  )
}

/* ---------------- Leaderboard ---------------- */

function Board({ rows, onBack }: { rows: LeaderRow[]; onBack: () => void }) {
  return (
    <div className="min-h-screen bg-[var(--surface)]">
      <div className="bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-4 flex items-center gap-3">
        <button onClick={onBack} className="w-9 h-9 rounded-xl bg-[var(--border)] flex items-center justify-center text-[var(--muted)]">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
            <path d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
        </button>
        <p className="font-bold text-[15px] text-[var(--text)]">جدول امتیازات</p>
      </div>
      <div className="px-4 py-4 max-w-[560px] mx-auto space-y-2">
        {rows.length === 0 && (
          <p className="text-[13px] text-[var(--muted-2)] text-center py-8">هنوز مسابقه‌ای ثبت نشده. اولین نفر باش!</p>
        )}
        {rows.map(r => (
          <div key={r.user_id}
            className={`flex items-center gap-3 rounded-2xl border p-3.5 ${r.is_you ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--border)] bg-[var(--card)]"}`}>
            <span className={`w-8 text-center font-bold tabular-nums ${r.rank === 1 ? "text-yellow-500 text-[18px]" : r.rank <= 3 ? "text-[var(--accent)]" : "text-[var(--muted-2)]"}`}>
              {r.rank}
            </span>
            <div className="flex-1 text-right min-w-0">
              <p className="text-[13px] font-bold text-[var(--text)] truncate">
                {r.username} {r.is_you && <span className="text-[10px] text-[var(--accent)]">(تو)</span>}
              </p>
              <span className="text-[10px] font-bold" style={{ color: r.color }}>{r.title}</span>
            </div>
            <EloBadge elo={r.elo} color={r.color} size="sm" />
          </div>
        ))}
      </div>
    </div>
  )
}

/* ---------------- Scheduling lobby ---------------- */

function ScheduledView({ me, open, mine, quota, busyId, error, onCreate, onAccept, onCancel, onEnterMatch, onBack, defaultWhen }: {
  me: MeInfo | null
  open: ScheduledOpen[]
  mine: ScheduledMine[]
  quota: ScheduledQuota | null
  busyId: string | null
  error: string
  onCreate: (startsISO: string) => void
  onAccept: (id: number) => void
  onCancel: (id: number) => void
  onEnterMatch: (matchId: number) => void
  onBack: () => void
  defaultWhen: string
}) {
  const [when, setWhen] = useState(defaultWhen)
  // Which quick-slot is highlighted; null = custom time typed by hand.
  // "tomorrow-am" matches the Page's defaultWhen (tomorrow 10:00).
  const [activeChip, setActiveChip] = useState<string | null>("tomorrow-am")
  const whenValid = !Number.isNaN(new Date(when).getTime())
  return (
    <div className="min-h-screen bg-[var(--surface)]">
      <div className="bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-4 flex items-center gap-3">
        <button onClick={onBack} className="w-9 h-9 rounded-xl bg-[var(--border)] flex items-center justify-center text-[var(--muted)]">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
            <path d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
        </button>
        <div className="flex-1">
          <p className="font-bold text-[15px] text-[var(--text)]">مسابقه زمان‌دار</p>
          {me && <EloBadge elo={me.elo} title={me.title.name} color={me.title.color} size="sm" />}
        </div>
      </div>

      <div className="px-4 py-4 max-w-[560px] mx-auto space-y-5">
        {error && <p className="text-[12px] font-bold text-red-500 text-center leading-relaxed">{error}</p>}

        {quota && (
          <p className="text-[11px] text-[var(--muted-2)] bg-[var(--card)] rounded-xl border border-[var(--border)] px-3 py-2 text-center">
            {quota.remaining === null
              ? "سهمیه دوئل امروز: نامحدود"
              : quota.remaining > 0
                ? <>سهمیه دوئل امروز: <span className="font-bold text-[var(--text)]">{faNum(quota.remaining)} از {faNum(quota.limit)}</span> باقی مانده</>
                : "سهمیه دوئل امروز تمام شد — فردا دوباره!"}
          </p>
        )}

        {/* My booked duels */}
        <section>
          <p className="text-[13px] font-bold text-[var(--text)] mb-2">مسابقه‌های رزروشده من</p>
          {mine.length === 0 ? (
            <p className="study-section text-[12px] text-[var(--muted-2)] p-4 leading-relaxed">
              هنوز دوئلی رزرو نکرده‌ای. یک زمان پیشنهاد بده یا از فهرست زیر یکی را رزرو کن.
            </p>
          ) : (
            <div className="space-y-2">
              {mine.map(row => (
                <div key={row.match_id} className="study-section p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-right">
                      <p className="text-[13px] font-bold text-[var(--text)]">حریف: {row.opponent}</p>
                      <p className="text-[11px] text-[var(--muted-2)] mt-0.5">{fmtWhen(row.starts_at)}</p>
                    </div>
                    <span className={`px-2.5 py-1 rounded-lg text-[11px] font-bold ${row.seconds_until <= 0 ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400" : "bg-[var(--accent-soft)] text-[var(--accent)]"}`}>
                      {row.status === "pending" ? "شروع شد!" : countdown(row.seconds_until)}
                    </span>
                  </div>
                  <div className="flex gap-2 mt-3">
                    {row.status === "pending" ? (
                      <button onClick={() => onEnterMatch(row.match_id)} disabled={busyId === `enter-${row.match_id}`}
                        className="flex-1 py-2.5 rounded-xl bg-[var(--accent)] text-white text-[12px] font-bold disabled:opacity-50">
                        ورود به دوئل
                      </button>
                    ) : (
                      <span className="flex-1 py-2.5 text-center text-[11px] text-[var(--muted-2)] font-bold">
                        {row.you_booked ? "تو رزرو کردی" : "حریفت رزرو کرده"}
                      </span>
                    )}
                    <button onClick={() => onCancel(row.invite_id)} disabled={busyId === `cancel-${row.invite_id}`}
                      className="px-4 py-2.5 rounded-xl border border-red-300 text-red-500 text-[12px] font-bold disabled:opacity-50">
                      لغو
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Open invites */}
        <section>
          <p className="text-[13px] font-bold text-[var(--text)] mb-2">مسابقه‌های در انتظار حریف</p>
          {open.length === 0 ? (
            <p className="study-section text-[12px] text-[var(--muted-2)] p-4">
              فعلاً پیشنهادی در صف نیست — اولین نفر باش!
            </p>
          ) : (
            <div className="space-y-2">
              {open.map(row => (
                <div key={row.id} className="study-section p-3.5 flex items-center gap-3">
                  <div className="flex-1 text-right min-w-0">
                    <p className="text-[13px] font-bold text-[var(--text)] truncate">
                      {row.host} {row.is_mine && <span className="text-[10px] text-[var(--accent)]">(پیشنهاد تو)</span>}
                    </p>
                    <p className="text-[11px] text-[var(--muted-2)]">{fmtWhen(row.starts_at)}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <EloBadge elo={row.host_elo} size="sm" />
                      {row.wanted.length > 0 && (
                        <span className="text-[10px] text-[var(--muted-2)] font-bold truncate">فیلتر: {row.wanted.join("، ")}</span>
                      )}
                    </div>
                  </div>
                  {row.is_mine ? (
                    <button onClick={() => onCancel(row.id)} disabled={busyId === `cancel-${row.id}`}
                      className="px-4 py-2.5 rounded-xl border border-red-300 text-red-500 text-[12px] font-bold disabled:opacity-40 flex-shrink-0">
                      لغو
                    </button>
                  ) : (
                    <button onClick={() => onAccept(row.id)}
                      disabled={!row.can_accept || quota?.remaining === 0 || busyId === `accept-${row.id}`}
                      className="px-4 py-2.5 rounded-xl bg-[var(--accent)] text-white text-[12px] font-bold disabled:opacity-40 flex-shrink-0">
                      {!row.can_accept ? "سطح نامنطبق" : quota?.remaining === 0 ? "سهمیه تمام" : "رزرو"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Create an offer */}
        <section className="study-section p-4">
          <p className="text-[13px] font-bold text-[var(--text)] mb-1">پیشنهاد دوئل بده</p>
          <p className="text-[11px] text-[var(--muted-2)] leading-relaxed mb-3">
            فقط یک زمان را بزن؛ پیشنهادت در فهرست بالا می‌آید تا حریفی هم‌سطح آن را رزرو کند. در زمان مقرر دوئل برای هر دو شروع می‌شود.
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            {QUICK_SLOTS.map(slot => (
              <button key={slot.key}
                onClick={() => { const d = slot.at(); setWhen(localInputValue(d)); setActiveChip(slot.key) }}
                className={`px-3.5 py-2 rounded-xl text-[12px] font-bold border transition-colors ${
                  activeChip === slot.key
                    ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                    : "bg-[var(--surface)] text-[var(--text)] border-[var(--border-strong)]"}`}>
                {slot.label}
              </button>
            ))}
          </div>
          {whenValid && (
            <p className="text-[12px] font-bold text-[var(--accent)] mb-3 text-center">
              شروع دوئل: {fmtWhen(new Date(when).toISOString())}
            </p>
          )}
          <details className="mb-3">
            <summary className="text-[11px] text-[var(--muted-2)] cursor-pointer select-none">
              زمان دقیق دیگر…
            </summary>
            <input type="datetime-local" value={when} onChange={e => { setWhen(e.target.value); setActiveChip(null) }}
              className="mt-2 w-full px-3 py-2.5 rounded-xl border border-[var(--border-strong)] bg-[var(--surface)] text-[13px] text-[var(--text)] tabular-nums" />
          </details>
          <button onClick={() => onCreate(when)} disabled={busyId === "create" || !whenValid}
            className="w-full py-3 rounded-xl bg-[var(--accent)] text-white text-[13px] font-bold disabled:opacity-50">
            {busyId === "create" ? "..." : "ثبت پیشنهاد"}
          </button>
        </section>
      </div>
    </div>
  )
}

/* ---------------- Page ---------------- */

export default function Arena({ nav, userData, initialPhase }: {
  nav: NavFn
  userData?: SignupData | null
  /** Sub-panel entry: the جدول امتیازات tab opens the board directly. */
  initialPhase?: Phase
}) {
  const [phase, setPhase] = useState<Phase>(initialPhase ?? "lobby")
  const [me, setMe] = useState<MeInfo | null>(null)
  const [waited, setWaited] = useState(0)
  const [match, setMatch] = useState<MatchInfo | null>(null)
  const [board, setBoard] = useState<LeaderRow[]>([])
  const [error, setError] = useState("")
  // Duel subject filter: the checkbox list comes from the server, which is
  // also what enforces the ticks when it pairs players.
  const [filters, setFilters] = useState<FilterOptions | null>(null)
  const [loadingLobby, setLoadingLobby] = useState(true)
  const [lobbyError, setLobbyError] = useState("")
  const [lobbyRetry, setLobbyRetry] = useState(0)
  const [wanted, setWanted] = useState<string[]>([])
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Scheduled-duel lobby state.
  const [schedOpen, setSchedOpen] = useState<ScheduledOpen[]>([])
  const [schedMine, setSchedMine] = useState<ScheduledMine[]>([])
  const [schedQuota, setSchedQuota] = useState<ScheduledQuota | null>(null)
  const [schedBusy, setSchedBusy] = useState<string | null>(null)
  const [schedError, setSchedError] = useState("")
  const schedPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (schedPollRef.current) clearInterval(schedPollRef.current)
    }
  }, [])

  useEffect(() => {
    let alive = true
    setLoadingLobby(true)
    setLobbyError("")
    const major = userData?.major ? `?major=${encodeURIComponent(userData.major)}` : ""
    Promise.all([apiJson<MeInfo>("/api/arena/me"), apiJson<FilterOptions>(`/api/arena/filters${major}`)])
      .then(([identity, subjects]) => { if (alive) { setMe(identity); setFilters(subjects) } })
      .catch(e => { if (alive) setLobbyError(e instanceof Error ? e.message : "ارتباط با سرور برقرار نشد.") })
      .finally(() => { if (alive) setLoadingLobby(false) })
    return () => { alive = false }
  }, [userData?.major, lobbyRetry])

  function toggleWanted(subject: string) {
    setWanted(w => (w.includes(subject) ? w.filter(s => s !== subject) : [...w, subject]))
  }

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  const loadMatch = useCallback(async (id: number) => {
    return apiJson<MatchInfo>(`/api/arena/${id}`)
  }, [])

  const startPolling = useCallback((matchId: number) => {
    stopPoll()
    pollRef.current = setInterval(async () => {
      let m
      try { m = await loadMatch(matchId) }
      catch (e) { setError(e instanceof Error ? e.message : "دریافت مسابقه ناموفق بود."); return }
      if (!m) return
      setMatch(m)
      if (m.status === "cancelled") {
        stopPoll(); setPhase("lobby"); setError(m.generation_error || "سوال مسابقه گزارش شد؛ مسابقه بدون تغییر رتبه لغو شد."); return;
      }
      if (m.status === "finished") {
        stopPoll()
        setPhase("finished")
        fetch(apiUrl("/api/arena/me"), { headers: authHeaders() })
          .then(r => (r.ok ? r.json() : null))
          .then(setMe)
          .catch(() => {})
      }
    }, 2500)
  }, [loadMatch, stopPoll])

  async function join() {
    setPhase("queued")
    setWaited(0)
    setError("")
    try {
      const res = await fetch(apiUrl("/api/arena/join"), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(authHeaders() as Record<string, string>) },
        body: JSON.stringify({
          // The server prefers its own profile row; this is the offline-cache
          // fallback (the arena used to send nothing, so every duel booklet
          // was built from a hardcoded ریاضی فیزیک plan).
          student: userData ? { major: userData.major, grade: userData.grade } : undefined,
          wanted,
        }),
      })
      if (!res.ok) throw new Error(await readApiError(res, "ورود به صف ناموفق بود"))
      const data = await res.json()
      // The server may drop ticks that are not in the player's own subjects.
      if (Array.isArray(data.wanted)) setWanted(data.wanted)
      if (data.match_id) {
        const m = await loadMatch(data.match_id)
        if (m.status === "cancelled") throw new Error(m.generation_error || "مسابقه بدون تغییر رتبه لغو شد.")
        setMatch(m)
        setPhase("playing")
        startPolling(data.match_id)
        return
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطا")
      setPhase("lobby")
      return
    }
    pollRef.current = setInterval(async () => {
      setWaited(w => w + 2)
      try {
        const res = await fetch(apiUrl("/api/arena/status"), { headers: authHeaders() })
        if (!res.ok) throw new Error(await readApiError(res, "دریافت وضعیت صف ناموفق بود."))
        const s = await res.json()
        if (s.state === "matched" && s.match_id) {
          stopPoll()
          const m = await loadMatch(s.match_id)
          if (m.status === "cancelled") throw new Error(m.generation_error || "مسابقه بدون تغییر رتبه لغو شد.")
          setMatch(m)
          if (m?.mock?.duration_minutes) { setPhase("playing"); startPolling(s.match_id) }
        } else if (s.state === "idle") {
          stopPoll()
          setPhase("lobby")
        }
      } catch (e) {
        stopPoll(); setPhase("lobby"); setError(e instanceof Error ? e.message : "دریافت وضعیت صف ناموفق بود.")
      }
    }, 2000)
  }

  async function cancelQueue() {
    stopPoll()
    await fetch(apiUrl("/api/arena/leave"), { method: "POST", headers: authHeaders() }).catch(() => {})
    setPhase("lobby")
  }

  async function submitDuel(answers: Record<string, number | "">, seconds: number) {
    if (!match) return
    try {
      await fetch(apiUrl(`/api/arena/${match.match_id}/submit`), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(authHeaders() as Record<string, string>) },
        body: JSON.stringify({ answers, duration_seconds: seconds }),
      })
    } catch { /* ignore; results loaded below */ }
    const m = await loadMatch(match.match_id)
    if (m) {
      setMatch(m)
      if (m.status === "cancelled") {
        stopPoll(); setPhase("lobby"); setError("سوال مسابقه گزارش شد؛ مسابقه بدون تغییر رتبه لغو شد.");
      } else setPhase("finished")
    }
  }

  /* ---------------- scheduled duels ---------------- */

  const loadScheduled = useCallback(async () => {
    try {
      const res = await fetch(apiUrl("/api/arena/scheduled"), { headers: authHeaders() })
      if (!res.ok) return
      const data = await res.json()
      setSchedOpen(data.open ?? [])
      setSchedMine(data.mine ?? [])
      setSchedQuota(data.quota ?? null)
    } catch { /* keep last view */ }
  }, [])

  function openScheduled() {
    setSchedError("")
    setPhase("scheduled")
    loadScheduled()
    // Live countdowns + kickoff activation: refresh every 10s while open.
    if (schedPollRef.current) clearInterval(schedPollRef.current)
    schedPollRef.current = setInterval(loadScheduled, 10000)
  }

  function closeScheduled() {
    if (schedPollRef.current) { clearInterval(schedPollRef.current); schedPollRef.current = null }
    setPhase("lobby")
  }

  async function createInvite(localValue: string) {
    if (!localValue) return
    setSchedBusy("create")
    setSchedError("")
    try {
      // datetime-local is wall-clock LOCAL; send an explicit offset so the
      // server can normalize to UTC regardless of the VM's zone.
      const startsISO = new Date(localValue).toISOString()
      const res = await fetch(apiUrl("/api/arena/scheduled"), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(authHeaders() as Record<string, string>) },
        body: JSON.stringify({ starts_at: startsISO, wanted, student: userData ? { major: userData.major, grade: userData.grade } : undefined }),
      })
      if (!res.ok) throw new Error(await readApiError(res, "ثبت پیشنهاد ناموفق بود"))
      await loadScheduled()
    } catch (e) {
      setSchedError(e instanceof Error ? e.message : "خطا")
    } finally {
      setSchedBusy(null)
    }
  }

  async function acceptInvite(id: number) {
    setSchedBusy(`accept-${id}`)
    setSchedError("")
    try {
      const res = await fetch(apiUrl(`/api/arena/scheduled/${id}/accept`), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(authHeaders() as Record<string, string>) },
        body: JSON.stringify({ student: userData ? { major: userData.major, grade: userData.grade } : undefined, wanted }),
      })
      if (!res.ok) throw new Error(await readApiError(res, "رزرو ناموفق بود"))
      await loadScheduled()
    } catch (e) {
      setSchedError(e instanceof Error ? e.message : "خطا")
    } finally {
      setSchedBusy(null)
    }
  }

  async function cancelInvite(id: number) {
    setSchedBusy(`cancel-${id}`)
    setSchedError("")
    try {
      const res = await fetch(apiUrl(`/api/arena/scheduled/${id}`), { method: "DELETE", headers: authHeaders() })
      if (!res.ok) throw new Error(await readApiError(res, "لغو ناموفق بود"))
      await loadScheduled()
    } catch (e) {
      setSchedError(e instanceof Error ? e.message : "خطا")
    } finally {
      setSchedBusy(null)
    }
  }

  async function enterScheduledMatch(matchId: number) {
    setSchedBusy(`enter-${matchId}`)
    try {
      const m = await loadMatch(matchId)
      if (!m) return
      setMatch(m)
      setPhase("playing")
      if (schedPollRef.current) { clearInterval(schedPollRef.current); schedPollRef.current = null }
      startPolling(matchId)
    } finally {
      setSchedBusy(null)
    }
  }

  async function openBoard() {
    try {
      const res = await fetch(apiUrl("/api/arena/leaderboard"), { headers: authHeaders() })
      if (res.ok) setBoard(await res.json())
    } catch { /* empty board view */ }
    setPhase("board")
  }

  // Sub-panel entry: load the leaderboard once when opened from the tab.
  useEffect(() => { if (initialPhase === "board") void openBoard() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (phase === "queued") return <Queue waited={waited} onCancel={cancelQueue}
    wanted={wanted} grade={filters?.grade} />
  if (phase === "playing" && match) return <DuelRunner match={match} onDone={submitDuel} onExit={cancelQueue} />
  if (phase === "finished" && match) return <MatchResult match={match} onHome={() => setPhase("lobby")} onBoard={openBoard} />
  if (phase === "board") return <Board rows={board}
    onBack={() => { if (initialPhase === "board") nav("arena"); else setPhase("lobby") }} />
  if (phase === "scheduled") return <ScheduledView me={me} open={schedOpen} mine={schedMine}
    quota={schedQuota} busyId={schedBusy} error={schedError} onCreate={createInvite} onAccept={acceptInvite}
    onCancel={cancelInvite} onEnterMatch={enterScheduledMatch} onBack={closeScheduled}
    defaultWhen={localInputValue(dayAt(1, 10))} />

  return <><Lobby me={me} onJoin={join} onBoard={openBoard} busy={loadingLobby || !!lobbyError}
    filters={filters} wanted={wanted} onToggle={toggleWanted} onClear={() => setWanted([])}
    error={lobbyError || error} onScheduled={openScheduled} />
    {lobbyError && <div className="px-4 py-5 text-center"><button onClick={() => setLobbyRetry(n => n + 1)} className="text-sm text-[var(--accent)]">تلاش دوباره برای دریافت آرنا</button></div>}</>
}
