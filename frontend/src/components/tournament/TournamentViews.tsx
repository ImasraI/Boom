import { useState } from "react";
import type { TournamentDetail, TournamentMatch, TournamentPersonalMatch, TournamentRound, TournamentStanding } from "../../tournamentApi";
import { StudySymbol } from "../StudySymbols";
import { eventDate, eventStatus, faNumber, faPercent } from "./format";

export function TournamentRules({ attendanceGraceMinutes = 3 }: { attendanceGraceMinutes?: number }) {
  return <section className="tn-rules" aria-labelledby="tournament-rules-title">
    <div className="tn-section-heading"><StudySymbol kind="document" size={19} /><h3 id="tournament-rules-title">قوانین لیگ و ترتیب هم‌امتیازی</h3></div>
    <ol>
      <li><strong>امتیاز هر بازی:</strong> برد ۳ امتیاز، مساوی ۱ امتیاز و باخت صفر. امتیاز تورنومنت مستقل از ریتینگ دائمی کولوسئوم است.</li>
      <li><strong>حریف هر دور:</strong> در لیگ سوئیسی، حریف‌ها تا حد امکان هم‌امتیازند و در مرحلهٔ لیگ دوباره با یکدیگر بازی نمی‌کنند.</li>
      <li><strong>ترتیب جدول:</strong> ابتدا امتیاز لیگ، سپس مجموع امتیاز حریفان و بعد مجموع درصد دورها. قدرت حریفان با پایان هر دور به‌روز می‌شود؛ مجموع درصدها ممکن است از ۱۰۰ بیشتر شود.</li>
      <li><strong>تساوی تعیین‌کننده:</strong> اگر تساوی بر صعود یا نتیجهٔ مرحلهٔ حذفی اثر بگذارد، نتیجه تا رفع تساوی نهایی نمی‌شود؛ سرعت پاسخ‌دادن به‌تنهایی تعیین‌کننده نیست.</li>
      <li><strong>زمان و سؤال مشترک:</strong> مهلت رسمی هر دور به وقت تهران نمایش داده می‌شود. شروع بازی، زمان باقی‌مانده و ثبت نتیجه را سرور کنترل می‌کند.</li>
      <li><strong>غیبت و پایان مهلت:</strong> حداکثر تا {faNumber(attendanceGraceMinutes)} دقیقه پس از زمان رسمی وارد بازی شو. در صورت غیبت حریف، بازیکن حاضر برنده است، حتی با درصد منفی؛ غیبت هر دو نفر برای هر دو صفر امتیاز دارد. برای هر غیبت، مقدار منفی ۱۰۰ در معیار «مجموع درصد دورها» ثبت می‌شود؛ این جریمه، نمرهٔ علمی نیست. مشکل فنی را به برگزارکننده اطلاع بده.</li>
      <li><strong>بازی منصفانه:</strong> هر نفر فقط با حساب خودش و بدون کمک دیگران یا ابزار پاسخ‌گو بازی کند. سؤال و پاسخ را تا پایان دور منتشر نکن؛ نتیجهٔ مورد اختلاف باید توسط برگزارکننده بررسی شود.</li>
    </ol>
    <p className="tn-footnote">ثبت‌نام این بخش هنوز باز نشده است؛ این صفحه در حال حاضر پرداخت یا ثبت درخواست شرکت انجام نمی‌دهد.</p>
  </section>;
}

