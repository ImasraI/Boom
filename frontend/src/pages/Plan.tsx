import { useState, useEffect, type ReactNode } from "react";
import { apiUrl } from "../api";
import { NavFn, SignupData } from "../types";

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-9 h-9 rounded-xl bg-[var(--border)] flex items-center justify-center text-[var(--muted)] hover:bg-[var(--border-strong)] transition-colors">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
        <path d="M19 12H5M12 5l-7 7 7 7"/>
      </svg>
    </button>
  );
}

const UPCOMING_EXAMS = [
  { label: "قلمچی — آزمون شماره ۴", date: "۱۵ شهریور ۱۴۰۵", daysAway: 10, color: "#5C8BA8" },
  { label: "آزمون ماهانه گاج", date: "۲۲ شهریور ۱۴۰۵", daysAway: 17, color: "#9B7AAD" },
  { label: "امتحان میانترم مدرسه", date: "۳۰ شهریور ۱۴۰۵", daysAway: 25, color: "var(--accent)" },
];

const MOCK_SUBJECTS_PROGRESS = [
  { subject: "حسابان", source: "کتاب تست مهر و ماه", read: 65, total: 100, testsLeft: 42 },
  { subject: "فیزیک", source: "کتاب تست خیلی سبز", read: 30, total: 100, testsLeft: 85 },
  { subject: "شیمی", source: "کتاب تست مبتکران", read: 80, total: 100, testsLeft: 20 },
];


const GOALS = [
  { horizon: "بلندمدت", icon: "💎", title: "رتبهی زیر ۵٬۰۰۰ کشوری", sub: "روز کنکور · خرداد ۱۴۰۶", progress: 28, color: "var(--accent)" },
  { horizon: "میانمدت", icon: "⏳", title: "رساندن فیزیک به ۷۵٪", sub: "هدف · مهر ۱۴۰۵", progress: 61, color: "#5C8BA8" },
  { horizon: "این هفته", icon: "✅", title: "تکمیل ۳۵ تکلیف", sub: "۲۴ از ۳۵ انجام شده", progress: 69, color: "var(--success)" },
];

// Shamsi day names (abbreviated)
const DAY_LETTERS = ["ش", "ی", "د", "س", "چ", "پ", "ج"];

// Helper to parse Markdown-like structure more robustly.
function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(p => p !== "");
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={`${keyPrefix}-${i}`} className="font-bold">{part.slice(2, -2)}</strong>;
    }
    return <span key={`${keyPrefix}-${i}`}>{part}</span>;
  });
}

function renderPlanContent(content: string): ReactNode[] {
  const lines = content.split("\n");
  const elements: ReactNode[] = [];
  let tableData: string[][] = [];

  lines.forEach((line, i) => {
    if (line.startsWith("## ")) {
      elements.push(<h3 key={i} className="font-bold text-[16px] text-[var(--text)] mt-5 mb-2">{renderInline(line.replace("## ", ""), `h${i}`)}</h3>);
    } else if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      const row = line.split("|").filter(cell => cell.trim() !== "").map(cell => cell.trim());
      tableData.push(row);
      if (!lines[i + 1]?.trim().startsWith("|")) {
        const [header, ...rows] = tableData;
        elements.push(
          <div key={i} className="overflow-x-auto my-3 border border-[var(--border)] rounded-xl">
            <table className="w-full text-[11px] text-right border-collapse">
              <thead className="bg-[var(--surface-2)]">
                <tr>{header.map((cell, j) => <th key={j} className="p-2 border border-[var(--border)]">{renderInline(cell, `th${i}-${j}`)}</th>)}</tr>
              </thead>
              <tbody>
                {rows.slice(1).map((row, j) => <tr key={j} className="border-t border-[var(--border)]">{row.map((cell, k) => <td key={k} className="p-2 border border-[var(--border)]">{renderInline(cell, `td${i}-${j}-${k}`)}</td>)}</tr>)}
              </tbody>
            </table>
          </div>
        );
        tableData = [];
      }
    } else if (line.trim()) {
      elements.push(<p key={i} className="text-[13px] text-[var(--text)] leading-relaxed my-1">{renderInline(line, `p${i}`)}</p>);
    }
  });
  return elements;
}

