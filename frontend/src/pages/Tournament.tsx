import { useCallback, useEffect, useRef, useState } from "react";
import type { NavFn, SignupData } from "../types";
import { getMyTournament, getTournament, listTournaments, startTournamentMatch, type TournamentDetail, type TournamentMe, type TournamentPersonalMatch, type TournamentSession, type TournamentSummary } from "../tournamentApi";
import { StudySymbol } from "../components/StudySymbols";
import { KnockoutBracket, LeagueDiagram, MyTournamentMatches, Standings, TournamentHero } from "../components/tournament/TournamentViews";
import TournamentGame from "../components/tournament/TournamentGame";
import { eventDate, faNumber } from "../components/tournament/format";
import "../tournament.css";

const readToken = () => typeof localStorage === "undefined" ? null : localStorage.getItem("boom-token");
const message = (failure: unknown) => failure instanceof Error ? failure.message : "دریافت اطلاعات تورنومنت انجام نشد؛ دوباره تلاش کن.";
type Tab = "standings" | "league" | "knockout";
const TABS: { key: Tab; label: string; number: string }[] = [{ key: "standings", label: "جدول و قوانین", number: "۰۱" }, { key: "league", label: "مسیر لیگ", number: "۰۲" }, { key: "knockout", label: "مرحلهٔ حذفی", number: "۰۳" }];

export function TournamentContent({ event, me, authenticated, personalLoading, personalError, startingId, onStart, onLogin, onRetry }: {
  event: TournamentDetail | null; me: TournamentMe | null; authenticated: boolean; personalLoading?: boolean; personalError?: string;
  startingId?: string | null; onStart: (match: TournamentPersonalMatch) => void; onLogin: () => void; onRetry: () => void;
}) {
  const [tab, setTab] = useState<Tab>("standings");
  return <>
    <TournamentHero event={event} />
    {event?.schedule_note && <p className="tn-notice" role="status">{event.schedule_note}</p>}
    {event?.tie_reason && <p className="tn-notice" role="status">{event.tie_reason}</p>}
    {!event && <div className="tn-preparation" role="status"><StudySymbol kind="discrete" size={23} /><div><strong>پیش‌نمایش ساختار تورنومنت</strong><p>هنوز تورنومنتی برای نمایش اعلام نشده است. جدول، دورهای لیگ و مسیر حذفی آماده‌اند؛ نام‌ها و نتیجه‌ها بعد از آماده‌سازی واقعی اضافه می‌شوند.</p></div></div>}
    <div className="tn-stat-strip"><div><span>{event ? "شرکت‌کنندگان" : "ظرفیت پیشنهادی"}</span><strong>{event ? `${faNumber(event.participant_count)} / ${faNumber(event.capacity)}` : "۳۲ نفر"}</strong></div><div><span>بازی‌های هر نفر در لیگ</span><strong>{faNumber(event?.league_rounds || 5)} دور</strong></div><div><span>{event ? "زمان هر بازی" : "زمان پیشنهادی هر بازی"}</span><strong>{faNumber(event?.duration_minutes || 15)} دقیقه</strong></div><div><span>آغاز رقابت · وقت تهران</span><strong className="tn-stat-date">{eventDate(event?.starts_at)}</strong></div></div>
    <div className={`tn-main-layout ${tab === "knockout" ? "tn-bracket-layout" : ""}`}><div className="tn-main-column"><nav className="tn-view-tabs" aria-label="بخش‌های تورنومنت">{TABS.map(item => <button key={item.key} type="button" aria-pressed={tab === item.key} className={tab === item.key ? "tn-view-active" : undefined} onClick={() => setTab(item.key)}><span>{item.number}</span>{item.label}</button>)}</nav>
      {tab === "standings" ? <Standings rows={event?.standings || []} myPlayerId={me?.player_id} playoffSize={event?.playoff_size || 8} attendanceGraceMinutes={event?.attendance_grace_minutes ?? 3} /> : tab === "league" ? <LeagueDiagram key={event?.id || "preview"} rounds={event?.rounds || []} leagueRounds={event?.league_rounds || 5} capacity={event?.capacity || 32} /> : <KnockoutBracket rounds={event?.rounds || []} awaitingTiebreak={event?.status === "awaiting_tiebreak"} playoffSize={event?.playoff_size || 8} />}
    </div><aside className="tn-side-column"><MyTournamentMatches matches={me?.matches || []} playerId={me?.player_id || null} authenticated={authenticated} loading={personalLoading} error={personalError} startingId={startingId} onStart={onStart} onLogin={onLogin} onRetry={onRetry} /><div className="tn-format-note"><StudySymbol kind="award" size={22} /><h3>از لیگ تا سکو</h3><p>در لیگ با یک باخت حذف نمی‌شوی. نفرات صعودکننده در مرحلهٔ حذفی برای رسیدن به فینال بازی می‌کنند.</p><span>لیگ سوئیسی ← حذفی ← فینال</span></div></aside></div>
  </>;
}

