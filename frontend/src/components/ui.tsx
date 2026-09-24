/**
 * Shared UI primitives for the auth flow (and reusable app-wide).
 * Pure presentation: no API calls, no business logic.
 */
import { useRef, useState, type ReactNode, type KeyboardEvent as ReactKeyboardEvent, type ClipboardEvent as ReactClipboardEvent } from "react";

/* ---------------------------------- Back ---------------------------------- */

export function BackButton({ onClick, label = "بازگشت" }: { onClick: () => void; label?: string }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className="press w-11 h-11 rounded-2xl bg-[var(--card)] border border-[var(--border-strong)] shadow-soft flex items-center justify-center text-[var(--muted)] hover:text-[var(--text)] hover:border-[var(--accent-soft-border)] transition-colors"
    >
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
        <path d="M19 12H5M12 5l-7 7 7 7" />
      </svg>
    </button>
  );
}

/* --------------------------------- Orbs ----------------------------------- */

/** Ambient blurred orbs behind auth screens (decorative only). */
export function AuthOrbs() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden>
      <div
        className="orb floaty"
        style={{ width: 340, height: 340, top: "-6rem", insetInlineStart: "-7rem", background: "rgb(var(--accent-rgb) / 0.16)" }}
      />
      <div
        className="orb"
        style={{ width: 260, height: 260, bottom: "-4rem", insetInlineEnd: "-5rem", background: "rgb(var(--accent-rgb) / 0.10)", animation: "floaty 6s ease-in-out infinite reverse" }}
      />
    </div>
  );
}

/* ------------------------------ Step heading ------------------------------ */

export function StepHeading({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="anim-fade-up" key={title}>
      <h2 className="font-display text-[32px] text-[var(--text)] leading-snug">{title}</h2>
      {sub && <p className="text-[13.5px] text-[var(--muted)] mt-1.5 leading-relaxed">{sub}</p>}
    </div>
  );
}

/* ------------------------------ Error banner ------------------------------ */

export function ErrorBanner({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="anim-shake mt-4 flex items-center gap-2.5 rounded-2xl border border-red-300/60 bg-red-50 px-4 py-3"
    >
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <p className="text-red-500 text-[13px] font-semibold leading-relaxed">{message}</p>
    </div>
  );
}

/* ----------------------------- Primary button ----------------------------- */

export function PrimaryButton({
  onClick, disabled, loading, children, loadingText,
}: {
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  children: ReactNode;
  loadingText?: string;
}) {
  const active = !disabled && !loading;
  return (
    <button
      onClick={onClick}
      disabled={!active}
      className={`w-full py-4 rounded-2xl font-bold text-[15px] transition-all ${
        active
          ? "press bg-[var(--accent)] text-[var(--surface)] hover:brightness-105 glow-accent"
          : "bg-[var(--border-strong)] text-[var(--muted-2)] cursor-not-allowed"
      }`}
    >
      {loading ? (
        <span className="inline-flex items-center justify-center gap-2">
          <svg className="animate-spin" width="17" height="17" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
            <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
          </svg>
          {loadingText || "..."}
        </span>
      ) : (
        children
      )}
    </button>
  );
}

/* ------------------------------ Phone input ------------------------------- */

/** Groups 10 digits as 912 345 6789 while typing; stores raw digits. */
export function formatPhone(digits: string): string {
  const d = digits.replace(/\D/g, "").slice(0, 10);
  const parts = [d.slice(0, 3), d.slice(3, 6), d.slice(6, 10)].filter(Boolean);
  return parts.join(" ");
}

export function PhoneInput({
  value, onChange, autoFocus, onEnter,
}: {
  value: string;
  onChange: (rawDigits: string) => void;
  autoFocus?: boolean;
  onEnter?: () => void;
}) {
  return (
    <div
      className="flex items-center bg-[var(--card)] border-2 border-[var(--border-strong)] focus-within:border-[var(--accent)] focus-within:shadow-soft rounded-2xl overflow-hidden transition-all"
      dir="ltr"
    >
      <div className="flex items-center px-4 py-4 bg-[var(--surface-2)] border-l border-[var(--border-strong)] flex-shrink-0">
        <span className="text-[15px] font-bold text-[var(--brown-text)]">+98</span>
      </div>
      <input
        autoFocus={autoFocus}
        type="tel"
        inputMode="numeric"
        autoComplete="tel-national"
        value={formatPhone(value)}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 10))}
        onKeyDown={(e) => e.key === "Enter" && onEnter?.()}
        placeholder="912 345 6789"
        className="flex-1 min-w-0 bg-transparent outline-none text-[17px] font-bold text-[var(--text)] placeholder:text-[var(--placeholder)] placeholder:tracking-normal placeholder:font-medium tracking-widest py-4 px-4 text-left"
      />
    </div>
  );
}

/* ----------------------------- Password input ----------------------------- */