export default function Plan({ nav, userData }: { nav: NavFn; userData: SignupData | null }) {
  const [studyPlan, setStudyPlan] = useState<string | null>(() => localStorage.getItem("boom-study-plan"));
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function fetchPlan() {
      const cached = localStorage.getItem("boom-study-plan");
      if (cached) {
        setStudyPlan(cached);
        return;
      }
      if (!userData || loading) return;
      setLoading(true);
      try {
        const body = {
          months: 6,
          daily_hours: Number((userData.studyHours || "4").match(/[0-9]+/)?.[0] || 4),
          major: userData.major || "ریاضی فیزیک",
          grade: userData.grade || "دوازدهم (سال کنکور)",
          target_rank: userData.targetRank || "زیر ۵٬۰۰۰",
          student: userData,
          weak_subjects: Object.keys(userData.completion ?? {}).filter(k => userData.completion![k] < 70),
          strong_subjects: Object.keys(userData.confidence ?? {}).filter(k => userData.confidence![k] >= 70),
          notes: "برنامه مطالعاتی اولیه بر اساس پروفایل من",
        };
        const res = await fetch(apiUrl("/api/boom/study-plan"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (res.ok) {
          const data = await res.json();
          if (data.plan) {
            setStudyPlan(data.plan);
            localStorage.setItem("boom-study-plan", data.plan);
          }
        }
      } catch (err) {
        console.error("Failed to generate auto-plan:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchPlan();
  }, [userData]);

  const today = new Date();
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [viewYear] = useState(today.getFullYear());
  const monthNames = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  const shamsiMonth = monthNames[(viewMonth + 3) % 12];
  const shamsiYear = viewMonth >= 9 ? "۱۴۰۵" : "۱۴۰۴";
  const firstDay = new Date(viewYear, viewMonth, 1).getDay();
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const examDays = new Set([5, 12, 20]);
  const taskDays = new Set([1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26]);

  return (
    <div className="min-h-screen bg-[var(--surface)] pb-10">
      <div className="px-5 pt-12 pb-4 flex items-center gap-4">
        <BackButton onClick={() => nav("home")} />
        <div className="text-right">
          <h1 className="font-display text-xl text-[var(--text)]">برنامه‌ی شما</h1>
          <p className="text-[12px] text-[var(--muted-2)] font-medium">اهداف، تقویم و آزمون‌های پیش رو</p>
        </div>
      </div>

      <div className="px-5 space-y-4">
        <div>
          <p className="text-[12px] font-bold text-[var(--muted-2)] mb-2 text-right">وضعیت دروس آزمون بعدی</p>
          <div className="space-y-2">
            {MOCK_SUBJECTS_PROGRESS.map(s => (
              <div key={s.subject} className="bg-[var(--card)] rounded-2xl border border-[var(--border)] p-4 text-right">
                <div className="flex justify-between mb-1"><p className="font-bold text-[14px]">{s.subject}</p><p className="text-[11px] text-[var(--muted-2)]">منبع: {s.source}</p></div>
                <div className="flex items-center gap-2 mb-2"><div className="flex-1 h-2 bg-[var(--border)] rounded-full overflow-hidden"><div className="h-full bg-[var(--accent)]" style={{ width: `${s.read}%` }} /></div><span className="text-[11px] font-bold">{s.read}%</span></div>
                <p className="text-[11px] text-[var(--muted-2)]">{100 - s.read}% باقیمانده · {s.testsLeft} تست باقیمانده تا هدف</p>
              </div>
            ))}
          </div>
        </div>

        {studyPlan && (
          <div className="bg-[var(--card)] rounded-2xl border border-[var(--border)] p-4 text-right">
            <h2 className="font-bold text-[var(--text)] mb-2">برنامه پیشنهادی بوم</h2>
            <div className="space-y-1">{renderPlanContent(studyPlan)}</div>
          </div>
        )}
        {loading && <div className="text-center text-[var(--muted)]">در حال تولید برنامه...</div>}

        {/* Goals */}
        <div className="space-y-2.5">
          {GOALS.map(g => (
            <div key={g.horizon} className="bg-[var(--card)] rounded-2xl border border-[var(--border)] p-4">
              <div className="flex items-start gap-3">
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-0.5">
                    <div className="h-1.5 w-full bg-[var(--border)] rounded-full overflow-hidden mt-3">
                      <div className="h-full rounded-full" style={{ width: `${g.progress}%`, background: g.color }} />
                    </div>
                  </div>
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-[11px] font-bold" style={{ color: g.color }}>{g.progress}%</span>
                    <div className="text-right">
                      <div className="flex items-center gap-1.5 justify-end mb-0.5">
                        <span className="text-[10px] font-bold" style={{ color: g.color }}>{g.horizon}</span>
                        <span className="text-lg">{g.icon}</span>
                      </div>
                      <p className="text-[14px] font-semibold text-[var(--text)]">{g.title}</p>
                      <p className="text-[11px] text-[var(--muted-2)] font-medium mt-0.5">{g.sub}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Calendar */}
        <div className="bg-[var(--card)] rounded-3xl border border-[var(--border)] p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex gap-1">
              <button onClick={() => setViewMonth(m => m + 1)}
                className="w-7 h-7 rounded-lg bg-[var(--border)] flex items-center justify-center text-[var(--muted)] hover:bg-[var(--border-strong)] transition-colors">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M15 18l-6-6 6-6"/>
                </svg>
              </button>
              <button onClick={() => setViewMonth(m => m - 1)}
                className="w-7 h-7 rounded-lg bg-[var(--border)] flex items-center justify-center text-[var(--muted)] hover:bg-[var(--border-strong)] transition-colors">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M9 18l6-6-6-6"/>
                </svg>
              </button>
            </div>
            <p className="text-[14px] font-bold text-[var(--text)]">{shamsiMonth} {shamsiYear}</p>
          </div>

          <div className="grid grid-cols-7 mb-1">
            {DAY_LETTERS.map((d, i) => (
              <div key={i} className="text-center text-[10px] font-bold text-[var(--muted-2)] py-1">{d}</div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-y-1">
            {Array.from({ length: firstDay }, (_, i) => <div key={`e-${i}`} />)}
            {Array.from({ length: daysInMonth }, (_, i) => {
              const day = i + 1;
              const isToday = day === today.getDate() && viewMonth === today.getMonth();
              const isExam = examDays.has(day);
              const hasTask = taskDays.has(day);
              return (
                <div key={day} className="flex flex-col items-center py-0.5">
                  <div className={`w-8 h-8 flex items-center justify-center rounded-full text-[12px] font-semibold ${
                    isToday ? "bg-[var(--accent)] text-white" : "text-[var(--text)]"
                  }`}>{day}</div>
                  <div className="flex gap-0.5 h-1.5 mt-0.5">
                    {hasTask && <div className="w-1 h-1 rounded-full bg-[var(--accent)] opacity-60" />}
                    {isExam && <div className="w-1 h-1 rounded-full bg-[#5C8BA8]" />}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex gap-4 mt-3 pt-3 border-t border-[var(--border)] justify-end">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-[var(--muted-2)] font-medium">روز مطالعه</span>
              <div className="w-2 h-2 rounded-full bg-[var(--accent)] opacity-70" />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-[var(--muted-2)] font-medium">آزمون</span>
              <div className="w-2 h-2 rounded-full bg-[#5C8BA8]" />
            </div>
          </div>
        </div>

        {/* Upcoming exams */}
        <div>
          <p className="text-[12px] font-bold text-[var(--muted-2)] mb-2 text-right">آزمون‌های پیش رو</p>
          <div className="space-y-2">
            {UPCOMING_EXAMS.map(e => (
              <div key={e.label} className="bg-[var(--card)] rounded-2xl border border-[var(--border)] px-4 py-3 flex items-center gap-3">
                <div className="text-right flex-1">
                  <p className="text-[13px] font-semibold text-[var(--text)]">{e.label}</p>
                  <p className="text-[11px] text-[var(--muted-2)] font-medium">{e.date}</p>
                </div>
                <div className="w-10 h-10 rounded-xl flex items-center justify-center text-[12px] font-bold text-white flex-shrink-0"
                  style={{ background: e.color }}>
                  {e.daysAway}r
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

