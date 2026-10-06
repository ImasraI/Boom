import { accountStorage, accountId } from "./accountStorage";
import { pullCalendar, flushCalendar } from "./calendarSync";
import { Component, lazy, Suspense, useEffect, useState } from "react";
import { apiUrl, authHeaders } from "./api";
import { pullServerProfile, toSignupData } from "./profileSync";
import { Screen, SignupData, normalizeSignupData, emptySignupData } from "./types";
import { PANELS, panelOf } from "./navConfig";
import PanelTabs from "./components/PanelTabs";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Home from "./pages/Home";
import Streak from "./pages/Streak";
import Recovery from "./pages/Recovery";
import Exams from "./pages/Exams";
import Plan from "./pages/Plan";
import Profile from "./pages/Profile";
const KnowledgeGraph = lazy(() => import("./pages/KnowledgeGraph"));
const Chat = lazy(() => import("./pages/Chat"));
const Schedule = lazy(() => import("./pages/Schedule"));
const Evaluation = lazy(() => import("./pages/Evaluation"));
const Mock = lazy(() => import("./pages/Mock"));
const Arena = lazy(() => import("./pages/Arena"));
const Admin = lazy(() => import("./pages/Admin"));

const USER_KEY = "boom-user-data";
const TOKEN_KEY = "boom-token";

const NAV_ITEMS: { screen: Screen; label: string; icon: React.ReactNode }[] = [
  { screen: "home", label: "خانه", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg> },
  { screen: "streak", label: "استریک", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C9 7 6 8 7 13c.7 3 3 5 5 5s4.3-2 5-5c1-5-2-6-5-11z"/></svg> },
  { screen: "recovery", label: "ریکاوری", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg> },
  { screen: "exams", label: "آزمونها", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg> },
  { screen: "plan", label: "برنامه", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> },
  { screen: "knowledge", label: "نقشه یادگیری", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="6" cy="6" r="2"/><circle cx="18" cy="12" r="2"/><circle cx="6" cy="18" r="2"/><path d="M8 7l8 4M8 17l8-4"/></svg> },
   { screen: "schedule", label: "برنامه هفتگی", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> },
   { screen: "evaluation", label: "ارزیابی", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/></svg> },
  { screen: "mock", label: "آزمون هوشمند", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> },
  { screen: "arena", label: "دوئل رنکینگ", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3h12l3 6-9 12L3 9z"/><path d="M3 9h18"/><path d="M12 21L8 9"/><path d="M12 21l4-12"/></svg> },
   { screen: "profile", label: "پروفایل", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> },
];

/** Icon shortcuts keyed by screen; panel rows get their labels from navConfig. */
const ICONS: Record<string, React.ReactNode> = {
  ...Object.fromEntries(NAV_ITEMS.map(item => [item.screen, item.icon])),
  leaderboard: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></svg>,
  admin: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
};

function persistUser(data: SignupData) {
  accountStorage.setItem(USER_KEY, JSON.stringify(normalizeSignupData(data)));
}

function SideButton({ screen, label, icon, current, nav }: {
  screen: Screen; label: string; icon: React.ReactNode; current: Screen; nav: (s: Screen) => void;
}) {
  const active = current === screen;
  return (
    <button aria-current={active ? "page" : undefined} onClick={() => nav(screen)}
      className={`press w-full flex items-center gap-3 px-4 py-3 rounded-2xl text-right transition-all ${
        active ? "bg-[var(--accent-soft)] text-[var(--accent)]" : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text-strong)]"
      }`}>
      <span className={active ? "text-[var(--accent)]" : "text-[var(--muted-2)]"}>{icon}</span>
      <span className="font-semibold text-[14px]">{label}</span>
      {active && <span className="me-auto w-1.5 h-1.5 rounded-full bg-[var(--accent)]" />}
    </button>
  );
}

function DesktopSidebar({ screen, nav, isAdmin }: { screen: Screen; nav: (s: Screen) => void; isAdmin: boolean }) {
  return (
    <aside className="boom-sidebar hidden md:flex flex-col fixed top-0 right-0 bottom-0 w-[220px] bg-[var(--card)] border-r border-[var(--border)] z-30">
      <div className="px-5 pt-7 pb-5 border-b border-[var(--border)]">
        <div className="flex items-center gap-3">
          <img src="/karzar-shield-detailed.png" alt="نشان سپر کارزار" className="w-10 h-10 flex-shrink-0" />
          <div>
            <p className="font-display text-2xl text-[var(--text)] leading-none">بوم</p>
            <p className="text-[10px] text-[var(--muted-2)] font-medium mt-0.5">برنامه ریز کنکور</p>
          </div>
        </div>
      </div>
      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        <SideButton screen="home" label="خانه" icon={ICONS.home} current={screen} nav={nav} />
        {(["ranked", "plan", "profile"] as const).map(key => (
          <div key={key}>
            <p className="px-4 pt-4 pb-1 text-[11px] font-bold text-[var(--muted-2)]">{PANELS[key].label}</p>
            {PANELS[key].items
              .filter(item => item.screen !== "admin" || isAdmin)
              .map(item => (
                <SideButton key={item.screen} screen={item.screen} label={item.label} icon={ICONS[item.screen]} current={screen} nav={nav} />
              ))}
          </div>
        ))}
      </nav>
      <div className="p-4 border-t border-[var(--border)]">
        <button onClick={() => nav("chat")}
          className="press w-full py-3.5 rounded-2xl bg-[var(--text)] text-[var(--surface)] font-bold text-[13px] flex items-center justify-center gap-2 hover:bg-[var(--text-strong)] transition-colors"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          گفتگو با بوم AI
        </button>
      </div>
    </aside>
  );
}

class ScreenBoundary extends Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div role="alert" className="plan-card m-5 p-6 bg-[var(--card)]"><h2>صفحه آماده نشد</h2><p className="text-sm text-[var(--muted)] mt-2">اتصال را بررسی کن و دوباره تلاش کن.</p><button className="mt-4 px-5 py-3 rounded-xl bg-[var(--accent-soft)] text-[var(--accent)]" onClick={() => window.location.reload()}>بارگذاری دوباره</button></div>;
    return this.props.children;
  }
}

