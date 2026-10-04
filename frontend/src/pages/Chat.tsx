import { accountStorage } from "../accountStorage";
import { useState, useRef, useEffect } from "react";
import { apiUrl, authHeaders } from "../api";
import { NavFn, SignupData } from "../types";
import { weeklyScheduleContext, loadWeekBlocks, saveWeekBlocks, getWeekISO, hasScheduleOverlap, StoredBlock } from "../scheduleStore";
import ChatMarkdown from "../components/ChatMarkdown";

interface Msg {
  role: "user" | "ai";
  text: string;
  confidence?: { level: string; label: string; score: number };
}
const NEW_CHAT_NAME = "گفتگوی جدید";

function storageKey(userData: SignupData | null) {
  return `boom-chat:${userData?.phone || userData?.name || "guest"}`;
}

function activeStorageKey(userData: SignupData | null) {
  return `${storageKey(userData)}:active`;
}

interface ChatSession {
  id: string;
  name: string;
  msgs: Msg[];
  pending?: boolean;
  updatedAt?: number;
}

function newId() {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function greeting(name: string): Msg {
  return { role: "ai", text: `سلام ${name}! من بوم هستم. چطور میتونم کمک کنم؟` };
}

function createBlank(studentName: string): ChatSession {
  return {
    id: newId(),
    name: NEW_CHAT_NAME,
    msgs: [greeting(studentName)],
    updatedAt: Date.now(),
  };
}

function loadSessions(userData: SignupData | null): Record<string, ChatSession> {
  try {
    const raw = accountStorage.getItem(storageKey(userData));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, ChatSession>;
    const out: Record<string, ChatSession> = {};
    for (const [key, session] of Object.entries(parsed || {})) {
      if (session && typeof session === "object" && Array.isArray(session.msgs)) {
        const id = session.id || key;
        out[id] = { ...session, id };
      }
    }
    return out;
  } catch {
    return {};
  }
}

function saveSessions(userData: SignupData | null, s: Record<string, ChatSession>) {
  accountStorage.setItem(storageKey(userData), JSON.stringify(s));
}

function loadActiveId(userData: SignupData | null, sessions: Record<string, ChatSession>) {
  try {
    const saved = accountStorage.getItem(activeStorageKey(userData));
    if (saved && sessions[saved]) return saved;
  } catch { /* ignore */ }
  const ids = Object.keys(sessions).sort(
    (a, b) => (sessions[b].updatedAt || 0) - (sessions[a].updatedAt || 0),
  );
  return ids[0] || "";
}

function isPlanRequest(t: string) {
  return /(برنامه|پلن).*(ماه|ماهه|هفته|کنکور)|\d+\s*ماه/.test(t);
}

export default function Chat({ nav, userData }: { nav: NavFn; userData: SignupData | null }) {
  const name = userData?.name ?? "دانشآموز";
  const storeKey = storageKey(userData);
  const [sessions, setSessions] = useState<Record<string, ChatSession>>({});
  const [activeId, setActiveId] = useState("");
  const [input, setInput] = useState("");
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const tabsRef = useRef<HTMLDivElement>(null);
  const processingRef = useRef<Set<string>>(new Set());
  const sessionsRef = useRef(sessions);
  const userDataRef = useRef(userData);

  sessionsRef.current = sessions;
  userDataRef.current = userData;

  const active = sessions[activeId];
  const msgs = active?.msgs ?? [];
  const tabs = Object.values(sessions).sort(
    (a, b) => (b.updatedAt || 0) - (a.updatedAt || 0),
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, active?.pending]);

  useEffect(() => {
    let loaded = loadSessions(userData);
    if (Object.keys(loaded).length === 0) {
      const fresh = createBlank(name);
      loaded = { [fresh.id]: fresh };
      saveSessions(userData, loaded);
    }
    setSessions(loaded);
    sessionsRef.current = loaded;
    setActiveId(loadActiveId(userData, loaded));
  }, [storeKey]);

  useEffect(() => {
    if (!activeId) return;
    accountStorage.setItem(activeStorageKey(userData), activeId);
  }, [activeId, storeKey]);

  function commit(next: Record<string, ChatSession>) {
    saveSessions(userDataRef.current, next);
    sessionsRef.current = next;
    setSessions(next);
    return next;
  }

  function processPending(sessionId: string) {
    if (processingRef.current.has(sessionId)) return;
    const session = sessionsRef.current[sessionId];
    if (!session) return;
    const lastUserMsg = [...session.msgs].reverse().find(m => m.role === "user");
    if (!lastUserMsg) return;

    processingRef.current.add(sessionId);
    const currentUser = userDataRef.current;
    const history = session.msgs
      .filter(m => m.role === "user" || m.role === "ai")
      .slice(-8)
      .map(m => ({ role: m.role === "ai" ? "assistant" : "user" as const, content: m.text }));
    const query = lastUserMsg.text;
    const endpoint = isPlanRequest(query) ? "/api/boom/study-plan" : "/api/boom/chat";
    const body = isPlanRequest(query) ? {
      months: Number(query.match(/(\d+)\s*ماه/)?.[1] || 6),
      daily_hours: Number((currentUser?.studyHours || "4").match(/[0-9]+/)?.[0] || 4),
      major: currentUser?.major || "ریاضی فیزیک",
      grade: currentUser?.grade || "دوازدهم (سال کنکور)",
      target_rank: currentUser?.targetRank || "زیر ۵٬۰۰۰",
      student: currentUser || {},
      weak_subjects: [], strong_subjects: [], notes: query,
    } : { question: query, history, student: currentUser || {}, schedule: weeklyScheduleContext() };

    const requestToken = localStorage.getItem("boom-token");
    fetch(apiUrl(endpoint), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    })
      .then(r => r.json())
      .then(data => {
        if (localStorage.getItem("boom-token") !== requestToken) return;
        let updateNotice = "";
        // Handle plan update if present
        if (data.plan_update) {
          const weekISO = getWeekISO();
          let currentBlocks = loadWeekBlocks(weekISO) || [];
          
          // Handle removed blocks (delete)
          if (data.plan_update.removed && data.plan_update.removed.length > 0) {
            currentBlocks = currentBlocks.filter((existingBlock: StoredBlock) => {
              return !data.plan_update.removed.some((removedBlock: StoredBlock) =>
                existingBlock.day === removedBlock.day &&
                existingBlock.startHour === removedBlock.startHour &&
                existingBlock.title === removedBlock.title
              );
            });
          }
          
          // Handle added/updated blocks
          if (data.plan_update.blocks && data.plan_update.blocks.length > 0) {
            const newBlocks = data.plan_update.blocks;
            
            const mergedBlocks = [...currentBlocks];
            newBlocks.forEach((newBlock: StoredBlock) => {
              const idx = mergedBlocks.findIndex(b => 
                b.day === newBlock.day && 
                b.startHour === newBlock.startHour && 
                b.duration === newBlock.duration && 
                b.title === newBlock.title
              );
              if (idx >= 0) {
                mergedBlocks[idx] = { ...mergedBlocks[idx], ...newBlock, id: mergedBlocks[idx].id, origin: "manual" };
              } else {
                mergedBlocks.push({ ...newBlock, id: newId(), origin: "manual" });
              }
            });
            
            currentBlocks = mergedBlocks;
          }
          // Apply deletions and additions together only after checking the
          // latest local plan; it may have changed while the request ran.
          const context = weeklyScheduleContext(weekISO);
          if (hasScheduleOverlap(currentBlocks, context.statics.map(staticBlock => ({ ...staticBlock, day: staticBlock.day ?? 0 })))) {
            updateNotice = "\n\nتغییر پیشنهادی با برنامه فعلی تداخل دارد؛ برنامه تغییر نکرد.";
          } else {
            saveWeekBlocks(weekISO, currentBlocks);
          }
        }
        
        const answer = (data.plan || data.answer || "پاسخی دریافت نشد.") + updateNotice;
        const current = sessionsRef.current;
        if (!current[sessionId]) return;
        commit({
          ...current,
          [sessionId]: {
            ...current[sessionId],
            msgs: [...current[sessionId].msgs, {
              role: "ai",
              text: answer,
              confidence: data.answer_confidence,
            }],
            pending: false,
            updatedAt: Date.now(),
          },
        });
      })
      .catch(() => {
        const current = sessionsRef.current;
        if (!current[sessionId]) return;
        commit({
          ...current,
          [sessionId]: {
            ...current[sessionId],
            msgs: [...current[sessionId].msgs, { role: "ai", text: "خطا در ارتباط با سرور." }],
            pending: false,
            updatedAt: Date.now(),
          },
        });
      })
      .finally(() => processingRef.current.delete(sessionId));
  }

  useEffect(() => {
    Object.values(sessions).forEach(session => {
      if (session.pending) processPending(session.id);
    });
  }, [sessions]);

  function switchSession(id: string) {
    if (!sessionsRef.current[id]) return;
    setActiveId(id);
    setInput("");
    setSessionsOpen(false);
  }

  function createSession() {
    const session = createBlank(name);
    commit({ ...sessionsRef.current, [session.id]: session });
    setActiveId(session.id);
    setInput("");
    setSessionsOpen(false);
    requestAnimationFrame(() => {
      tabsRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  function deleteSession(id: string) {
    const next = { ...sessionsRef.current };
    delete next[id];
    if (Object.keys(next).length === 0) {
      const fresh = createBlank(name);
      next[fresh.id] = fresh;
      commit(next);
      setActiveId(fresh.id);
      setInput("");
      return;
    }
    commit(next);
    if (activeId === id) {
      const fallback = Object.values(next).sort(
        (a, b) => (b.updatedAt || 0) - (a.updatedAt || 0),
      )[0];
      setActiveId(fallback.id);
      setInput("");
    }
  }

  function send(text?: string) {
    const t = (text ?? input).trim();
    if (!t) return;

    let targetId = activeId;
    let next = { ...sessionsRef.current };

    if (!next[targetId]) {
      const session = createBlank(name);
      targetId = session.id;
      next[targetId] = session;
    }

    const current = next[targetId];
    const titled = current.name === NEW_CHAT_NAME ? (t.length > 25 ? `${t.slice(0, 25)}…` : t) : current.name;
    next[targetId] = {
      ...current,
      name: titled,
      msgs: [...current.msgs, { role: "user", text: t }],
      pending: true,
      updatedAt: Date.now(),
    };
    commit(next);
    setActiveId(targetId);
    setInput("");
  }

  return (
    <div className="h-screen flex bg-[var(--surface)]">
      {/* Main chat — first in RTL so it sits on the right */}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex-shrink-0 bg-[var(--card)] border-b border-[var(--border)] px-4 pt-12 pb-3">
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => nav("home")} className="w-9 h-9 rounded-xl bg-[var(--border)] flex items-center justify-center text-[var(--muted)]">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}><path d="M19 12H5M12 5l-7 7 7 7"/></svg>
            </button>
            <h1 className="flex-1 text-right font-bold text-lg text-[var(--text)] truncate">
              {active?.name || "گفتگو"}
            </h1>
            <button type="button" onClick={() => setSessionsOpen(true)} className="sm:hidden w-9 h-9 rounded-xl bg-[var(--chip)] flex items-center justify-center text-[var(--text)]" aria-label="فهرست گفتگوها" aria-expanded={sessionsOpen}>
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 6h16M4 12h16M4 18h11" /></svg>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          <div className="flex flex-col gap-5">
            {msgs.map((m, i) => (
              <div key={i} className="flex justify-start">
                {m.role === "user" ? (
                  <div className="max-w-[85%] px-4 py-3 rounded-3xl bg-[var(--chip)] text-[var(--text)] text-[13px] leading-relaxed whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
                    {m.text}
                  </div>
                ) : (
                  <div className="w-full max-w-[920px] min-w-0 text-[13px] leading-relaxed text-[var(--text)] break-words [overflow-wrap:anywhere]">
                    {m.confidence && <div className="mb-2 text-[10px] font-semibold text-[var(--muted-2)]">{m.confidence.label}</div>}
                    <ChatMarkdown text={m.text} />
                  </div>
                )}
              </div>
            ))}
            {active?.pending && (
              <div className="flex justify-start">
                <div className="flex gap-1.5 items-center">
                  {[0, 1, 2].map(i => <div key={i} className="w-1.5 h-1.5 rounded-full bg-[var(--placeholder)] animate-bounce" style={{ animationDelay: `${i * 0.18}s` }} />)}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="flex-shrink-0 px-4 pb-8 pt-3 bg-[var(--card)] border-t border-[var(--border)]">
          <div className="flex items-end gap-2.5 bg-[var(--surface)] rounded-2xl border-2 border-[var(--border-strong)] focus-within:border-[var(--accent)] px-4 py-3 transition-colors">
            <button type="button" onClick={() => send()} disabled={!input.trim() || !!active?.pending}
              className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mb-0.5 transition-colors ${
                input.trim() && !active?.pending ? "bg-[var(--accent)] text-[var(--surface)]" : "bg-[var(--border-strong)] text-[var(--muted-2)]"
              }`}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
            </button>
            <textarea value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="هر چیزی دربارهی کنکور بپرس..." rows={1}
              className="flex-1 bg-transparent outline-none text-[13px] text-[var(--text)] placeholder:text-[var(--placeholder)] resize-none font-medium leading-relaxed text-right" />
          </div>
          <p className="text-center text-[10px] text-[var(--placeholder)] mt-2">پاسخ‌ها با منابع RAG بوم تولید می‌شوند</p>
        </div>
      </div>

      {/* Session list — second in RTL so it sits on the left */}
      {sessionsOpen && <button type="button" className="sm:hidden fixed inset-0 z-20 bg-black/40" onClick={() => setSessionsOpen(false)} aria-label="بستن فهرست گفتگوها" />}
      <aside className={`fixed sm:static z-30 inset-y-0 left-0 w-[min(82vw,280px)] sm:w-[180px] flex-shrink-0 flex flex-col bg-[var(--card)] border-r border-[var(--border)] shadow-[var(--shadow-lg)] sm:shadow-none transition-transform sm:translate-x-0 sm:visible ${sessionsOpen ? "visible translate-x-0" : "invisible -translate-x-full"}`} aria-label="گفتگوها">
        <div className="flex-shrink-0 px-3 pt-12 pb-3 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <h2 className="flex-1 text-right font-bold text-sm text-[var(--text)]">گفتگوها</h2>
            <button
              type="button"
              onClick={createSession}
              className="w-8 h-8 rounded-xl bg-[#C4714A] text-white font-bold text-lg flex items-center justify-center"
              aria-label="گفتگوی جدید"
            >
              +
            </button>
          </div>
        </div>
        <div ref={tabsRef} className="flex-1 overflow-y-auto p-2 space-y-1.5" style={{ scrollbarWidth: "thin" }}>
          {tabs.map(s => {
            const selected = s.id === activeId;
            return (
              <div key={s.id} className="relative group">
                <button
                  type="button"
                  aria-current={selected ? "true" : undefined}
                  onClick={() => switchSession(s.id)}
                  className={`w-full flex items-center gap-1.5 pe-7 ps-2.5 py-2.5 rounded-xl text-[11px] font-medium text-right border ${
                    selected
                      ? "bg-[#C4714A] text-white border-[#C4714A]"
                      : "bg-[#F5F0EA] text-[var(--text)] border-[#E5DDD4] hover:bg-[#EFE8E0]"
                  }`}
                >
                  {s.pending && (
                    <span className={`w-1.5 h-1.5 rounded-full animate-pulse flex-shrink-0 ${selected ? "bg-[var(--card)]" : "bg-[#C4714A]"}`} />
                  )}
                  <span className="truncate flex-1">{s.name}</span>
                </button>
                <button
                  type="button"
                  onClick={() => deleteSession(s.id)}
                  className={`absolute left-1 top-1/2 -translate-y-1/2 w-5 h-5 rounded-md text-[10px] flex items-center justify-center ${
                    selected ? "text-white/80 hover:bg-[var(--card)]/15" : "text-[var(--muted-2)] hover:bg-[#F8E8E4] hover:text-[#C45A4A]"
                  }`}
                  aria-label={`حذف ${s.name}`}
                  title="حذف گفتگو"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
      </aside>
    </div>
  );
}

