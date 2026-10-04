export interface Recurrence {
  frequency: "daily" | "weekly" | "monthly" | "yearly";
  interval: number;
  weekdays?: number[];
  until?: string;
  count?: number;
}
type Template = { id?: string; date?: string; day?: number; recurrence?: Recurrence };
function parse(iso: string) { const [y, m, d] = iso.split("-").map(Number); return new Date(Date.UTC(y, m - 1, d)); }
function iso(d: Date) { return d.toISOString().slice(0, 10); }
const weekday = (d: Date) => (d.getUTCDay() + 1) % 7;
/** UTC date-only arithmetic makes recurrence independent of browser DST. */
export function expandTemplates<T extends Template>(templates: T[], weekISO: string): (T & { day: number; templateId?: string })[] {
  const start = parse(weekISO), end = new Date(+start + 6 * 86400000);
  return templates.flatMap(t => {
    if (!t.recurrence && typeof t.day === "number") return [{ ...t, day: t.day, templateId: t.id }];
    if (!t.date) return [];
    const anchor = parse(t.date);
    const rule: Recurrence = t.recurrence || { frequency: "yearly", interval: 1 };
    const interval = Math.max(1, rule.interval || 1);
    const until = rule.until ? parse(rule.until) : end;
    const days = rule.weekdays?.length ? rule.weekdays : [weekday(anchor)];
    const out: (T & { day: number; templateId?: string })[] = [];
    let count = 0;
    for (let cursor = anchor; cursor <= end && cursor <= until; cursor = new Date(+cursor + 86400000)) {
      const delta = Math.round((+cursor - +anchor) / 86400000);
      const weeks = Math.floor((delta + weekday(anchor)) / 7);
      const months = (cursor.getUTCFullYear() - anchor.getUTCFullYear()) * 12 + cursor.getUTCMonth() - anchor.getUTCMonth();
      const match = rule.frequency === "daily" ? delta % interval === 0
        : rule.frequency === "weekly" ? weeks % interval === 0 && days.includes(weekday(cursor))
        : rule.frequency === "monthly" ? months % interval === 0 && cursor.getUTCDate() === anchor.getUTCDate()
        : (cursor.getUTCFullYear() - anchor.getUTCFullYear()) % interval === 0 && cursor.getUTCMonth() === anchor.getUTCMonth() && cursor.getUTCDate() === anchor.getUTCDate();
      if (!match) continue;
      count++;
      if (rule.count && count > rule.count) break;
      if (cursor >= start) out.push({ ...t, id: `${t.id || "repeat"}:${iso(cursor)}`, templateId: t.id, day: Math.round((+cursor - +start) / 86400000) });
    }
    return out;
  });
}