function Shell({ children, screen, nav, isAdmin }: { children: React.ReactNode; screen: Screen; nav: (s: Screen) => void; isAdmin: boolean }) {
  const hideSidebar = ["landing", "login", "signup"].includes(screen);
  const panelKey = hideSidebar ? null : (panelOf(screen)?.key ?? null);
  return (
    <div dir="rtl" className="min-h-screen bg-[var(--page-bg)]">
      {!hideSidebar && <DesktopSidebar screen={screen} nav={nav} isAdmin={isAdmin} />}
      {!hideSidebar && <MobileTabBar screen={screen} nav={nav} isAdmin={isAdmin} />}
      <div className={`min-h-screen ${!hideSidebar ? "md:mr-[220px]" : ""}`}>
        <div className={`w-full max-w-[430px] mx-auto md:max-w-none min-h-screen bg-[var(--surface)] md:shadow-none ${!hideSidebar ? "pb-24 md:pb-0" : ""}`}>
          {!hideSidebar && panelKey && <PanelTabs panelKey={panelKey} screen={screen} nav={nav} isAdmin={isAdmin} />}
          <main key={screen} className={`page-scene page-${screen}`}><ScreenBoundary><Suspense fallback={<div className="page-loading" role="status" aria-label="در حال آماده‌سازی صفحه"><span>در حال آماده‌سازی…</span><i /><i /><i /></div>}>{panelKey ? <div className="panel-body">{children}</div> : children}</Suspense></ScreenBoundary></main>
        </div>
      </div>
    </div>
  );
}

const CHAT_ICON = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
);

/** Fixed bottom navigation for phones (< md). Mirrors DesktopSidebar so
 * every screen is reachable without a keyboard/mouse; the کمی tabs that
 * don't fit live in the «بیشتر» sheet. */
