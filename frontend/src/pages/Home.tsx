import { useCallback, useEffect, useState } from "react";
import React from "react";
import { NavFn, SignupData, Task } from "../types";
import { SUBJECT_COLORS } from "../data";
import {
  homeTasksForDate,
  postponeToTomorrow,
  saveTaskEdit,
  toggleDone,
  type HomeTask,
} from "../homeTasks";
import { SCHEDULE_CHANGED_EVENT, toISO } from "../scheduleStore";

const STREAK = 7;
const KONKOOR_DATE = "2027-06-20";

function daysUntil(d: string) {
  const diff = new Date(d).getTime() - new Date().setHours(0, 0, 0, 0);
  return Math.max(0, Math.ceil(diff / 86400000));
}

function getSubjectColor(subject: string) {
  const key = Object.keys(SUBJECT_COLORS).find(k => subject.includes(k));
  return SUBJECT_COLORS[key ?? "default"];
}

const typeLabels: Record<Task["type"], string> = {
  study: "درسی", test: "آزمونی", quiz: "کوییز", review: "مرور", practice: "تمرین",
};
const typeBg: Record<Task["type"], string> = {
  study: "var(--accent-soft)",
  test: "var(--success-bg)",
  quiz: "var(--accent-soft)",
  review: "var(--success-bg)",
  practice: "var(--accent-soft)",
};
const typeColor: Record<Task["type"], string> = {
  study: "var(--accent)",
  test: "var(--muted)",
  quiz: "var(--accent)",
  review: "var(--success-text)",
  practice: "var(--muted)",
};

function TaskTypeIcon({ type }: { type: Task["type"] }) {
  const icons: Record<Task["type"], React.ReactElement> = {
    study: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>,
    test: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>,
    quiz: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
    review: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-.46-5.25"/></svg>,
    practice: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>,
  };
  return icons[type] ?? icons.study;
}

function CircularProgress({ done, total }: { done: number; total: number }) {
  const r = 48;
  const circ = 2 * Math.PI * r;
  const dash = total ? circ * (done / total) : 0;
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="flex flex-col items-center">
      <svg width="130" height="130" viewBox="0 0 130 130">
        <circle cx="65" cy="65" r={r} fill="none" stroke="#F0EBE3" strokeWidth="11"/>
        <circle cx="65" cy="65" r={r} fill="none" stroke="url(#prog)" strokeWidth="11"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          transform="rotate(-90 65 65)"
          style={{ transition: "stroke-dasharray 0.8s ease" }}
        />
        <defs>
          <linearGradient id="prog" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#E8A070"/>
            <stop offset="100%" stopColor="#C4714A"/>
          </linearGradient>
        </defs>
        <text x="65" y="58" textAnchor="middle" fontSize="26" fontWeight="800" fill="#1A1108" fontFamily="Vazirmatn,sans-serif">{done}</text>
        <text x="65" y="74" textAnchor="middle" fontSize="11" fill="#7A6858" fontFamily="Vazirmatn,sans-serif">از {total} تکلیف</text>
        <text x="65" y="89" textAnchor="middle" fontSize="13" fontWeight="700" fill="#C4714A" fontFamily="Vazirmatn,sans-serif">{pct}٪</text>
      </svg>
      <p className="text-[11px] font-bold text-[var(--muted-2)] mt-1">پیشرفت امروز</p>
    </div>
  );
}

