export interface QueueStats {
  enabled: boolean;
  capacity: number;
  pending_booklets: number;
  pending_questions: number;
  drafting_booklets: number;
  verifying_booklets: number;
  completed_booklets: number;
  rejected_booklets: number;
  verified_questions: number;
  rejected_questions: number;
}
export interface PoolWorkerState {
  status: string;
  provider?: string;
  fallback?: boolean;
  retry_at?: string;
}
const labels: Record<string, string> = {
  generating: "در حال طراحی سؤال", verifying: "در حال بررسی پاسخ",
  waiting_for_quota: "منتظر سهمیهٔ سرویس", waiting_for_queue: "منتظر خالی شدن صف",
  waiting_for_drafts: "منتظر پیش‌نویس", error: "خطا؛ پیش‌نویس‌ها حفظ شده‌اند",
};
export default function PoolDraftQueue({ queue, drafting, verification, running }: {
  queue?: QueueStats;
  drafting?: PoolWorkerState;
  verification?: PoolWorkerState;
  running?: boolean;
}) {
  if (!queue?.enabled) return null;
  const n = (value: number) => value.toLocaleString("fa-IR");
  return <section className="study-section p-5 space-y-4" aria-labelledby="draft-queue-title">
    <h2 id="draft-queue-title" className="font-bold">صف پیش‌نویس‌های آزمون</h2>
    <p className="text-xs text-[var(--muted)] leading-relaxed">
      طراحی و بررسی پاسخ هم‌زمان اجرا می‌شوند. پیش‌نویس‌ها در سرور ذخیره می‌شوند و تا تأیید وارد تمرین یا رنکینگ نمی‌شوند.
      سقف صف برای جلوگیری از مصرف بی‌وقفهٔ سهمیه است؛ بانک سؤال‌های تأییدشده سقف ندارد.
    </p>
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 border-y border-[var(--border)] py-4 text-xs">
      <div><strong className="block text-lg mb-1">{n(queue.pending_booklets)} / {n(queue.capacity)}</strong>دفترچهٔ در صف</div>
      <div><strong className="block text-lg mb-1">{n(queue.pending_questions)}</strong>سؤال منتظر بررسی</div>
      <div><strong className="block text-lg mb-1">{n(queue.verified_questions)}</strong>سؤال تأییدشده از صف</div>
      <div><strong className="block text-lg mb-1">{n(queue.rejected_questions)}</strong>سؤال ردشده و کنارگذاشته‌شده</div>
    </div>
    <div className="grid sm:grid-cols-2 gap-4 text-xs">
      {[{ name: "طراحی", worker: drafting }, { name: "بررسی پاسخ", worker: verification }].map(({ name, worker }) =>
        <div key={name} className="space-y-1">
          <p className="font-bold">{name}: {running ? labels[worker?.status ?? ""] ?? "در حال راه‌اندازی" : "متوقف"}</p>
          {running && worker?.provider && <p className="text-[var(--muted)]">{worker.provider === "groq" ? "Groq" : "Gemini"}{worker.fallback ? " · پشتیبان" : ""}</p>}
          {running && worker?.retry_at && <p className="text-[var(--muted)]">بررسی دوباره پس از: {new Date(worker.retry_at).toLocaleString("fa-IR", { timeZone: "Asia/Tehran" })}</p>}
        </div>)}
    </div>
  </section>;
}