function MobileTabBar({ screen, nav }: { screen: Screen; nav: (s: Screen) => void; isAdmin: boolean }) {
  // 5 tabs: home, Plan, Ranked (middle), chat, Profile. Every sub-screen
  // is highlighted through its panel, so no "بیشتر" overflow is needed.
  const items: { screen: Screen; label: string; icon: React.ReactNode }[] = [
    { screen: "home", label: "خانه", icon: ICONS.home },
    { screen: "plan", label: "برنامه", icon: ICONS.plan },
    { screen: "arena", label: "آرنا", icon: ICONS.arena },
    { screen: "chat", label: "بوم AI", icon: CHAT_ICON },
    { screen: "profile", label: "پروفایل", icon: ICONS.profile },
  ];
  const activePanel = panelOf(screen)?.key ?? null;
  const isActive = (tab: Screen) =>
    screen === tab || (activePanel !== null && panelOf(tab)?.key === activePanel);

  function go(s: Screen) {
    nav(s);
  }

  return (
    <>
      <nav
        aria-label="ناوبری موبایل"
        className="md:hidden fixed bottom-0 inset-x-0 z-50 bg-[var(--card)]/95 border-t border-[var(--border)]"
        style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
      >
        <div className="flex items-stretch justify-around px-1">
          {items.map(item => {
            const active = isActive(item.screen);
            return (
              <button key={item.screen} aria-current={active ? "page" : undefined} onClick={() => go(item.screen)}
                className={`press flex-1 flex flex-col items-center gap-0.5 py-2.5 transition-colors ${
                  active ? "text-[var(--accent)]" : "text-[var(--muted-2)]"
                }`}>
                {item.icon}
                <span className="text-[10px] font-bold">{item.label}</span>
                {active && <span className="w-4 h-0.5 rounded-full bg-[var(--accent)]" />}
              </button>
            );
          })}
        </div>
      </nav>
    </>
  );
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [dark, setDark] = useState(() => { const stored = localStorage.getItem("boom-theme"); return stored ? stored === "dark" : true; });
  const [userData, setUserData] = useState<SignupData | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  // Ask the server who we are (is_admin lives server-side; the sidebar
  // entry is only cosmetic - /api/admin/* enforces it for real).
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return;
    fetch(apiUrl("/api/auth/me"), { headers: authHeaders(token) })
      .then(res => {
        if (localStorage.getItem(TOKEN_KEY) !== token) return null;
        if (res.status === 401) {
          localStorage.removeItem(TOKEN_KEY);
          accountStorage.removeItem(USER_KEY);
          setUserData(null);
          setIsAdmin(false);
          setScreen("login");
          return null;
        }
        return res.ok ? res.json() : null;
      })
      .then(me => { if (localStorage.getItem(TOKEN_KEY) === token) setIsAdmin(Boolean(me?.is_admin)); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    const savedUser = accountStorage.getItem(USER_KEY);
    if (!token) {
      accountStorage.removeItem(USER_KEY);
      if (!token) localStorage.removeItem(TOKEN_KEY);
      return;
    }
    try {
      const profile = savedUser ? normalizeSignupData(JSON.parse(savedUser)) : emptySignupData();
      setUserData(profile);
      setScreen("home");
      // Growth-readiness project 1: refresh the cache from the server so a
      // second device (or a cleared storage) converges on the same state.
      pullServerProfile().then(server => {
        if (server && localStorage.getItem(TOKEN_KEY) === token) setUserData(prev => (prev ? toSignupData(server, prev) : prev));
      });
      void flushCalendar(token).then(ok => ok && pullCalendar(token));
    } catch {
      accountStorage.removeItem(USER_KEY);
    }
  }, []);

  function toggleDark() {
    setDark(current => {
      const next = !current;
      localStorage.setItem("boom-theme", next ? "dark" : "light");
      document.documentElement.classList.toggle("dark", next);
      return next;
    });
  }

  function nav(s: Screen) {
    setScreen(s);
    window.scrollTo(0, 0);
  }

  function handleLogin(token: string, data: SignupData) {
    localStorage.setItem(TOKEN_KEY, token);
    const profile = normalizeSignupData(data);
    persistUser(profile);
    setUserData(profile);
    nav("home");
    void flushCalendar(token).then(ok => ok && pullCalendar(token));
    pullServerProfile().then(server => {
      if (server && localStorage.getItem(TOKEN_KEY) === token) {
        const refreshed = toSignupData(server, profile);
        persistUser(refreshed);
        setUserData(refreshed);
      }
    });
    fetch(apiUrl("/api/auth/me"), { headers: authHeaders(token) })
      .then(res => res.ok ? res.json() : null)
      .then(me => { if (localStorage.getItem(TOKEN_KEY) === token) setIsAdmin(Boolean(me?.is_admin)); })
      .catch(() => {});
  }

  function handleSignupComplete(data: SignupData) {
    const profile = normalizeSignupData(data);
    persistUser(profile);
    setUserData(profile);
    nav("home");
  }

  function handleUpdateProfile(data: SignupData) {
    const profile = normalizeSignupData(data);
    persistUser(profile);
    setUserData(profile);
  }

  function handleSaveProfile(data: SignupData) {
    persistUser(data);
    setUserData(data);
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setIsAdmin(false);
    setUserData(null);
    nav("landing");
  }

  const p = { nav };
  const settingsProps = { dark, toggleDark, onSave: handleSaveProfile, logout };

  return (
    <Shell key={accountId() || "anonymous"} screen={screen} nav={nav} isAdmin={isAdmin}>
      {screen === "landing" && <Landing {...p} />}
      {screen === "login" && <Login {...p} onLogin={handleLogin} />}
      {screen === "signup" && <Signup {...p} onComplete={handleSignupComplete} />}
      {screen === "home" && userData && <Home {...p} userData={userData} logout={logout} />}
      {screen === "streak" && <Streak {...p} />}
      {screen === "recovery" && <Recovery {...p} />}
      {screen === "exams" && <Exams {...p} />}
      {screen === "plan" && <Plan {...p} userData={userData} />}
      {screen === "schedule" && <Schedule {...p} userData={userData} />}
      {screen === "chat" && <Chat {...p} userData={userData} />}
      {screen === "evaluation" && <Evaluation {...p} />}
      {screen === "mock" && <Mock {...p} userData={userData} />}
      {screen === "arena" && <Arena {...p} userData={userData} />}
      {screen === "leaderboard" && <Arena {...p} userData={userData} initialPhase="board" />}
      {screen === "admin" && <Admin {...p} />}
      {screen === "profile" && userData && <Profile {...p} userData={userData} {...settingsProps} />}
      {screen === "knowledge" && userData && <KnowledgeGraph {...p} userData={userData} />}
    </Shell>
  );
}

