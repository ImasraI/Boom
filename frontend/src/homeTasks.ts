/**
 * Home to-do list <-> weekly plan sync.
 *
 * The Home "تکالیف امروز" list is no longer hardcoded demo data: it is
 * derived, in real time, from the same store the Schedule page authors and
 * the AI chat updates (boom-weekly-schedule:<weekISO> + weekly statics).
 *
 * Derived shape:  homeTasks:YYYY-MM-DD -> { done: number[], skipped: number[] }
 * Task identity is a numeric hash of (title, startHour), so checkboxes stay
 * stable across reloads as long as the plan block is unchanged.
 *
 * Only study/test blocks become to-dos — classes and breaks fill the
 * Schedule grid but would be noise as a to-do list.
 */
import {
  addDays,
  fromISO,
  loadStaticTemplates,
  loadWeekBlocks,
  saveWeekBlocks,
  SCHEDULE_CHANGED_EVENT,
  startOfWeek,
  staticWeekday,
  toISO,
  weekdayOf,
  type StoredBlock,
  type StoredStatic,
} from "./scheduleStore";
import type { Task } from "./types";

export const HOME_TASKS_PREFIX = "homeTasks:";

export interface HomeTask {
  id: number; // stable hash; index into done/skipped arrays
  planBlock: StoredBlock; // always present; edits/postpones write back
  title: string;
  description: string;
  subject: string;
  type: Task["type"];
  duration: string;
  scheduledTime: string;
  done: boolean;
  skipped: boolean;
}

interface DoneSkipped {
  done: number[];
  skipped: number[];
}

/** Block types that make sense as a to-do for the day. */
const TODO_TYPES = new Set<string>(["study", "test"]);

export function loadDoneSkipped(dateISO: string): DoneSkipped {
  const raw = localStorage.getItem(HOME_TASKS_PREFIX + dateISO);
  if (!raw) return { done: [], skipped: [] };
  try {
    const parsed = JSON.parse(raw) as Partial<DoneSkipped> | null;
    const nums = (x: unknown) =>
      Array.isArray(x) && x.every((n) => typeof n === "number") ? (x as number[]) : [];
    return { done: nums(parsed?.done), skipped: nums(parsed?.skipped) };
  } catch {
    return { done: [], skipped: [] };
  }
}

export function saveDoneSkipped(dateISO: string, state: DoneSkipped) {
  localStorage.setItem(HOME_TASKS_PREFIX + dateISO, JSON.stringify(state));
}

/** Numeric hash of title+startHour: stable across reloads within a day. */
function taskHash(title: string, startHour: number): number {
  const s = `${title}@${startHour}`;
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h % 100000);
}

/** "9.5" -> "9:30" */
function fmtHour(h: number): string {
  const hh = Math.floor(h) % 24;
  const mm = Math.round((h - Math.floor(h)) * 60);
  return `${hh}:${mm === 0 ? "00" : mm}`;
}

/** 1.5 -> "۱.۵ ساعت"-style label used by the task cards. */
function fmtDuration(duration: number): string {
  const totalMin = Math.round(duration * 60);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h && m) return `${h} ساعت و ${m} دقیقه`;
  if (h) return `${h} ساعت`;
  return `${m} دقیقه`;
}

/** Best-effort subject extraction from a block title (for the color chip). */
export function subjectOf(title: string): string {
  const subjects = [
    "حسابان", "ریاضی", "هندسه", "فیزیک", "شیمی", "زیست", "ادبیات", "عربی",
    "دین و زندگی", "تاریخ", "جغرافیا", "اقتصاد", "منطق", "جامعه‌شناسی",
    "روان‌شناسی", "زبان انگلیسی", "زبان", "گسسته", "جبر", "فلسفه", "عمران",
  ];
  const hit = subjects.find((w) => title.includes(w));
  if (hit) return hit;
  // Class/test blocks usually name the subject after the type word.
  const m = title.match(/^(?:کلاس|آزمون|آزمایی)\s+(.+)$/)
  if (m) return m[1];
  return "عمومی";
}

function blockToHomeTask(block: StoredBlock): HomeTask {
  const isTest = block.type === "test";
  return {
    id: taskHash(block.title, block.startHour),
    planBlock: block,
    title: block.title,
    description: block.description ?? "",
    subject: subjectOf(block.title),
    type: isTest ? "test" : "study",
    duration: fmtDuration(block.duration),
    scheduledTime: fmtHour(block.startHour),
    done: false,
    skipped: false,
  };
}

/** Week key that owns a given calendar date (Persian week starts شنبه). */
export function weekOf(d: Date): string {
  return toISO(startOfWeek(d));
}

