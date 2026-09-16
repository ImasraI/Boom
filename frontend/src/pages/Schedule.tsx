import { useEffect, useMemo, useRef, useState } from "react"
import { NavFn, SignupData } from "../types"
import { apiUrl } from "../api"
import GroqChart from "../components/GroqChart"
import {
  addDays,
  fromISO,
  LEGACY_KEY,
  loadGeneratedMarkers,
  loadStaticTemplates,
  markWeekGenerated,
  saveWeekBlocks,
  startOfWeek,
  STATIC_KEY,
  STORAGE_PREFIX,
  toISO,
  weekdayOf,
} from "../scheduleStore"

const DAYS = [
  "شنبه",
  "یکشنبه",
  "دوشنبه",
  "سه‌شنبه",
  "چهارشنبه",
  "پنجشنبه",
  "جمعه",
]
const HOUR_START = 6
const TOTAL_HOURS = 18
const SLOT_COUNT = TOTAL_HOURS * 2
const HOUR_END = HOUR_START + TOTAL_HOURS - 0.5
const HOURS = Array.from({ length: SLOT_COUNT }, (_, i) => {
  const val = HOUR_START + i * 0.5
  const h = Math.floor(val) % 24
  const m = Math.round((val - Math.floor(val)) * 60)
  return `${h}:${m === 0 ? "00" : m}`
})

const SLOT_HEIGHT = 32
const MIN_DURATION = 0.5
const MAX_DURATION = 6

const MS_PER_DAY = 86400000
const MS_PER_WEEK = 7 * MS_PER_DAY

// The calendar shows 2 years before and 2 years after the current week.
const YEARS_PRIOR = 2
const YEARS_AFTER = 2
const MAX_WEEKS = Math.round((YEARS_AFTER * 365.25) / 7) // 104

const PERSIAN_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
]

type BlockType = "class" | "study" | "test" | "break"

interface ScheduleBlock {
  id: string
  day: number
  startHour: number
  duration: number
  title: string
  type: BlockType
  color: string
}

// A "static" timeblock is anchored to a specific date (YYYY-MM-DD) and
// automatically repeats every year on the same month/day.
interface StaticBlock {
  id: string
  date?: string
  day?: number
  startHour: number
  duration: number
  title: string
  type: BlockType
  color: string
}

interface StaticInstance extends ScheduleBlock {
  static: true
  templateId: string
}

interface BlockDraft {
  title: string
  startHour: number
  duration: number
  type: BlockType
  color: string
  day?: number
  date?: string
}

type DragMode = "move" | "resize"

interface DragState {
  id: string
  mode: DragMode
  originX: number
  originY: number
  originDay: number
  originHour: number
  startDay: number
  startHour: number
  startDuration: number
  moved: boolean
}

const TYPE_COLORS: Record<BlockType, string> = {
  class: "#5C8BA8",
  study: "#e2c983",
  test: "#9B7AAD",
  break: "#97b094",
}

const COLOR_OPTIONS = [
  "#e2c983",
  "#5C8BA8",
  "#9B7AAD",
  "#97b094",
  "#FF6B6B",
  "#4D96FF",
  "#FFD93D",
  "#6BCB77",
  "#A267AC",
]

const TYPE_LABELS: Record<BlockType, string> = {
  class: "کلاس",
  study: "مطالعه",
  test: "آزمون",
  break: "استراحت",
}

const DEFAULT_DRAFT = (): BlockDraft => ({
  title: "",
  startHour: HOUR_START,
  duration: 1,
  type: "class",
  color: TYPE_COLORS.class,
})

function faNum(input: string | number) {
  const fa = "۰۱۲۳۴۵۶۷۸۹"
  return String(input).replace(/[0-9]/g, (d) => fa[Number(d)])
}

// Gregorian -> Jalali (Persian calendar) conversion.
function toJalali(date: Date): [number, number, number] {
  let gy = date.getFullYear()
  const gm = date.getMonth() + 1
  const gd = date.getDate()

  const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
  let jy = gy <= 1600 ? 0 : 979
  gy -= gy <= 1600 ? 621 : 1600
  const gy2 = gm > 2 ? gy + 1 : gy
  let days =
    365 * gy +
    Math.floor((gy2 + 3) / 4) -
    Math.floor((gy2 + 99) / 100) +
    Math.floor((gy2 + 399) / 400) -
    80 +
    gd +
    g_d_m[gm - 1]

  jy += 33 * Math.floor(days / 12053)
  days %= 12053
  jy += 4 * Math.floor(days / 1461)
  days %= 1461
  if (days > 365) {
    jy += Math.floor((days - 1) / 365)
    days = (days - 1) % 365
  }
  const jm =
    days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30)
  const jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30)
  return [jy, jm, jd]
}

