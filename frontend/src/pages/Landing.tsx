import { NavFn } from "../types";
import { AuthOrbs } from "../components/ui";

const HIGHLIGHTS = [
  { icon: "🧠", title: "مربی هوشمند", sub: "پاسخ به هر سؤال درسی، همان لحظه" },
  { icon: "📅", title: "برنامه هفتگی", sub: "برنامه‌ای که با آزمون‌های تو هماهنگ می‌شود" },
  { icon: "🎯", title: "آزمون هوشمند", sub: "دفترچه استاندارد از کتاب‌های خودت" },
];

export default function Landing({ nav }: { nav: NavFn }) {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--page-bg)]">
      <AuthOrbs />
      <div className="relative flex-1 flex flex-col items-center justify-center text-center px-8">
        {/* Animated logo */}
        <div className="anim-pop mb-6 flex flex-col items-center">
          <div className="logo-badge w-20 h-20 rounded-3xl flex items-center justify-center mb-4 floaty">
            <span className="font-display text-4xl text-[var(--surface)] leading-none">ب</span>
          </div>
          <h1 className="font-display text-5xl text-[var(--text)] leading-none">بوم</h1>
          <p className="text-[11px] font-bold tracking-[0.25em] text-[var(--accent)] mt-1">BOOM</p>
        </div>

        <p className="anim-fade-up delay-1 text-[var(--muted)] text-[15px] leading-relaxed max-w-[280px]">
          برنامه‌ریز هوشمند شخصی‌سازی‌شده.
        </p>
        <p className="anim-fade-up delay-2 mt-2 text-[var(--muted-2)] text-[13px] leading-relaxed max-w-[260px]">
          دستیاری که سبک مطالعه‌ات رو یاد می‌گیره.
        </p>

        {/* Floating feature cards (desktop only) */}
        <div className="anim-fade-up delay-3 hidden lg:flex gap-4 mt-12">
          {HIGHLIGHTS.map((h) => (
            <div key={h.title} className="card-elevated px-5 py-4 w-[190px] text-right">
              <span className="text-xl">{h.icon}</span>
              <p className="font-bold text-[13px] text-[var(--text)] mt-1.5">{h.title}</p>
              <p className="text-[11.5px] text-[var(--muted)] mt-0.5 leading-relaxed">{h.sub}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="relative flex flex-col items-center gap-4 px-8 pb-14">
        <button
          onClick={() => nav("signup")}
          className="press anim-fade-up delay-2 w-full max-w-xs py-[15px] rounded-2xl bg-[var(--accent)] text-[var(--surface)] font-bold text-[15px] hover:brightness-105 active:scale-95 transition-all glow-accent"
        >
          ایجاد حساب کاربری
        </button>
        <button
          onClick={() => nav("login")}
          className="anim-fade-up delay-3 text-[13px] text-[var(--muted)] font-semibold hover:text-[var(--text)] transition-colors"
        >
          قبلاً ثبت‌نام کردی؟{" "}
          <span className="text-[var(--accent)] underline underline-offset-2">ورود به حساب</span>
        </button>
      </div>
    </div>
  );
}
