import { useId } from "react";
import type { CSSProperties } from "react";
import type { HomeTask } from "../homeTasks";
import type { NavFn, SignupData } from "../types";
import { StudySymbol } from "./StudySymbols";

const fa = (n: number) => n.toLocaleString("fa-IR");
const tones = ["var(--accent)", "var(--desk-blue)", "var(--desk-pink)", "var(--desk-gold)"];

/** The rings encode actual scheduled activities, never predicted mastery. */
export function StudyDial({ tasks }: { tasks: Pick<HomeTask, "subject" | "done" | "skipped">[] }) {
  const id = useId();
  const active = tasks.filter(t => !t.skipped);
  const done = active.filter(t => t.done).length;
  const subjects = [...new Set(active.map(t => t.subject).filter(Boolean))];
  const shown = subjects.slice(0, 3);
  const label = active.length ? `${fa(done)} از ${fa(active.length)} فعالیت امروز انجام شده` : "هنوز فعالیتی برای امروز ثبت نشده";
  return <div className="study-dial">
    <svg viewBox="0 0 320 320" role="img" aria-labelledby={`${id}-title`}>
      <title id={`${id}-title`}>{label}</title>
      <g className="dial-guides" fill="none" stroke="currentColor">
        <path d="M160 12v18m0 260v18M12 160h18m260 0h18M55 55l9 9m192 192 9 9M55 265l9-9m192-192 9-9" />
        <circle cx="160" cy="160" r="140" strokeDasharray="1 8" />
        <circle cx="160" cy="160" r="68" strokeDasharray="2 7" />
      </g>
      {(shown.length ? shown : [""]).map((subject, i) => {
        const items = active.filter(t => t.subject === subject);
        const fraction = items.length ? items.filter(t => t.done).length / items.length : 0;
        const radius = 124 - i * 17;
        return <g key={subject} fill="none" strokeWidth="5" transform="rotate(-90 160 160)">
          <circle cx="160" cy="160" r={radius} stroke="var(--border)" />
          <circle className="dial-progress" cx="160" cy="160" r={radius} stroke={tones[i]} strokeLinecap="round"
            pathLength="100" strokeDasharray={`${fraction * 100} 100`} />
        </g>;
      })}
      <text x="160" y="158" textAnchor="middle" className="dial-number">{active.length ? fa(Math.round(done / active.length * 100)) : "—"}<tspan className="dial-percent">{active.length ? "٪" : ""}</tspan></text>
      <text x="160" y="188" textAnchor="middle" className="dial-caption">تکمیل برنامهٔ امروز</text>
      <path d="M150 207h20" stroke="var(--accent)" strokeWidth="2" />
    </svg>
    <div className="dial-legend">{shown.map((s, i) => <span key={s}><i style={{ background: tones[i] }} />{s}</span>)}{subjects.length > 3 && <span>+{fa(subjects.length - 3)} درس</span>}</div>
  </div>;
}

export default function StudyDeskHero({ tasks, userData, nav, logout, streak, daysLeft, date }: {
  tasks: HomeTask[]; userData: SignupData; nav: NavFn; logout: () => void;
  streak: number; daysLeft: number | string; date: string;
}) {
  const active = tasks.filter(t => !t.skipped);
  const done = active.filter(t => t.done).length;
  const next = active.find(t => !t.done);
  const parsed = new Date(`${date}T12:00:00`);
  const day = Number.isNaN(parsed.valueOf()) ? "" : parsed.toLocaleDateString("fa-IR", { weekday: "long", day: "numeric", month: "long" });
  return <section className="study-hero desk-hero" aria-label="میز مطالعهٔ امروز">
    <div className="desk-dayline"><span><i />{day}</span><div>
      <button onClick={() => nav("profile")} aria-label="تنظیمات پروفایل"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="8" r="4" /><path d="M4 22v-3a8 8 0 0 1 16 0v3" /></svg></button>
      <button onClick={logout} aria-label="خروج از حساب"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 3H4v18h5m7-14 5 5-5 5M9 12h12" /></svg></button>
    </div></div>
    <div className="desk-hero-grid">
      <div className="desk-hero-copy">
        <span className="desk-eyebrow">میز مطالعهٔ {userData.name || "تو"}</span>
        <h1>مسیرت را<br /><em>دقیق‌تر</em> بساز.</h1>
        <p className="desk-intro">از فهم یک نکته تا حل یک مسئله؛<br />هر قدم امروز، بخشی از مسیر کنکور توست.</p>
        <div className="desk-hero-actions">
          <button className="desk-primary" onClick={() => nav("schedule")}><StudySymbol kind="plan" size={18} />{active.length ? "ادامهٔ برنامهٔ من" : "ساخت برنامهٔ من"}<span aria-hidden="true">←</span></button>
          <button className="desk-text-link" onClick={() => nav("chat")}>گفتگو با بوم <span aria-hidden="true">↗</span></button>
        </div>
        <div className="desk-next-step"><span className="desk-step-marker">{next ? "قدم بعد" : done > 0 ? "ثبت امروز" : "قدم اول"}</span><p>{next?.title || (done > 0 ? "فعالیت‌های امروزت انجام شده؛ برای فردا آماده شو." : "زمان‌های آزادت را مشخص کن و برنامه‌ات را بچین.")}</p>{next && <time dir="ltr">{next.scheduledTime}</time>}</div>
      </div>
      <StudyDial tasks={tasks} />
    </div>
    <div className="desk-metrics">
      {[{ n: fa(done), suffix: `از ${fa(active.length)}`, label: "فعالیت انجام‌شده", color: tones[0], action: () => nav("schedule") },
        { n: fa(streak), suffix: "روز", label: "پیوستگی مطالعه", color: tones[2], action: () => nav("streak") },
        { n: typeof daysLeft === "number" ? fa(daysLeft) : daysLeft, suffix: "روز", label: "تا آزمون ثبت‌شده", color: tones[1], action: () => nav("exams") }].map(item =>
        <button key={item.label} onClick={item.action} style={{ "--metric-tone": item.color } as CSSProperties}><span className="desk-metric-value">{item.n}<small>{item.suffix}</small></span><span className="desk-metric-label">{item.label}<span aria-hidden="true">↗</span></span></button>)}
    </div>
  </section>;
}
