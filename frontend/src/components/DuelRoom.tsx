import { useEffect, useRef, useState } from "react"
import { apiJson, ApiError } from "../api"
import { roomUrl } from "../duelLink"
import { faNumber } from "./tournament/format"
import { StudySymbol } from "./StudySymbols"

type Room = {
  code: string; host: string; guest: string | null; is_host: boolean
  host_ready: boolean; guest_ready: boolean; match_id: number | null
  starts_at: string | null; server_now: string
  is_public: boolean
}

const roomPath = (code: string, action = "") => "/api/arena/rooms/" + encodeURIComponent(code) + action
const errorText = (error: unknown) => error instanceof Error ? error.message : "ارتباط با اتاق برقرار نشد."

/** Creation/join are idempotent. Recover once if the response was lost in transit. */
export async function connectRoom(path: string, signal: AbortSignal, onAttempt: (attempt: number) => void) {
  for (let attempt = 1; attempt <= 2; attempt++) {
    onAttempt(attempt)
    try {
      return await apiJson<Room>(path, { method: "POST", signal }, 20000)
    } catch (error) {
      if (signal.aborted || error instanceof ApiError || attempt === 2) throw error
    }
  }
  throw new Error("ارتباط با اتاق برقرار نشد؛ دوباره تلاش کن.")
}