export function PasswordInput({
  value, onChange, placeholder, autoFocus, onEnter, error,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  autoFocus?: boolean;
  onEnter?: () => void;
  error?: boolean;
}) {
  const [show, setShow] = useState(false);
  return (
    <div
      className={`flex items-center bg-[var(--card)] border-2 rounded-2xl overflow-hidden transition-all focus-within:shadow-soft ${
        error ? "border-red-400" : "border-[var(--border-strong)] focus-within:border-[var(--accent)]"
      }`}
    >
      <input
        autoFocus={autoFocus}
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onEnter?.()}
        placeholder={placeholder}
        autoComplete="new-password"
        className="flex-1 min-w-0 bg-transparent outline-none px-5 py-4 text-[17px] font-bold text-[var(--text)] placeholder:text-[var(--placeholder)] placeholder:font-medium transition-colors"
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? "پنهان کردن رمز" : "نمایش رمز"}
        className="px-4 text-[var(--muted-2)] hover:text-[var(--accent)] transition-colors flex-shrink-0"
      >
        {show ? (
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
            <line x1="1" y1="1" x2="23" y2="23" />
          </svg>
        ) : (
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        )}
      </button>
    </div>
  );
}

/** 0-4 score → label + filled segments. */
export function passwordStrength(pw: string): { score: 0 | 1 | 2 | 3 | 4; label: string } {
  let score = 0;
  if (pw.length >= 4) score++;
  if (pw.length >= 8) score++;
  if (/\d/.test(pw) && /[a-zA-Z\u0600-\u06FF]/.test(pw)) score++;
  if (/[^a-zA-Z0-9\u0600-\u06FF]/.test(pw)) score++;
  const labels = ["خیلی ضعیف", "ضعیف", "متوسط", "خوب", "عالی"];
  return { score: score as 0 | 1 | 2 | 3 | 4, label: labels[score] };
}

export function StrengthMeter({ pw }: { pw: string }) {
  const { score, label } = passwordStrength(pw);
  if (!pw) return null;
  const color = ["bg-red-400", "bg-red-400", "bg-amber-400", "bg-emerald-400", "bg-emerald-500"][score];
  return (
    <div className="flex items-center gap-2 mt-2.5" dir="rtl">
      <div className="flex gap-1.5 flex-1">
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={`strength-seg ${i <= score ? color : ""}`} />
        ))}
      </div>
      <span className="text-[11px] font-bold text-[var(--muted)]">{label}</span>
    </div>
  );
}

/* -------------------------------- OTP input ------------------------------- */

export function OtpInput({
  value, onChange, onComplete, autoFocus = true,
}: {
  value: string;
  onChange: (digits: string) => void;
  onComplete?: (digits: string) => void;
  autoFocus?: boolean;
}) {
  const LEN = 6;
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = value.replace(/\D/g, "").slice(0, LEN).split("");

  function setDigit(index: number, d: string) {
    const next = digits.slice();
    next[index] = d;
    const joined = next.join("").slice(0, LEN);
    onChange(joined);
    if (d && index < LEN - 1) refs.current[index + 1]?.focus();
    if (joined.length === LEN) onComplete?.(joined);
  }

  function handleKey(index: number, e: ReactKeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace") {
      e.preventDefault();
      if (digits[index]) {
        setDigit(index, "");
      } else if (index > 0) {
        setDigit(index - 1, "");
        refs.current[index - 1]?.focus();
      }
    } else if (e.key === "ArrowLeft" && index < LEN - 1) {
      refs.current[index + 1]?.focus();
    } else if (e.key === "ArrowRight" && index > 0) {
      refs.current[index - 1]?.focus();
    }
  }

  function handlePaste(e: ReactClipboardEvent<HTMLInputElement>) {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, LEN);
    if (!pasted) return;
    e.preventDefault();
    onChange(pasted);
    const focusIdx = Math.min(pasted.length, LEN - 1);
    refs.current[focusIdx]?.focus();
    if (pasted.length === LEN) onComplete?.(pasted);
  }

  return (
    <div className="flex gap-2 justify-center" dir="ltr">
      {Array.from({ length: LEN }).map((_, i) => (
        <input
          key={i}
          ref={(el) => { refs.current[i] = el; }}
          className={`otp-box no-spin ${digits[i] ? "filled" : ""}`}
          type="tel"
          inputMode="numeric"
          maxLength={1}
          autoFocus={autoFocus && i === 0}
          value={digits[i] || ""}
          onChange={(e) => setDigit(i, e.target.value.replace(/\D/g, "").slice(-1))}
          onKeyDown={(e) => handleKey(i, e)}
          onPaste={handlePaste}
          onFocus={(e) => e.currentTarget.select()}
          aria-label={`رقم ${i + 1}`}
        />
      ))}
    </div>
  );
}

/* ------------------------------ Choice button ----------------------------- */

export function ChoiceButton({
  selected, onClick, children, delay,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
  delay?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`press anim-fade-up ${delay || ""} w-full py-3.5 px-5 rounded-2xl text-right font-semibold text-[14px] flex items-center gap-3 transition-all ${
        selected
          ? "bg-[var(--accent)] text-[var(--surface)] glow-accent"
          : "bg-[var(--card)] border border-[var(--border-strong)] text-[var(--text-strong)] hover:border-[var(--accent)] shadow-soft"
      }`}
    >
      <span className="flex-1 text-right">{children}</span>
      {selected && (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0">
          <path d="M20 6L9 17l-5-5" />
        </svg>
      )}
    </button>
  );
}
