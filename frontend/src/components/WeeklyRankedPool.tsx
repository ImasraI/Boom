import { useCallback, useEffect, useState } from "react"
import { apiJson } from "../api"

interface WeeklyPreview {
  available: boolean; message: string; date?: string; document?: string;
  topics?: Record<string,string[]>; ready_matches: number; players_supported_one_round: number;
  missing?: { subject: string; topic: string; year?: number }[];
}

export default function WeeklyRankedPool({ running, onStarted }: { running: boolean; onStarted: () => void }) {
  const [preview,setPreview]=useState<WeeklyPreview|null>(null)
  const [count,setCount]=useState("20")
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState("")
  const refresh=useCallback(async()=>{
    try { setPreview(await apiJson<WeeklyPreview>("/api/admin/pool/weekly-ranked"));setError("") }
    catch (e) { setError(e instanceof Error ? e.message : "برنامهٔ ماز دریافت نشد") }
  },[])
  useEffect(()=>{ void refresh();const timer=setInterval(()=>void refresh(),15000);return()=>clearInterval(timer) },[refresh])
  const start=async()=>{
    const amount=count.trim()==="" ? 0 : Number(count)
    if (!Number.isInteger(amount)||amount<0) { setError("تعداد دفترچه باید عدد صحیح نامنفی باشد");return }
    setBusy(true)
    try {
      await apiJson("/api/admin/pool/restock",{ method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"weekly_ranked",count:amount}) })
      onStarted();void refresh()
    } catch(e) { setError(e instanceof Error ? e.message : "تولید آغاز نشد") }
    finally { setBusy(false) }
  }
  return <section className="study-section p-5 space-y-4" aria-labelledby="weekly-ranked-title">
    <div className="flex items-center justify-between gap-4">
      <h2 id="weekly-ranked-title" className="font-bold">کولوسئوم هفتگی · ماز</h2>
      <span className="text-xs text-[var(--muted)]">دوازدهم ریاضی‌فیزیک · ۱۰ سؤال</span>
    </div>
    <p className="text-xs text-[var(--muted)] leading-relaxed">مبحث‌ها از آزمون آیندهٔ برنامهٔ ماز انتخاب می‌شوند. پس از گذشت تاریخ آزمون یا تغییر برنامه، محدوده خودکار عوض می‌شود؛ دفترچه‌های محدوده قبلی برای مسابقه جدید مصرف نمی‌شوند.</p>
    {preview?.date && <p className="text-sm">آزمون آینده: {new Date(preview.date+"T12:00:00+03:30").toLocaleDateString("fa-IR",{timeZone:"Asia/Tehran"})} · {preview.document}</p>}
    {preview?.topics && <div className="divide-y divide-[var(--border)] border-y border-[var(--border)]">
      {Object.entries(preview.topics).map(([subject,topics])=><p key={subject} className="py-3 text-xs leading-relaxed"><strong>{subject}: </strong>{topics.join("، ")}</p>)}
    </div>}
    {preview && <p className="text-sm">{preview.ready_matches.toLocaleString("fa-IR")} مسابقهٔ تأییدشده برای همین محدوده · یک دور برای {preview.players_supported_one_round.toLocaleString("fa-IR")} بازیکن</p>}
    {preview && !preview.available && <div role="alert" className="text-xs text-orange-400 leading-relaxed">
      <p>{preview.message}</p>
      {preview.missing?.map((m,i)=><p key={i}>{m.subject} · {m.topic}{m.year ? ` · پایه ${m.year}` : ""}</p>)}
    </div>}
    <div className="flex flex-wrap items-end gap-4">
      <label className="text-xs">تعداد دفترچه؛ صفر = پیوسته<input aria-label="تعداد مسابقه هفتگی" type="number" min={0} step={1} value={count} disabled={running||busy} onChange={e=>setCount(e.target.value)} className="block bg-transparent border-b border-[var(--border-strong)] py-2" /></label>
      <button disabled={running||busy||!preview?.available} onClick={()=>void start()} className="px-4 py-2 bg-[var(--accent)] text-[var(--surface)] font-bold text-xs disabled:opacity-40">{busy ? "در حال شروع..." : "تولید مسابقه‌های هفتگی"}</button>
    </div>
    <p className="text-xs text-[var(--muted)]">برای ۲۰ دانش‌آموز، یک دور هم‌زمان حداقل ۱۰ دفترچهٔ متفاوت می‌خواهد؛ ۲۰ دفترچه برای دو دور است. اگر تولید دیگری فعال است ابتدا آن را متوقف کن. سطح این مسابقه‌ها استاندارد کنکور و بررسی کیفیت مستقل است.</p>
    {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
  </section>
}
