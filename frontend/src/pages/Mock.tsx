import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { NavFn } from "../types"
import { apiUrl, authHeaders, readApiError } from "../api"
import { RichText } from "../richText"

type Phase = "config" | "loading" | "test" | "result"

interface MockQuestion {
  id: number
  subject: string
  topic?: string
  text: string
  options: string[]
}

interface MockInfo {
  mock_id: number
  title: string
  duration_minutes: number
  total_questions: number
  subjects: { name: string; questions: number; minutes: number }[]
}

interface ReviewQuestion extends MockQuestion {
  answer: number
  explanation?: string
  your_answer?: string | null
}

interface MockResult {
  attempt_id: number
  score: number
  raw_score: number
  correct: number
  wrong: number
  blank: number
  subjects: { name: string; score: number; correct: number; wrong: number; blank: number }[]
  review: ReviewQuestion[]
}

const LABELS = ["الف", "ب", "ج", "د"]
const DIFFICULTIES = [
  { id: "easy", label: "آسان" },
  { id: "konkur", label: "استاندارد کنکور" },
  { id: "hard", label: "سخت" },
]

function fmt(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
}

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-9 h-9 rounded-xl bg-[var(--border)] flex items-center justify-center text-[var(--muted)]">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
        <path d="M19 12H5M12 5l-7 7 7 7" />
      </svg>
    </button>
  )
}

/* ---------------- Config screen ---------------- */