function klarLabel(date: Date) {
  const [jy, jm, jd] = toJalali(date)
  return `${faNum(jd)} ${PERSIAN_MONTHS[jm - 1]} ${faNum(jy)}`
}

function weekDiff(a: Date, b: Date) {
  return Math.round(
    (startOfWeek(a).getTime() - startOfWeek(b).getTime()) / MS_PER_WEEK,
  )
}

function weekRangeLabel(weekStart: Date) {
  const start = weekStart
  const end = addDays(weekStart, 6)
  const [sy, sm, sd] = toJalali(start)
  const [ey, em, ed] = toJalali(end)
  if (sy === ey && sm === em) {
    return `${faNum(sd)}–${faNum(ed)} ${PERSIAN_MONTHS[sm - 1]} ${faNum(sy)}`
  }
  if (sy === ey) {
    return `${faNum(sd)} ${PERSIAN_MONTHS[sm - 1]} – ${faNum(ed)} ${PERSIAN_MONTHS[em - 1]} ${faNum(sy)}`
  }
  return `${faNum(sd)} ${PERSIAN_MONTHS[sm - 1]} ${faNum(sy)} – ${faNum(ed)} ${PERSIAN_MONTHS[em - 1]} ${faNum(ey)}`
}

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n))
}

function resolveColor(color: string) {
  if (color === "var(--accent)") return TYPE_COLORS.study
  if (color === "var(--success)") return TYPE_COLORS.break
  return color
}

function formatTime(val: number) {
  const h = Math.floor(val) % 24
  const m = Math.round((val - Math.floor(val)) * 60)
  return `${h}:${m === 0 ? "00" : m}`
}

function parseBlocks(raw: string): ScheduleBlock[] {
  try {
    const parsed = JSON.parse(raw) as ScheduleBlock[]
    if (!Array.isArray(parsed)) return []
    return parsed.map((block) => ({
      ...block,
      color: resolveColor(block.color),
    }))
  } catch {
    return []
  }
}

function loadBlocks(weekStart: Date): ScheduleBlock[] {
  const raw = localStorage.getItem(STORAGE_PREFIX + toISO(weekStart))
  return raw ? parseBlocks(raw) : []
}

function loadStatics(): StaticBlock[] {
  return loadStaticTemplates().map((t) => ({
    id: t.id ?? newId(),
    date: t.date,
    day: t.day,
    startHour: t.startHour,
    duration: t.duration,
    title: t.title,
    type: t.type,
    color: resolveColor(t.color ?? TYPE_COLORS[t.type]),
  }))
}

function maxDurationForHour(startHour: number) {
  return clamp(HOUR_START + TOTAL_HOURS - startHour, MIN_DURATION, MAX_DURATION)
}