export function Standings({ rows, myPlayerId, playoffSize = 8, attendanceGraceMinutes = 3 }: { rows: TournamentStanding[]; myPlayerId?: number | null; playoffSize?: number; attendanceGraceMinutes?: number }) {
  return <>
    <section className="tn-standings" aria-labelledby="standings-title">
      <div className="tn-section-heading"><div><span className="tn-eyebrow">LEAGUE STANDINGS</span><h2 id="standings-title">جدول امتیازات لیگ</h2></div><span className="tn-small-label">برد ۳ · مساوی ۱ · باخت ۰</span></div>
      <div className="tn-table-scroll" tabIndex={0} role="region" aria-label="جدول امتیازات؛ برای دیدن همهٔ ستون‌ها افقی حرکت کن">
        <table className="tn-table">
          <caption className="tn-sr-only">رتبه‌بندی لیگ بر اساس امتیاز، قدرت حریفان و درصد تجمیعی</caption>
          <thead><tr><th scope="col">رتبه</th><th scope="col">بازیکن</th><th scope="col">بازی</th><th scope="col">برد</th><th scope="col">مساوی</th><th scope="col">باخت</th><th scope="col">امتیاز</th><th scope="col">امتیاز حریفان</th><th scope="col">مجموع درصد دورها</th></tr></thead>
          <tbody>{rows.length ? rows.map(row => <tr key={row.player_id} className={row.player_id === myPlayerId ? "tn-my-standing" : undefined}>
            <td><span className={`tn-rank ${row.rank <= playoffSize ? "tn-rank-qualified" : ""}`}>{faNumber(row.rank)}</span></td>
            <th scope="row"><span>{row.name}</span>{row.player_id === myPlayerId && <small>شما</small>}{row.tied && <small className="tn-tied">هم‌امتیاز</small>}</th>
            <td>{faNumber(row.played)}</td><td>{faNumber(row.wins)}</td><td>{faNumber(row.draws)}</td><td>{faNumber(row.losses)}</td>
            <td className="tn-points">{faNumber(row.points)}</td><td>{faNumber(row.buchholz)}</td><td>{faPercent(row.score_percent)}</td>
          </tr>) : <tr><td colSpan={9}><div className="tn-empty-table"><StudySymbol kind="statistics" size={33} /><strong>جدول هنوز بازیکنی ندارد</strong><p>پس از مشخص شدن شرکت‌کنندگان، نام‌ها و امتیازهای واقعی اینجا نمایش داده می‌شوند.</p></div></td></tr>}</tbody>
        </table>
      </div>
      {rows.length > 0 && <p className="tn-footnote">نشان رتبه‌های اول، محدودهٔ مرحلهٔ حذفی را مشخص می‌کند؛ صعودهای هم‌امتیاز تا تعیین تکلیف نهایی قطعی نیستند.</p>}
    </section>
    <TournamentRules attendanceGraceMinutes={attendanceGraceMinutes} />
  </>;
}

export function MatchCard({ match, fallbackA = "در انتظار تعیین بازیکن", fallbackB = "در انتظار تعیین بازیکن", compact = false }: {
  match?: TournamentMatch; fallbackA?: string; fallbackB?: string; compact?: boolean;
}) {
  return <article className={`tn-match ${compact ? "tn-match-compact" : ""} ${match?.status === "completed" ? "tn-match-complete" : ""}`}>
    <div className="tn-match-meta"><span>{match ? `بازی ${faNumber(match.slot)}` : "مسیر صعود"}</span><span>{match ? eventStatus(match.status) : "حریف‌ها هنوز مشخص نیستند"}</span></div>
    {[{ player: match?.player_a, score: match?.score_a, fallback: fallbackA }, { player: match?.player_b, score: match?.score_b, fallback: fallbackB }].map((row, index) =>
      <div key={index} className={`tn-match-player ${row.player && row.player.id === match?.winner_id ? "tn-match-winner" : ""}`}>
        <span className={`tn-player-dot ${!row.player ? "tn-player-pending" : ""}`} aria-hidden="true">{row.player ? row.player.name.slice(0, 1) : "—"}</span>
        <span className="tn-player-name">{row.player?.name || row.fallback}</span><strong>{faPercent(row.score)}</strong>
      </div>)}
  </article>;
}

