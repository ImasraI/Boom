const numerals = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });

export const faNumber = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? "—" : numerals.format(value);
export const faPercent = (value: number | null | undefined) => value == null ? "—" : `${faNumber(value)}٪`;

/** API timestamps are UTC; date labels always belong to the Tehran event clock. */
export function timestamp(value: string): number {
  return Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

export function eventDate(value: string | null | undefined): string {
  if (!value) return "زمان به‌زودی اعلام می‌شود";
  const time = timestamp(value);
  return Number.isFinite(time) ? new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Tehran",
  }).format(time) : "زمان اعلام نشده";
}

export function eventStatus(status: string): string {
  return ({ draft: "در حال آماده‌سازی", league: "مرحلهٔ لیگ", knockout: "مرحلهٔ حذفی",
    completed: "پایان‌یافته", scheduled: "در انتظار بازی", active: "در حال برگزاری",
    live: "در حال بازی", playing: "در حال بازی", pending: "در انتظار تعیین حریف",
    bye: "استراحت این دور", forfeit: "نتیجهٔ غیبت", awaiting_tiebreak: "در انتظار رفع تساوی",
    awaiting_result: "در انتظار نتیجه", finished: "پایان‌یافته", closed: "پایان مهلت",
  } as Record<string, string>)[status] || "در انتظار اعلام وضعیت";
}

export function clockText(milliseconds: number): string {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}