function ConfigView({ onStart }: { onStart: (cfg: Record<string, unknown>) => void }) {
  const [difficulty, setDifficulty] = useState("konkur")
  const [count, setCount] = useState(0) // 0 = konkur standard
  const [topics, setTopics] = useState("")

  return (
    <div className="min-h-screen bg-[var(--surface)] pb-16">
      <div className="bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-4 flex items-center gap-3">
        <BackButton onClick={() => history.back()} />
        <div>
          <h1 className="font-bold text-lg text-[var(--text)]">آزمون آزمایشی هوشمند</h1>
          <p className="text-[11px] text-[var(--muted-2)]">دفترچه استاندارد کنکور از کتاب‌های خودت</p>
        </div>
      </div>

      <div className="px-4 mt-5 space-y-4 max-w-[430px] mx-auto">
        <div className="bg-[var(--card)] rounded-2xl border border-[var(--border)] p-4">
          <p className="text-[12px] font-bold text-[var(--muted)] mb-2.5">سطح دشواری</p>
          <div className="grid grid-cols-3 gap-2">
            {DIFFICULTIES.map(d => (
              <button key={d.id} onClick={() => setDifficulty(d.id)}
                className={`py-2.5 rounded-xl text-[12px] font-bold border transition-colors ${
                  difficulty === d.id
                    ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                    : "border-[var(--border-strong)] text-[var(--muted)]"
                }`}>
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-[var(--card)] rounded-2xl border border-[var(--border)] p-4">
          <p className="text-[12px] font-bold text-[var(--muted)] mb-2.5">تعداد سوال هر درس</p>
          <div className="grid grid-cols-3 gap-2">
            {[0, 5, 10].map(n => (
              <button key={n} onClick={() => setCount(n)}
                className={`py-2.5 rounded-xl text-[12px] font-bold border transition-colors ${
                  count === n
                    ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                    : "border-[var(--border-strong)] text-[var(--muted)]"
                }`}>
                {n === 0 ? "استاندارد کنکور" : `${n} سوال`}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-[var(--card)] rounded-2xl border border-[var(--border)] p-4">
          <p className="text-[12px] font-bold text-[var(--muted)] mb-2">مباحث هدف (اختیاری)</p>
          <textarea rows={2} value={topics} onChange={e => setTopics(e.target.value)}
            placeholder="مثلاً: حرکت‌شناسی، اثر داپلر، استوکیومتری — هر مبحث در یک خط"
            className="w-full border rounded-xl px-3 py-2.5 text-[13px] text-right bg-[var(--card)] text-[var(--text)] resize-none leading-relaxed" />
          <p className="text-[10px] text-[var(--muted-2)] mt-1.5">خالی بگذاری، سوالات از کل مباحث کنکوری می‌آید. مباحث آزمون ماز این هفته خودکار در اولویت است.</p>
        </div>

        <button onClick={() => onStart({ difficulty, questions_per_subject: count || undefined, topics: topics.trim() ? topics.split("\n").map(t => t.trim()).filter(Boolean) : [] })}
          className="w-full py-4 rounded-2xl bg-[var(--accent)] text-white font-bold text-[14px] hover:brightness-110 active:scale-[0.99] transition-all">
          ساخت دفترچه آزمون
        </button>
        <p className="text-[11px] text-[var(--muted-2)] text-center leading-relaxed">
          تصحیح با نمره منفی کنکور (هر ۳ غلط، ۱ درست را حذف می‌کند) — بعد از آزمون، تحلیل کامل هر سوال را می‌بینی و غلط‌ها در برنامه هفتگی‌ات لحاظ می‌شود.
        </p>
      </div>
    </div>
  )
}

/* ---------------- Timed test runner ---------------- */

function TestRunner({ info, questions, onFinish, onExit }: {
  info: MockInfo
  questions: MockQuestion[]
  onFinish: (answers: Record<string, number | "">, seconds: number) => void
  onExit: () => void
}) {
  const [current, setCurrent] = useState(0)
  const [answers, setAnswers] = useState<Record<string, number | "">>({})
  const [showSheet, setShowSheet] = useState(false)
  const [remaining, setRemaining] = useState(info.duration_minutes * 60)
  const submittedRef = useRef(false)
  const answersRef = useRef(answers)
  answersRef.current = answers

  const submit = useCallback(() => {
    if (submittedRef.current) return
    submittedRef.current = true
    onFinish(answersRef.current, info.duration_minutes * 60 - remaining)
  }, [info.duration_minutes, onFinish, remaining])

  useEffect(() => {
    const t = setInterval(() => {
      setRemaining(r => {
        if (r <= 1) {
          clearInterval(t)
          submit()
          return 0
        }
        return r - 1
      })
    }, 1000)
    return () => clearInterval(t)
  }, [submit])

  const q = questions[current]
  const answered = useMemo(
    () => Object.entries(answers).filter(([, v]) => v !== "" && v !== undefined).length,
    [answers],
  )
  const danger = remaining <= 300

  function pick(i: number) {
    setAnswers(a => ({ ...a, [String(q.id)]: a[String(q.id)] === i ? "" : i }))
  }

  return (
    <div className="min-h-screen bg-[var(--surface)] flex flex-col">
      {/* header */}
      <div className="bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-3 sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <BackButton onClick={onExit} />
          <div className="flex-1 text-right">
            <p className="text-[13px] font-bold text-[var(--text)]">{info.title}</p>
            <p className="text-[10px] text-[var(--muted-2)]">{q?.subject} — سوال {current + 1} از {questions.length}</p>
          </div>
          <div className={`px-3 py-1.5 rounded-xl font-bold text-[15px] tabular-nums ${danger ? "bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400" : "bg-[var(--accent-soft)] text-[var(--accent)]"}`}>
            {fmt(remaining)}
          </div>
        </div>
      </div>

      {/* question */}
      <div className="flex-1 overflow-auto px-4 py-5">
        <div className="max-w-[560px] mx-auto">
          {q?.topic && (
            <span className="inline-block px-2.5 py-1 rounded-lg bg-[var(--chip)] text-[var(--muted)] text-[10px] font-bold mb-3">{q.topic}</span>
          )}
          <p className="text-[15px] font-bold text-[var(--text)] leading-relaxed mb-5 text-right whitespace-pre-wrap"><RichText text={q?.text ?? ""} /></p>
          <div className="space-y-2.5">
            {q?.options.map((opt, i) => {
              const sel = answers[String(q.id)] === i
              return (
                <button key={i} onClick={() => pick(i)}
                  className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-xl border text-right transition-all ${
                    sel ? "bg-[var(--accent-soft)] border-[var(--accent)] text-[var(--accent)]" : "bg-[var(--card)] border-[var(--border)] text-[var(--text)] hover:border-[var(--border-strong)]"
                  }`}>
                  <span className="w-7 h-7 rounded-lg bg-[var(--chip)] flex items-center justify-center text-[11px] font-bold flex-shrink-0">{LABELS[i]}</span>
                  <span className="flex-1 text-[14px] font-medium"><RichText text={opt} /></span>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* footer nav */}
      <div className="border-t border-[var(--border)] bg-[var(--card)] px-4 py-3">
        <div className="max-w-[560px] mx-auto flex items-center gap-2">
          <button onClick={() => setCurrent(c => Math.max(0, c - 1))} disabled={current === 0}
            className="px-4 h-10 rounded-xl border border-[var(--border-strong)] text-[13px] font-bold text-[var(--muted)] disabled:opacity-35">
            قبلی
          </button>
          <button onClick={() => setShowSheet(true)}
            className="px-4 h-10 rounded-xl border border-[var(--border-strong)] text-[12px] font-bold text-[var(--muted)]">
            پاسخ‌برگ ({answered}/{questions.length})
          </button>
          <div className="flex-1" />
          {current < questions.length - 1 ? (
            <button onClick={() => setCurrent(c => c + 1)}
              className="px-6 h-10 rounded-xl bg-[var(--accent)] text-white text-[13px] font-bold">
              بعدی
            </button>
          ) : (
            <button onClick={submit}
              className="px-6 h-10 rounded-xl bg-[var(--accent)] text-white text-[13px] font-bold">
              پایان و تصحیح
            </button>
          )}
        </div>
      </div>

      {/* answer sheet */}
      {showSheet && (
        <div className="fixed inset-0 bg-black/40 z-40 flex items-end justify-center" onClick={() => setShowSheet(false)}>
          <div className="w-full max-w-[430px] bg-[var(--card)] rounded-t-3xl p-5 pb-10 max-h-[70vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <button onClick={submit} className="px-4 h-9 rounded-xl bg-[var(--accent)] text-white text-[12px] font-bold">پایان آزمون</button>
              <p className="text-[13px] font-bold text-[var(--text)]">پاسخ‌برگ — {answered} از {questions.length} پر شده</p>
            </div>
            <div className="grid grid-cols-8 gap-1.5">
              {questions.map((qq, i) => {
                const a = answers[String(qq.id)]
                const done = a !== "" && a !== undefined
                return (
                  <button key={qq.id} onClick={() => { setCurrent(i); setShowSheet(false) }}
                    className={`h-9 rounded-lg text-[11px] font-bold ${
                      i === current ? "ring-2 ring-[var(--accent)] " : ""
                    }${done ? "bg-[var(--accent-soft)] text-[var(--accent)]" : "bg-[var(--chip)] text-[var(--muted)]"}`}>
                    {i + 1}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ---------------- Result / analysis ---------------- */

function ResultView({ result, onBack, onRetry }: { result: MockResult; onBack: () => void; onRetry: () => void }) {
  const [tab, setTab] = useState<"summary" | "review">("summary")
  const pctColor = result.score >= 70 ? "text-green-500" : result.score >= 40 ? "text-[var(--accent)]" : "text-red-500"

  return (
    <div className="min-h-screen bg-[var(--surface)]">
      <div className="bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-4">
        <div className="flex items-center gap-3 mb-4">
          <BackButton onClick={onBack} />
          <p className="font-bold text-[15px] text-[var(--text)]">نتیجه و تحلیل آزمون</p>
        </div>
        <div className="flex items-center gap-5">
          <div className="text-left">
            <p className={`text-[44px] font-bold leading-none ${pctColor}`}>{result.score}٪</p>
            <p className="text-[10px] text-[var(--muted-2)] mt-1">نمره با احتساب نمره منفی</p>
          </div>
          <div className="flex-1 flex gap-4 justify-end text-[12px] font-bold">
            <span className="text-green-600 dark:text-green-400">✓ {result.correct} درست</span>
            <span className="text-red-500">✗ {result.wrong} غلط</span>
            <span className="text-[var(--muted)]">— {result.blank} نزده</span>
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          {(["summary", "review"] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`flex-1 py-2 rounded-xl text-[12px] font-bold border ${
                tab === t ? "bg-[var(--accent)] text-white border-[var(--accent)]" : "border-[var(--border-strong)] text-[var(--muted)]"
              }`}>
              {t === "summary" ? "خلاصه دروس" : "تحلیل سوال‌به‌سوال"}
            </button>
          ))}
        </div>
      </div>

      <div className="px-4 py-4 max-w-[560px] mx-auto space-y-3">
        {tab === "summary" ? (
          <>
            {result.subjects.map(s => (
              <div key={s.name} className="bg-[var(--card)] rounded-2xl border border-[var(--border)] p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[12px] font-bold">{s.score}٪</span>
                  <p className="text-[13px] font-bold text-[var(--text)]">{s.name}</p>
                </div>
                <div className="h-1.5 bg-[var(--border)] rounded-full overflow-hidden mb-2">
                  <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${Math.max(0, Math.min(100, s.score))}%` }} />
                </div>
                <div className="flex gap-3 text-[11px] text-[var(--muted-2)] font-bold" dir="ltr">
                  <span className="text-green-600 dark:text-green-400">✓ {s.correct}</span>
                  <span className="text-red-500">✗ {s.wrong}</span>
                  <span>— {s.blank}</span>
                </div>
              </div>
            ))}
            <div className="bg-[#FFF5F0] dark:bg-[#3A2A1A] rounded-2xl border border-[#F5DDD0] p-4">
              <p className="text-[12px] font-bold text-[#C4714A] mb-1.5">چه اتفاقی در برنامه‌ات می‌افتد</p>
              <p className="text-[12px] text-[var(--text)] leading-relaxed text-right">
                غلط‌ها و نزده‌های این آزمون با درس و مبحث ثبت شد. دفعه بعد که برنامه هفتگی بسازی، بوم برای همین مباحث بلوک تست اختصاصی با بازه صفحه و شماره تست می‌گذارد.
              </p>
            </div>
            <button onClick={onRetry} className="w-full py-3.5 rounded-2xl border border-[var(--border-strong)] text-[13px] font-bold text-[var(--muted)]">
              آزمون جدید بساز
            </button>
          </>
        ) : (
          result.review.map((q, i) => {
            const yours = q.your_answer === "" || q.your_answer === null || q.your_answer === undefined ? null : Number(q.your_answer)
            const ok = yours !== null && yours === q.answer
            const blankQ = yours === null
            return (
              <div key={q.id} className={`rounded-2xl border p-4 ${
                ok ? "border-green-300 dark:border-green-700 bg-green-50/50 dark:bg-green-900/10"
                : blankQ ? "border-[var(--border)] bg-[var(--card)]"
                : "border-red-300 dark:border-red-700 bg-red-50/50 dark:bg-red-900/10"
              }`}>
                <div className="flex items-start gap-2 mb-2">
                  <span className={`w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold flex-shrink-0 ${
                    ok ? "bg-green-500 text-white" : blankQ ? "bg-[var(--chip)] text-[var(--muted)]" : "bg-red-500 text-white"
                  }`}>{ok ? "✓" : blankQ ? "—" : "✗"}</span>
                  <p className="flex-1 text-[13px] font-bold text-[var(--text)] leading-relaxed text-right">
                    <span className="text-[var(--muted-2)]">{i + 1}. [{q.subject}] </span><RichText text={q.text} />
                  </p>
                </div>
                <div className="space-y-1.5 pr-8">
                  {q.options.map((opt, oi) => (
                    <p key={oi} className={`text-[12px] font-medium ${
                      oi === q.answer ? "text-green-600 dark:text-green-400 font-bold"
                      : oi === yours ? "text-red-500"
                      : "text-[var(--muted-2)]"
                    }`}>
                      {LABELS[oi]}. <RichText text={opt} /> {oi === q.answer ? "← پاسخ صحیح" : oi === yours ? "← پاسخ تو" : ""}
                    </p>
                  ))}
                  {q.explanation && (
                    <p className="text-[12px] text-[var(--text)] leading-relaxed bg-[var(--surface-2)] rounded-xl p-3 mt-2 text-right">
                      <span className="font-bold text-[var(--accent)]">راه‌حل: </span><RichText text={q.explanation} />
                    </p>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

/* ---------------- Page ---------------- */

export default function Mock({ nav }: { nav: NavFn }) {
  const [phase, setPhase] = useState<Phase>("config")
  const [info, setInfo] = useState<MockInfo | null>(null)
  const [questions, setQuestions] = useState<MockQuestion[]>([])
  const [result, setResult] = useState<MockResult | null>(null)
  const [error, setError] = useState("")

  async function start(cfg: Record<string, unknown>) {
    setPhase("loading")
    setError("")
    try {
      const res = await fetch(apiUrl("/api/mocks/generate"), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(authHeaders() as Record<string, string>) },
        body: JSON.stringify(cfg),
      })
      if (!res.ok) throw new Error(await readApiError(res, "ساخت آزمون ناموفق بود"))
      const data: MockInfo = await res.json()
      const qRes = await fetch(apiUrl(`/api/mocks/${data.mock_id}`), {
        headers: authHeaders(),
      })
      if (!qRes.ok) throw new Error(await readApiError(qRes, "دریافت دفترچه ناموفق بود"))
      const qData = await qRes.json()
      setInfo(data)
      setQuestions(qData.questions)
      setPhase("test")
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطای نامشخص")
      setPhase("config")
    }
  }

  async function finish(answers: Record<string, number | "">, seconds: number) {
    if (!info) return
    try {
      const res = await fetch(apiUrl(`/api/mocks/${info.mock_id}/submit`), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(authHeaders() as Record<string, string>) },
        body: JSON.stringify({ answers: Object.fromEntries(Object.entries(answers).map(([k, v]) => [k, v === "" ? "" : v])), duration_seconds: seconds }),
      })
      if (res.ok) {
        setResult(await res.json())
        setPhase("result")
        return
      }
    } catch { /* fall through to local scoring below */ }
    // Network failed mid-exam: keep the user unstuck with a local score.
    setPhase("config")
  }

  if (phase === "loading") {
    return (
      <div className="min-h-screen bg-[var(--surface)] flex flex-col items-center justify-center gap-4">
        <div className="w-10 h-10 border-3 border-[var(--accent)] border-t-transparent rounded-full animate-spin" style={{ borderWidth: 3 }} />
        <p className="text-[13px] font-bold text-[var(--muted)]">در حال ساخت دفترچه از کتاب‌های تو...</p>
        <p className="text-[11px] text-[var(--muted-2)]">حدود یک دقیقه طول می‌کشد</p>
      </div>
    )
  }

  if (phase === "test" && info && questions.length) {
    return (
      <TestRunner
        info={info}
        questions={questions}
        onFinish={finish}
        onExit={() => setPhase("config")}
      />
    )
  }

  if (phase === "result" && result) {
    return (
      <ResultView
        result={result}
        onBack={() => { setResult(null); setPhase("config") }}
        onRetry={() => { setResult(null); setPhase("config") }}
      />
    )
  }

  return <ConfigView onStart={start} />
}