export function LeagueDiagram({ rounds, leagueRounds = 5, capacity = 32 }: { rounds: TournamentRound[]; leagueRounds?: number; capacity?: number }) {
  const league = rounds.filter(round => round.stage === "league");
  const [selected, setSelected] = useState(() => Math.max(0, league.findIndex(round => ["active", "live", "playing"].includes(round.status))));
  const count = Math.max(leagueRounds, league.length);
  const current = league[Math.min(selected, Math.max(0, count - 1))];
  return <section className="tn-league-diagram" aria-labelledby="league-diagram-title">
    <div className="tn-section-heading"><div><span className="tn-eyebrow">THE LEAGUE PATH</span><h2 id="league-diagram-title">مسیر دورهای لیگ</h2></div><span className="tn-small-label">هر دور، یک قدم نزدیک‌تر</span></div>
    <p className="tn-section-intro">یک دور را انتخاب کن تا بازی‌ها و نتیجه‌های همان دور را ببینی. حریف دور بعد بر اساس نتیجهٔ دورهای قبلی مشخص می‌شود.</p>
    <div className="tn-round-track" role="tablist" aria-label="انتخاب دور لیگ">{Array.from({ length: count }, (_, i) => {
      const round = league[i];
      return <button key={round?.id || i} type="button" role="tab" aria-selected={selected === i} aria-controls="league-round-panel" id={`league-round-tab-${i}`} onClick={() => setSelected(i)} className={`tn-round-stop ${selected === i ? "tn-round-selected" : ""}`}>
        <span className="tn-round-node">{faNumber(i + 1)}</span><strong>دور {faNumber(i + 1)}</strong><small>{round ? eventStatus(round.status) : "در انتظار قرعه"}</small>
      </button>;
    })}</div>
    <div id="league-round-panel" role="tabpanel" aria-labelledby={`league-round-tab-${selected}`} className="tn-round-panel">
      <div className="tn-round-heading"><h3>{current?.label || `بازی‌های دور ${faNumber(selected + 1)}`}</h3><span>{current ? `${eventDate(current.starts_at)}${current.question_count ? ` · ${faNumber(current.question_count)} سؤال` : ""}` : `${faNumber(Math.floor(capacity / 2))} بازی در ساختار کامل ${faNumber(capacity)}نفره`}</span></div>
      {current?.matches.length ? <div className="tn-match-grid">{current.matches.map(match => <MatchCard key={match.id} match={match} />)}</div> : <div className="tn-unpaired"><StudySymbol kind="discrete" size={32} /><strong>حریف‌های این دور هنوز مشخص نشده‌اند</strong><p>{league.length ? "پس از تکمیل نتیجه‌ها، جفت‌سازی این دور از سمت برگزارکننده انجام می‌شود." : "این نمای ساختار لیگ است؛ هنوز شرکت‌کننده و مسابقه‌ای برای نمایش ثبت نشده است."}</p><div className="tn-unpaired-slots" aria-hidden="true"><i /><span>در انتظار جفت‌سازی</span><i /></div></div>}
    </div>
  </section>;
}

