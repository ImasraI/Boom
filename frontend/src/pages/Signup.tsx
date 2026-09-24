import { useState } from "react";
import { apiUrl, readApiError } from "../api";
import { NavFn, SignupData } from "../types";
import { MAJORS, GRADES, EXAM_YEARS, TARGET_RANKS, STUDY_HOURS_OPTIONS, TEST_EXAM_OPTIONS } from "../data";
import {
  AuthOrbs, BackButton, ErrorBanner, StepHeading, PrimaryButton,
  PhoneInput, PasswordInput, StrengthMeter, OtpInput, ChoiceButton,
} from "../components/ui";

interface Props { nav: NavFn; onComplete: (data: SignupData) => void; }

const MAJOR_ICONS: Record<string, string> = {
  "ریاضی فیزیک": "📐",
  "علوم تجربی": "🧬",
  "علوم انسانی": "📚",
  "هنر": "🎨",
};

const GRADE_ICONS: Record<string, string> = {
  "دهم": "🌱",
  "یازدهم": "🌿",
  "دوازدهم": "🌳",
  "فارغ‌التحصیل": "🎓",
};

/** Stagger delay class for the i-th choice in a list. */
function stagger(i: number): string {
  return ["", "delay-1", "delay-2", "delay-3", "delay-4"][i % 5] || "";
}

