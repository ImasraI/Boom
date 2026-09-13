/**
 * Shared weekly-schedule storage + date helpers.
 *
 * Used by both the Schedule page (authoring the plan) and the Chat page
 * (sending the current plan to the backend so the agent plans against the
 * latest official version of the schedule).
 *
 * Storage layout:
 *   boom-weekly-schedule:YYYY-MM-DD  -> JSON array of blocks (per week)
 *   boom-weekly-static              -> JSON array of yearly static templates
 *   boom-weekly-generated           -> JSON { "YYYY-MM-DD": true } markers
 */

export const STORAGE_PREFIX = "boom-weekly-schedule:"
export const STATIC_KEY = "boom-weekly-static"
export const LEGACY_KEY = "boom-weekly-schedule"
export const GENERATED_KEY = "boom-weekly-generated"

export type BlockType = "class" | "study" | "test" | "break"

export interface StoredBlock {
  id?: string
  day: number
  startHour: number
  duration: number
  title: string
  type: BlockType
  color?: string
  count?: number | null
}

export interface StoredStatic {
  id?: string
  date: string
  startHour: number
  duration: number
  title: string
  type: BlockType
  color?: string
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
  return parseArray<StoredBlock>(localStorage.getItem(STORAGE_PREFIX + weekISO))
}

export function saveWeekBlocks(weekISO: string, blocks: StoredBlock[]) {
  localStorage.setItem(STORAGE_PREFIX + weekISO, JSON.stringify(blocks))
}

export function loadStaticTemplates(): StoredStatic[] {
  return parseArray<StoredStatic>(localStorage.getItem(STATIC_KEY))
}

export function saveStaticTemplates(templates: StoredStatic[]) {
  localStorage.setItem(STATIC_KEY, JSON.stringify(templates))
}

export function loadGeneratedMarkers(): Record<string, boolean> {
  const raw = localStorage.getItem(GENERATED_KEY)
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
  localStorage.setItem(GENERATED_KEY, JSON.stringify(markers))
}

export function unmarkWeekGenerated(weekISO: string) {
  const markers = loadGeneratedMarkers()
  delete markers[weekISO]
  localStorage.setItem(GENERATED_KEY, JSON.stringify(markers))
}

/**
 * Compact context blob shipped to the backend with chat/plan requests so the
 * agent always sees the user's current weekly plan + yearly static blocks.
 */
export function weeklyScheduleContext(): {
  week_start: string
  blocks: StoredBlock[]
  statics: StoredStatic[]
} {
  const weekStart = startOfWeek(new Date())
  const weekISO = toISO(weekStart)
  return {
    week_start: weekISO,
    blocks: loadWeekBlocks(weekISO),
    statics: loadStaticTemplates(),
  }
}