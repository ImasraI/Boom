import { useCallback, useEffect, useRef, useState } from "react"
import { NavFn } from "../types"
import { apiUrl, authHeaders, readApiError } from "../api"

type Phase = "lobby" | "queued" | "playing" | "finished" | "board"

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
}

interface AQ {
  id: number
  subject: string
  text: string
  options: string[]
}

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

function Lobby({ me, onJoin, onBoard, busy }: { me: MeInfo | null; onJoin: () => void; onBoard: () => void; busy: boolean }) {
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
        <div className="bg-[var(--card)] rounded-2xl border border-[var(--border)] p-5 text-right">
          <p className="text-[13px] font-bold text-[var(--text)] mb-2">چطور کار می‌کند؟</p>
          <ul className="text-[12px] text-[var(--muted-2)] leading-relaxed space-y-1.5">
            <li>• وارد صف شو؛ تا وقتی حریف هم‌سطح پیدا نشود در صف می‌مانی — بدون ربات.</li>
            <li>• هر دو یک دفترچه آزمون یکسان و کوتاه می‌گیرید، با زمان واقعی.</li>
            <li>• تصحیح با نمره منفی کنکور؛ امتیاز بیشتری بگیری، Elo بیشتری می‌گیری.</li>
            <li>• برنده‌ها بالا می‌روند: تازه‌کار → رنک C → رنک B → حرفه‌ای → نابغه → استاد → اسطوره.</li>
          </ul>
        </div>

        <button onClick={onJoin} disabled={busy}
          className="w-full py-4 rounded-2xl bg-[var(--accent)] text-white font-bold text-[14px] hover:brightness-110 active:scale-[0.99] transition-all disabled:opacity-50">
          {busy ? "در حال جستجوی حریف..." : "جستجوی حریف"}
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

function Queue({ waited, onCancel }: { waited: number; onCancel: () => void }) {
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
      <p className="text-[14px] font-bold text-[var(--text)]">در حال پیدا کردن حریف هم‌سطح...</p>
      <p className="text-[12px] text-[var(--muted-2)] text-center leading-relaxed">
        تا وقتی حریفی از سطح خودت در صف نباشد صبر می‌کنیم — مسابقه با ربات انجام نمی‌شود؛ هر چقدر طول بکشد.
      </p>
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
  const totalSec = (match.mock?.duration_minutes ?? 10) * 60
  const submittedRef = useRef(false)
  const answersRef = useRef(answers)
  answersRef.current = answers

  useEffect(() => {
    fetch(apiUrl(`/api/mocks/${match.mock_id}`), { headers: authHeaders() })
      .then(r => r.json())
      .then(d => setQuestions(d.questions || []))
      .catch(() => setQuestions([]))
  }, [match.mock_id])

  useEffect(() => {
    const t = setInterval(() => setElapsed(e => e + 1), 1000)
    return () => clearInterval(t)
  }, [])

  const submit = useCallback(() => {
    if (submittedRef.current) return
    submittedRef.current = true
    onDone(answersRef.current, elapsed)
  }, [elapsed, onDone])

  useEffect(() => {
    if (elapsed >= totalSec) submit()
  }, [elapsed, totalSec, submit])

  const q = questions[current]

  if (!questions.length) {
    return (
      <div className="min-h-screen bg-[var(--surface)] flex items-center justify-center">
        <div className="w-9 h-9 border-3 border-[var(--accent)] border-t-transparent rounded-full animate-spin" style={{ borderWidth: 3 }} />
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
          <p className="text-[15px] font-bold text-[var(--text)] leading-relaxed mb-5 text-right whitespace-pre-wrap">{q.text}</p>
          <div className="space-y-2.5">
            {q.options.map((opt, i) => {
              const sel = answers[String(q.id)] === i
              return (
                <button key={i} onClick={() => setAnswers(a => ({ ...a, [String(q.id)]: a[String(q.id)] === i ? "" : i }))}
                  className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-xl border text-right transition-all ${
                    sel ? "bg-[var(--accent-soft)] border-[var(--accent)] text-[var(--accent)]" : "bg-[var(--card)] border-[var(--border)] text-[var(--text)]"
                  }`}>
                  <span className="w-7 h-7 rounded-lg bg-[var(--chip)] flex items-center justify-center text-[11px] font-bold flex-shrink-0">{LABELS[i]}</span>
                  <span className="flex-1 text-[14px] font-medium">{opt}</span>
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
        <p className="text-[13px] text-[var(--muted-2)] mb-5">حریف: {match.opponent}</p>

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

/* ---------------- Page ---------------- */

export default function Arena({ nav }: { nav: NavFn }) {
  const [phase, setPhase] = useState<Phase>("lobby")
  const [me, setMe] = useState<MeInfo | null>(null)
  const [waited, setWaited] = useState(0)
  const [match, setMatch] = useState<MatchInfo | null>(null)
  const [board, setBoard] = useState<LeaderRow[]>([])
  const [error, setError] = useState("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    fetch(apiUrl("/api/arena/me"), { headers: authHeaders() })
      .then(r => (r.ok ? r.json() : null))
      .then(setMe)
      .catch(() => setMe(null))
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  const loadMatch = useCallback(async (id: number) => {
    const res = await fetch(apiUrl(`/api/arena/${id}`), { headers: authHeaders() })
    if (!res.ok) return null
    return res.json()
  }, [])

  const startPolling = useCallback((matchId: number) => {
    stopPoll()
    pollRef.current = setInterval(async () => {
      const m = await loadMatch(matchId)
      if (!m) return
      setMatch(m)
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
        body: JSON.stringify({}),
      })
      if (!res.ok) throw new Error(await readApiError(res, "ورود به صف ناموفق بود"))
      const data = await res.json()
      if (data.match_id) {
        setMatch(await loadMatch(data.match_id))
        setPhase("playing")
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
        if (!res.ok) return
        const s = await res.json()
        if (s.state === "matched" && s.match_id) {
          stopPoll()
          const m = await loadMatch(s.match_id)
          setMatch(m)
          if (m?.mock?.duration_minutes) setPhase("playing")
        } else if (s.state === "idle") {
          stopPoll()
          setPhase("lobby")
        }
      } catch { /* keep polling */ }
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
      setPhase("finished")
    }
  }

  async function openBoard() {
    try {
      const res = await fetch(apiUrl("/api/arena/leaderboard"), { headers: authHeaders() })
      if (res.ok) setBoard(await res.json())
    } catch { /* empty board view */ }
    setPhase("board")
  }

  if (phase === "queued") return <Queue waited={waited} onCancel={cancelQueue} />
  if (phase === "playing" && match) return <DuelRunner match={match} onDone={submitDuel} onExit={cancelQueue} />
  if (phase === "finished" && match) return <MatchResult match={match} onHome={() => setPhase("lobby")} onBoard={openBoard} />
  if (phase === "board") return <Board rows={board} onBack={() => setPhase("lobby")} />

  return <Lobby me={me} onJoin={join} onBoard={openBoard} busy={false} />
}
