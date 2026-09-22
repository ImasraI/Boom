import { useState, useRef, useEffect } from "react";
import { apiUrl, authHeaders } from "../api";
import { NavFn, SignupData } from "../types";
import { weeklyScheduleContext, loadWeekBlocks, saveWeekBlocks, getWeekISO, StoredBlock } from "../scheduleStore";

interface Msg { role: "user" | "ai"; text: string; }
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
    const raw = localStorage.getItem(storageKey(userData));
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
  localStorage.setItem(storageKey(userData), JSON.stringify(s));
}

function loadActiveId(userData: SignupData | null, sessions: Record<string, ChatSession>) {
  try {
    const saved = localStorage.getItem(activeStorageKey(userData));
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

// Very small markdown renderer covering what the AI model actually sends:
// **bold**, "# / ## " headings, "* / -" bullets and "1." numbered lists.
// Avoids pulling in a full markdown library for a handful of patterns.
function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(p => p !== "");
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={`${keyPrefix}-${i}`} className="font-bold">{part.slice(2, -2)}</strong>;
    }
    return <span key={`${keyPrefix}-${i}`}>{part}</span>;
  });
}

function renderMarkdown(text: string): React.ReactNode {
  const lines = text.split("\n");
  let inCodeBlock = false;
  let codeBlockLines: string[] = [];
  let lang = "";

  return lines.map((rawLine, i) => {
    const line = rawLine.trim();

    if (line.startsWith("```")) {
      if (inCodeBlock) {
        // End code block
        inCodeBlock = false;
        const result = (
          <pre key={i} className="bg-[var(--surface-2)] p-3 rounded-xl overflow-x-auto text-[12px] font-mono mt-2 mb-2 border border-[var(--border)]">
            <code>{codeBlockLines.join("\n")}</code>
          </pre>
        );
        codeBlockLines = [];
        return result;
      } else {
        // Start code block
        inCodeBlock = true;
        lang = line.slice(3).trim();
        return null;
      }
    }

    if (inCodeBlock) {
      codeBlockLines.push(rawLine);
      return null;
    }

    if (!line) return <div key={i} className="h-2" />;

    const heading = line.match(/^#{1,6}\s+(.*)$/);
    if (heading) {
      return (
        <div key={i} className="font-bold text-[14px] mt-1 mb-1">
          {renderInline(heading[1], `h${i}`)}
        </div>
      );
    }

    const bullet = line.match(/^[*-]\s+(.*)$/);
    if (bullet) {
      return (
        <div key={i} className="flex gap-1.5 items-start">
          <span className="text-[var(--accent)] mt-0.5 flex-shrink-0">•</span>
          <span className="min-w-0 break-words [overflow-wrap:anywhere]">{renderInline(bullet[1], `b${i}`)}</span>
        </div>
      );
    }

    const numbered = line.match(/^(\d+)[.)]\s+(.*)$/);
    if (numbered) {
      return (
        <div key={i} className="flex gap-1.5 items-start">
          <span className="text-[var(--muted-2)] font-bold flex-shrink-0">{numbered[1]}.</span>
          <span className="min-w-0 break-words [overflow-wrap:anywhere]">{renderInline(numbered[2], `n${i}`)}</span>
        </div>
      );
    }

    return <div key={i} className="break-words [overflow-wrap:anywhere]">{renderInline(line, `p${i}`)}</div>;
  });
}

export default function Chat({ nav, userData }: { nav: NavFn; userData: SignupData | null }) {
  const name = userData?.name ?? "دانشآموز";
  const storeKey = storageKey(userData);
  const [sessions, setSessions] = useState<Record<string, ChatSession>>({});
  const [activeId, setActiveId] = useState("");
  const [input, setInput] = useState("");
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
    localStorage.setItem(activeStorageKey(userData), activeId);
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

    fetch(apiUrl(endpoint), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    })
      .then(r => r.json())
.then(data => {
        // Handle plan update if present
        if (data.plan_update) {
          const weekISO = getWeekISO();
          let currentBlocks = loadWeekBlocks(weekISO) || [];
          
          // Handle removed blocks (delete)
          if (data.plan_update.removed && data.plan_update.removed.length > 0) {
            const removedBlocks = data.plan_update.removed;
            currentBlocks = currentBlocks.filter((existingBlock: StoredBlock) => {
              return !data.plan_update.removed.some((removedBlock: StoredBlock) =>
                existingBlock.day === removedBlock.day &&
                existingBlock.startHour === removedBlock.startHour &&
                existingBlock.title === removedBlock.title
              );
            });
            saveWeekBlocks(weekISO, currentBlocks);
          }
          
          // Handle added/updated blocks
          if (data.plan_update.blocks && data.plan_update.blocks.length > 0) {
            const newBlocks = data.plan_update.blocks;
            currentBlocks = loadWeekBlocks(weekISO) || [];
            
            const mergedBlocks = [...currentBlocks];
            newBlocks.forEach((newBlock: StoredBlock) => {
              const idx = mergedBlocks.findIndex(b => 
                b.day === newBlock.day && 
                b.startHour === newBlock.startHour && 
                b.duration === newBlock.duration && 
                b.title === newBlock.title
              );
              if (idx >= 0) {
                mergedBlocks[idx] = { ...mergedBlocks[idx], ...newBlock };
              } else {
                mergedBlocks.push(newBlock);
              }
            });
            
            saveWeekBlocks(weekISO, mergedBlocks);
          }
        }
        
        const answer = data.plan || data.answer || "پاسخی دریافت نشد.";
        const current = sessionsRef.current;
        if (!current[sessionId]) return;
        commit({
          ...current,
          [sessionId]: {
            ...current[sessionId],
            msgs: [...current[sessionId].msgs, { role: "ai", text: answer }],
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
  }

  function createSession() {
    const session = createBlank(name);
    commit({ ...sessionsRef.current, [session.id]: session });
    setActiveId(session.id);
    setInput("");
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
                  <div className="max-w-[85%] min-w-0 text-[13px] leading-relaxed text-[var(--text)] break-words [overflow-wrap:anywhere]">
                    {renderMarkdown(m.text)}
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
      <aside className="w-[148px] sm:w-[180px] flex-shrink-0 flex flex-col bg-[var(--card)] border-r border-[var(--border)]">
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

