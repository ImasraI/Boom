import { useState, useEffect, useRef, useCallback } from "react"
import { NavFn } from "../types"
import { SUBJECT_TESTS, SubjectTest, Question } from "../questions"

type Phase = "select" | "test" | "result"

interface AnswerRecord {
  questionIndex: number
  selected: number | null
  correct: boolean
}

function formatTime(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
}

function SubjectCard({ test, onClick }: { test: SubjectTest; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="relative overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 text-right transition-all hover:shadow-lg hover:scale-[1.02] active:scale-[0.98]"
    >
      <div className="flex items-center gap-4">
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl font-bold flex-shrink-0"
          style={{ backgroundColor: test.color + "20", color: test.color }}
        >
          {test.icon}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-[var(--text)] text-[15px]">{test.name}</p>
          <p className="text-[12px] text-[var(--muted)] mt-0.5">{test.questions.length} سوال</p>
        </div>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted-2)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
          <path d="M9 18l6-6-6-6" />
        </svg>
      </div>
    </button>
  )
}

function TimerBar({ elapsed, total }: { elapsed: number; total: number }) {
  const pct = total > 0 ? (elapsed / total) * 100 : 0
  const mins = Math.floor(elapsed / 60)
  return (
    <div className="flex items-center gap-2">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
      <span className="text-[13px] font-bold text-[var(--muted)] tabular-nums">{formatTime(elapsed)}</span>
      {total > 0 && (
        <div className="flex-1 h-1 bg-[var(--border)] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full bg-[var(--accent)] transition-all duration-1000"
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
      )}
    </div>
  )
}

function QuestionNav({
  questions,
  answers,
  current,
  onSelect,
}: {
  questions: Question[]
  answers: (number | null)[]
  current: number
  onSelect: (i: number) => void
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {questions.map((_, i) => {
        const answered = answers[i] !== null
        const isCorrect = answered && answers[i] === questions[i].answer
        const isWrong = answered && answers[i] !== questions[i].answer
        const isCurrent = i === current
        return (
          <button
            key={i}
            onClick={() => onSelect(i)}
            className={`w-8 h-8 rounded-lg text-[11px] font-bold transition-all ${
              isCurrent
                ? "bg-[var(--accent)] text-white scale-110 shadow-md"
                : isCorrect
                ? "bg-green-500/20 text-green-600 dark:text-green-400 border border-green-500/30"
                : isWrong
                ? "bg-red-500/20 text-red-600 dark:text-red-400 border border-red-500/30"
                : answered
                ? "bg-[var(--accent-soft)] text-[var(--accent)] border border-[var(--accent-soft-border)]"
                : "bg-[var(--chip)] text-[var(--muted)] border border-[var(--border)]"
            }`}
          >
            {i + 1}
          </button>
        )
      })}
    </div>
  )
}