function TaskSheet({ task, onClose, onPostpone, onSave }: {
  task: HomeTask; onClose: () => void; onPostpone: () => void; onSave: (updated: HomeTask) => void;
}) {
  const color = getSubjectColor(task.subject);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description);
  const [duration, setDuration] = useState(task.duration);
  const [scheduledTime, setScheduledTime] = useState(task.scheduledTime);

  function handleSave() {
    onSave({ ...task, title, description, duration, scheduledTime });
    setEditing(false);
    onClose();
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/25 backdrop-blur-[2px]" onClick={onClose}>
      <div className="w-full max-w-[430px] bg-[#F8F6F2] rounded-t-3xl p-6 pb-10 shadow-2xl"
        onClick={e => e.stopPropagation()}>
        {/* Handle */}
        <div className="w-10 h-1 bg-[#D5CCC3] rounded-full mx-auto mb-5" />

        {/* Type badge + title */}
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
            style={{ background: typeBg[task.type], color: typeColor[task.type] }}>
            <TaskTypeIcon type={task.type} />
          </div>
          <div className="flex-1 min-w-0">
            {editing ? (
              <input value={title} onChange={e => setTitle(e.target.value)}
                className="w-full font-bold text-[16px] text-[var(--text)] bg-[var(--card)] border-2 border-[#C4714A] rounded-xl px-3 py-1.5 outline-none" />
            ) : (
              <p className="font-bold text-[16px] text-[var(--text)] leading-snug">{task.title}</p>
            )}
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[11px] font-bold" style={{ color }}>{task.subject}</span>
              <span className="text-[11px] text-[#C4B8A8]">·</span>
              <span className="text-[11px] text-[var(--muted-2)] font-medium">{typeLabels[task.type]}</span>
            </div>
          </div>
        </div>

        {editing ? (
          <textarea value={description} onChange={e => setDescription(e.target.value)} rows={3}
            className="w-full text-[13px] text-[#5A4030] leading-relaxed mb-4 bg-[var(--card)] rounded-2xl px-4 py-3 border-2 border-[#C4714A] outline-none resize-none" />
        ) : (
          <p className="text-[13px] text-[#5A4030] leading-relaxed mb-4 bg-[var(--card)] rounded-2xl px-4 py-3 border border-[var(--border)]">
            {task.description}
          </p>
        )}

        <div className="flex gap-2 mb-5">
          <div className="flex-1 bg-[#F0EBE3] rounded-xl px-3 py-2.5">
            <p className="text-[10px] font-bold text-[var(--muted-2)] mb-0.5">مدت</p>
            {editing ? (
              <input value={duration} onChange={e => setDuration(e.target.value)}
                className="w-full text-[12px] font-bold text-[#3A2A1A] bg-transparent outline-none border-b border-[#C4714A]" />
            ) : (
              <p className="text-[13px] font-bold text-[#3A2A1A]">{task.duration}</p>
            )}
          </div>
          <div className="flex-1 bg-[#F0EBE3] rounded-xl px-3 py-2.5">
            <p className="text-[10px] font-bold text-[var(--muted-2)] mb-0.5">ساعت</p>
            {editing ? (
              <input value={scheduledTime} onChange={e => setScheduledTime(e.target.value)} dir="ltr"
                className="w-full text-[12px] font-bold text-[#3A2A1A] bg-transparent outline-none border-b border-[#C4714A] text-left" />
            ) : (
              <p className="text-[13px] font-bold text-[#3A2A1A]" dir="ltr">{task.scheduledTime}</p>
            )}
          </div>
        </div>

        {editing ? (
          <div className="flex gap-2.5">
            <button onClick={() => setEditing(false)}
              className="flex-1 py-3.5 rounded-2xl border border-[#E5DDD4] text-[var(--muted)] font-bold text-[13px] hover:bg-[#F0EBE3] transition-colors">
              انصراف
            </button>
            <button onClick={handleSave}
              className="flex-1 py-3.5 rounded-2xl bg-[#C4714A] text-[#F8F6F2] font-bold text-[13px] hover:bg-[#A85C38] transition-colors">
              ذخیره
            </button>
          </div>
        ) : (
          <div className="flex gap-2.5">
            <button onClick={onPostpone}
              className="flex-1 py-3.5 rounded-2xl border border-[#E5DDD4] text-[var(--muted)] font-bold text-[13px] hover:bg-[#F0EBE3] transition-colors">
              تعویق به فردا
            </button>
            <button onClick={() => setEditing(true)}
              className="flex-1 py-3.5 rounded-2xl bg-[#C4714A] text-[#F8F6F2] font-bold text-[13px] hover:bg-[#A85C38] transition-colors">
              ویرایش
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function QuizResultModal({ task, onClose, onSubmit }: { task: HomeTask; onClose: () => void; onSubmit: (time: string, pct: string) => void }) {
  const [time, setTime] = useState("");
  const [pct, setPct] = useState("");
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 backdrop-blur-[2px] p-6" onClick={onClose}>
      <div className="w-full max-w-[360px] bg-[#F8F6F2] rounded-3xl p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="w-9 h-9 rounded-xl mb-4 flex items-center justify-center"
          style={{ background: typeBg[task.type], color: typeColor[task.type] }}>
          <TaskTypeIcon type={task.type} />
        </div>
        <h3 className="font-display text-xl text-[var(--text)] mb-1">{task.title}</h3>
        <p className="text-[12px] text-[var(--muted-2)] mb-5">نتیجه‌ی {typeLabels[task.type]} رو وارد کن</p>

        <div className="flex flex-col gap-3 mb-5">
          <div>
            <label className="text-[11px] font-bold text-[var(--muted)] mb-1.5 block">زمان صرف‌شده (دقیقه)</label>
            <input type="number" value={time} onChange={e => setTime(e.target.value)}
              placeholder="مثلاً ۳۵" dir="ltr"
              className="w-full bg-[var(--card)] border-2 border-[#E5DDD4] focus:border-[#C4714A] outline-none rounded-xl px-4 py-3 text-[14px] font-bold text-[var(--text)] placeholder:text-[#C4B8A8] transition-colors text-left" />
          </div>
          <div>
            <label className="text-[11px] font-bold text-[var(--muted)] mb-1.5 block">درصد پاسخ درست</label>
            <input type="number" min="0" max="100" value={pct} onChange={e => setPct(e.target.value)}
              placeholder="مثلاً ۷۲" dir="ltr"
              className="w-full bg-[var(--card)] border-2 border-[#E5DDD4] focus:border-[#C4714A] outline-none rounded-xl px-4 py-3 text-[14px] font-bold text-[var(--text)] placeholder:text-[#C4B8A8] transition-colors text-left" />
          </div>
        </div>

        <div className="flex gap-2">
          <button onClick={onClose}
            className="flex-1 py-3.5 rounded-2xl border border-[#E5DDD4] text-[var(--muted)] font-bold text-[13px] hover:bg-[#F0EBE3] transition-colors">
            انصراف
          </button>
          <button onClick={() => onSubmit(time, pct)} disabled={!time || !pct}
            className={`flex-1 py-3.5 rounded-2xl font-bold text-[13px] transition-all ${
              time && pct ? "bg-[#C4714A] text-[#F8F6F2] hover:bg-[#A85C38]" : "bg-[#E5DDD4] text-[#B0A898] cursor-not-allowed"
            }`}>
            ثبت نتیجه
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Home({ userData, nav, logout }: { userData: SignupData; nav: NavFn; logout: () => void }) {
  const todayISO = toISO(new Date());
  const [tasks, setTasks] = useState<HomeTask[]>(() => homeTasksForDate(todayISO));
  const done = tasks.filter(t => t.done).length;
  const daysLeft = daysUntil(KONKOOR_DATE);
  const [showTime, setShowTime] = useState(false);
  const [selectedTask, setSelectedTask] = useState<HomeTask | null>(null);
  const [quizTask, setQuizTask] = useState<HomeTask | null>(null);
  const [postponingId, setPostponingId] = useState<number | null>(null);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "صبح بخیر" : hour < 17 ? "ظهر بخیر" : "شب بخیر";

  // 3 hero states based on streak + completion
  const isFirstWeek = STREAK <= 3;
  const donePct = tasks.length ? done / tasks.length : 0;
  const heroMode: "ai" | "countdown" | "circular" = isFirstWeek ? "ai" : donePct < 0.5 ? "countdown" : "circular";

  const AI_LEVEL = 47;

  // Re-derive whenever the weekly plan or statics change anywhere in the app
  // (Schedule edits, AI chat plan_update) or the day rolls over.
  const refreshTasks = useCallback(() => {
    setTasks(homeTasksForDate(todayISO));
  }, [todayISO]);

  useEffect(() => {
    refreshTasks();
    window.addEventListener(SCHEDULE_CHANGED_EVENT, refreshTasks);
    return () => window.removeEventListener(SCHEDULE_CHANGED_EVENT, refreshTasks);
  }, [refreshTasks]);

  function handleCheckbox(task: HomeTask) {
    if ((task.type === "quiz" || task.type === "test") && !task.done) {
      setQuizTask(task);
    } else {
      toggleDone(todayISO, task);
      refreshTasks();
    }
  }

  function handlePostpone(task: HomeTask) {
    setSelectedTask(null);
    setPostponingId(task.id);
    setTimeout(() => {
      postponeToTomorrow(todayISO, task);
      setPostponingId(null);
    }, 380);
  }

  function handleSaveTask(updated: HomeTask) {
    saveTaskEdit(todayISO, updated, {
      title: updated.title,
      description: updated.description,
      duration: updated.duration,
      scheduledTime: updated.scheduledTime,
    });
    refreshTasks();
  }

  function handleQuizSubmit(_time: string, _pct: string) {
    if (!quizTask) return;
    toggleDone(todayISO, quizTask, true);
    refreshTasks();
    setQuizTask(null);
  }

  return (
    <div className="min-h-screen bg-[#F8F6F2] pb-32">

      {/* ── Hero card ── */}
      <div className="mx-4 mt-6">
        <div className="bg-[var(--card)] rounded-3xl p-5 shadow-sm border border-[var(--border)] flex flex-col">

          {/* Top row: [settings + greeting] right | [streak] left */}
          <div className="flex items-center justify-between">
            {/* Right side: settings button + greeting (RTL: first = rightmost) */}
            <div className="flex items-center gap-2.5">
              <button onClick={() => { nav("profile"); }}
                className="w-9 h-9 rounded-xl bg-[#F0EBE3] flex items-center justify-center text-[var(--muted)] hover:bg-[#E5DDD4] transition-colors flex-shrink-0">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3"/>
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                </svg>
              </button>
              <button onClick={logout}
                className="w-9 h-9 rounded-xl bg-red-50 flex items-center justify-center text-red-500 hover:bg-red-100 transition-colors flex-shrink-0">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
                </svg>
              </button>
              <div>
                <p className="text-[10px] text-[var(--muted-2)] font-medium">{greeting}</p>
                <p className="font-display text-[17px] text-[var(--text)] leading-tight">{userData.name || userData.phone || "دانش‌آموز"}</p>
              </div>
            </div>

            {/* Left side: streak (RTL: last = leftmost) */}
              <button onClick={() => { nav("streak"); }}
              className="flex items-center gap-1.5 bg-[var(--accent-soft)] border border-[var(--accent-soft-border)] rounded-xl px-3 py-1.5 hover:bg-[var(--chip-hover)] transition-colors">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" className="text-[var(--accent)]">
                <path d="M12 2C9 7 6 8 7 13c.7 3 3 5 5 5s4.3-2 5-5c1-5-2-6-5-11z"/>
              </svg>
              <span className="text-[13px] font-bold text-[var(--accent)]">{STREAK}</span>
              <span className="text-[11px] text-[var(--muted-2)] font-medium">روز</span>
            </button>
          </div>

          {/* Hero content */}
          <div className="mt-5">
            {heroMode === "ai" && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <p className="text-[11px] font-bold tracking-[0.08em] text-[var(--muted-2)]">شخصی‌سازی هوش مصنوعی</p>
                    <div className="flex items-end gap-2 mt-1">
                      <span className="text-3xl font-bold text-[var(--text)]">{AI_LEVEL}٪</span>
                      <span className="text-[12px] text-[var(--muted)] mb-0.5">از تو یاد گرفته</span>
                    </div>
                  </div>
                  <div className="w-12 h-12 rounded-2xl bg-[#1A1108] flex items-center justify-center">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#F8F6F2" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z"/><line x1="9" y1="21" x2="15" y2="21"/><line x1="10" y1="17" x2="10" y2="21"/><line x1="14" y1="17" x2="14" y2="21"/>
                    </svg>
                  </div>
                </div>
                <div className="relative h-2.5 bg-[#F0EBE3] rounded-full overflow-hidden mb-2">
                  <div className="absolute inset-y-0 right-0 rounded-full transition-all duration-1000"
                    style={{ width: `${AI_LEVEL}%`, background: "linear-gradient(to left, #C4714A, #E8A070)" }} />
                </div>
                <p className="text-[11px] text-[var(--muted-2)]">هر تکلیف که انجام بدی، بوم بیشتر یاد می‌گیره</p>
                <div className="mt-4 pt-4 border-t border-[var(--border)] flex items-center justify-between">
                  <div>
                    <p className="text-[10px] text-[var(--muted-2)]">XP امروز</p>
                    <p className="text-xl font-bold text-[#6B9E7A]">۴۰</p>
                  </div>
                  <div className="text-left">
                    <p className="text-[10px] text-[var(--muted-2)]">روز تا کنکور</p>
                    <p className="text-xl font-bold text-[#C4714A]">{daysLeft}</p>
                  </div>
                </div>
              </div>
            )}

            {heroMode === "countdown" && (
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-bold text-[var(--muted-2)] mb-1">روز تا کنکور</p>
                  <p className="text-[72px] font-bold text-[var(--text)] leading-none tabular-nums">{daysLeft}</p>
                  <p className="text-[11px] text-[var(--muted-2)] mt-1">{[userData.examYear, userData.major].filter(Boolean).join(" · ") || "پروفایل ناقص"}</p>
                </div>
                <div className="bg-[#FFF5F0] rounded-2xl px-4 py-3 text-left">
                  <p className="text-[9px] font-bold text-[var(--muted-2)]">تکمیل امروز</p>
                  <p className="text-[20px] font-bold text-[#C4714A] leading-none">{done}<span className="text-[12px] text-[#C4A080]">/{tasks.length}</span></p>
                </div>
              </div>
            )}

            {heroMode === "circular" && (
              <div className="flex items-center justify-between">
                <CircularProgress done={done} total={tasks.length} />
                <div className="text-left">
                  <p className="text-[10px] font-bold text-[var(--muted-2)]">روز تا کنکور</p>
                  <p className="text-[42px] font-bold text-[#C4714A] leading-none">{daysLeft}</p>
                  <p className="text-[11px] text-[var(--muted-2)] mt-1">{userData.examYear || "—"}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Tasks ── */}
      <div className="px-4 mt-5">
        <div className="flex items-center justify-between mb-3">
          <button onClick={() => setShowTime(s => !s)}
            className="text-[11px] font-bold text-[var(--muted-2)] bg-[#F0EBE3] px-3 py-1 rounded-full hover:bg-[#E5DDD4] transition-colors">
            {showTime ? "نمایش مدت" : "نمایش ساعت"}
          </button>
          <h2 className="font-display text-[18px] text-[var(--text)]">تکالیف امروز</h2>
        </div>

        <div className="flex flex-col gap-2">
          {tasks.filter(t => !t.skipped).length === 0 && (
            <div className="bg-[var(--card)] rounded-2xl border border-dashed border-[#D5CCC3] p-6 text-center">
              <p className="text-[13px] font-semibold text-[var(--muted)]">برنامه‌ای برای امروز نیست</p>
              <p className="text-[11px] text-[var(--muted-2)] mt-1 leading-relaxed">
                از «برنامه هفتگی» برنامه‌ات را بساز یا از بوم AI بخواه برایت بریزد؛ همین‌جا نشان داده می‌شود.
              </p>
              <div className="flex justify-center gap-2 mt-4">
                <button onClick={() => nav("schedule")}
                  className="press px-4 py-2 rounded-xl bg-[var(--accent)] text-[var(--surface)] text-[12px] font-bold hover:brightness-105 transition-all">
                  برنامه هفتگی
                </button>
                <button onClick={() => nav("chat")}
                  className="press px-4 py-2 rounded-xl border border-[var(--border-strong)] text-[var(--muted)] text-[12px] font-bold hover:bg-[#F0EBE3] transition-colors">
                  گفتگو با بوم AI
                </button>
              </div>
            </div>
          )}
          {tasks.filter(t => !t.skipped).map(task => {
            const color = getSubjectColor(task.subject);
            const isQuizOrTest = task.type === "quiz" || task.type === "test";
            const isPostponing = postponingId === task.id;
            return (
              <div key={task.id}
                className={`bg-[var(--card)] rounded-2xl border flex items-stretch overflow-hidden transition-all duration-[380ms] ${
                  task.done ? "border-[var(--border)] opacity-55" : "border-[var(--border)] hover:border-[#E5DDD4] shadow-sm"
                }`}
                style={isPostponing ? {
                  opacity: 0, transform: "translateX(100%)", maxHeight: 0, marginBottom: 0, overflow: "hidden",
                } : { maxHeight: "200px" }}
              >
                {/* Checkbox — rightmost in RTL */}
                <div className="flex items-center pr-3.5">
                  <button onClick={() => handleCheckbox(task)}
                    className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all flex-shrink-0 ${
                      task.done ? "border-[#C4714A] bg-[#C4714A]" : isQuizOrTest ? "border-[#9B7AAD] hover:border-[#7A4A9A]" : "border-[#D5CCC3] hover:border-[#C4714A]"
                    }`}
                  >
                    {task.done && (
                      <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                        <path d="M1 4l3 3 5-6" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                    {!task.done && isQuizOrTest && (
                      <div className="w-2 h-2 rounded-full bg-[#9B7AAD] opacity-60" />
                    )}
                  </button>
                </div>

                {/* Body — clickable to open sheet */}
                <button onClick={() => setSelectedTask(task)}
                  className="flex-1 py-3 px-2 text-right min-w-0">
                  <p className={`text-[13px] font-semibold leading-snug ${task.done ? "line-through text-[#B0A898]" : "text-[var(--text)]"}`}>
                    {task.title}
                  </p>
                  <p className="text-[11px] text-[var(--muted-2)] mt-0.5 font-medium line-clamp-1">{task.description}</p>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className="text-[10px] font-bold" style={{ color }}>{task.subject}</span>
                    <span className="text-[10px] text-[#D5CCC3]">·</span>
                    <span className="text-[10px] font-medium" style={{ color: typeColor[task.type] }}>{typeLabels[task.type]}</span>
                  </div>
                </button>

                {/* Type icon */}
                <div className="flex items-center pl-1.5 pr-1">
                  <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: typeBg[task.type], color: typeColor[task.type] }}>
                    <TaskTypeIcon type={task.type} />
                  </div>
                </div>

                {/* Time/Duration */}
                <div className="flex flex-col items-center justify-center px-3 py-4 min-w-[58px] bg-[#FAFAF8] border-r border-[var(--border)]">
                  <span className="text-[10px] font-bold text-[var(--muted-2)] text-center leading-tight" dir="ltr">
                    {showTime ? task.scheduledTime : task.duration}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── 3 Action buttons ── */}
      <div className="px-4 mt-4 grid grid-cols-3 gap-2.5">
        {[
          { label: "ریکاوری", sub: "خواب و خلق‌وخو", screen: "recovery" as const, bg: "#EDF5F0", color: "#6B9E7A",
            icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg> },
          { label: "آزمون‌ها", sub: "نتایج و تحلیل", screen: "exams" as const, bg: "#F0EBF5", color: "#9B7AAD",
            icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg> },
          { label: "برنامه", sub: "اهداف و تقویم", screen: "plan" as const, bg: "#EBF0F5", color: "#5C8BA8",
            icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> },
        ].map(({ label, sub, screen, bg, color, icon }) => (
          <button key={label} onClick={() => { nav(screen); }}
            className="bg-[var(--card)] rounded-2xl border border-[var(--border)] p-3 flex flex-col items-center gap-2 hover:border-[#E5DDD4] hover:shadow-sm active:scale-95 transition-all">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: "var(--surface-2)", color: "var(--text)" }}>
              {icon}
            </div>
            <div className="text-center">
              <p className="text-[12px] font-bold text-[var(--text)]">{label}</p>
              <p className="text-[10px] text-[var(--muted-2)] font-medium leading-tight mt-0.5">{sub}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Chat lives in the mobile tab bar now (App.tsx MobileTabBar). */}

      {/* Popups */}
      {selectedTask && (
        <TaskSheet task={selectedTask} onClose={() => setSelectedTask(null)}
          onPostpone={() => handlePostpone(selectedTask)}
          onSave={handleSaveTask} />
      )}
      {quizTask && (
        <QuizResultModal task={quizTask} onClose={() => setQuizTask(null)} onSubmit={handleQuizSubmit} />
      )}
    </div>
  );
}