export default function Tournament({ nav }: { nav: NavFn; userData?: SignupData | null; isAdmin?: boolean }) {
  const [items, setItems] = useState<TournamentSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [event, setEvent] = useState<TournamentDetail | null>(null);
  const [me, setMe] = useState<TournamentMe | null>(null);
  const [token, setToken] = useState(readToken);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [personalLoading, setPersonalLoading] = useState(false);
  const [error, setError] = useState("");
  const [personalError, setPersonalError] = useState("");
  const [revision, setRevision] = useState(0);
  const [startingId, setStartingId] = useState<string | null>(null);
  const [session, setSession] = useState<TournamentSession | null>(null);
  const startRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const refreshIdentity = () => setToken(readToken());
    window.addEventListener("storage", refreshIdentity);
    window.addEventListener("focus", refreshIdentity);
    return () => { window.removeEventListener("storage", refreshIdentity); window.removeEventListener("focus", refreshIdentity); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    void listTournaments(controller.signal).then(response => {
      if (controller.signal.aborted) return;
      setItems(response.items);
      setSelected(previous => response.items.some(item => item.id === previous) ? previous : response.items[0]?.id || null);
    }).catch(failure => { if (!controller.signal.aborted) setError(message(failure)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    startRequest.current?.abort(); setStartingId(null); setSession(null); setMe(null); setPersonalError("");
    if (!selected) { setEvent(null); setDetailLoading(false); return; }
    const controller = new AbortController();
    let running = false;
    setEvent(null); setPersonalLoading(!!token); setDetailLoading(true);
    const refresh = async () => {
      if (running) return;
      running = true;
      const [publicResult, personalResult] = await Promise.allSettled([
        getTournament(selected, controller.signal),
        token ? getMyTournament(selected, controller.signal) : Promise.resolve(null),
      ]);
      running = false;
      if (controller.signal.aborted) return;
      setDetailLoading(false);
      if (publicResult.status === "fulfilled") { setEvent(publicResult.value); setError(""); }
      else setError(message(publicResult.reason));
      if (readToken() === token) {
        if (personalResult.status === "fulfilled") { setMe(personalResult.value); setPersonalError(""); }
        else { setMe(null); setPersonalError(message(personalResult.reason)); }
        setPersonalLoading(false);
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 20000);
    return () => { controller.abort(); window.clearInterval(timer); startRequest.current?.abort(); };
  }, [selected, token, revision]);

  useEffect(() => () => startRequest.current?.abort(), []);
  const reload = useCallback(() => setRevision(value => value + 1), []);
  const start = async (match: TournamentPersonalMatch) => {
    if (!selected || !token || startingId || !(match.can_start || match.can_resume)) return;
    const controller = new AbortController(); startRequest.current = controller; setStartingId(match.id); setPersonalError("");
    try {
      const response = await startTournamentMatch(selected, match.id, controller.signal);
      if (!controller.signal.aborted && readToken() === token) setSession(response);
    } catch (failure) { if (!controller.signal.aborted && readToken() === token) setPersonalError(message(failure)); }
    finally { if (!controller.signal.aborted) setStartingId(null); }
  };
  const leaveGame = () => { setSession(null); reload(); };

  if (session) return <div className="tournament-page"><TournamentGame key={`${session.tournament_id}:${session.match_id}`} session={session} onBack={leaveGame} onRecorded={() => { /* Public data is refreshed when the player returns. */ }} /></div>;
  return <div className="tournament-page">
    <div className="tn-topline"><span>کولوسئوم / تورنومنت</span><button type="button" onClick={reload} disabled={loading} aria-label="به‌روزرسانی اطلاعات تورنومنت"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5M5.5 8a7 7 0 0 1 11.6-3L20 8M4 16l2.9 3A7 7 0 0 0 18.5 16" /></svg>به‌روزرسانی</button></div>
    {items.length > 1 && <label className="tn-event-picker">انتخاب تورنومنت<select value={selected || ""} onChange={e => setSelected(Number(e.target.value))}>{items.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>}
    {event && <p className="tn-event-title">{event.title}</p>}
    {(loading || detailLoading) && <div className="tn-loading" role="status"><span />در حال دریافت تورنومنت‌ها…</div>}
    {error && <div className="tn-inline-error tn-public-error" role="alert"><p>{error}</p><button type="button" onClick={reload}>دوباره تلاش کن</button></div>}
    {event || (!loading && !error && !selected) ? <TournamentContent event={event} me={me} authenticated={!!token} personalLoading={personalLoading} personalError={personalError} startingId={startingId} onStart={match => void start(match)} onLogin={() => nav("login")} onRetry={reload} /> : <TournamentHero event={null} />}
  </div>;
}