function newId() {
  return (
    crypto.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(36).slice(2)}`
  )
}

function isStaticInstance(
  b: ScheduleBlock | StaticInstance,
): b is StaticInstance {
  return typeof (b as StaticInstance).templateId === "string"
}

// Compute which static (yearly or weekly) blocks land inside the displayed week.
function staticInstancesForWeek(
  statics: StaticBlock[],
  weekStart: Date,
): StaticInstance[] {
  const out: StaticInstance[] = []
  const weekEnd = addDays(weekStart, 6)

  for (const t of statics) {
    if (typeof t.day === "number") {
      // Weekly repeating: appears every week.
      out.push({
        id: t.id,
        static: true,
        templateId: t.id,
        day: t.day,
        startHour: t.startHour,
        duration: t.duration,
        title: t.title,
        type: t.type,
        color: t.color,
      })
    } else if (t.date) {
      // Yearly repeating: anchored to a specific date.
      const [, m, d] = t.date.split("-").map(Number)
      const years = [
        weekStart.getFullYear() - 1,
        weekStart.getFullYear(),
        weekStart.getFullYear() + 1,
      ]
      for (const y of years) {
        const dt = new Date(y, m - 1, d)
        if (dt.getMonth() !== m - 1 || dt.getDate() !== d) continue
        if (
          dt.getTime() >= weekStart.getTime() &&
          dt.getTime() <= weekEnd.getTime()
        ) {
          out.push({
            id: t.id,
            static: true,
            templateId: t.id,
            day: weekdayOf(dt),
            startHour: t.startHour,
            duration: t.duration,
            title: t.title,
            type: t.type,
            color: t.color,
          })
          break
        }
      }
    }
  }
  return out
}

export default function Schedule({
  nav,
  userData,
}: {
  nav: NavFn
  userData?: SignupData | null
}) {
  const today = useMemo(() => new Date(), [])
  const todayWeekStart = useMemo(() => startOfWeek(today), [today])

  const [weekStart, setWeekStart] = useState<Date>(todayWeekStart)
  const [blocks, setBlocks] = useState<ScheduleBlock[]>(() => loadBlocks(todayWeekStart))
  const [statics, setStatics] = useState<StaticBlock[]>(loadStatics)
  const [editingBlock, setEditingBlock] = useState<ScheduleBlock | null>(null)
  const [editingStatic, setEditingStatic] = useState<StaticBlock | null>(null)
  const [recurring, setRecurring] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [selectedDay, setSelectedDay] = useState(0)
  const [newBlock, setNewBlock] = useState<BlockDraft>(DEFAULT_DRAFT)
  const [drag, setDrag] = useState<DragState | null>(null)
  const [generating, setGenerating] = useState(false)
  const [generatingWeeks, setGeneratingWeeks] = useState<Set<string>>(new Set())
  const genBusyRef = useRef<Record<string, boolean>>({})
  const genAbortRef = useRef<Record<string, AbortController>>({})
  const skipPersistRef = useRef(true)

  const [showChart, setShowChart] = useState(false)
  const gridRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<DragState | null>(null)
  const blocksRef = useRef(blocks)
  const weekStartRef = useRef(weekStart)
  const suppressClickRef = useRef(false)

  const currentOffset = weekDiff(weekStart, todayWeekStart)

  useEffect(() => {
    blocksRef.current = blocks
  }, [blocks])

  useEffect(() => {
    weekStartRef.current = weekStart
  }, [weekStart])

  useEffect(() => {
    dragRef.current = drag
  }, [drag])

  // Migrate the old single-week key ("boom-weekly-schedule") into the
  // current week's per-week store, then drop it.
  useEffect(() => {
    const legacy = localStorage.getItem(LEGACY_KEY)
    if (legacy) {
      try {
        const arr = JSON.parse(legacy)
        if (Array.isArray(arr)) {
          const key = STORAGE_PREFIX + toISO(todayWeekStart)
          if (!localStorage.getItem(key)) localStorage.setItem(key, legacy)
        }
      } catch {
        /* ignore malformed legacy data */
      }
      localStorage.removeItem(LEGACY_KEY)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Load blocks whenever the displayed week changes.
  useEffect(() => {
    const loaded = loadBlocks(weekStart)
    setBlocks(loaded)
    setEditingBlock(null)
    setEditingStatic(null)
    setShowModal(false)
    // Empty weeks get auto-filled once with the standard generated plan
    // (unless the user explicitly cleared them, tracked via the marker).
    if (loaded.length === 0 && !loadGeneratedMarkers()[toISO(weekStart)]) {
      void generateWeekPlan(weekStart)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weekStart])

  // Persist blocks to the currently displayed week's key. Skip the first
  // run so a mount cannot overwrite a previously saved week with [].
  useEffect(() => {
    if (skipPersistRef.current) {
      skipPersistRef.current = false
      return
    }
    const key = STORAGE_PREFIX + toISO(weekStartRef.current)
    localStorage.setItem(key, JSON.stringify(blocks))
  }, [blocks])

  // Persist static templates separately (they are global / yearly).
  useEffect(() => {
    localStorage.setItem(STATIC_KEY, JSON.stringify(statics))
  }, [statics])

  const staticInstances = useMemo(
    () => staticInstancesForWeek(statics, weekStart),
    [statics, weekStart],
  )
  const displayedBlocks = useMemo(
    () => [...blocks, ...staticInstances],
    [blocks, staticInstances],
  )

  function clampWeek(d: Date) {
    const off = clamp(weekDiff(d, todayWeekStart), -MAX_WEEKS, MAX_WEEKS)
    return addDays(todayWeekStart, off * 7)
  }

  function navigate(delta: number) {
    setWeekStart((w) => clampWeek(addDays(startOfWeek(w), delta * 7)))
  }

  function goToday() {
    setWeekStart(todayWeekStart)
  }

  // Ask the backend to build a standard weekly plan (study + test blocks
  // grounded in the retrieved Konkoor books), then store it as the week's
  // official blocks.  Auto-fills empty weeks and powers the "بازسازی" button.
  // Runs in the background and continues even when switching weeks.
  async function generateWeekPlan(ws: Date) {
    const key = toISO(ws)
    if (genBusyRef.current[key]) return
    genBusyRef.current[key] = true
    
    const abortController = new AbortController()
    genAbortRef.current[key] = abortController
    
    setGeneratingWeeks(prev => new Set(prev).add(key))
    setGenerating(true)
    
    try {
      const resp = await fetch(apiUrl("/api/boom/weekly-plan"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          week_start: key,
          daily_hours: 4,
          student: userData ?? undefined,
          statics: statics,
        }),
        signal: abortController.signal,
      })
      if (!resp.ok) return
      const data: any = await resp.json()
      const list: ScheduleBlock[] = Array.isArray(data.blocks)
        ? data.blocks.map(
            (b: any): ScheduleBlock => ({
              id: b.id ?? newId(),
              day: Number(b.day) || 0,
              startHour: Number(b.startHour) || 0,
              duration: Number(b.duration) || 1,
              title: String(b.title ?? "فعالیت"),
              type: (b.type in TYPE_LABELS ? b.type : "study") as BlockType,
              color: resolveColor(String(b.color ?? TYPE_COLORS.study)),
            }),
          )
        : []
      if (list.length) {
        saveWeekBlocks(key, list)
        markWeekGenerated(key)
        if (toISO(weekStartRef.current) === key) setBlocks(list)
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        console.log(`Generation cancelled for week ${key}`)
      }
    } finally {
      genBusyRef.current[key] = false
      delete genAbortRef.current[key]
      setGeneratingWeeks(prev => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
      setGenerating(Object.keys(genBusyRef.current).some(k => genBusyRef.current[k]))
    }
  }

  function stopGeneration(ws?: Date) {
    const key = ws ? toISO(ws) : toISO(weekStart)
    const controller = genAbortRef.current[key]
    if (controller) {
      controller.abort()
      genBusyRef.current[key] = false
      delete genAbortRef.current[key]
      setGeneratingWeeks(prev => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
      setGenerating(Object.keys(genBusyRef.current).some(k => genBusyRef.current[k]))
    }
  }

  function openAdd(day: number, hour: number) {
    setSelectedDay(day)
    setNewBlock({ ...DEFAULT_DRAFT(), startHour: hour })
    setEditingBlock(null)
    setEditingStatic(null)
    setRecurring(false)
    setShowModal(true)
  }

  function openEdit(block: ScheduleBlock) {
    setSelectedDay(block.day)
    setNewBlock({
      title: block.title,
      startHour: block.startHour,
      duration: block.duration,
      type: block.type,
      color: resolveColor(block.color),
    })
    setEditingBlock(block)
    setEditingStatic(null)
    setRecurring(false)
    setShowModal(true)
  }

  function openEditStatic(instance: StaticInstance) {
    const template = statics.find((t) => t.id === instance.templateId)
    if (!template) return
    setSelectedDay(instance.day)
    setNewBlock({
      title: template.title,
      startHour: template.startHour,
      duration: template.duration,
      type: template.type,
      color: resolveColor(template.color),
    })
    setEditingBlock(null)
    setEditingStatic(template)
    setRecurring(true)
    setShowModal(true)
  }

  function saveBlock() {
    if (!newBlock.title.trim()) return
    const startHour = clamp(
      newBlock.startHour,
      HOUR_START,
      HOUR_START + TOTAL_HOURS - MIN_DURATION,
    )
    const duration = clamp(
      newBlock.duration,
      MIN_DURATION,
      maxDurationForHour(startHour),
    )
    const base = {
      ...newBlock,
      startHour,
      duration,
      color: resolveColor(newBlock.color),
    }

    if (recurring) {
      const day = newBlock.day !== undefined ? newBlock.day : selectedDay
      const date = newBlock.date ?? (newBlock.day === undefined ? toISO(addDays(startOfWeek(weekStartRef.current), selectedDay)) : undefined)
      if (editingStatic) {
        setStatics((prev) =>
          prev.map((t) =>
            t.id === editingStatic.id ? { ...t, ...base, day, date } : t,
          ),
        )
      } else {
        setStatics((prev) => [...prev, { id: newId(), day, date, ...base }])
      }
    } else if (editingBlock) {
      setBlocks((prev) =>
        prev.map((b) =>
          b.id === editingBlock.id ? { ...b, ...base, day: selectedDay } : b,
        ),
      )
    } else {
      setBlocks((prev) => [
        ...prev,
        {
          id: newId(),
          day: selectedDay,
          ...base,
        },
      ])
    }
    setShowModal(false)
  }

  function deleteCurrentBlock() {
    if (recurring && editingStatic) {
      setStatics((prev) => prev.filter((t) => t.id !== editingStatic.id))
    } else if (editingBlock) {
      setBlocks((prev) => prev.filter((b) => b.id !== editingBlock.id))
    }
    setShowModal(false)
  }

  function toggleRecurring(v: boolean) {
    // Only allowed when adding a new block or editing a static template.
    if (editingBlock) return
    setRecurring(v)
  }

  function slotFromPoint(clientX: number, clientY: number) {
    const grid = gridRef.current
    if (!grid) return null
    const rect = grid.getBoundingClientRect()
    const isRtl = getComputedStyle(grid).direction === "rtl"
    const x = isRtl ? rect.right - clientX : clientX - rect.left
    const y = clientY - rect.top - SLOT_HEIGHT
    const colWidth = rect.width / 8
    const visualCol = Math.floor(x / colWidth)
    const day = clamp(visualCol - 1, 0, DAYS.length - 1)
    const slotIndex = Math.floor(y / SLOT_HEIGHT)
    const hour = HOUR_START + slotIndex * 0.5
    return {
      day,
      hour: clamp(hour, HOUR_START, HOUR_START + TOTAL_HOURS - 0.5),
    }
  }

  function applyDrag(current: DragState, clientX: number, clientY: number) {
    const slot = slotFromPoint(clientX, clientY)
    if (!slot) return
    const moved =
      current.moved ||
      Math.abs(clientX - current.originX) > 4 ||
      Math.abs(clientY - current.originY) > 4
    if (moved !== current.moved) {
      const next = { ...current, moved }
      dragRef.current = next
      setDrag(next)
    }

    // Track the offset from the point originally grabbed, rather than
    // snapping the block to the cursor's absolute slot — otherwise the
    // block jumps by however far off-center you grabbed it, which makes
    // it look like it moves faster than the mouse.
    const deltaDay = slot.day - current.originDay
    const deltaHour = slot.hour - current.originHour

    setBlocks((prev) =>
      prev.map((block) => {
        if (block.id !== current.id) return block
        if (current.mode === "resize") {
          const duration = clamp(
            current.startDuration + deltaHour,
            MIN_DURATION,
            maxDurationForHour(current.startHour),
          )
          return { ...block, duration }
        }
        const day = clamp(current.startDay + deltaDay, 0, DAYS.length - 1)
        const maxStart = HOUR_START + TOTAL_HOURS - current.startDuration
        const startHour = clamp(
          current.startHour + deltaHour,
          HOUR_START,
          Math.max(HOUR_START, maxStart),
        )
        return { ...block, day, startHour }
      }),
    )
  }

  function startInteraction(
    e: React.PointerEvent,
    block: ScheduleBlock,
    mode: DragMode,
  ) {
    e.preventDefault()
    e.stopPropagation()
    const originSlot = slotFromPoint(e.clientX, e.clientY) ?? {
      day: block.day,
      hour: block.startHour,
    }
    const next: DragState = {
      id: block.id,
      mode,
      originX: e.clientX,
      originY: e.clientY,
      originDay: originSlot.day,
      originHour: originSlot.hour,
      startDay: block.day,
      startHour: block.startHour,
      startDuration: block.duration,
      moved: false,
    }
    dragRef.current = next
    setDrag(next)
  }

  useEffect(() => {
    if (!drag) return

    function onMove(e: PointerEvent) {
      const current = dragRef.current
      if (!current) return
      applyDrag(current, e.clientX, e.clientY)
    }

    function onUp() {
      const current = dragRef.current
      dragRef.current = null
      setDrag(null)
      if (!current) return
      if (current.moved) {
        suppressClickRef.current = true
        return
      }
      const block = blocksRef.current.find((b) => b.id === current.id)
      if (block) openEdit(block)
    }

    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", onUp)
    return () => {
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", onUp)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drag])

  const draggingId = drag?.id ?? null
  const todayColumn = weekdayOf(today)
  const isCurrentWeek = currentOffset === 0
  const weekNumbers = MAX_WEEKS * 2 + 1
  const currentWeekKey = toISO(weekStart)
  const isCurrentWeekGenerating = generatingWeeks.has(currentWeekKey)

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
          <h1 className="flex-1 text-right font-bold text-lg">برنامه هفتگی</h1>
          {isCurrentWeekGenerating ? (
            <button
              onClick={() => stopGeneration(weekStart)}
              className="px-3 h-9 rounded-xl border border-red-400 bg-red-100 text-[11px] font-bold text-red-600 hover:bg-red-200 transition-colors dark:border-red-500 dark:bg-red-900/50 dark:text-red-400 dark:hover:bg-red-900"
            >
              توقف
            </button>
) : (
            <button
              onClick={() => void generateWeekPlan(weekStart)}
              disabled={generating && !isCurrentWeekGenerating}
              className="px-3 h-9 rounded-xl border border-[var(--border-strong)] text-[11px] font-bold text-[var(--muted)] disabled:opacity-40 hover:text-[var(--accent)] transition-colors"
            >
              {generating && !isCurrentWeekGenerating ? "در حال ساخت..." : "باز reconstruction"}
            </button>
          )}
          <button
            onClick={() => setShowChart(v => !v)}
            className={`px-3 h-9 rounded-xl border text-[11px] font-bold transition-colors ${showChart ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]" : "border-[var(--border-strong)] text-[var(--muted)] hover:text-[var(--accent)]"}`}
          >
            {showChart ? "تقویم" : "نمودار"}
          </button>
          <button
            onClick={() => openAdd(0, HOUR_START)}
            className="w-9 h-9 rounded-xl bg-[var(--accent)] text-white font-bold"
          >
            +
          </button>
        </div>

        {/* Week navigation (like Google Calendar) */}
        <div className="mt-3 flex items-center gap-2">
          <button
            onClick={() => navigate(-1)}
            disabled={currentOffset <= -MAX_WEEKS}
            className="w-8 h-8 rounded-lg bg-[var(--border)] flex items-center justify-center text-[var(--muted)] disabled:opacity-35 hover:bg-[var(--border-strong)] transition-colors"
            aria-label="هفته قبل"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
            >
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
          <button
            onClick={() => navigate(1)}
            disabled={currentOffset >= MAX_WEEKS}
            className="w-8 h-8 rounded-lg bg-[var(--border)] flex items-center justify-center text-[var(--muted)] disabled:opacity-35 hover:bg-[var(--border-strong)] transition-colors"
            aria-label="هفته بعد"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
            >
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>
          <div className="flex-1 text-center">
            <p className="text-[13px] font-bold text-[var(--text)]">
              {weekRangeLabel(weekStart)}
            </p>
            <p className="text-[10px] text-[var(--muted-2)] font-medium mt-0.5">
              {isCurrentWeek
                ? "هفته جاری"
                : `هفته ${faNum(currentOffset + MAX_WEEKS + 1)} از ${faNum(weekNumbers)}`}
            </p>
          </div>
          <button
            onClick={goToday}
            className="px-3 h-8 rounded-lg border border-[var(--border-strong)] text-[11px] font-bold text-[var(--muted)] hover:text-[var(--text)] transition-colors"
          >
            امروز
          </button>
        </div>
      </div>

      {!showChart && (
      <div className="flex-1 overflow-auto">
        <div
          ref={gridRef}
          className="relative grid grid-cols-8 min-w-[720px] select-none"
          style={{
            gridTemplateRows: `${SLOT_HEIGHT}px repeat(${SLOT_COUNT}, ${SLOT_HEIGHT}px)`,
          }}
        >
          <div className="sticky top-0 z-20 bg-[var(--card)] border-b border-l border-[var(--border)] p-2 text-center text-xs font-bold text-[var(--muted)]">
            ساعت
          </div>
          {DAYS.map((d, i) => {
            const date = addDays(weekStart, i)
            const [, jm, jd] = toJalali(date)
            const isToday = isCurrentWeek && i === todayColumn
            return (
              <div
                key={i}
                className={`sticky top-0 z-20 border-b border-l border-[var(--border)] p-2 text-center ${
                  isToday ? "bg-[var(--accent-soft)]" : "bg-[var(--card)]"
                }`}
              >
                <p
                  className={`text-xs font-bold ${
                    isToday ? "text-[var(--accent)]" : "text-[var(--text)]"
                  }`}
                >
                  {d}
                </p>
                <p
                  className="text-[9px] font-medium text-[var(--muted-2)] mt-0.5"
                  dir="rtl"
                >
                  {faNum(jd)} {jd === 1 ? PERSIAN_MONTHS[jm - 1] : ""}
                </p>
              </div>
            )
          })}

          {HOURS.map((hour, hIdx) => (
            <div key={hour} className="contents">
              <div className="border-l border-b border-[var(--border)] p-1 text-center text-xs text-[var(--muted)] flex items-center justify-center">
                {hour}
              </div>
              {DAYS.map((_, dIdx) => {
                const hourValue = HOUR_START + hIdx * 0.5
                const date = addDays(weekStart, dIdx)
                const isToday = isCurrentWeek && dIdx === todayColumn
                return (
                  <div
                    key={dIdx}
                    onClick={() => {
                      if (suppressClickRef.current) {
                        suppressClickRef.current = false
                        return
                      }
                      if (!dragRef.current) openAdd(dIdx, hourValue)
                    }}
                    className={`border-l border-b border-[var(--border)] relative cursor-pointer ${
                      isToday && date.getDate() === today.getDate()
                        ? "bg-[var(--accent-soft)]/60"
                        : ""
                    }`}
                  />
                )
              })}
            </div>
          ))}

          <div
            className="absolute pointer-events-none"
            style={{
              top: SLOT_HEIGHT,
              left: 0,
              right: "calc(100% / 8)",
              bottom: 0,
            }}
          >
            {displayedBlocks.map((b) =>
              isStaticInstance(b) ? (
                <div
                  key={b.id}
                  onClick={() => openEditStatic(b)}
                  className="schedule-block schedule-static pointer-events-auto absolute z-10 overflow-hidden px-1.5 py-1 text-xs cursor-pointer"
                  style={
                    {
                      "--block-color": resolveColor(b.color),
                      top: `${(b.startHour - HOUR_START) * 2 * SLOT_HEIGHT + 4}px`,
                      height: `${b.duration * 2 * SLOT_HEIGHT - 8}px`,
                      right: `calc(${(b.day * 100) / DAYS.length}% + 4px)`,
                      width: `calc(${100 / DAYS.length}% - 8px)`,
                    } as React.CSSProperties
                  }
                >
                  <div className="font-bold truncate flex items-center gap-1 pointer-events-none">
                    <span className="text-[10px] leading-none">↻</span>
                    <span className="truncate">{b.title}</span>
                  </div>
                  <div className="text-[10px] opacity-80 pointer-events-none">
                    {formatTime(b.startHour)} -{" "}
                    {formatTime(b.startHour + b.duration)}
                  </div>
                </div>
              ) : (
                <div
                  key={b.id}
                  onPointerDown={(e) => startInteraction(e, b, "move")}
                  onClick={(e) => e.stopPropagation()}
                  className={`schedule-block pointer-events-auto absolute z-10 overflow-hidden px-1.5 py-1 text-xs ${
                    draggingId === b.id ? "is-dragging z-30" : ""
                  }`}
                  style={
                    {
                      "--block-color": resolveColor(b.color),
                      top: `${(b.startHour - HOUR_START) * 2 * SLOT_HEIGHT + 4}px`,
                      height: `${b.duration * 2 * SLOT_HEIGHT - 8}px`,
                      right: `calc(${(b.day * 100) / DAYS.length}% + 4px)`,
                      width: `calc(${100 / DAYS.length}% - 8px)`,
                    } as React.CSSProperties
                  }
                >
                  <div className="font-bold truncate pointer-events-none">
                    {b.title}
                  </div>
                  <div className="text-[10px] opacity-80 pointer-events-none">
                    {formatTime(b.startHour)} -{" "}
                    {formatTime(b.startHour + b.duration)}
                  </div>
                  <div
                    className="schedule-block-resize-handle"
                    onPointerDown={(e) => startInteraction(e, b, "resize")}
                  />
                </div>
              ),
            )}
          </div>
        </div>
      </div>
      )}

      {showChart && (
        <GroqChart
          blocks={displayedBlocks
            .filter((b) => !isStaticInstance(b))
            .map((b) => ({ day: b.day, type: b.type, title: b.title, duration: b.duration }))}
        />
      )}

      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[var(--card)] rounded-2xl p-5 w-80 max-w-[90vw]">
            <h2 className="text-right font-bold mb-4">
              {editingStatic
                ? "ویرایش بلاک ثابت سالانه"
                : `افزودن ${recurring ? "بلاک ثابت سالانه" : "فعالیت"}`}
            </h2>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-[var(--muted)] mb-1 text-right">
                  روز
                </label>
                <select
                  value={selectedDay}
                  onChange={(e) => setSelectedDay(Number(e.target.value))}
                  className="w-full border rounded-xl px-3 py-2 text-sm bg-[var(--card)] text-[var(--text)]"
                >
                  {DAYS.map((d, i) => (
                    <option key={i} value={i}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-[var(--muted)] mb-1 text-right">
                  عنوان
                </label>
                <input
                  type="text"
                  value={newBlock.title}
                  onChange={(e) =>
                    setNewBlock({ ...newBlock, title: e.target.value })
                  }
                  placeholder="مثال: ریاضی"
                  className="w-full border rounded-xl px-3 py-2 text-sm text-right bg-[var(--card)] text-[var(--text)]"
                />
              </div>

              <div>
                <label className="block text-xs text-[var(--muted)] mb-1 text-right">
                  رنگ
                </label>
                <div className="flex gap-2 justify-end overflow-x-auto py-1">
                  {COLOR_OPTIONS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setNewBlock({ ...newBlock, color: c })}
                      className={`w-6 h-6 rounded-full border ${
                        newBlock.color === c
                          ? "ring-2 ring-[var(--text)]"
                          : "border-[var(--border-strong)]"
                      }`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs text-[var(--muted)] mb-1 text-right">
                  نوع
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {(Object.keys(TYPE_LABELS) as BlockType[]).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() =>
                        setNewBlock({
                          ...newBlock,
                          type: t,
                          color: TYPE_COLORS[t],
                        })
                      }
                      className={`py-2 rounded-xl text-xs font-medium ${
                        newBlock.type === t
                          ? "text-[#1b1c1a]"
                          : "bg-[var(--surface-2)] text-[var(--text)]"
                      }`}
                      style={
                        newBlock.type === t
                          ? { backgroundColor: TYPE_COLORS[t] }
                          : undefined
                      }
                    >
                      {TYPE_LABELS[t]}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-[var(--muted)] mb-1 text-right">
                    ساعت شروع
                  </label>
                  <select
                    value={newBlock.startHour}
                    onChange={(e) =>
                      setNewBlock({
                        ...newBlock,
                        startHour: Number(e.target.value),
                      })
                    }
                    className="w-full border rounded-xl px-3 py-2 text-sm bg-[var(--card)] text-[var(--text)]"
                  >
                    {Array.from({ length: SLOT_COUNT }, (_, i) => {
                      const val = HOUR_START + i * 0.5
                      return (
                        <option key={i} value={val}>
                          {formatTime(val)}
                        </option>
                      )
                    })}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-[var(--muted)] mb-1 text-right">
                    مدت (ساعت)
                  </label>
                  <select
                    value={newBlock.duration}
                    onChange={(e) =>
                      setNewBlock({
                        ...newBlock,
                        duration: Number(e.target.value),
                      })
                    }
                    className="w-full border rounded-xl px-3 py-2 text-sm bg-[var(--card)] text-[var(--text)]"
                  >
                    {[0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6].map(
                      (d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ),
                    )}
                  </select>
                </div>
              </div>

              {/* Static (yearly repeating) toggle */}
              {!editingBlock && (
                <div className="space-y-2">
                  <button
                    type="button"
                    onClick={() => toggleRecurring(!recurring)}
                    className={`w-full flex items-center gap-2 rounded-xl border px-3 py-2.5 text-right text-xs font-bold transition-colors ${
                      recurring
                        ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                        : "border-[var(--border-strong)] text-[var(--muted)]"
                    }`}
                  >
                    <span style={{ opacity: recurring ? 1 : 0.4 }}>↻</span>
                    <span className="flex-1">
                      بلاک ثابت (تکرارشونده)
                    </span>
                    <span
                      className={`w-8 h-4.5 rounded-full relative transition-colors ${
                        recurring
                          ? "bg-[var(--accent)]"
                          : "bg-[var(--toggle-off)]"
                      }`}
                      style={{ height: 18 }}
                    >
                      <span
                        className={`absolute top-0.5 w-3.5 h-3.5 rounded-full bg-white transition-all ${
                          recurring ? "right-0.5" : "right-[16px]"
                        }`}
                        style={{ top: 2, width: 14, height: 14 }}
                      />
                    </span>
                  </button>
                  {recurring && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => setNewBlock(b => ({ ...b, date: undefined, day: selectedDay }))}
                        className={`flex-1 py-1 rounded-lg text-xs font-bold border ${newBlock.day !== undefined ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]" : "border-[var(--border-strong)] text-[var(--muted)]"}`}
                      >
                        هفتگی
                      </button>
                      <button
                        onClick={() => setNewBlock(b => ({ ...b, day: undefined, date: toISO(addDays(startOfWeek(weekStartRef.current), selectedDay)) }))}
                        className={`flex-1 py-1 rounded-lg text-xs font-bold border ${newBlock.date !== undefined ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]" : "border-[var(--border-strong)] text-[var(--muted)]"}`}
                      >
                        سالانه
                      </button>
                    </div>
                  )}
                </div>
              )}
              {recurring && (
                <p className="text-[10px] text-[var(--muted-2)] text-right leading-relaxed">
                  این بلاک هر سال در همین هفته به‌صورت خودکار ظاهر می‌شود (مثلاً
                  آزمون‌های سالانه).
                </p>
              )}
            </div>

            <div className="flex gap-2 mt-5">
              {(editingBlock || editingStatic) && (
                <button
                  onClick={deleteCurrentBlock}
                  className="px-4 py-2 rounded-xl bg-red-100 text-red-600 font-bold text-sm"
                >
                  حذف
                </button>
              )}
              <div className="flex-1" />
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 rounded-xl border text-sm text-[var(--text)]"
              >
                انصراف
              </button>
              <button
                onClick={saveBlock}
                className="px-4 py-2 rounded-xl bg-[var(--accent)] text-white font-bold text-sm"
              >
                ذخیره
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