export function KnockoutBracket({ rounds, awaitingTiebreak = false, playoffSize = 8 }: { rounds: TournamentRound[]; awaitingTiebreak?: boolean; playoffSize?: number }) {
  const quarter = rounds.find(round => round.stage === "quarterfinal");
  const semi = rounds.find(round => round.stage === "semifinal");
  const final = rounds.find(round => round.stage === "final");
  const bronze = rounds.find(round => round.stage === "third_place");
  const seedPairs = [[1, 8], [4, 5], [2, 7], [3, 6]];
  const matchAt = (round: TournamentRound | undefined, index: number) => round?.matches[index];
  const four = playoffSize === 4;
  return <section className="tn-knockout" aria-labelledby="knockout-title">
    <div className="tn-section-heading"><div><span className="tn-eyebrow">ROAD TO THE FINAL</span><h2 id="knockout-title">نمودار مرحلهٔ حذفی</h2></div><StudySymbol kind="award" size={28} /></div>
    <p className="tn-section-intro">{four ? "چهار نفر، دو مرحله تا قهرمانی." : "هشت نفر، سه مرحله تا قهرمانی."} هر اتصال، مسیر برندهٔ بازی قبلی است؛ بازنده‌های نیمه‌نهایی برای رتبهٔ سوم بازی می‌کنند.</p>
    {awaitingTiebreak && <div className="tn-notice" role="status">ترتیب صعود در انتظار رفع تساوی است؛ جایگاه‌های مرحلهٔ حذفی هنوز نهایی نیستند.</div>}
    <div className="tn-bracket-scroll" tabIndex={0} role="region" aria-label={`نمودار حذفی ${four ? "چهار" : "هشت"}نفره؛ در صفحهٔ کوچک افقی حرکت کن`}>
      <div className={`tn-bracket ${four ? "tn-bracket-four" : ""}`} dir="ltr">
        <svg className="tn-bracket-lines" viewBox={`0 0 ${four ? 556 : 850} 628`} preserveAspectRatio="none" aria-hidden="true"><g fill="none" stroke="currentColor" strokeWidth="1.5">
          {four ? <path d="M240 158H267V302H294M240 446H267V302" /> : <><path d="M240 86H267V158H294M240 230H267V158M240 374H267V446H294M240 518H267V446" /><path d="M534 158H563V302H590M534 446H563V302" /></>}
        </g></svg>
        {!four && <div className="tn-bracket-column tn-bracket-quarter" dir="rtl"><h3>یک‌چهارم نهایی</h3>{seedPairs.map((pair, index) => <div key={index} className={`tn-bracket-slot tn-qf-${index}`}><MatchCard compact match={matchAt(quarter, index)} fallbackA={`رتبهٔ ${faNumber(pair[0])} لیگ`} fallbackB={`رتبهٔ ${faNumber(pair[1])} لیگ`} /></div>)}</div>}
        <div className="tn-bracket-column tn-bracket-semi" dir="rtl"><h3>نیمه‌نهایی</h3>{[0, 1].map(index => <div key={index} className={`tn-bracket-slot tn-sf-${index}`}><MatchCard compact match={matchAt(semi, index)} fallbackA={four ? `رتبهٔ ${faNumber(index + 1)} لیگ` : `برندهٔ یک‌چهارم ${faNumber(index * 2 + 1)}`} fallbackB={four ? `رتبهٔ ${faNumber(4 - index)} لیگ` : `برندهٔ یک‌چهارم ${faNumber(index * 2 + 2)}`} /></div>)}</div>
        <div className="tn-bracket-column tn-bracket-final" dir="rtl"><h3>فینال</h3><div className="tn-bracket-slot tn-final-slot"><div className="tn-final-mark"><StudySymbol kind="award" size={30} /><span>مسیر قهرمانی</span></div><MatchCard compact match={matchAt(final, 0)} fallbackA="برندهٔ نیمه‌نهایی اول" fallbackB="برندهٔ نیمه‌نهایی دوم" /></div><div className="tn-bracket-slot tn-bronze-slot"><h4>رده‌بندی · جایگاه سوم</h4><MatchCard compact match={matchAt(bronze, 0)} fallbackA="بازندهٔ نیمه‌نهایی اول" fallbackB="بازندهٔ نیمه‌نهایی دوم" /></div></div>
      </div>
    </div>
    <p className="tn-footnote">در موبایل، نمودار را افقی حرکت بده تا همهٔ مرحله‌ها دیده شوند. جایگاه‌های خالی، نتیجه یا شرکت‌کنندهٔ ساختگی نیستند.</p>
  </section>;
}

