import { useState } from "react";
import { apiUrl, authHeaders, readApiError } from "../api";
import { NavFn, SignupData, normalizeSignupData } from "../types";
import { AuthOrbs, BackButton, ErrorBanner, PhoneInput, PasswordInput, PrimaryButton } from "../components/ui";

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
    <div className="min-h-screen flex flex-col bg-[var(--page-bg)]">
      <AuthOrbs />
      <div className="relative flex-1 flex flex-col px-5 pt-6 pb-8">
        <div className="anim-fade-in"><BackButton onClick={() => nav("landing")} /></div>

        <div className="flex-1 flex flex-col justify-center max-w-md w-full mx-auto">
          <div className="card-elevated p-7 sm:p-8 anim-fade-up shadow-float">
            <div className="flex flex-col items-center text-center">
              <img src="/logo.png" alt="لوگوی بوم" className="w-14 h-14 mb-4"
                   style={{ filter: "drop-shadow(0 6px 16px rgba(0,0,0,0.22))" }} />
              <p className="text-xs font-bold tracking-[0.2em] text-[var(--accent)] mb-1">خوش برگشتی</p>
              <h1 className="font-display text-4xl text-[var(--text)] leading-snug">ورود به حساب</h1>
              <p className="text-[13px] text-[var(--muted)] mt-2">شماره موبایل و رمز عبورت رو وارد کن.</p>
            </div>

            <div className="mt-7 space-y-3.5">
              <PhoneInput value={phone} onChange={setPhone} autoFocus />
              <PasswordInput value={password} onChange={setPassword} placeholder="رمز عبور" onEnter={handleSubmit} />
            </div>

            <ErrorBanner message={error} />

            <div className="mt-7">
              <PrimaryButton
                onClick={handleSubmit}
                disabled={!phone || !password}
                loading={loading}
                loadingText="در حال ورود..."
              >
                ورود
              </PrimaryButton>
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
        </div>
      </div>
    </div>
  );
}
