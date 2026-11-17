import { useEffect, useState } from "react"
import { faNumber } from "./tournament/format"

const monthParts = new Intl.DateTimeFormat("fa-IR-u-ca-persian-nu-latn", { month: "numeric", day: "numeric" })
const monthLabel = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { month: "long", year: "numeric" })
const dateLabel = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "full" })
const weekdayNames = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
const weekdays = ["ش", "ی", "د", "س", "چ", "پ", "ج"]

function addDays(date: Date, days: number) {
  const result = new Date(date)
  result.setDate(result.getDate() + days)
  return result
}

function parts(date: Date) {
  const fields = monthParts.formatToParts(date)
  return {
    month: fields.find(field => field.type === "month")?.value,
    day: Number(fields.find(field => field.type === "day")?.value),
  }
}

function firstOfMonth(date: Date) {
  return addDays(date, 1 - parts(date).day)
}

function dayKey(date: Date) {
  const pad = (n: number) => String(n).padStart(2, "0")
  return [date.getFullYear(), pad(date.getMonth() + 1), pad(date.getDate())].join("-")
}

export function validDuelTime(value: string, now = Date.now()) {
  const time = new Date(value).getTime()
  return time >= now + 5 * 60_000 && time <= now + 14 * 24 * 60 * 60_000
}

export default function DuelCalendar({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const day = value.slice(0, 10)
  const time = value.slice(11)
  const now = new Date()
  const min = new Date(now.getTime() + 5 * 60_000)
  const max = new Date(now.getTime() + 14 * 24 * 60 * 60_000)
  const [month, setMonth] = useState(() => firstOfMonth(new Date(day + "T12:00")))
  useEffect(() => { setMonth(firstOfMonth(new Date(day + "T12:00"))) }, [day])
  const firstDay = (month.getDay() + 1) % 7
  const previous = firstOfMonth(addDays(month, -1))
  const next = firstOfMonth(addDays(month, 32))
  const days = Array.from({ length: 42 }, (_, index) => addDays(month, index - firstDay))
  const monthId = parts(month).month

  return <div className="duel-calendar">
    <div className="duel-calendar-head">
      <button className="tn-button tn-button-secondary" type="button" aria-label="ماه قبل"
        disabled={dayKey(previous) < dayKey(firstOfMonth(min))} onClick={() => setMonth(previous)}>›</button>
      <strong aria-live="polite">{monthLabel.format(month)}</strong>
      <button className="tn-button tn-button-secondary" type="button" aria-label="ماه بعد"
        disabled={dayKey(next) > dayKey(max)} onClick={() => setMonth(next)}>‹</button>
    </div>
    <div className="duel-calendar-grid">
      {weekdays.map((label, i) => <span className="duel-weekday" key={label} title={weekdayNames[i]}>{label}</span>)}
      {days.map(date => {
        const key = dayKey(date)
        const current = parts(date)
        const selected = key === day
        const available = current.month === monthId && key >= dayKey(min) && key <= dayKey(max)
        return <button key={key} type="button" disabled={!available} aria-pressed={selected}
          aria-label={dateLabel.format(date)} onClick={() => onChange(key + "T" + (time || "10:00"))}>
          {current.month === monthId ? faNumber(current.day) : ""}
        </button>
      })}
    </div>
    <div className="duel-calendar-time">
      <label>ساعت شروع <input type="time" value={time} dir="ltr"
        onChange={event => onChange(day + "T" + event.target.value)} /></label>
      <span>به وقت دستگاهت</span>
    </div>
  </div>
}