/** Today's plan (week blocks + repeating statics) as HomeTask[]. */
export function homeTasksForDate(
  dateISO: string,
  opts?: { includeSkipped?: boolean },
): HomeTask[] {
  const includeSkipped = opts?.includeSkipped ?? true;
  const date = fromISO(dateISO);
  const dayOfWeek = weekdayOf(date);
  const blocks = loadWeekBlocks(weekOf(date));
  const statics = loadStaticTemplates();

  const dayBlocks: StoredBlock[] = blocks
    .filter((b) => b.day === dayOfWeek && TODO_TYPES.has(b.type))
    .sort((a, b) => a.startHour - b.startHour);

  for (const t of statics) {
    if (staticWeekday(t) === dayOfWeek && TODO_TYPES.has(t.type)) {
      dayBlocks.push({
        day: dayOfWeek,
        startHour: t.startHour,
        duration: t.duration,
        title: t.title,
        type: t.type,
        color: t.color,
        description: t.description,
      });
    }
  }
  dayBlocks.sort((a, b) => a.startHour - b.startHour);
  // A static template can duplicate a generated block (same title+hour):
  // keep one card per (title, startHour).
  const seen = new Set<string>();
  const unique = dayBlocks.filter((b) => {
    const k = `${b.title}@${b.startHour}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });

  const { done, skipped } = loadDoneSkipped(dateISO);
  const tasks = unique.map((b) => {
    const task = blockToHomeTask(b);
    task.done = done.includes(task.id);
    task.skipped = skipped.includes(task.id);
    return task;
  });

  return includeSkipped ? tasks : tasks.filter((t) => !t.skipped);
}

function notifyChanged() {
  window.dispatchEvent(new CustomEvent(SCHEDULE_CHANGED_EVENT));
}

/** Checkbox handler; `done` omitted = toggle. */
export function toggleDone(dateISO: string, task: HomeTask, done?: boolean) {
  const state = loadDoneSkipped(dateISO);
  const next = {
    done: state.done.includes(task.id)
      ? state.done.filter((x) => x !== task.id)
      : [...state.done, task.id],
    skipped: state.skipped,
  };
  void done; // kept for future explicit set; toggle covers current UI
  saveDoneSkipped(dateISO, next);
}

/** Remove the block from today's list AND copy it into tomorrow's plan
 * (same title, same hour) — a real postpone, not just hiding. If the plan
 * already has that block tomorrow, only today's list is updated. */
export function postponeToTomorrow(dateISO: string, task: HomeTask) {
  const tomorrow = addDays(fromISO(dateISO), 1);
  const tomorrowISO = toISO(tomorrow);
  const block = task.planBlock;
  const moved: StoredBlock = {
    ...block,
    id: undefined,
    day: weekdayOf(tomorrow),
  };
  const weekISO = weekOf(tomorrow);
  const blocks = loadWeekBlocks(weekISO);
  const exists = blocks.some(
    (b) =>
      b.day === moved.day &&
      b.startHour === moved.startHour &&
      b.title === moved.title,
  );
  if (!exists) {
    blocks.push(moved);
    saveWeekBlocks(weekISO, blocks); // fires SCHEDULE_CHANGED_EVENT
  } else {
    notifyChanged();
  }

  // Hide it from today's list from now on.
  const state = loadDoneSkipped(dateISO);
  if (!state.skipped.includes(task.id)) {
    state.skipped = [...state.skipped, task.id];
    state.done = state.done.filter((x) => x !== task.id);
    saveDoneSkipped(dateISO, state);
  }
}

/** Edit sheet "ذخیره" writes the edit back into the weekly plan block. */
export function saveTaskEdit(
  dateISO: string,
  task: HomeTask,
  patch: { title: string; description: string; duration?: string; scheduledTime?: string },
) {
  const weekISO = weekOf(fromISO(dateISO));
  const blocks = loadWeekBlocks(weekISO);
  const b = task.planBlock;
  const idx = blocks.findIndex(
    (x) =>
      x.day === b.day &&
      x.startHour === b.startHour &&
      x.duration === b.duration &&
      x.title === b.title,
  );
  if (idx >= 0) {
    const next: StoredBlock = { ...blocks[idx], title: patch.title, description: patch.description };
    const hour = parseScheduledTime(patch.scheduledTime);
    if (hour !== null) next.startHour = hour;
    const dur = parseDuration(patch.duration);
    if (dur !== null) next.duration = dur;
    blocks[idx] = next;
    saveWeekBlocks(weekISO, blocks);
  }
}

function toLatinDigits(s: string): string {
  return s.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)));
}

/** "9:30" / "۹:۳۰" -> 9.5 (null if unparseable). */
function parseScheduledTime(s?: string): number | null {
  if (!s) return null;
  const m = toLatinDigits(s).trim().match(/^(\d{1,2})[:.](\d{1,2})$/);
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return null;
  return h + min / 60;
}

/** "1.5 ساعت" / "۹۰ دقیقه" / "1.5" -> hours (null if no number found). */
function parseDuration(s?: string): number | null {
  if (!s) return null;
  const latin = toLatinDigits(s);
  const m = latin.match(/(\d+(?:\.\d+)?)/);
  if (!m) return null;
  const n = Number(m[1]);
  const isMinutes = /دقیقه|min/i.test(latin) || (!/ساعت|hour/i.test(latin) && n > 8);
  const hours = isMinutes ? n / 60 : n;
  return Math.min(6, Math.max(0.25, hours));
}