export default function DuelRoom({ invite, onBack, onStart }: {
  invite: string | null; onBack: () => void; onStart: (id: number) => Promise<void>
}) {
  const initialInvite = useRef(invite)
  const [room, setRoom] = useState<Room | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [pollError, setPollError] = useState("")
  const [copied, setCopied] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [connectionAttempt, setConnectionAttempt] = useState(1)
  const [deadline, setDeadline] = useState<number | null>(null)
  const [seconds, setSeconds] = useState(3)
  const roomLatest = useRef<Room | null>(null)
  const starting = useRef(false)

  function acceptRoom(next: Room) {
    if (roomLatest.current?.match_id && !next.match_id) return
    if (roomLatest.current && Date.parse(next.server_now) < Date.parse(roomLatest.current.server_now)) return
    roomLatest.current = next
    setRoom(next)
    if (next.starts_at) {
      const remaining = Date.parse(next.starts_at) - Date.parse(next.server_now)
      setDeadline(previous => previous ?? (performance.now() + Math.max(0, remaining)))
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    const code = initialInvite.current
    setBusy(true)
    setError("")
    const path = code ? roomPath(code, "/join") : "/api/arena/rooms"
    void connectRoom(path, controller.signal, setConnectionAttempt).then(next => {
      if (controller.signal.aborted) return
      acceptRoom(next)
      initialInvite.current = next.code
      window.history.replaceState(null, "", roomUrl(next.code))
    }).catch(failure => {
      if (!controller.signal.aborted) setError(errorText(failure))
    }).finally(() => {
      if (!controller.signal.aborted) setBusy(false)
    })
    return () => controller.abort()
  }, [attempt])

  const code = room?.code
  const matchId = room?.match_id
  useEffect(() => {
    if (!code || matchId) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const next = await apiJson<Room>(roomPath(code), { signal: controller.signal }, 6000)
        if (!controller.signal.aborted) {
          setPollError("")
          acceptRoom(next)
        }
      } catch (failure) {
        if (!controller.signal.aborted) setPollError(errorText(failure))
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 550)
      }
    }
    timer = setTimeout(poll, 550)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [code, matchId])

  useEffect(() => {
    if (deadline === null || !matchId) return
    const tick = () => {
      const left = Math.max(0, Math.ceil((deadline - performance.now()) / 1000))
      setSeconds(left)
      if (left !== 0 || starting.current) return
      starting.current = true
      void onStart(matchId).catch(failure => setError(errorText(failure)))
    }
    const timer = setInterval(tick, 65)
    tick()
    return () => clearInterval(timer)
  }, [deadline, matchId, onStart])

  async function ready() {
    if (!room || busy) return
    setBusy(true)
    setError("")
    try {
      acceptRoom(await apiJson<Room>(roomPath(room.code, "/ready"), { method: "POST" }, 25000))
    } catch (failure) {
      setError(errorText(failure))
    } finally { setBusy(false) }
  }

  async function copyLink() {
    if (!room) return
    try {
      await navigator.clipboard.writeText(roomUrl(room.code).href)
      setCopied(true)
    } catch { setCopied(false) }
  }

  async function changeVisibility(is_public: boolean) {
    if (!room || busy) return
    setBusy(true)
    setError("")
    try {
      acceptRoom(await apiJson<Room>(roomPath(room.code, "/visibility"), {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_public }),
      }))
    } catch (failure) { setError(errorText(failure)) }
    finally { setBusy(false) }
  }

  async function leave() {
    if (room && !room.match_id) {
      setBusy(true)
      try { await apiJson(roomPath(room.code), { method: "DELETE" }) }
      catch (failure) { setError(errorText(failure)); setBusy(false); return }
    }
    onBack()
  }

  const amReady = room?.is_host ? room?.host_ready : room?.guest_ready
  return <section className="tournament-page duel-room" dir="rtl">
    <div className="tn-topline"><span>کولوسئوم / دوئل دوستانه</span>
      <button type="button" disabled={busy} onClick={() => void leave()}>بازگشت به کولوسئوم</button></div>
    <div className="tn-hero-title"><StudySymbol kind="award" size={31} /><h1>اتاق دوئل دوستانه</h1></div>
    <p className="tn-hero-description">۱۰ سؤال مشترک · بدون تغییر رتبه</p>
    {(error || pollError) && <p className="tn-inline-error" role="alert">{error || pollError}</p>}
    {!room && busy && <p role="status">{connectionAttempt > 1 ? "در حال برقراری دوبارهٔ ارتباط با اتاق…" : "در حال باز کردن اتاق…"}</p>}
    {!room && error && <button className="tn-button tn-button-secondary" onClick={() => setAttempt(n => n + 1)}>تلاش دوباره</button>}
    {room && <>
      <div className="duel-seats">
        <div><small>میزبان</small><strong>{room.host}</strong><span data-ready={room.host_ready}>{room.host_ready ? "آماده" : "در انتظار آمادگی"}</span></div>
        <div><small>دوست</small><strong>{room.guest || "جای دوستت خالی است"}</strong><span data-ready={room.guest_ready}>{room.guest_ready ? "آماده" : room.guest ? "در انتظار آمادگی" : "در انتظار ورود"}</span></div>
      </div>
      {!room.guest && <div className="duel-invite">
        <label>لینک دعوت <input dir="ltr" readOnly value={roomUrl(room.code).href} onFocus={event => event.target.select()} /></label>
        <button className="tn-button tn-button-secondary" type="button" onClick={() => void copyLink()}>{copied ? "کپی شد" : "کپی لینک"}</button>
      </div>}
      {room.is_host && !room.guest && !room.match_id && <label className="duel-public-choice">
        <input type="checkbox" checked={room.is_public} disabled={busy} onChange={event => void changeVisibility(event.target.checked)} />
        <span>نمایش در اتاق‌های عمومی کولوسئوم<small>دانش‌آموزان هم‌رشته و هم‌پایه می‌توانند وارد شوند. با خاموش بودن، ورود فقط با لینک دعوت است.</small></span>
      </label>}
      {room.match_id ? <div className="duel-countdown" role="status" aria-live="polite">
        {seconds > 0 ? <><span>شروع دوئل</span><strong>{faNumber(seconds)}</strong></> : <span>در حال باز کردن دفترچه…</span>}
        {error && <button className="tn-button tn-button-secondary" type="button" onClick={() => {
          if (room.match_id) { setError(""); void onStart(room.match_id).catch(failure => setError(errorText(failure))) }
        }}>باز کردن مسابقه</button>}
      </div> : <div className="duel-room-actions">
        <button className="tn-button tn-button-primary" type="button" disabled={!room.guest || amReady || busy} onClick={() => void ready()}>
          {busy ? "در حال آماده‌سازی دفترچه…" : amReady ? "آماده‌ای؛ منتظر دوستت هستیم" : "آماده‌ام"}
        </button>
        <button className="tn-button tn-button-secondary" type="button" disabled={busy} onClick={() => void leave()}>{room.is_host ? "بستن اتاق" : "خروج از اتاق"}</button>
      </div>}
    </>}
  </section>
}
