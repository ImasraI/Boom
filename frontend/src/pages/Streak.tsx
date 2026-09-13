import { NavFn } from "../types";
import { PAST_RECORDS } from "../data";

const DAYS_FA = ["پنج‌شنبه", "جمعه", "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه"];
const DAYS_SHORT = ["پ", "ج", "ش", "ی", "د", "س", "چ"];
const TOTAL_XP = PAST_RECORDS.reduce((s, r) => s + r.xp, 0);

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-9 h-9 rounded-xl bg-[#F0EBE3] flex items-center justify-center text-[var(--muted)] hover:bg-[#E5DDD4] transition-colors">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
        <path d="M19 12H5M12 5l-7 7 7 7"/>
      </svg>
    </button>
  );
}

export default function Streak({ nav }: { nav: NavFn }) {
  const maxXP = Math.max(...PAST_RECORDS.map(r => r.xp));

  return (
    <div className="min-h-screen bg-[#F8F6F2]">
      <div className="px-5 pt-12 pb-4 flex items-center gap-4">
        <BackButton onClick={() => nav("home")} />
        <h1 className="font-display text-xl text-[var(--text)]">استریک شما</h1>
      </div>

      {/* Streak hero */}
      <div className="mx-5 mt-2 bg-[var(--card)] rounded-3xl p-6 border border-[var(--border)] flex items-center gap-5">
        <div className="w-20 h-20 rounded-2xl bg-[#FFF5F0] flex items-center justify-center">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="#C4714A">
            <path d="M12 2C9 7 6 8 7 13c.7 3 3 5 5 5s4.3-2 5-5c1-5-2-6-5-11z"/>
            <path d="M12 14c-1 0-2-1-2-2.5C10 10 11 9 12 9s2 1 2 1.5C14 13 13 14 12 14z" fill="white"/>
          </svg>
        </div>
        <div>
          <p className="text-[11px] font-bold text-[var(--muted-2)]">استریک فعلی</p>
          <p className="text-5xl font-bold text-[#C4714A] leading-tight">۷</p>
          <p className="text-[13px] text-[var(--muted)] font-medium">روز متوالی</p>
        </div>
      </div>

      {/* XP grid */}
      <div className="mx-5 mt-3 grid grid-cols-2 gap-3">
        <div className="bg-[var(--card)] rounded-2xl p-4 border border-[var(--border)]">
          <p className="text-[11px] font-bold text-[var(--muted-2)]">مجموع XP</p>
          <p className="text-3xl font-bold text-[var(--text)] mt-1">{TOTAL_XP.toLocaleString("fa-IR")}</p>
          <p className="text-[12px] text-[var(--muted)] font-medium">کل زمان</p>
        </div>
        <div className="bg-[var(--card)] rounded-2xl p-4 border border-[var(--border)]">
          <p className="text-[11px] font-bold text-[var(--muted-2)]">این هفته</p>
          <p className="text-3xl font-bold text-[var(--text)] mt-1">۱٬۰۵۰</p>
          <p className="text-[12px] text-[var(--muted)] font-medium">XP کسب‌شده</p>
        </div>
      </div>

      {/* Bar chart */}
      <div className="mx-5 mt-4 bg-[var(--card)] rounded-3xl p-5 border border-[var(--border)]">
        <p className="text-[12px] font-bold text-[var(--muted-2)] mb-4">۷ روز گذشته</p>
        <div className="flex items-end justify-between gap-1.5 h-28">
          {PAST_RECORDS.map((r, i) => {
            const height = maxXP ? (r.xp / maxXP) * 100 : 0;
            const isToday = i === PAST_RECORDS.length - 1;
            const pct = r.tasksTotal ? Math.round((r.tasksDone / r.tasksTotal) * 100) : 0;
            return (
              <div key={r.date} className="flex flex-col items-center gap-1.5 flex-1">
                <span className="text-[9px] font-bold text-[var(--muted-2)]">{r.xp.toLocaleString("fa-IR")}</span>
                <div className="w-full flex items-end" style={{ height: "80px" }}>
                  <div className="w-full rounded-lg transition-all duration-700"
                    style={{
                      height: `${height}%`,
                      background: isToday
                        ? "linear-gradient(to top, #C4714A, #E8A070)"
                        : pct === 100 ? "#6B9E7A" : "#E5DDD4",
                    }}
                  />
                </div>
                <span className={`text-[9px] font-bold ${isToday ? "text-[#C4714A]" : "text-[var(--muted-2)]"}`}>
                  {DAYS_SHORT[i]}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Day breakdown */}
      <div className="mx-5 mt-4 mb-8">
        <p className="text-[12px] font-bold text-[var(--muted-2)] mb-3">جزئیات روزانه</p>
        <div className="flex flex-col gap-2">
          {[...PAST_RECORDS].reverse().map((r, i) => {
            const pct = r.tasksTotal ? Math.round((r.tasksDone / r.tasksTotal) * 100) : 0;
            const label = i === 0 ? "امروز" : i === 1 ? "دیروز" : DAYS_FA[PAST_RECORDS.length - 1 - i];
            return (
              <div key={r.date} className="bg-[var(--card)] rounded-2xl border border-[var(--border)] px-4 py-3 flex items-center gap-3">
                <div className="flex-1 text-right">
                  <p className="text-[13px] font-semibold text-[var(--text)]">{label}</p>
                  <p className="text-[11px] text-[var(--muted-2)] font-medium">{r.tasksDone}/{r.tasksTotal} تکلیف · {r.xp} XP</p>
                </div>
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-[12px] font-bold ${
                  pct === 100 ? "bg-[#EAF5EC] text-[#6B9E7A]" : pct >= 50 ? "bg-[#FFF5F0] text-[#C4714A]" : "bg-[#F5F5F5] text-[var(--muted-2)]"
                }`}>
                  {pct === 100 ? "✓" : `${pct}%`}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

