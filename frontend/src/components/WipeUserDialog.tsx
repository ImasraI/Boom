import { useEffect, useId, useRef } from "react";

/**
 * Type-to-confirm guard for the admin wipe. The backend compares the same
 * trimmed string against the account's username, so keep this in sync with
 * `wipe_user_data` in backend/app/routers/admin.py.
 */
export function wipeConfirmReady(typed: string, username: string) {
  return typed.trim() === username;
}

/** Roughly what `_wipe_user_data` removes; kept in the copy so the admin
 *  knows the pool and the signup allowlist survive. */
const REMOVED = [
  "حساب کاربر و پروفایل دانش‌آموزی",
  "گفتگوهای چت و پاسخ‌های ذخیره‌شده",
  "آزمون‌ها، کارنامه‌ها و پاسخ‌های غلط",
  "کارهای روزانه و جلسات مطالعه",
  "دفترچه‌های مصرف‌شده و تلاش‌های آزمون",
  "نوبت‌ها و بازی‌های کولوسئوم",
  "فایل‌های آپلودی و تصاویر صفحات این کاربر",
  "همهٔ بردارهای این کاربر در سه مجموعهٔ جست‌وجو",
];

interface Props {
  target: { id: number; username: string };
  typed: string;
  busy?: boolean;
  error?: string;
  onTypedChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function WipeUserDialog({
  target, typed, busy = false, error = "", onTypedChange, onCancel, onConfirm,
}: Props) {
  const titleId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const ready = wipeConfirmReady(typed, target.username);

  // Focus the confirm field on open and let Escape back out without destroying
  // anything, matching the other modals in the app.
  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={busy ? undefined : onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={event => event.stopPropagation()}
        className="w-full max-w-[420px] max-h-[85vh] overflow-y-auto bg-[var(--card)] rounded-2xl p-5 shadow-2xl space-y-4"
      >
        <div className="space-y-1">
          <h2 id={titleId} className="font-display text-lg text-[var(--text)]">
            حذف کامل داده‌های کاربر
          </h2>
          <p className="text-xs text-[var(--muted)] leading-relaxed">
            شناسه #{target.id} · <span dir="ltr" className="font-mono">{target.username}</span>
          </p>
        </div>

        <p className="text-xs text-red-400 leading-relaxed">
          این کار قابل بازگشت نیست. با تایید، موارد زیر برای همیشه پاک می‌شوند:
        </p>
        <ul className="text-xs text-[var(--muted)] space-y-1 list-disc ps-4">
          {REMOVED.map(item => <li key={item}>{item}</li>)}
        </ul>
        <p className="text-[11px] text-[var(--muted-2)] leading-relaxed">
          بانک مشترک آزمون‌ها و لیست عبور ثبت‌نام دست‌نخورده می‌ماند. حساب‌های مدیر از این
          مسیر حذف نمی‌شوند.
        </p>

        <label className="block space-y-1.5">
          <span className="text-[11px] text-[var(--muted)]">
            برای تایید، نام کاربری (شماره) را دوباره بنویسید:
          </span>
          <input
            ref={inputRef}
            value={typed}
            onChange={event => onTypedChange(event.target.value)}
            disabled={busy}
            dir="ltr"
            inputMode="tel"
            autoComplete="off"
            aria-label="تایید نام کاربری برای حذف کامل"
            placeholder={target.username}
            className="w-full px-3 py-2.5 rounded-xl bg-[var(--surface-2)] border border-[var(--border)] text-sm text-[var(--text)] outline-none focus:border-[var(--accent)] disabled:opacity-50"
          />
        </label>

        {error && <p role="alert" className="text-xs text-red-400 leading-relaxed">{error}</p>}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="flex-1 py-3 rounded-xl border border-[var(--border)] text-[var(--muted)] font-bold text-[13px] hover:text-[var(--text)] disabled:opacity-40"
          >
            انصراف
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy || !ready}
            className="flex-1 py-3 rounded-xl bg-red-500/90 text-white font-bold text-[13px] hover:bg-red-500 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {busy ? "در حال حذف…" : "حذف کامل داده‌ها"}
          </button>
        </div>
        {!ready && !busy && (
          <p className="text-[10px] text-[var(--muted-2)]">
            تا وقتی نام کاربری دقیقاً مطابق نباشد، دکمهٔ حذف فعال نمی‌شود.
          </p>
        )}
      </div>
    </div>
  );
}