export default function Signup({ nav, onComplete }: Props) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [bypassMode, setBypassMode] = useState(false);
  const [authDisabled, setAuthDisabled] = useState(false);
  const [debugCode, setDebugCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [major, setMajor] = useState("");
  const [grade, setGrade] = useState("");
  const [examYear, setExamYear] = useState("");
  const [targetRank, setTargetRank] = useState("");
  const [studyHours, setStudyHours] = useState("");
  const [testExams, setTestExams] = useState<string[]>([]);
  const [customExam, setCustomExam] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const TOTAL = 10;

  async function advance() {
    if (submitting) return;
    setError("");

    // Phone step: send the SMS verification code, then continue.
    if (step === 1) {
      await sendCode();
      return;
    }

    // Password step: verify the code + create the account, then continue.
    if (step === 3) {
      setSubmitting(true);
      try {
        const res = await fetch(apiUrl("/api/auth/register/complete"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone, code, password }),
        });
        if (!res.ok) {
          setError(await readApiError(res, "خطا در تایید کد"));
          return;
        }
        const data = await res.json();
        localStorage.setItem("boom-token", data.access_token);
        setStep(4);
      } catch {
        setError("خطا در ارتباط با سرور");
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (step < TOTAL - 1) { setStep(s => s + 1); return; }
    // Profile done: everything is already registered + logged in.
    onComplete({ name, phone, major, grade, examYear, targetRank, studyHours, testExams });
  }

  function toggleExam(e: string) {
    setTestExams(prev => prev.includes(e) ? prev.filter(x => x !== e) : [...prev, e]);
  }
  function addCustom() {
    const t = customExam.trim();
    if (t && !testExams.includes(t)) setTestExams(prev => [...prev, t]);
    setCustomExam("");
  }
  function pick<T>(setter: (v: T) => void, value: T) {
    setter(value);
    setTimeout(advance, 180);
  }

  async function sendCode() {
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch(apiUrl("/api/auth/request-code"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone }),
      });
      if (!res.ok) {
        setError(await readApiError(res, "خطا در ارسال کد"));
        return;
      }
      const data = await res.json();
      setDebugCode(data.debug_code || "");
      setBypassMode(Boolean(data.bypass_mode));
      setAuthDisabled(Boolean(data.auth_disabled));
      // Dev convenience (DISABLE_AUTH=true): skip the code entry step and go
      // straight to setting a password.
      setStep(Boolean(data.auth_disabled) ? 3 : 2);
    } catch {
      setError("خطا در ارتباط با سرور");
    } finally {
      setSubmitting(false);
    }
  }

  async function resendCode() {
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch(apiUrl("/api/auth/request-code"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone }),
      });
      if (!res.ok) {
        setError(await readApiError(res, "خطا در ارسال کد"));
        return;
      }
      const data = await res.json();
      setDebugCode(data.debug_code || "");
      setBypassMode(Boolean(data.bypass_mode));
      setAuthDisabled(Boolean(data.auth_disabled));
    } catch {
      setError("خطا در ارتباط با سرور");
    } finally {
      setSubmitting(false);
    }
  }

  const canContinue = [
    name.trim().length > 0,
    phone.length >= 10,
    code.replace(/\D/g, "").length === 6 || authDisabled,
    password.length >= 4 && password === confirmPassword,
    major.length > 0,
    grade.length > 0,
    examYear.length > 0,
    targetRank.length > 0,
    studyHours.length > 0,
    testExams.length > 0,
  ][step] ?? false;

  const steps = [
    {
      q: "اسمت چیه؟",
      sub: "اینطوری بهت خطاب می‌کنیم.",
      content: (
        <input autoFocus value={name} onChange={e => setName(e.target.value)}
          placeholder="مثلاً پریسا" onKeyDown={e => e.key === "Enter" && canContinue && advance()}
          className="w-full bg-[var(--card)] border-2 border-[var(--border-strong)] focus:border-[var(--accent)] focus:shadow-soft outline-none rounded-2xl px-5 py-4 text-lg font-semibold text-[var(--text)] placeholder:text-[var(--placeholder)] placeholder:font-medium transition-all" />
      ),
    },
    {
      q: "شماره موبایلت چیه؟",
      sub: "برای ورود به حسابت ازش استفاده می‌کنی.",
      content: <PhoneInput value={phone} onChange={setPhone} autoFocus onEnter={() => canContinue && advance()} />,
    },
    {
      q: bypassMode ? "کد عبور موقت چیه؟" : "کد تایید پیامک‌شده چیه؟",
      sub: bypassMode
        ? `شماره ${phone} توسط پشتیبانی تأیید شده. کد عبور موقتی که به تو داده شده را وارد کن.`
        : `کد ۶ رقمی را که به ${phone} پیامک کردیم وارد کنید.`,
      content: (
        <div>
          <OtpInput value={code} onChange={setCode} onComplete={() => canContinue && advance()} />
          {bypassMode && (
            <p className="text-[12px] text-[var(--muted-2)] mt-3 text-center">
              پیامک موقتاً غیرفعال است؛ ورود با کد پشتیبانی
            </p>
          )}
          {!bypassMode && debugCode && (
            <p className="text-[12px] text-[var(--muted-2)] mt-3 text-center" dir="ltr">
              debug mode: code = {debugCode}
            </p>
          )}
          <div className="mt-4 text-center">
            <button onClick={resendCode} disabled={submitting}
              className="text-[12.5px] font-bold text-[var(--accent)] hover:underline disabled:opacity-40 transition-opacity">
              کد دریافت نکردید؟ ارسال دوباره
            </button>
          </div>
        </div>
      ),
    },
    {
      q: "رمز عبورت چیه؟",
      sub: "حداقل ۴ کاراکتر. برای ورود دوباره ازش استفاده می‌کنی.",
      content: (
        <div className="flex flex-col gap-3">
          <PasswordInput value={password} onChange={setPassword} placeholder="••••••••" autoFocus />
          <StrengthMeter pw={password} />
          <PasswordInput
            value={confirmPassword} onChange={setConfirmPassword}
            placeholder="تکرار رمز عبور"
            error={Boolean(confirmPassword && password !== confirmPassword)}
            onEnter={() => canContinue && advance()}
          />
          {confirmPassword && password !== confirmPassword && (
            <p className="text-red-500 text-[12px] text-right">رمزها یکسان نیستند</p>
          )}
        </div>
      ),
    },
    {
      q: "رشته‌ات چیه؟",
      sub: "برنامه‌ی درسی‌ات رو بر اساسش تنظیم می‌کنیم.",
      content: (
        <div className="flex flex-col gap-2">
          {MAJORS.map((m, i) => (
            <ChoiceButton key={m} selected={major === m} onClick={() => pick(setMajor, m)} delay={stagger(i)}>
              <span className="me-2">{MAJOR_ICONS[m] || "🎓"}</span>{m}
            </ChoiceButton>
          ))}
        </div>
      ),
    },
    {
      q: "چه پایه‌ای هستی؟",
      sub: "بر اساسش زمان‌بندی‌ات رو تنظیم می‌کنیم.",
      content: (
        <div className="flex flex-col gap-2">
          {GRADES.map((g, i) => (
            <ChoiceButton key={g} selected={grade === g} onClick={() => pick(setGrade, g)} delay={stagger(i)}>
              <span className="me-2">{GRADE_ICONS[g] || "🏫"}</span>{g}
            </ChoiceButton>
          ))}
        </div>
      ),
    },
    {
      q: "کدوم سال می‌خوای کنکور بدی؟",
      sub: "افق برنامه‌ریزی‌ات رو مشخص می‌کنه.",
      content: (
        <div className="grid grid-cols-2 gap-2.5">
          {EXAM_YEARS.map((y, i) => (
            <button key={y} onClick={() => pick(setExamYear, y)}
              className={`press anim-fade-up ${stagger(i)} py-6 rounded-2xl font-bold text-2xl text-center font-display transition-all ${
                examYear === y
                  ? "bg-[var(--accent)] text-[var(--surface)] glow-accent"
                  : "bg-[var(--card)] border border-[var(--border-strong)] text-[var(--text-strong)] hover:border-[var(--accent)] shadow-soft"
              }`}>{y}</button>
          ))}
        </div>
      ),
    },
    {
      q: "رتبه‌ی هدفت چنده؟",
      sub: "صادقانه بگو — سطح و سرعت برنامه‌ات رو تعیین می‌کنه.",
      content: (
        <div className="flex flex-col gap-2">
          {TARGET_RANKS.map((r, i) => (
            <ChoiceButton key={r} selected={targetRank === r} onClick={() => pick(setTargetRank, r)} delay={stagger(i)}>
              <span className="me-2">🎯</span>{r}
            </ChoiceButton>
          ))}
        </div>
      ),
    },
    {
      q: "روزانه چند ساعت می‌تونی درس بخونی؟",
      sub: "یه روز معمولی — نه بهترین و نه بدترین روزت.",
      content: (
        <div className="flex flex-col gap-2">
          {STUDY_HOURS_OPTIONS.map((h, i) => (
            <ChoiceButton key={h} selected={studyHours === h} onClick={() => pick(setStudyHours, h)} delay={stagger(i)}>
              <span className="me-2">⏱</span>{h}
            </ChoiceButton>
          ))}
        </div>
      ),
    },
    {
      q: "تو کدوم آزمون‌ها شرکت می‌کنی؟",
      sub: "همه رو انتخاب کن. نتایجت رو باهاشون هماهنگ می‌کنیم.",
      content: (
        <div className="flex flex-col gap-2">
          {TEST_EXAM_OPTIONS.map((e, i) => (
            <ChoiceButton key={e} selected={testExams.includes(e)} onClick={() => toggleExam(e)} delay={stagger(i)}>
              <span className="me-2">📝</span>{e}
            </ChoiceButton>
          ))}
          {testExams.filter(e => !TEST_EXAM_OPTIONS.includes(e)).map(e => (
            <ChoiceButton key={e} selected onClick={() => toggleExam(e)}>
              <span className="me-2">✏️</span>{e}
              <span className="text-[11px] opacity-70 ms-2">(سفارشی)</span>
            </ChoiceButton>
          ))}
          <div className="flex gap-2 mt-1.5">
            <button onClick={addCustom} disabled={!customExam.trim()}
              className="press px-4 py-2.5 rounded-xl bg-[var(--border)] text-[var(--muted)] font-bold text-[13px] hover:bg-[var(--border-strong)] disabled:opacity-40 transition-colors flex-shrink-0">افزودن</button>
            <input value={customExam} onChange={e => setCustomExam(e.target.value)}
              onKeyDown={e => e.key === "Enter" && addCustom()}
              placeholder="آزمون دیگه‌ای داری؟"
              className="flex-1 min-w-0 bg-[var(--card)] border border-[var(--border-strong)] focus:border-[var(--accent)] outline-none rounded-xl px-4 py-2.5 text-[13px] font-semibold text-[var(--text)] placeholder:text-[var(--placeholder)] transition-colors text-right" />
          </div>
        </div>
      ),
    },
  ];

  const showCta = step === 0 || step === 1 || step === 2 || step === 3 || step === TOTAL - 1;
  const ctaLabel =
    step === 1 ? (submitting ? "در حال ارسال کد..." : "ادامه")
    : step === 3 ? (submitting ? "در حال تایید..." : "تایید و ساخت حساب ←")
    : step === TOTAL - 1 ? "ثبت‌نام و ورود ←"
    : "ادامه";

  return (
    <div className="min-h-screen flex flex-col bg-[var(--page-bg)]">
      <AuthOrbs />
      {/* Segmented progress + counter + back */}
      <div className="sticky top-0 z-10 bg-[var(--page-bg)]/90 backdrop-blur-sm px-5 pt-5 pb-3">
        <div className="max-w-lg mx-auto">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[12px] font-bold text-[var(--muted-2)] tabular-nums">{step + 1} از {TOTAL}</span>
            <BackButton
              onClick={() => (step === 0 ? nav("landing") : setStep(s => ((authDisabled && s === 3) ? 1 : s - 1)))}
            />
          </div>
          <div className="flex gap-1.5">
            {Array.from({ length: TOTAL }).map((_, i) => (
              <span key={i} className={`progress-seg ${i < step ? "done" : i === step ? "current" : ""}`} />
            ))}
          </div>
        </div>
      </div>

      <div className="relative flex-1 flex flex-col px-5 pt-4 pb-8 overflow-y-auto">
        <div className="w-full max-w-lg mx-auto flex flex-col flex-1">
          <div key={step} className="anim-fade-up">
            <StepHeading title={steps[step].q} sub={steps[step].sub} />
            <div className="mt-6">{steps[step].content}</div>
            <ErrorBanner message={error} />
          </div>

          {showCta && (
            <div className="mt-auto pt-8">
              <PrimaryButton
                onClick={advance}
                disabled={!canContinue}
                loading={submitting && (step === 1 || step === 3)}
                loadingText={ctaLabel}
              >
                {ctaLabel}
              </PrimaryButton>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
