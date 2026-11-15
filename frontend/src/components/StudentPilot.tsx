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

export default function StudentPilot() {
  const [code, setCode] = useState("")
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
        headers: { "X-Pilot-Code": code.trim(), "Content-Type": "application/json" },
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

  return <details className="mx-4 my-4 rounded-xl border border-[var(--border)] p-4" dir="rtl">
    <summary className="cursor-pointer font-bold">آزمون آزمایشی با کد دعوت</summary>
    {!session ? <form className="mt-3 flex flex-wrap gap-3" onSubmit={e => { e.preventDefault(); void request() }}>
      <label>کد دعوت <input dir="ltr" value={code} onChange={e => setCode(e.target.value)} required /></label>
      <button disabled={busy || !code.trim()}>باز کردن آزمون</button>
    </form> : <>
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
  </details>
}
