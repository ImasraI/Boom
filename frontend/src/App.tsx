import { useEffect, useState } from "react";
import { apiUrl, authHeaders } from "./api";
import { Screen, SignupData, normalizeSignupData } from "./types";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Home from "./pages/Home";
import Streak from "./pages/Streak";
import Recovery from "./pages/Recovery";
import Exams from "./pages/Exams";
import Plan from "./pages/Plan";
import Chat from "./pages/Chat";
import Profile from "./pages/Profile";
import Schedule from "./pages/Schedule";
import Evaluation from "./pages/Evaluation";
import Mock from "./pages/Mock";
import Arena from "./pages/Arena";
import Admin from "./pages/Admin";

const USER_KEY = "boom-user-data";
const TOKEN_KEY = "boom-token";

const NAV_ITEMS: { screen: Screen; label: string; icon: React.ReactNode }[] = [
  { screen: "home", label: "خانه", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg> },
  { screen: "streak", label: "استریک", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C9 7 6 8 7 13c.7 3 3 5 5 5s4.3-2 5-5c1-5-2-6-5-11z"/></svg> },
  { screen: "recovery", label: "ریکاوری", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg> },
  { screen: "exams", label: "آزمونها", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg> },
   { screen: "plan", label: "برنامه", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> },
   { screen: "schedule", label: "برنامه هفتگی", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> },
   { screen: "evaluation", label: "ارزیابی", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/></svg> },
  { screen: "mock", label: "آزمون هوشمند", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> },
  { screen: "arena", label: "دوئل رنکینگ", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3h12l3 6-9 12L3 9z"/><path d="M3 9h18"/><path d="M12 21L8 9"/><path d="M12 21l4-12"/></svg> },
   { screen: "profile", label: "پروفایل", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> },
];

function persistUser(data: SignupData) {
  localStorage.setItem(USER_KEY, JSON.stringify(normalizeSignupData(data)));
}

function DesktopSidebar({ screen, nav, isAdmin }: { screen: Screen; nav: (s: Screen) => void; isAdmin: boolean }) {
  return (
    <aside className="hidden md:flex flex-col fixed top-0 right-0 bottom-0 w-[220px] bg-[var(--card)] border-r border-[var(--border)] z-30">
      <div className="px-5 pt-7 pb-5 border-b border-[var(--border)]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-[var(--accent)] flex items-center justify-center flex-shrink-0">
            <span className="text-[var(--surface)] font-display text-lg leading-none">ب</span>
          </div>
          <div>
            <p className="font-display text-2xl text-[var(--text)] leading-none">بوم</p>
            <p className="text-[10px] text-[var(--muted-2)] font-medium mt-0.5">برنامهریز کنکور</p>
          </div>
        </div>
      </div>
      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map(item => {
          const active = screen === item.screen;
          return (
            <button key={item.screen} onClick={() => nav(item.screen)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-2xl text-right transition-all ${
                active ? "bg-[var(--accent-soft)] text-[var(--accent)]" : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text-strong)]"
              }`}
            >
              <span className={active ? "text-[var(--accent)]" : "text-[var(--muted-2)]"}>{item.icon}</span>
              <span className="font-semibold text-[14px]">{item.label}</span>
              {active && <span className="me-auto w-1.5 h-1.5 rounded-full bg-[var(--accent)]" />}
            </button>
          );
        })}
        {isAdmin && (
          <button onClick={() => nav("admin")}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-2xl text-right transition-all ${
              screen === "admin" ? "bg-[var(--accent-soft)] text-[var(--accent)]" : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text-strong)]"
            }`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span className="font-semibold text-[14px]">مدیریت</span>
          </button>
        )}
      </nav>
      <div className="p-4 border-t border-[var(--border)]">
        <button onClick={() => nav("chat")}
          className="w-full py-3.5 rounded-2xl bg-[var(--text)] text-[var(--surface)] font-bold text-[13px] flex items-center justify-center gap-2 hover:bg-[var(--text-strong)] transition-colors"
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

function Shell({ children, screen, nav, isAdmin }: { children: React.ReactNode; screen: Screen; nav: (s: Screen) => void; isAdmin: boolean }) {
  const hideSidebar = ["landing", "login", "signup"].includes(screen);
  return (
    <div dir="rtl" className="min-h-screen bg-[var(--page-bg)]">
      {!hideSidebar && <DesktopSidebar screen={screen} nav={nav} isAdmin={isAdmin} />}
      <div className={`min-h-screen ${!hideSidebar ? "md:mr-[220px]" : ""}`}>
        <div className="w-full max-w-[430px] mx-auto md:max-w-none min-h-screen bg-[var(--surface)] md:shadow-none">
          {children}
        </div>
      </div>
    </div>
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
      .then(res => (res.ok ? res.json() : null))
      .then(me => setIsAdmin(Boolean(me?.is_admin)))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    const savedUser = localStorage.getItem(USER_KEY);
    if (!token || !savedUser) {
      localStorage.removeItem(USER_KEY);
      if (!token) localStorage.removeItem(TOKEN_KEY);
      return;
    }
    try {
      const profile = normalizeSignupData(JSON.parse(savedUser));
      setUserData(profile);
      setScreen("home");
    } catch {
      localStorage.removeItem(USER_KEY);
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
    localStorage.removeItem(USER_KEY);
    setUserData(null);
    nav("landing");
  }

  const p = { nav };
  const settingsProps = { dark, toggleDark, onSave: handleSaveProfile, logout };

  return (
    <Shell screen={screen} nav={nav} isAdmin={isAdmin}>
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
      {screen === "mock" && <Mock {...p} />}
      {screen === "arena" && <Arena {...p} />}
      {screen === "admin" && <Admin {...p} />}
      {screen === "profile" && userData && <Profile {...p} userData={userData} {...settingsProps} />}
    </Shell>
  );
}

