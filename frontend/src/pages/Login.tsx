import { useState } from "react";
import { apiUrl, authHeaders, readApiError } from "../api";
import { NavFn, SignupData, normalizeSignupData } from "../types";

function BackBtn({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-10 h-10 rounded-2xl bg-[var(--border)] flex items-center justify-center text-[var(--muted)] hover:bg-[var(--border-strong)] transition-colors">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
        <path d="M19 12H5M12 5l-7 7 7 7" />
      </svg>
    </button>
  );
}

function profileForPhone(phone: string): SignupData {
  try {
    const raw = localStorage.getItem("boom-user-data");
    if (raw) {
      const saved = normalizeSignupData(JSON.parse(raw), phone);
      if (saved.phone === phone) {
        return { ...saved, name: saved.name || phone };
      }
    }
  } catch { /* ignore corrupt storage */ }
  return normalizeSignupData({ phone, name: phone }, phone);
}

export default function Login({ nav, onLogin }: { nav: NavFn; onLogin: (token: string, data: SignupData) => void }) {
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    if (!phone || !password || loading) return;
    setLoading(true);
    setError("");
    try {
      const formData = new URLSearchParams();
      formData.append("username", phone);
      formData.append("password", password);
      const res = await fetch(apiUrl("/api/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
      });
      if (!res.ok) {
        setError(await readApiError(res, "شماره یا رمز اشتباه است"));
        return;
      }
      const data = await res.json();
      const token = data.access_token as string;
      localStorage.setItem("boom-token", token);

      let profile = profileForPhone(phone);
      try {
        const meRes = await fetch(apiUrl("/api/auth/me"), { headers: { ...authHeaders(token) } });
        if (meRes.ok) {
          const me = await meRes.json();
          profile = {
            ...profile,
            phone: me.phone || phone,
            name: profile.name || me.username || phone,
          };
        }
      } catch { /* profile still usable offline */ }

      onLogin(token, profile);
    } catch {
      setError("خطا در ارتباط با سرور");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-[var(--surface)] px-6 pt-14 pb-10">
      <BackBtn onClick={() => nav("landing")} />
      <div className="mt-10">
        <p className="text-xs font-bold tracking-[0.2em] text-[var(--accent)] mb-1">خوش برگشتی</p>
        <h1 className="font-display text-4xl text-[var(--text)] leading-snug">ورود به حساب</h1>
        <p className="text-[13px] text-[var(--muted)] mt-2">شماره موبایل و رمز عبورت رو وارد کن.</p>
      </div>

      <div className="mt-10 space-y-3">
        <div className="flex items-center bg-[var(--card)] border-2 border-[var(--border-strong)] focus-within:border-[var(--accent)] rounded-2xl overflow-hidden transition-colors" dir="ltr">
          <div className="flex items-center px-4 py-4 bg-[var(--surface-2)] border-l border-[var(--border-strong)] flex-shrink-0 gap-1">
            <span className="text-[15px] font-bold text-[var(--brown-text)]">+98</span>
          </div>
          <input autoFocus type="tel" value={phone}
            onChange={e => setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))}
            placeholder="912 345 6789"
            className="flex-1 bg-transparent outline-none text-[17px] font-bold text-[var(--text)] placeholder:text-[var(--placeholder)] tracking-widest py-4 px-4 text-left" />
        </div>

        <input type="password" value={password} onChange={e => setPassword(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleSubmit()}
          placeholder="رمز عبور"
          className="w-full bg-[var(--card)] border-2 border-[var(--border-strong)] focus:border-[var(--accent)] outline-none rounded-2xl px-5 py-4 text-[17px] font-bold text-[var(--text)] placeholder:text-[var(--placeholder)] transition-colors" />
      </div>

      {error && <p className="text-red-500 text-[13px] mt-3 text-center">{error}</p>}

      <div className="mt-8">
        <button disabled={!phone || !password || loading} onClick={handleSubmit}
          className={`w-full py-4 rounded-2xl font-bold text-[15px] transition-all active:scale-95 ${
            phone && password && !loading
              ? "bg-[var(--accent)] text-[var(--surface)] hover:bg-[#A85C38] shadow-sm"
              : "bg-[var(--border-strong)] text-[#B0A898] cursor-not-allowed"
          }`}>
          {loading ? "در حال ورود..." : "ورود"}
        </button>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <div className="flex-1 h-px bg-[var(--border-strong)]" />
        <span className="text-[12px] text-[var(--muted-2)]">یا</span>
        <div className="flex-1 h-px bg-[var(--border-strong)]" />
      </div>

      <p className="mt-5 text-center text-[13px] text-[var(--muted)]">
        هنوز ثبت‌نام نکردی؟{" "}
        <button onClick={() => nav("signup")} className="text-[var(--accent)] font-bold underline underline-offset-2">ثبت‌نام</button>
      </p>
    </div>
  );
}

