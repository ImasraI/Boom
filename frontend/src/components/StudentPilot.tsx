import { useState } from "react"
import { apiJson } from "../api"
import { RichText } from "../richText"

type Answers = Record<string, number | null>
type Session = {
  revision: string
  questions: { id: string; text: string; options: string[]; figure?: string; answer?: number; explanation?: string }[]
  answers: Answers | null
  feedback: Record<string, string>
}

export default function StudentPilot({ primary = false }: { primary?: boolean }) {
  const [session, setSession] = useState<Session>()
  const [answers, setAnswers] = useState<Answers>({})
  const [confidence, setConfidence] = useState<Record<string, number>>({})
  const [comments, setComments] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")

  async function request(action = "", body?: object) {
    setBusy(true)
    setMessage("")
    try {
      const next = await apiJson<Session>("/api/student-pilot" + action, {
        method: body ? "POST" : "GET",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify({ ...body, revision: session?.revision }) : undefined,
      })
      setSession(next)
      setComments(next.feedback)
      if (action === "/feedback") setMessage("بازخورد ثبت شد.")
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ارتباط برقرار نشد.")
    } finally {
      setBusy(false)
    }
  }

  const content = <>
    {!session ? <div className="mt-3">
      <button type="button" className="w-full rounded-xl bg-[var(--accent)] px-5 py-3 font-bold text-white disabled:opacity-50 sm:w-auto" disabled={busy} onClick={() => void request()}>
        {busy ? "در حال باز کردن…" : "شروع آزمون آزمایشی"}
      </button>
    </div> : <>
      {session.questions.map(q => <fieldset key={q.id} className="my-5 border-t border-[var(--border)] pt-3">
        <legend>{q.id}</legend>
        <RichText text={q.text} />
        {q.figure && <img className="mx-auto max-w-full bg-white" src={q.figure} alt="شکل سؤال" />}
        {q.options.map((option, index) => <label className="block" key={index}>
          <input type="radio" name={q.id} disabled={!!session.answers || busy}
            checked={(session.answers ?? answers)[q.id] === index}
            onChange={() => setAnswers(old => ({ ...old, [q.id]: index }))} /> <RichText text={option} />
        </label>)}
        {!session.answers && answers[q.id] != null && <button type="button" disabled={busy}
          onClick={() => setAnswers(old => ({ ...old, [q.id]: null }))}>پاک کردن پاسخ</button>}
        {session.answers ? <>
          <p>گزینهٔ درست {Number(q.answer) + 1}</p>
          <RichText text={q.explanation ?? ""} />
          <label className="block">چه چیزی باعث شد این پاسخ را انتخاب کنید؟ نکتهٔ سؤال چه بود؟
            <textarea className="block w-full border border-[var(--border)]" maxLength={1000}
              value={comments[q.id] ?? ""} onChange={e => setComments(old => ({ ...old, [q.id]: e.target.value }))} />
          </label>
        </> : <label>میزان اطمینان <select value={confidence[q.id] ?? ""} onChange={e => {
          const value = Number(e.target.value)
          setConfidence(old => {
            const next = { ...old }
            if (value) next[q.id] = value
            else delete next[q.id]
            return next
          })
        }}>
          <option value="">انتخاب نشده</option><option value="1">حدس</option><option value="2">کم</option>
          <option value="3">زیاد</option><option value="4">کاملاً مطمئن</option>
        </select></label>}
      </fieldset>)}
      <button disabled={busy} onClick={() => {
        if (session.answers) { void request("/feedback", { comments }); return }
        const unanswered = session.questions.filter(q => answers[q.id] == null).length
        if (window.confirm(`تعداد سؤال‌های بی‌پاسخ: ${unanswered}. پس از ثبت، پاسخ‌ها قابل تغییر نیستند. ثبت شود؟`)) {
          void request("/submit", { answers: Object.fromEntries(session.questions.map(q => [q.id, answers[q.id] ?? null])), confidence })
        }
      }}>
        {session.answers ? "ثبت بازخورد" : "ثبت پاسخ اول و دیدن پاسخنامه"}
      </button>
    </>}
    {message && <p role="status">{message}</p>}
  </>

  const cardClass = "mx-4 my-4 rounded-xl border border-[var(--border)] p-4"
  const title = "آزمون آزمایشی دانش‌آموزان"
  return primary ? (
    <div className="mx-auto max-w-[560px] px-4 pt-5">
      <section aria-labelledby="student-pilot-title" className="rounded-2xl border border-[var(--accent)] bg-[var(--accent-soft)] p-5 text-[var(--text)]" dir="rtl">
        <h1 id="student-pilot-title" className="text-xl font-bold">{title}</h1>
        {!session && <p className="mt-2 text-sm text-[var(--muted)]">با پاسخ‌نامهٔ تشریحی · بدون کد دعوت</p>}
        {content}
      </section>
    </div>
  ) : (
    <details className={cardClass} dir="rtl">
      <summary className="cursor-pointer font-bold">{title}</summary>
      {content}
    </details>
  )
}
