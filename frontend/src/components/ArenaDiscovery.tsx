import { useCallback, useEffect, useState } from "react"
import { apiJson } from "../api"
import { faNumber, timestamp } from "./tournament/format"

type PublicRoom = { code: string; host: string; major: string; grade: string; is_mine: boolean }
type Offer = { id: number; host: string; starts_at: string; is_mine: boolean; can_accept: boolean }
type Booking = { match_id: number; opponent: string; starts_at: string; seconds_until: number }
type Schedule = { open: Offer[]; mine: Booking[]; quota: { remaining: number | null } }
const when = (iso: string) => new Date(timestamp(iso)).toLocaleString("fa-IR", {
  weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit",
})

export default function ArenaDiscovery({ onRoom, onScheduled, onMatch }: {
  onRoom: (code: string) => void; onScheduled: () => void; onMatch: (id: number) => Promise<void>
}) {
  const [rooms, setRooms] = useState<PublicRoom[] | null>(null)
  const [profileRequired, setProfileRequired] = useState(false)
  const [schedule, setSchedule] = useState<Schedule | null>(null)
  const [roomError, setRoomError] = useState("")
  const [scheduleError, setScheduleError] = useState("")
  const [actionError, setActionError] = useState("")
  const [busy, setBusy] = useState(false)
  const refresh = useCallback(async (signal?: AbortSignal) => {
    await Promise.all([
      apiJson<{ rooms: PublicRoom[]; profile_required: boolean }>("/api/arena/rooms", { signal }, 8000)
        .then(data => { if (!signal?.aborted) { setRooms(data.rooms); setProfileRequired(data.profile_required); setRoomError("") } })
        .catch(() => { if (!signal?.aborted) setRoomError("فهرست اتاق‌ها دریافت نشد؛ دوباره تلاش کن.") }),
      apiJson<Schedule>("/api/arena/scheduled", { signal }, 8000)
        .then(data => { if (!signal?.aborted) { setSchedule(data); setScheduleError("") } })
        .catch(() => { if (!signal?.aborted) setScheduleError("فهرست مسابقه‌های زمان‌دار دریافت نشد؛ دوباره تلاش کن.") }),
    ])
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      if (document.visibilityState !== "hidden") await refresh(controller.signal)
      if (!controller.signal.aborted) timer = setTimeout(poll, 15000)
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [refresh])

  async function act(action: () => Promise<unknown>) {
    if (busy) return
    setBusy(true); setActionError("")
    try { await action(); await refresh() }
    catch (error) { setActionError(error instanceof Error ? error.message : "درخواست انجام نشد؛ دوباره تلاش کن.") }
    finally { setBusy(false) }
  }
  const offers = schedule?.open.filter(row => row.is_mine || row.can_accept) ?? []
  return <section className="arena-discovery" aria-label="مسابقه‌های قابل ورود">
    <div className="arena-discovery-heading"><h2>همین‌جا یک مسابقه پیدا کن</h2>
      <button type="button" className="boom-button boom-button-secondary" disabled={busy} onClick={() => void act(async () => {})}>تازه‌سازی فهرست</button></div>
    {actionError && <p role="alert" className="boom-notice">{actionError}</p>}
    <div className="arena-discovery-grid">
      <section className="boom-panel" aria-labelledby="public-rooms-heading">
        <h3 id="public-rooms-heading" className="boom-section-heading">اتاق‌های عمومی</h3>
        <p className="arena-discovery-intro">دوئل دوستانه با دانش‌آموزان هم‌رشته و هم‌پایه · بدون تغییر رتبه</p>
        {roomError && <p role="alert">{roomError}</p>}
        {!rooms && !roomError && <p role="status">در حال دریافت اتاق‌ها…</p>}
        {rooms?.length === 0 && !roomError && <p>{profileRequired ? "برای دیدن اتاق‌های مناسب، رشته و پایه‌ات را در پروفایل ثبت کن." : "هنوز اتاق عمومیِ بازی در محدودهٔ تو نیست. یک اتاق بساز و نمایش عمومی را روشن کن."}</p>}
        <ul className="arena-discovery-list">{rooms?.map(room => <li key={room.code}>
          <div><strong>{room.host}{room.is_mine ? " · اتاق تو" : ""}</strong><p>{room.major} · {room.grade}</p><small>۱ از ۲ بازیکن · در انتظار حریف</small></div>
          <button type="button" className="boom-button boom-button-primary" onClick={() => onRoom(room.code)}>{room.is_mine ? "باز کردن اتاق" : "ورود به اتاق"}</button>
        </li>)}</ul>
      </section>
      <section className="boom-panel" aria-labelledby="scheduled-games-heading">
        <h3 id="scheduled-games-heading" className="boom-section-heading">مسابقه‌های زمان‌دار</h3>
        {scheduleError && <p role="alert">{scheduleError}</p>}
        {!schedule && !scheduleError && <p role="status">در حال دریافت مسابقه‌ها…</p>}
        {schedule && <>
          <ul className="arena-discovery-list">{schedule.mine.map(row => <li key={row.match_id}>
            <div><strong>دوئل تو با {row.opponent}</strong><p>{when(row.starts_at)}</p><small>رزرو شده</small></div>
            <button type="button" className="boom-button boom-button-primary" disabled={busy || row.seconds_until > 0} onClick={() => void act(() => onMatch(row.match_id))}>{row.seconds_until <= 0 ? "ورود به مسابقه" : "در انتظار شروع"}</button>
          </li>)}{offers.map(row => <li key={"offer-" + row.id}>
            <div><strong>{row.host}{row.is_mine ? " · پیشنهاد تو" : ""}</strong><p>{when(row.starts_at)}</p><small>دوئل رنک‌دار · ۱۰ سؤال</small></div>
            <button type="button" className="boom-button boom-button-secondary" disabled={busy || (!row.is_mine && schedule.quota.remaining === 0)} onClick={() => row.is_mine ? onScheduled() : void act(() => apiJson(`/api/arena/scheduled/${row.id}/accept`, { method: "POST" }))}>{row.is_mine ? "مدیریت" : schedule.quota.remaining === 0 ? "سهمیه تمام" : "رزرو مسابقه"}</button>
          </li>)}</ul>
          {!schedule.mine.length && !offers.length && <p>فعلاً مسابقهٔ زمان‌دار مناسبی برای رزرو نیست.</p>}
          {schedule.quota.remaining !== null && <p className="arena-discovery-intro">سهمیهٔ باقی‌ماندهٔ امروز: {faNumber(schedule.quota.remaining)}</p>}
        </>}
        <button type="button" className="boom-button boom-button-secondary" onClick={onScheduled}>پیشنهاد زمان و مدیریت رزروها</button>
      </section>
    </div>
  </section>
}
