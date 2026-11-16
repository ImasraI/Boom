import { useEffect, useState } from "react"
import { apiJson } from "../api"
import type { MockQuestion } from "../pages/Mock"

type Preview = {
  status: string; accepted_by_me: boolean; sender_name: string; mock_title: string;
  question_count: number; duration_minutes: number;
}
export type ChallengeBooklet = {
  mock_id: number; title: string; duration_minutes: number; questions: MockQuestion[]; invite_code: string;
}
type Comparison = { sender_name: string; sender_score: number; your_score: number; won: boolean; tied: boolean }

const action = "px-4 py-2 rounded-xl border border-[var(--border-strong)] font-bold text-sm disabled:opacity-50"
const route = (code: string) => "/api/challenges/" + encodeURIComponent(code)
const errorMessage = (error: unknown) => error instanceof Error ? error.message : "ارتباط با سرور برقرار نشد."

export function FriendChallengeEntry({ onOpen }: { onOpen: (booklet: ChallengeBooklet) => void }) {
  const [input, setInput] = useState("")
  const code = input.trim().toUpperCase()
  const [preview, setPreview] = useState<Preview | null>(null)
  const [finished, setFinished] = useState<Comparison | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const valid = /^[A-HJ-KM-NP-Z2-9]{6}$/.test(code)

  async function lookup(event: React.FormEvent) {
    event.preventDefault()
    if (busy || !valid) return
    setBusy(true); setError("")
    try {
      const data = await apiJson<Preview>(route(code))
      setPreview(data)
      if (data.status === "completed" && data.accepted_by_me) {
        setFinished(await apiJson<Comparison>(route(code) + "/complete", { method: "POST" }))
      }
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }

  async function accept() {
    setBusy(true); setError("")
    try {
      const booklet = await apiJson<ChallengeBooklet>(route(code) + "/accept", { method: "POST" })
      onOpen(booklet)
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }

  return <section aria-label="چالش دوستانه" className="max-w-[560px] mx-auto px-4 pt-5 text-[var(--text)]">
    <details className="study-section p-4">
      <summary className="font-bold cursor-pointer">چالش دوستانه · ورود با کد</summary>
      <p className="text-sm text-[var(--muted)] mt-2">با کد دوستت همان دفترچه را حل کن و امتیازهایتان را مقایسه کن.</p>
      <form className="flex flex-wrap items-end gap-2 mt-3" onSubmit={lookup}>
        <label className="text-sm">کد شش‌کاراکتری
          <input dir="ltr" autoComplete="off" spellCheck={false} value={input} disabled={busy}
            onChange={e => { setInput(e.target.value); setPreview(null); setFinished(null); setError("") }}
            className="block w-36 mt-1 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-2 text-center" />
        </label>
        <button type="submit" className={action} disabled={!valid || busy}>بررسی کد</button>
      </form>
      {busy && <p className="mt-2 text-sm" role="status">در حال بررسی…</p>}
      {error && <p className="mt-2 text-sm text-red-500" role="alert">{error}</p>}
      {preview && <div className="mt-3 space-y-2">
        <p className="font-bold text-sm">{preview.mock_title} · {preview.question_count} سؤال · {preview.duration_minutes} دقیقه</p>
        <p className="text-sm text-[var(--muted)]">دعوت از {preview.sender_name}</p>
        {finished && <ScoreComparison result={finished} />}
        {preview.status === "pending" || (preview.status === "accepted" && preview.accepted_by_me)
          ? <button type="button" className={action} onClick={accept} disabled={busy || preview.question_count === 0}>باز کردن دفترچهٔ چالش</button>
          : !preview.accepted_by_me && <p className="text-sm">این کد قبلاً استفاده شده است.</p>}
      </div>}
    </details>
  </section>
}

function ScoreComparison({ result }: { result: Comparison }) {
  return <div className="space-y-1 text-sm">
    <p>امتیاز تو {result.your_score.toLocaleString("fa-IR")}٪ · امتیاز {result.sender_name} {result.sender_score.toLocaleString("fa-IR")}٪</p>
    <p className="font-bold">{result.tied ? "نتیجه مساوی شد." : result.won ? "امتیاز بالاتر برای توست." : "امتیاز بالاتر برای دوستت است."}</p>
  </div>
}

export function FriendChallengeResult({ mockId, code }: { mockId: number; code: string }) {
  const [invite, setInvite] = useState("")
  const [copied, setCopied] = useState(false)
  const [result, setResult] = useState<Comparison | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (!code) return
    const controller = new AbortController()
    setBusy(true); setError("")
    apiJson<Comparison>(route(code) + "/complete", { method: "POST", signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setResult(value) })
      .catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)) })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [code, retry])

  async function create() {
    setBusy(true); setError("")
    try {
      const data = await apiJson<{ invite_code: string }>("/api/challenges/create", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mock_id: mockId }),
      })
      setInvite(data.invite_code)
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }

  async function copy() {
    try { await navigator.clipboard.writeText(invite); setCopied(true) }
    catch { setError("کپی خودکار در دسترس نیست؛ کد را انتخاب و کپی کن.") }
  }

  return <section aria-label="نتیجهٔ چالش دوستانه" className="study-section p-4 text-[var(--text)] space-y-2">
    <h2 className="font-bold">چالش دوستانه</h2>
    {result && <ScoreComparison result={result} />}
    {!code && !invite && <button type="button" className={action} disabled={busy} onClick={create}>دوستم همین دفترچه را حل کند</button>}
    {invite && <>
      <p className="text-sm">کد را به دوستت بده تا آن را در بخش چالش دوستانه وارد کند.</p>
      <div className="flex flex-wrap items-center gap-3">
        <output dir="ltr" className="select-all font-mono font-bold">{invite}</output>
        <button type="button" className={action} onClick={copy}>{copied ? "کپی شد" : "کپی کد"}</button>
      </div>
    </>}
    {busy && <p className="text-sm" role="status">در حال دریافت…</p>}
    {error && <p className="text-sm text-red-500" role="alert">{error}</p>}
    {code && error && <button type="button" className={action} onClick={() => setRetry(n => n+1)}>دریافت دوبارهٔ نتیجه</button>}
  </section>
}
