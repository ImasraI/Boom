import { accountStorage } from "./accountStorage";
import { queueCalendar } from "./calendarSync";
import { expandTemplates, type Recurrence } from "./recurrence";
/**
 * Shared weekly-schedule storage + date helpers.
 *
 * Used by both the Schedule page (authoring the plan) and the Chat page
 * (sending the current plan to the backend so the agent plans against the
 * latest official version of the schedule).
 *
 * Storage layout:
 *   boom-weekly-schedule:YYYY-MM-DD  -> JSON array of blocks (per week)
 *   boom-weekly-static              -> JSON array of weekly-repeating templates
 *   boom-weekly-generated           -> JSON { "YYYY-MM-DD": true } markers
 */

export const STORAGE_PREFIX = "boom-weekly-schedule:"
export const STATIC_KEY = "boom-weekly-static"
export const LEGACY_KEY = "boom-weekly-schedule"
export const GENERATED_KEY = "boom-weekly-generated"

export type BlockType = "class" | "study" | "test" | "break"

export interface StoredBlock {
  origin?: "manual" | "generated";
  source_ref?: string;
  subject?: string;
  topic?: string;
  task_type?: string;
  resource?: string | null;
  question_start?: number | null;
  question_end?: number | null;
  page_start?: number | null;
  page_end?: number | null;
  id?: string
  day: number
  startHour: number
  duration: number
  title: string
  type: BlockType
  color?: string
  count?: number | null
  description?: string
}

export interface StoredStatic extends Omit<StoredBlock, "day"> {
  recurrence?: Recurrence;
  id?: string
  day?: number
  date?: string
  startHour: number
  duration: number
  title: string
  type: BlockType
  color?: string
  description?: string
}

/** Fired (window CustomEvent) whenever the weekly plan or statics change, so
 * views derived from them (e.g. the Home to-do list) can reload live. */
export const SCHEDULE_CHANGED_EVENT = "boom-schedule-changed"

type TimeSlot = { day: number; startHour: number; duration: number };

export function blocksOverlap(a: TimeSlot, b: TimeSlot): boolean {
  return a.day === b.day && Math.round(a.startHour * 60) < Math.round((b.startHour + b.duration) * 60)
    && Math.round(b.startHour * 60) < Math.round((a.startHour + a.duration) * 60);
}

export function hasScheduleOverlap(blocks: TimeSlot[], fixed: TimeSlot[] = []): boolean {
  return blocks.some((block, index) => fixed.some(other => blocksOverlap(block, other))
    || blocks.slice(index + 1).some(other => blocksOverlap(block, other)));
}

function notifyScheduleChanged() {
  window.dispatchEvent(new CustomEvent(SCHEDULE_CHANGED_EVENT))
}

export function staticWeekday(t: StoredStatic): number {
  if (typeof t.day === "number" && t.day >= 0 && t.day <= 6) return t.day
  if (t.date) return weekdayOf(fromISO(t.date))
  return 0
}

export function pad2(n: number) {
  return n < 10 ? `0${n}` : String(n)
}

export function toISO(d: Date) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

export function fromISO(s: string) {
  const [y, m, d] = s.split("-").map(Number)
  return new Date(y, m - 1, d)
}

// Persian week starts on Saturday.
export function getWeekISO(d: Date = new Date()): string {
  const start = startOfWeek(d);
  return toISO(start);
}

export function startOfWeek(d: Date) {
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  t.setDate(t.getDate() - ((t.getDay() + 1) % 7))
  return t
}

export function addDays(d: Date, n: number) {
  const t = new Date(d)
  t.setDate(t.getDate() + n)
  return t
}

export function weekdayOf(d: Date) {
  return (d.getDay() + 1) % 7 // 0 = شنبه
}

function parseArray<T>(raw: string | null): T[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : []
  } catch {
    return []
  }
}

export function loadWeekBlocks(weekISO: string): StoredBlock[] {
  return parseArray<StoredBlock>(accountStorage.getItem(STORAGE_PREFIX + weekISO))
}

export function saveWeekBlocks(weekISO: string, blocks: StoredBlock[]) {
  if (hasScheduleOverlap(blocks, staticBlocksForWeek(weekISO))) {
    throw new Error("این زمان با فعالیت دیگری تداخل دارد؛ ساعت یا مدت را تغییر دهید.");
  }
  accountStorage.setItem(STORAGE_PREFIX + weekISO, JSON.stringify(blocks))
  queueCalendar({ weeks: { [weekISO]: blocks } });
  notifyScheduleChanged()
}

export function loadStaticTemplates(): StoredStatic[] {
  return parseArray<StoredStatic>(accountStorage.getItem(STATIC_KEY))
}

export function saveStaticTemplates(templates: StoredStatic[]) {
  accountStorage.setItem(STATIC_KEY, JSON.stringify(templates))
  queueCalendar({ statics: templates });
  notifyScheduleChanged()
}

/** Converting a single activity to/from a series changes both stores at once. */
export function saveCalendarWeek(weekISO: string, blocks: StoredBlock[], templates: StoredStatic[]) {
  if (hasScheduleOverlap(blocks, expandTemplates(templates, weekISO))) {
    throw new Error("این زمان با فعالیت دیگری تداخل دارد؛ ساعت یا مدت را تغییر دهید.");
  }
  accountStorage.setItem(STORAGE_PREFIX + weekISO, JSON.stringify(blocks));
  accountStorage.setItem(STATIC_KEY, JSON.stringify(templates));
  queueCalendar({ weeks: { [weekISO]: blocks }, statics: templates });
  notifyScheduleChanged();
}

export function loadGeneratedMarkers(): Record<string, boolean> {
  const raw = accountStorage.getItem(GENERATED_KEY)
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === "object" ? parsed : {}
  } catch {
    return {}
  }
}

export function markWeekGenerated(weekISO: string) {
  const markers = loadGeneratedMarkers()
  markers[weekISO] = true
  accountStorage.setItem(GENERATED_KEY, JSON.stringify(markers))
}

export function staticBlocksForWeek(weekISO: string): StoredBlock[] {
  return expandTemplates(loadStaticTemplates(), weekISO);
}

export function unmarkWeekGenerated(weekISO: string) {
  const markers = loadGeneratedMarkers()
  delete markers[weekISO]
  accountStorage.setItem(GENERATED_KEY, JSON.stringify(markers))
}

/**
 * Compact context blob shipped to the backend with chat/plan requests so the
 * agent always sees the user's current weekly plan + yearly static blocks.
 */
export function weeklyScheduleContext(weekISO?: string): {
  week_start: string
  blocks: StoredBlock[]
  statics: StoredStatic[]
} {
  const iso = weekISO ?? toISO(startOfWeek(new Date()))
  return {
    week_start: iso,
    blocks: loadWeekBlocks(iso),
    statics: staticBlocksForWeek(iso),
  }
}