function OptionButton({
  index,
  label,
  selected,
  revealed,
  correctIndex,
  onClick,
}: {
  index: number
  label: string
  selected: number | null
  revealed: boolean
  correctIndex: number
  onClick: () => void
}) {
  const isSelected = selected === index
  const isCorrect = index === correctIndex

  let bg = "bg-[var(--card)] border-[var(--border)]"
  let text = "text-[var(--text)]"
  let border = "border"

  if (revealed) {
    if (isCorrect) {
      bg = "bg-green-50 dark:bg-green-900/30"
      border = "border-green-400 dark:border-green-600"
      text = "text-green-700 dark:text-green-300"
    } else if (isSelected && !isCorrect) {
      bg = "bg-red-50 dark:bg-red-900/30"
      border = "border-red-400 dark:border-red-600"
      text = "text-red-700 dark:text-red-300"
    }
  } else if (isSelected) {
    bg = "bg-[var(--accent-soft)]"
    border = "border-[var(--accent)]"
    text = "text-[var(--accent)]"
  }

  const labels = ["الف", "ب", "ج", "د"]
  return (
    <button
      onClick={onClick}
      disabled={revealed}
      className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-xl border transition-all text-right ${bg} ${text} ${border} ${!revealed ? "hover:scale-[1.01] active:scale-[0.99]" : ""}`}
    >
      <span className="w-7 h-7 rounded-lg bg-[var(--chip)] flex items-center justify-center text-[11px] font-bold flex-shrink-0">
        {labels[index]}
      </span>
      <span className="flex-1 text-[14px] font-medium">{label}</span>
      {revealed && isCorrect && (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-green-500 flex-shrink-0">
          <path d="M20 6L9 17l-5-5" />
        </svg>
      )}
      {revealed && isSelected && !isCorrect && (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-red-500 flex-shrink-0">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      )}
    </button>
  )
}

function TestView({
  test,
  onBack,
  onFinish,
}: {
  test: SubjectTest
  onBack: () => void
  onFinish: (answers: (number | null)[], timeSeconds: number) => void
}) {
  const [current, setCurrent] = useState(0)
  const [answers, setAnswers] = useState<(number | null)[]>(
    () => new Array(test.questions.length).fill(null)
  )
  const [selected, setSelected] = useState<number | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  const q = test.questions[current]

  const handleSelect = useCallback(
    (idx: number) => {
      if (revealed) return
      setSelected(idx)
    },
    [revealed]
  )

  const handleCheck = useCallback(() => {
    if (selected === null || revealed) return
    setRevealed(true)
    setAnswers((prev) => {
      const next = [...prev]
      next[current] = selected
      return next
    })
  }, [selected, revealed, current])

  const handleNext = useCallback(() => {
    if (current < test.questions.length - 1) {
      setCurrent((c) => c + 1)
      setSelected(answers[current + 1])
      setRevealed(answers[current + 1] !== null)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
      onFinish(answers, elapsed)
    }
  }, [current, test.questions.length, answers, elapsed, onFinish])

  const handlePrev = useCallback(() => {
    if (current > 0) {
      setCurrent((c) => c - 1)
      setSelected(answers[current - 1])
      setRevealed(answers[current - 1] !== null)
    }
  }, [current, answers])

  const answeredCount = answers.filter((a) => a !== null).length
  const correctCount = answers.filter(
    (a, i) => a !== null && a === test.questions[i].answer
  ).length

  return (
    <div className="h-full flex flex-col bg-[var(--surface)]">
      <div className="bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-3">
        <div className="flex items-center gap-3 mb-3">
          <button
            onClick={onBack}
            className="w-9 h-9 rounded-xl bg-[var(--border)] flex items-center justify-center text-[var(--muted)]"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
          <div className="flex-1 text-right">
            <p className="font-bold text-[var(--text)] text-[15px]">{test.name}</p>
          </div>
          <span className="text-[12px] text-[var(--muted)] font-medium tabular-nums">
            {answeredCount}/{test.questions.length}
          </span>
        </div>
        <TimerBar elapsed={elapsed} total={0} />
        <div className="mt-3">
          <QuestionNav questions={test.questions} answers={answers} current={current} onSelect={setCurrent} />
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        <div className="mb-4">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] text-[11px] font-bold">
            سوال {current + 1} از {test.questions.length}
          </span>
        </div>
        <p className="text-[15px] font-bold text-[var(--text)] leading-relaxed mb-5 text-right">
          {q.question}
        </p>
        <div className="space-y-2.5">
          {q.options.map((opt, i) => (
            <OptionButton
              key={i}
              index={i}
              label={opt}
              selected={selected}
              revealed={revealed}
              correctIndex={q.answer}
              onClick={() => handleSelect(i)}
            />
          ))}
        </div>
      </div>

      <div className="border-t border-[var(--border)] bg-[var(--card)] px-4 py-3 flex items-center gap-2">
        <button
          onClick={handlePrev}
          disabled={current === 0}
          className="px-4 h-10 rounded-xl border border-[var(--border-strong)] text-[13px] font-bold text-[var(--muted)] disabled:opacity-35 hover:text-[var(--text)] transition-colors"
        >
          قبلی
        </button>
        <div className="flex-1" />
        {!revealed ? (
          <button
            onClick={handleCheck}
            disabled={selected === null}
            className="px-6 h-10 rounded-xl bg-[var(--accent)] text-white text-[13px] font-bold disabled:opacity-40 hover:brightness-110 transition-all"
          >
            بررسی
          </button>
        ) : current < test.questions.length - 1 ? (
          <button
            onClick={handleNext}
            className="px-6 h-10 rounded-xl bg-[var(--accent)] text-white text-[13px] font-bold hover:brightness-110 transition-all"
          >
            بعدی
          </button>
        ) : (
          <button
            onClick={() => {
              if (timerRef.current) clearInterval(timerRef.current)
              onFinish(answers, elapsed)
            }}
            className="px-6 h-10 rounded-xl bg-[var(--accent)] text-white text-[13px] font-bold hover:brightness-110 transition-all"
          >
            پایان آزمون
          </button>
        )}
      </div>
    </div>
  )
}

function ResultView({
  test,
  answers,
  timeSeconds,
  onBack,
  onRetry,
}: {
  test: SubjectTest
  answers: (number | null)[]
  timeSeconds: number
  onBack: () => void
  onRetry: () => void
}) {
  const correct = answers.filter(
    (a, i) => a !== null && a === test.questions[i].answer
  ).length
  const wrong = answers.filter(
    (a, i) => a !== null && a !== test.questions[i].answer
  ).length
  const blank = answers.filter((a) => a === null).length
  const total = test.questions.length
  const pct = Math.round((correct / total) * 100)
  const grade =
    pct >= 90 ? "عالی" : pct >= 70 ? "خوب" : pct >= 50 ? "متوسط" : "ضعیف"
  const gradeColor =
    pct >= 90
      ? "text-green-500"
      : pct >= 70
      ? "text-[var(--accent)]"
      : pct >= 50
      ? "text-yellow-500"
      : "text-red-500"

  return (
    <div className="h-full flex flex-col bg-[var(--surface)]">
      <div className="bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-4">
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={onBack}
            className="w-9 h-9 rounded-xl bg-[var(--border)] flex items-center justify-center text-[var(--muted)]"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
          <p className="font-bold text-[var(--text)] text-[15px]">نتیجه {test.name}</p>
        </div>

        <div className="flex items-center gap-4">
          <div className="relative w-20 h-20 flex-shrink-0">
            <svg width="80" height="80" viewBox="0 0 80 80">
              <circle cx="40" cy="40" r="34" fill="none" stroke="var(--border)" strokeWidth="6" />
              <circle
                cx="40"
                cy="40"
                r="34"
                fill="none"
                stroke={pct >= 70 ? "var(--accent)" : pct >= 50 ? "#EAB308" : "#EF4444"}
                strokeWidth="6"
                strokeDasharray={`${(pct / 100) * 213.6} 213.6`}
                strokeLinecap="round"
                transform="rotate(-90 40 40)"
                className="transition-all duration-1000"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[18px] font-bold text-[var(--text)]">{pct}%</span>
            </div>
          </div>
          <div className="flex-1 space-y-1.5">
            <p className={`text-[16px] font-bold ${gradeColor}`}>{grade}</p>
            <div className="flex items-center gap-3 text-[12px]">
              <span className="flex items-center gap-1 text-green-600 dark:text-green-400 font-bold">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                {correct} درست
              </span>
              <span className="flex items-center gap-1 text-red-600 dark:text-red-400 font-bold">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                {wrong} غلط
              </span>
              <span className="flex items-center gap-1 text-[var(--muted)] font-bold">
                {blank} نزده
              </span>
            </div>
            <p className="text-[11px] text-[var(--muted)] font-medium">
              زمان: {formatTime(timeSeconds)} | میانگین: {formatTime(Math.round(timeSeconds / total))}/سوال
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-3">
        <p className="text-[13px] font-bold text-[var(--muted)] mb-2">جزئیات پاسخ‌ها</p>
        {test.questions.map((q, i) => {
          const userAns = answers[i]
          const isCorrect = userAns !== null && userAns === q.answer
          const isWrong = userAns !== null && userAns !== q.answer
          const labels = ["الف", "ب", "ج", "د"]
          return (
            <div
              key={i}
              className={`rounded-xl border p-3.5 ${
                isCorrect
                  ? "border-green-300 dark:border-green-700 bg-green-50/50 dark:bg-green-900/15"
                  : isWrong
                  ? "border-red-300 dark:border-red-700 bg-red-50/50 dark:bg-red-900/15"
                  : "border-[var(--border)] bg-[var(--card)]"
              }`}
            >
              <div className="flex items-start gap-2 mb-2">
                <span className={`w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold flex-shrink-0 ${
                  isCorrect
                    ? "bg-green-500 text-white"
                    : isWrong
                    ? "bg-red-500 text-white"
                    : "bg-[var(--chip)] text-[var(--muted)]"
                }`}>
                  {isCorrect ? "✓" : isWrong ? "✗" : "—"}
                </span>
                <p className="text-[13px] font-medium text-[var(--text)] leading-relaxed text-right flex-1">
                  {q.question}
                </p>
              </div>
              {userAns !== null && (
                <p className="text-[11px] text-[var(--muted)] pr-8">
                  پاسخ شما: <span className={isCorrect ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}>{labels[userAns]}. {q.options[userAns]}</span>
                  {!isCorrect && (
                    <span className="text-green-600 dark:text-green-400 mr-2">
                      | پاسخ صحیح: {labels[q.answer]}. {q.options[q.answer]}
                    </span>
                  )}
                </p>
              )}
              {userAns === null && (
                <p className="text-[11px] text-[var(--muted)] pr-8">
                  پاسخ صحیح: <span className="text-green-600 dark:text-green-400">{labels[q.answer]}. {q.options[q.answer]}</span>
                </p>
              )}
            </div>
          )
        })}
      </div>

      <div className="border-t border-[var(--border)] bg-[var(--card)] px-4 py-3 flex items-center gap-2">
        <button
          onClick={onRetry}
          className="flex-1 h-10 rounded-xl border border-[var(--border-strong)] text-[13px] font-bold text-[var(--muted)] hover:text-[var(--text)] transition-colors"
        >
          تکرار آزمون
        </button>
        <button
          onClick={onBack}
          className="flex-1 h-10 rounded-xl bg-[var(--accent)] text-white text-[13px] font-bold hover:brightness-110 transition-all"
        >
          بازگشت
        </button>
      </div>
    </div>
  )
}

export default function Evaluation({ nav }: { nav: NavFn }) {
  const [phase, setPhase] = useState<Phase>("select")
  const [activeTest, setActiveTest] = useState<SubjectTest | null>(null)
  const [resultAnswers, setResultAnswers] = useState<(number | null)[]>([])
  const [resultTime, setResultTime] = useState(0)

  const [history, setHistory] = useState<
    Record<string, { score: number; time: number; date: string }[]>
  >(() => {
    try {
      return JSON.parse(localStorage.getItem("boom-eval-history") || "{}")
    } catch {
      return {}
    }
  })

  function saveHistory(testId: string, score: number, time: number) {
    setHistory((prev) => {
      const next = { ...prev }
      if (!next[testId]) next[testId] = []
      next[testId] = [
        ...next[testId],
        { score, time, date: new Date().toISOString() },
      ]
      localStorage.setItem("boom-eval-history", JSON.stringify(next))
      return next
    })
  }

  function handleStartTest(test: SubjectTest) {
    setActiveTest(test)
    setPhase("test")
  }

  function handleFinishTest(answers: (number | null)[], timeSeconds: number) {
    if (!activeTest) return
    const correct = answers.filter(
      (a, i) => a !== null && a === activeTest.questions[i].answer
    ).length
    const pct = Math.round((correct / activeTest.questions.length) * 100)
    saveHistory(activeTest.id, pct, timeSeconds)
    setResultAnswers(answers)
    setResultTime(timeSeconds)
    setPhase("result")
  }

  function handleBackToSelect() {
    setPhase("select")
    setActiveTest(null)
  }

  function handleRetry() {
    if (activeTest) {
      setPhase("test")
    }
  }

  if (phase === "test" && activeTest) {
    return (
      <TestView
        test={activeTest}
        onBack={handleBackToSelect}
        onFinish={handleFinishTest}
      />
    )
  }

  if (phase === "result" && activeTest) {
    return (
      <ResultView
        test={activeTest}
        answers={resultAnswers}
        timeSeconds={resultTime}
        onBack={handleBackToSelect}
        onRetry={handleRetry}
      />
    )
  }

  const totalQuestions = SUBJECT_TESTS.reduce((s, t) => s + t.questions.length, 0)
  const completedTests = Object.keys(history).length

  return (
    <div className="h-full flex flex-col bg-[var(--surface)]">
      <div className="bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => nav("home")}
            className="w-9 h-9 rounded-xl bg-[var(--border)] flex items-center justify-center text-[var(--muted)]"
          >
            →
          </button>
          <h1 className="flex-1 text-right font-bold text-lg">ارزیابی</h1>
        </div>
        <p className="text-[12px] text-[var(--muted)] text-right mt-2">
          سطح خود را در هر درس بسنجید و نقاط ضعف خود را شناسایی کنید
        </p>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-3 text-center">
            <p className="text-[20px] font-bold text-[var(--accent)]">{SUBJECT_TESTS.length}</p>
            <p className="text-[11px] text-[var(--muted)] font-medium mt-0.5">درس</p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-3 text-center">
            <p className="text-[20px] font-bold text-[var(--accent)]">{totalQuestions}</p>
            <p className="text-[11px] text-[var(--muted)] font-medium mt-0.5">سوال</p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-3 text-center">
            <p className="text-[20px] font-bold text-[var(--accent)]">{completedTests}</p>
            <p className="text-[11px] text-[var(--muted)] font-medium mt-0.5">آزمون انجام شده</p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-3 text-center">
            <p className="text-[20px] font-bold text-[var(--accent)]">
              {Object.values(history).flat().length > 0
                ? Math.round(
                    Object.values(history)
                      .flat()
                      .reduce((s, h) => s + h.score, 0) /
                      Object.values(history).flat().length
                  )
                : "—"}
              {Object.values(history).flat().length > 0 && "%"}
            </p>
            <p className="text-[11px] text-[var(--muted)] font-medium mt-0.5">میانگین کل</p>
          </div>
        </div>

        <div>
          <p className="text-[13px] font-bold text-[var(--text)] mb-2">انتخاب درس</p>
          <div className="space-y-2">
            {SUBJECT_TESTS.map((test) => {
              const testHistory = history[test.id]
              const lastScore =
                testHistory && testHistory.length > 0
                  ? testHistory[testHistory.length - 1].score
                  : null
              return (
                <div key={test.id} className="relative">
                  <SubjectCard
                    test={test}
                    onClick={() => handleStartTest(test)}
                  />
                  {lastScore !== null && (
                    <div className="absolute top-3 left-3 px-2 py-0.5 rounded-md bg-[var(--chip)] border border-[var(--border)]">
                      <span
                        className={`text-[10px] font-bold ${
                          lastScore >= 70
                            ? "text-green-600 dark:text-green-400"
                            : lastScore >= 50
                            ? "text-yellow-600 dark:text-yellow-400"
                            : "text-red-600 dark:text-red-400"
                        }`}
                      >
                        آخرین نمره: {lastScore}%
                      </span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
