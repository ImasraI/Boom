import { NavFn } from "../types";

export default function Landing({ nav }: { nav: NavFn }) {
  return (
    <div className="min-h-screen flex flex-col bg-[#F8F6F2]">
      <div className="flex-1 flex flex-col items-center justify-center text-center px-8">
        {/* Logo placeholder + name */}
        <div className="flex flex-col items-center mb-6">
          <div className="w-20 h-20 rounded-3xl bg-[#C4714A] flex items-center justify-center mb-4 shadow-lg">
            {/* Logo placeholder — replace with actual logo asset */}
            <span className="font-display text-4xl text-[#F8F6F2] leading-none">ب</span>
          </div>
          <h1 className="font-display text-5xl text-[var(--text)] leading-none">بوم</h1>
          <p className="text-[11px] font-bold tracking-[0.25em] text-[#C4714A] mt-1">BOOM</p>
        </div>

        <p className="text-[var(--muted)] text-[15px] leading-relaxed max-w-[280px]">
          برنامه‌ریز هوشمند شخصی‌سازی‌شده.
        </p>
        <p className="mt-2 text-[var(--muted-2)] text-[13px] leading-relaxed max-w-[260px]">
          دستیاری که سبک مطالعه‌ات رو یاد می‌گیره.
        </p>
      </div>

      <div className="flex flex-col items-center gap-4 px-8 pb-14">
        <button
          onClick={() => nav("signup")}
          className="w-full max-w-xs py-[15px] rounded-2xl bg-[#C4714A] text-[#F8F6F2] font-bold text-[15px] hover:bg-[#A85C38] active:scale-95 transition-all shadow-sm"
        >
          ایجاد حساب کاربری
        </button>
        <button
          onClick={() => nav("login")}
          className="text-[13px] text-[var(--muted)] font-semibold hover:text-[var(--text)] transition-colors"
        >
          قبلاً ثبت‌نام کردی؟{" "}
          <span className="text-[#C4714A] underline underline-offset-2">ورود به حساب</span>
        </button>
      </div>
    </div>
  );
}

