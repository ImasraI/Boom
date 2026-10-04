import { accountStorageFor } from "./accountStorage";
import { apiUrl, authHeaders } from "./api";
import type { StoredBlock, StoredStatic } from "./scheduleStore";

type Calendar = { weeks: Record<string, StoredBlock[]>; statics: StoredStatic[]; version: number };
type Changes = { weeks: Record<string, StoredBlock[]>; statics?: StoredStatic[] };
const VERSION = "boom-calendar-version";
const OUTBOX = "boom-calendar-outbox";
const active = new Map<string, Promise<boolean>>();
const errors = new Map<string, string>();
function readChanges(cache: ReturnType<typeof accountStorageFor>): Changes {
  try { return JSON.parse(cache.getItem(OUTBOX) || '{"weeks":{}}'); }
  catch { return { weeks: {} }; }
}
function signal(token: string) {
  if (localStorage.getItem("boom-token") === token) window.dispatchEvent(new CustomEvent("boom-schedule-changed"));
}
function cacheCalendar(token: string, data: Calendar, pending: Changes = { weeks: {} }) {
  const cache = accountStorageFor(token);
  let previous: string[] = [];
  try { previous = JSON.parse(cache.getItem("boom-calendar-weeks") || "[]"); } catch { /* cache */ }
  const weeks = { ...data.weeks, ...pending.weeks };
  for (const iso of previous) if (!(iso in weeks)) cache.removeItem("boom-weekly-schedule:" + iso);
  for (const [iso, blocks] of Object.entries(weeks)) cache.setItem("boom-weekly-schedule:" + iso, JSON.stringify(blocks));
  cache.setItem("boom-calendar-weeks", JSON.stringify(Object.keys(weeks)));
  cache.setItem("boom-weekly-static", JSON.stringify(pending.statics ?? data.statics));
  cache.setItem(VERSION, String(data.version));
  signal(token);
}
export function calendarVersion() {
  const raw = accountStorageFor().getItem(VERSION);
  return raw === null ? undefined : Number(raw);
}
export function acceptGeneratedCalendar(week: string, blocks: StoredBlock[], version: number) {
  const cache = accountStorageFor();
  if (readChanges(cache).weeks[week]) throw new Error("برنامه هنگام بازسازی تغییر کرده است؛ تغییرات شما نگه داشته شدند. دوباره همگام‌سازی کنید.");
  cache.setItem("boom-weekly-schedule:" + week, JSON.stringify(blocks));
  cache.setItem(VERSION, String(version));
  signal(localStorage.getItem("boom-token") || "");
}
export function queueCalendar(changes: Partial<Changes>) {
  const token = localStorage.getItem("boom-token");
  if (!token) return;
  const cache = accountStorageFor(token), old = readChanges(cache);
  cache.setItem(OUTBOX, JSON.stringify({ ...old, ...changes, weeks: { ...old.weeks, ...changes.weeks } }));
  void flushCalendar(token);
}
export async function pullCalendar(token = localStorage.getItem("boom-token")): Promise<boolean> {
  if (!token) return false;
  try {
    const response = await fetch(apiUrl("/api/profile/calendar"), { headers: authHeaders(token) });
    if (!response.ok) throw new Error("بارگذاری برنامه انجام نشد.");
    const data: Calendar = await response.json();
    const cache = accountStorageFor(token), pending = readChanges(cache);
    const previousVersion = cache.getItem(VERSION);
    if ((Object.keys(pending.weeks).length || pending.statics) && previousVersion !== null && Number(previousVersion) !== data.version) {
      throw new Error("برنامه روی دستگاه دیگری تغییر کرده است؛ تغییرات ارسال‌نشده نگه داشته شدند.");
    }
    // Migrate only this account's cache, and only weeks absent on the server.
    if (previousVersion === null) {
      const prefix = `boom-account:`;
      const captured = accountStorageFor(token);
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        const iso = key?.startsWith(prefix) ? key.match(/:boom-weekly-schedule:(\d{4}-\d{2}-\d{2})$/)?.[1] : undefined;
        if (iso && !(iso in data.weeks)) {
          const raw = captured.getItem("boom-weekly-schedule:" + iso);
          if (raw) { try { pending.weeks[iso] = JSON.parse(raw); } catch { /* malformed legacy cache */ } }
        }
      }
      const oldStatics = captured.getItem("boom-weekly-static");
      if (oldStatics && !data.statics.length) { try { pending.statics = JSON.parse(oldStatics); } catch { /* cache */ } }
      if (Object.keys(pending.weeks).length || pending.statics) cache.setItem(OUTBOX, JSON.stringify(pending));
    }
    cacheCalendar(token, data, pending);
    errors.delete(token);
    return true;
  } catch (error) {
    errors.set(token, error instanceof Error ? error.message : "خطای ارتباط با برنامه");
    signal(token);
    return false;
  }
}
export function calendarSyncError() { return errors.get(localStorage.getItem("boom-token") || "") || ""; }
export async function flushCalendar(token = localStorage.getItem("boom-token")): Promise<boolean> {
  if (!token) return false;
  const running = active.get(token);
  if (running) return running;
  const job = (async () => {
    const cache = accountStorageFor(token);
    if (cache.getItem(VERSION) === null && !await pullCalendar(token)) return false;
    while (true) {
      const snapshot = cache.getItem(OUTBOX), changes = readChanges(cache);
      if (!Object.keys(changes.weeks).length && changes.statics === undefined) return true;
      try {
        const response = await fetch(apiUrl("/api/profile/calendar"), {
          method: "PATCH", headers: { ...authHeaders(token), "Content-Type": "application/json" },
          body: JSON.stringify({ ...changes, version: Number(cache.getItem(VERSION)) }),
        });
        if (!response.ok) throw new Error(response.status === 409
          ? "برنامه روی دستگاه دیگری تغییر کرده است؛ تغییرات شما نگه داشته شدند."
          : "ذخیرهٔ برنامه انجام نشد؛ تغییرات روی این دستگاه نگه داشته شدند.");
        const data: Calendar = await response.json();
        // Keep newer edits queued while an earlier snapshot was in flight.
        if (cache.getItem(OUTBOX) === snapshot) cache.removeItem(OUTBOX);
        cacheCalendar(token, data, readChanges(cache));
        errors.delete(token);
      } catch (error) {
        errors.set(token, error instanceof Error ? error.message : "خطای ذخیره برنامه");
        signal(token);
        return false;
      }
    }
  })();
  active.set(token, job);
  try { return await job; } finally { active.delete(token); }
}
