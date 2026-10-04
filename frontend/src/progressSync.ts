import { accountId, accountStorageFor } from "./accountStorage";
import { apiUrl, authHeaders } from "./api";

const KEY = "study-progress-outbox";
export interface ProgressUpdate {
  client_ref: string; source_ref?: string; date: string; subject: string; topic: string;
  task_type: string; planned_minutes: number; actual_minutes: number;
  resource?: string | null; question_start?: number | null; question_end?: number | null;
  page_start?: number | null; page_end?: number | null;
  status: "planned" | "completed" | "missed" | "partially_completed" | "rescheduled";
}

const pending = new Map<string, Promise<boolean>>();

export function flushProgress(): Promise<boolean> {
  const token = localStorage.getItem("boom-token");
  const id = accountId(token);
  if (!id) return Promise.resolve(false);
  const previous = pending.get(id) || Promise.resolve(true);
  const next = previous.then(() => sendProgress(token));
  pending.set(id, next);
  void next.finally(() => { if (pending.get(id) === next) pending.delete(id); });
  return next;
}

async function sendProgress(token: string | null): Promise<boolean> {
  const cache = accountStorageFor(token);
  const read = (): Record<string, ProgressUpdate> => {
    try { return JSON.parse(cache.getItem(KEY) || "{}"); } catch { return {}; }
  };
  for (const [key, item] of Object.entries(read())) {
    try {
      const response = await fetch(apiUrl("/api/profile/progress"), {
        method: "PUT", headers: { "Content-Type": "application/json", ...authHeaders(token) },
        body: JSON.stringify(item),
      });
      if (!response.ok) return false;
      const latest = read();
      if (JSON.stringify(latest[key]) === JSON.stringify(item)) delete latest[key];
      cache.setItem(KEY, JSON.stringify(latest));
    } catch { return false; }
  }
  return true;
}

export function queueProgress(item: ProgressUpdate) {
  const cache = accountStorageFor();
  let outbox: Record<string, ProgressUpdate> = {};
  try { outbox = JSON.parse(cache.getItem(KEY) || "{}"); } catch { /* restore below */ }
  outbox[item.client_ref] = item;
  cache.setItem(KEY, JSON.stringify(outbox));
  void flushProgress();
}