export function MyTournamentMatches({ matches, playerId, authenticated, loading = false, error = "", startingId, onStart, onLogin, onRetry }: {
  matches: TournamentPersonalMatch[]; playerId: number | null; authenticated: boolean; loading?: boolean; error?: string;
  startingId?: string | null; onStart: (match: TournamentPersonalMatch) => void; onLogin: () => void; onRetry: () => void;
}) {
  const group = (match: TournamentPersonalMatch) => match.can_start || match.can_resume ? 0
    : match.has_submitted || ["completed", "forfeit", "bye"].includes(match.status) ? 2 : 1;
  const orderedMatches = [...matches].sort((a, b) => group(a) - group(b)
    || (group(a) === 2 ? -1 : 1) * ((Date.parse(a.starts_at || "") || 0) - (Date.parse(b.starts_at || "") || 0)));
  return <section className="tn-my-matches" aria-labelledby="my-tournament-title">
    <div className="tn-section-heading"><div><span className="tn-eyebrow">YOUR MATCH DESK</span><h2 id="my-tournament-title">بازی‌های من</h2></div><StudySymbol kind="plan" size={23} /></div>
    {loading ? <p role="status" className="tn-muted-block">در حال دریافت برنامهٔ بازی‌ها…</p> : error ? <div className="tn-inline-error" role="alert"><p>{error}</p><button type="button" onClick={onRetry}>دوباره تلاش کن</button></div> : !authenticated ? <div className="tn-muted-block"><p>جدول و نمودارها برای همه باز است. برای دیدن بازی‌های خودت وارد حساب شو.</p><button type="button" className="tn-button tn-button-secondary" onClick={onLogin}>ورود به حساب</button></div> : !playerId ? <div className="tn-muted-block"><p>هنوز در فهرست شرکت‌کنندگان این تورنومنت نیستی.</p><small>ثبت‌نام به‌زودی اعلام می‌شود؛ فعلاً می‌توانی مسیر مسابقات را دنبال کنی.</small></div> : !matches.length ? <div className="tn-muted-block"><p>هنوز بازی‌ای برای تو تعیین نشده است.</p><small>پس از جفت‌سازی، حریف و زمان بازی در همین پنل می‌آیند.</small></div> : <div className="tn-my-list">{orderedMatches.map(match => {
      const opponent = match.player_a?.id === playerId ? match.player_b : match.player_a;
      const mayPlay = match.can_start || match.can_resume;
      return <article key={match.id} className={`tn-my-match ${mayPlay ? "tn-my-match-ready" : ""}`}>
        <div className="tn-my-match-head"><span>{mayPlay ? match.can_resume ? "در حال بازی" : "آمادهٔ شروع" : eventStatus(match.status)}</span><span>بازی {faNumber(match.slot)}</span></div>
        <strong>{opponent ? `تو و ${opponent.name}` : "در انتظار تعیین حریف"}</strong>
        {match.starts_at && <p>شروع بازی: {eventDate(match.starts_at)}</p>}
        {match.deadline_at && <p>پایان مهلت: {eventDate(match.deadline_at)}</p>}
        {match.reason && <p className="tn-match-reason">{match.reason}</p>}
        <button type="button" className={`tn-button ${mayPlay ? "tn-button-primary" : "tn-button-secondary"}`} disabled={!mayPlay || !!startingId} onClick={() => onStart(match)} aria-label={`${match.can_resume ? "ادامهٔ" : "شروع"} بازی با ${opponent?.name || "حریف تعیین‌شده"}`}>
          {startingId === match.id ? "در حال آماده‌سازی…" : match.has_submitted ? "پاسخ‌ها ثبت شده‌اند" : match.can_resume ? "ادامهٔ بازی" : match.can_start ? "شروع بازی" : "بازی هنوز باز نیست"}
          {mayPlay && <span aria-hidden="true">←</span>}
        </button>
      </article>;
    })}</div>}
    <div className="tn-my-note"><span aria-hidden="true" /><p>فقط بازی تعیین‌شده برای حساب تو، در زمان رسمی قابل شروع است. همهٔ زمان‌ها به وقت تهران‌اند.</p></div>
  </section>;
}

export function TournamentHero({ event }: { event: TournamentDetail | null }) {
  return <header className="tn-hero">
    <div className="tn-hero-copy"><span className="tn-eyebrow">COLOSSEUM TOURNAMENT</span><div className="tn-hero-title"><StudySymbol kind="award" size={34} /><h1>تورنومنت</h1></div>
      <p className="tn-hero-lead"><span className="tn-hero-preface">چند دور رقابت.<br /></span><em>یک مسیر تا قهرمانی.</em></p>
      <p className="tn-hero-description">{event?.description || "لیگ علمی کولوسئوم؛ بازی‌های مشخص، جدول شفاف و فرصت دوباره برای پیشرفت در هر دور."}</p>
      <div className="tn-hero-tags"><span>{event ? eventStatus(event.status) : "در حال آماده‌سازی فصل اول"}</span>{event?.major && <span>{event.major} · {event.grade}</span>}</div>
    </div>
    <div className="tn-hero-side"><div className="tn-format-map" aria-label="ساختار تورنومنت"><div><strong>{faNumber(event?.league_rounds || 5)}</strong><span>دور لیگ</span></div><i aria-hidden="true" /><div><strong>{faNumber(event?.playoff_size || 8)}</strong><span>نفر در حذفی</span></div><i aria-hidden="true" /><div className="tn-format-champion"><StudySymbol kind="award" size={33} /><span>قهرمان</span></div></div>
      <div className="tn-register"><div><strong>همراه رقابت بعدی باش</strong><p>زمان و شرایط ثبت‌نام بعداً اعلام می‌شود.</p></div><button type="button" className="tn-button tn-button-primary" disabled>ثبت‌نام به‌زودی</button></div>
    </div>
  </header>;
}
