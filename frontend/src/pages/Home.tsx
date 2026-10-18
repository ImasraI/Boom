import { useCallback, useEffect, useState } from "react";
import { celebrate } from "../components/Experience";
import React from "react";
import { NavFn, SignupData, Task } from "../types";
import { SUBJECT_COLORS } from "../data";
import {
  homeTasksForDate,
  postponeToTomorrow,
  reportTaskActual,
  saveTaskEdit,
  toggleDone,
  type HomeTask,
} from "../homeTasks";
import { SCHEDULE_CHANGED_EVENT, toISO } from "../scheduleStore";
import WeaknessMap from "../components/WeaknessMap";
import StudyDeskHero from "../components/StudyDeskHero";

import { currentStreak } from "../studyStats";
import { apiUrl, authHeaders } from "../api";
import { calendarSyncError, flushCalendar, pullCalendar } from "../calendarSync";

function daysUntil(d: string) {
  const diff = new Date(d + "T00:00:00").getTime() - new Date().setHours(0, 0, 0, 0);
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

function TaskSheet({ task, onClose, onPostpone, onSave }: {
  task: HomeTask; onClose: () => void; onPostpone: () => void; onSave: (updated: HomeTask) => void;
}) {
  const color = getSubjectColor(task.subject);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description);
  const [duration, setDuration] = useState(task.duration);
  const [scheduledTime, setScheduledTime] = useState(task.scheduledTime);
  const [error, setError] = useState("");

  function handleSave() {
    try {
      onSave({ ...task, title, description, duration, scheduledTime });
      setEditing(false);
      onClose();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "ثبت تغییرات انجام نشد."); }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/25 backdrop-blur-[2px]" onClick={onClose}>
      <div className="w-full max-w-[430px] bg-[var(--surface)] rounded-t-3xl p-6 pb-10 shadow-2xl"
        onClick={e => e.stopPropagation()}>
        {/* Handle */}
        <div className="w-10 h-1 bg-[var(--chip)] rounded-full mx-auto mb-5" />

        {/* Type badge + title */}
        {error && <p role="alert" className="text-xs text-red-600 mb-3">{error}</p>}
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
            style={{ background: typeBg[task.type], color: typeColor[task.type] }}>
            <TaskTypeIcon type={task.type} />
          </div>
          <div className="flex-1 min-w-0">
            {editing ? (
              <input value={title} onChange={e => setTitle(e.target.value)}
                className="w-full font-bold text-[16px] text-[var(--text)] bg-[var(--card)] border-2 border-[var(--accent)] rounded-xl px-3 py-1.5 outline-none" />
            ) : (
              <p className="font-bold text-[16px] text-[var(--text)] leading-snug">{task.title}</p>
            )}
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[11px] font-bold" style={{ color }}>{task.subject}</span>
              <span className="text-[11px] text-[var(--muted-2)]">·</span>
              <span className="text-[11px] text-[var(--muted-2)] font-medium">{typeLabels[task.type]}</span>
            </div>
          </div>
        </div>

        {editing ? (
          <textarea value={description} onChange={e => setDescription(e.target.value)} rows={3}
            className="w-full text-[13px] text-[var(--brown-text)] leading-relaxed mb-4 bg-[var(--card)] rounded-2xl px-4 py-3 border-2 border-[var(--accent)] outline-none resize-none" />
        ) : (
          <p className="text-[13px] text-[var(--brown-text)] leading-relaxed mb-4 bg-[var(--card)] rounded-2xl px-4 py-3 border border-[var(--border)]">
            {task.description}
          </p>
        )}

        <div className="flex gap-2 mb-5">
          <div className="flex-1 bg-[var(--chip)] rounded-xl px-3 py-2.5">
            <p className="text-[10px] font-bold text-[var(--muted-2)] mb-0.5">مدت</p>
            {editing ? (
              <input value={duration} onChange={e => setDuration(e.target.value)}
                className="w-full text-[12px] font-bold text-[var(--text-strong)] bg-transparent outline-none border-b border-[var(--accent)]" />
            ) : (
              <p className="text-[13px] font-bold text-[var(--text-strong)]">{task.duration}</p>
            )}
          </div>
          <div className="flex-1 bg-[var(--chip)] rounded-xl px-3 py-2.5">
            <p className="text-[10px] font-bold text-[var(--muted-2)] mb-0.5">ساعت</p>
            {editing ? (
              <input value={scheduledTime} onChange={e => setScheduledTime(e.target.value)} dir="ltr"
                className="w-full text-[12px] font-bold text-[var(--text-strong)] bg-transparent outline-none border-b border-[var(--accent)] text-left" />
            ) : (
              <p className="text-[13px] font-bold text-[var(--text-strong)]" dir="ltr">{task.scheduledTime}</p>
            )}
          </div>
        </div>

        {editing ? (
          <div className="flex gap-2.5">
            <button onClick={() => setEditing(false)}
              className="flex-1 py-3.5 rounded-2xl border border-[var(--chip)] text-[var(--muted)] font-bold text-[13px] hover:bg-[var(--chip)] transition-colors">
              انصراف
            </button>
            <button onClick={handleSave}
              className="flex-1 py-3.5 rounded-2xl bg-[var(--accent)] text-[var(--action-ink)] font-bold text-[13px] hover:bg-[var(--accent-ink)] transition-colors">
              ذخیره
            </button>
          </div>
        ) : (
          <>
            <ReportActualBlock task={task} onClose={onClose} />
            <div className="flex gap-2.5">
              <button onClick={() => { try { onPostpone(); } catch (cause) { setError(cause instanceof Error ? cause.message : "جابه‌جایی انجام نشد."); } }}
                className="flex-1 py-3.5 rounded-2xl border border-[var(--chip)] text-[var(--muted)] font-bold text-[13px] hover:bg-[var(--chip)] transition-colors">
                تعویق به فردا
              </button>
              <button onClick={() => setEditing(true)}
                className="flex-1 py-3.5 rounded-2xl bg-[var(--accent)] text-[var(--action-ink)] font-bold text-[13px] hover:bg-[var(--accent-ink)] transition-colors">
                ویرایش
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const REPORT_PRESETS = [15, 30, 45, 60, 90];

/** Roadmap §3 quick report: actual minutes + honest status, 3 taps.
 * Replaces the binary checkbox as the *optional* richer path. */
function ReportActualBlock({ task, onClose }: { task: HomeTask; onClose: () => void }) {
  const planMin = Math.max(1, Math.round(task.planBlock.duration * 60));
  const [minutes, setMinutes] = useState(planMin);
  const [saved, setSaved] = useState(false);

  function report(status: "completed" | "partially_completed" | "missed") {
    reportTaskActual(toISO(new Date()), task, { status, actualMinutes: minutes });
    setSaved(true);
    setTimeout(onClose, 450);
  }

  if (saved) {
    return (
      <div className="mb-3 p-3 rounded-2xl bg-[var(--success-bg)] text-[12px] font-bold text-[var(--success-text)] text-center">
        ثبت شد — برنامه‌ریز آن را می‌بیند
      </div>
    );
  }

  return (
    <div className="mb-5 p-4 rounded-2xl bg-[var(--card)] border border-[var(--border)]">
      <p className="text-[11px] font-bold text-[var(--muted-2)] mb-2">واقعاً چقدر انجام شد؟ (اختیاری)</p>
      <div className="flex gap-1.5 mb-3" dir="ltr">
        {REPORT_PRESETS.map((m) => (
          <button key={m} onClick={() => setMinutes(m)}
            className={`flex-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
              minutes === m ? "bg-[var(--accent)] text-[var(--action-ink)]" : "bg-[var(--chip)] text-[var(--muted)]"}`}>
            {m}
          </button>
        ))}
      </div>
      <div className="flex gap-1.5">
        <button onClick={() => report("completed")}
          className="flex-1 py-2 rounded-xl bg-[var(--syntax-green)] text-white text-[11px] font-bold hover:bg-[var(--success-text)] transition-colors">
          کامل
        </button>
        <button onClick={() => report("partially_completed")}
          className="flex-1 py-2 rounded-xl bg-[var(--syntax-orange)] text-white text-[11px] font-bold hover:bg-[var(--warn-text)] transition-colors">
          ناقص
        </button>
        <button onClick={() => report("missed")}
          className="flex-1 py-2 rounded-xl bg-[var(--error-text)] text-white text-[11px] font-bold hover:bg-[var(--error-text)] transition-colors">
          نشد
        </button>
      </div>
    </div>
  );
}

function QuizResultModal({ task, onClose, onSubmit }: { task: HomeTask; onClose: () => void; onSubmit: (time: string, pct: string) => void }) {
  const [time, setTime] = useState("");
  const [pct, setPct] = useState("");
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 backdrop-blur-[2px] p-6" onClick={onClose}>
      <div className="w-full max-w-[360px] bg-[var(--surface)] rounded-3xl p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
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
              className="w-full bg-[var(--card)] border-2 border-[var(--chip)] focus:border-[var(--accent)] outline-none rounded-xl px-4 py-3 text-[14px] font-bold text-[var(--text)] placeholder:text-[var(--muted-2)] transition-colors text-left" />
          </div>
          <div>
            <label className="text-[11px] font-bold text-[var(--muted)] mb-1.5 block">درصد پاسخ درست</label>
            <input type="number" min="0" max="100" value={pct} onChange={e => setPct(e.target.value)}
              placeholder="مثلاً ۷۲" dir="ltr"
              className="w-full bg-[var(--card)] border-2 border-[var(--chip)] focus:border-[var(--accent)] outline-none rounded-xl px-4 py-3 text-[14px] font-bold text-[var(--text)] placeholder:text-[var(--muted-2)] transition-colors text-left" />
          </div>
        </div>

        <div className="flex gap-2">
          <button onClick={onClose}
            className="flex-1 py-3.5 rounded-2xl border border-[var(--chip)] text-[var(--muted)] font-bold text-[13px] hover:bg-[var(--chip)] transition-colors">
            انصراف
          </button>
          <button onClick={() => onSubmit(time, pct)} disabled={!time || !pct}
            className={`flex-1 py-3.5 rounded-2xl font-bold text-[13px] transition-all ${
              time && pct ? "bg-[var(--accent)] text-[var(--action-ink)] hover:bg-[var(--accent-ink)]" : "bg-[var(--chip)] text-[var(--muted-2)] cursor-not-allowed"
            }`}>
            ثبت نتیجه
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Home({ userData, nav, logout }: { userData: SignupData; nav: NavFn; logout: () => void }) {
  const [todayISO, setTodayISO] = useState(() => toISO(new Date()));
  const [syncError, setSyncError] = useState("");
  const [tasks, setTasks] = useState<HomeTask[]>(() => homeTasksForDate(todayISO));
  const STREAK = currentStreak();
  const [nextExamDate, setNextExamDate] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    fetch(apiUrl("/api/boom/plan-overview"), { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (active) setNextExamDate(data?.exams?.[0]?.date || null); })
      .catch(() => {});
    return () => { active = false; };
  }, []);
  const daysLeft = nextExamDate ? daysUntil(nextExamDate) : "—";
  const [showTime, setShowTime] = useState(false);
  const [selectedTask, setSelectedTask] = useState<HomeTask | null>(null);
  const [quizTask, setQuizTask] = useState<HomeTask | null>(null);
  const [postponingId, setPostponingId] = useState<number | null>(null);
  // Re-derive whenever the weekly plan or statics change anywhere in the app
  // (Schedule edits, AI chat plan_update) or the day rolls over.
  const refreshTasks = useCallback(() => {
    setTasks(homeTasksForDate(todayISO));
  }, [todayISO]);

  useEffect(() => {
    refreshTasks();
    let active = true;
    const token = localStorage.getItem("boom-token");
    const sync = async () => {
      setTodayISO(toISO(new Date()));
      const ok = await flushCalendar(token) && await pullCalendar(token);
      if (active && localStorage.getItem("boom-token") === token) setSyncError(ok ? "" : calendarSyncError());
    };
    void sync();
    window.addEventListener("focus", sync);
    const timer = window.setInterval(() => setTodayISO(toISO(new Date())), 60000);
    window.addEventListener(SCHEDULE_CHANGED_EVENT, refreshTasks);
    return () => { active = false; window.clearInterval(timer); window.removeEventListener("focus", sync); window.removeEventListener(SCHEDULE_CHANGED_EVENT, refreshTasks); };
  }, [refreshTasks]);

  function handleCheckbox(task: HomeTask) {
    if ((task.type === "quiz" || task.type === "test") && !task.done) {
      setQuizTask(task);
    } else {
      toggleDone(todayISO, task);
      if (!task.done) celebrate("این قدم ثبت شد. همین‌طور ادامه بده.");
      refreshTasks();
    }
  }

  function handlePostpone(task: HomeTask) {
    postponeToTomorrow(todayISO, task);
    setSelectedTask(null);
    setPostponingId(task.id);
    setTimeout(() => {
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
    celebrate("تمرین امروزت ثبت شد.");
    refreshTasks();
    setQuizTask(null);
  }

  return (
    <div className="home-desk min-h-screen bg-[var(--surface)] pb-32">

      <StudyDeskHero tasks={tasks} userData={userData} nav={nav} logout={logout}
        streak={STREAK} daysLeft={daysLeft} date={todayISO} />

      {/* ── Weakness map (from wrong_answers across all tests) ── */}
      <div className="border-b border-[var(--border)]">
        <WeaknessMap />
      </div>

      {/* ── Tasks ── */}
      <div className="desk-tasks bg-[var(--card)] border-b border-[var(--border)] px-4 pt-4 pb-2">
        <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
          <button onClick={() => setShowTime(s => !s)}
            className="text-[11px] font-bold text-[var(--muted-2)] bg-[var(--chip)] px-3 py-1 rounded-full hover:bg-[var(--chip)] transition-colors">
            {showTime ? "نمایش مدت" : "نمایش ساعت"}
          </button>
          <h2 className="font-display text-[18px] text-[var(--text)]">تکالیف امروز</h2>
        </div>
        <div className="flex items-center justify-between gap-3 py-3 text-[11px] text-[var(--muted)]">
          <p>فعالیت‌های امروز از برنامهٔ هفتگی خودت؛ مطالعه، تمرین و تکلیف.</p>
          <button onClick={() => nav("chat")} className="shrink-0 font-bold text-[var(--accent)]">ثبت تکلیف در گفتگو</button>
        </div>
        {syncError && <p role="alert" className="text-xs text-[var(--danger)] pb-3">{syncError}</p>}

        <div className="flex flex-col">
          {tasks.filter(t => !t.skipped).length === 0 && (
            <div className="py-8 text-center">
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
                  className="press px-4 py-2 rounded-xl border border-[var(--border-strong)] text-[var(--muted)] text-[12px] font-bold hover:bg-[var(--chip)] transition-colors">
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
                data-subject={task.subject} className={`task-tile flex items-stretch overflow-hidden border-b border-[var(--border)] last:border-b-0 transition-all duration-[380ms] ${
                  task.done ? "opacity-55" : "hover:bg-[var(--surface-2)]"
                }`}
                style={isPostponing ? {
                  opacity: 0, transform: "translateX(100%)", maxHeight: 0, marginBottom: 0, overflow: "hidden",
                } : { maxHeight: "200px", "--task-tone": color } as React.CSSProperties}
              >
                {/* Checkbox — rightmost in RTL */}
                <div className="flex items-center pr-3.5">
                  <button onClick={() => handleCheckbox(task)}
                    aria-label={`${task.done ? "لغو انجام" : "انجام شد"}: ${task.title} (${task.scheduledTime})`}
                    aria-pressed={task.done}
                    className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all flex-shrink-0 ${
                      task.done ? "border-[var(--accent)] bg-[var(--accent)]" : isQuizOrTest ? "border-[var(--syntax-purple)] hover:border-[var(--syntax-purple)]" : "border-[var(--chip)] hover:border-[var(--accent)]"
                    }`}
                  >
                    {task.done && (
                      <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                        <path d="M1 4l3 3 5-6" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                    {!task.done && isQuizOrTest && (
                      <div className="w-2 h-2 rounded-full bg-[var(--syntax-purple)] opacity-60" />
                    )}
                  </button>
                </div>

                {/* Body — clickable to open sheet */}
                <button onClick={() => setSelectedTask(task)}
                  className="flex-1 py-3 px-2 text-right min-w-0">
                  <p className={`text-[13px] font-semibold leading-snug ${task.done ? "line-through text-[var(--muted-2)]" : "text-[var(--text)]"}`}>
                    {task.title}
                  </p>
                  <p className="text-[11px] text-[var(--muted-2)] mt-0.5 font-medium line-clamp-1">{task.description}</p>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className="text-[10px] font-bold" style={{ color }}>{task.subject}</span>
                    <span className="text-[10px] text-[var(--chip)]">·</span>
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
                <div className="flex flex-col items-center justify-center px-3 py-4 min-w-[58px] bg-[var(--field)] border-r border-[var(--border)]">
                  <span className="text-[10px] font-bold text-[var(--muted-2)] text-center leading-tight" dir="ltr">
                    {showTime ? task.scheduledTime : task.duration}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Planning and exam shortcuts ── */}
      <div className="desk-shortcuts bg-[var(--card)] grid grid-cols-2 [&>*+*]:border-r [&>*+*]:border-[var(--border)]">
        {[
          { label: "آزمون‌ها", sub: "نتایج و تحلیل", screen: "exams" as const, bg: "var(--accent-soft)", color: "var(--syntax-purple)",
            icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg> },
          { label: "برنامه", sub: "اهداف و تقویم", screen: "plan" as const, bg: "var(--accent-soft)", color: "var(--syntax-blue)",
            icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> },
        ].map(({ label, sub, screen, icon }) => (
          <button key={label} onClick={() => { nav(screen); }}
            className="p-4 flex flex-col items-center gap-2 hover:bg-[var(--surface-2)] transition-colors">
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
