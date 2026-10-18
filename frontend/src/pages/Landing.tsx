import type { NavFn } from "../types";
import { StudySymbol } from "../components/StudySymbols";

/** A geometric study sketch, not a chart of student performance. */
function LearningSketch() {
  return <div className="learning-sketch" aria-hidden="true">
    <svg viewBox="0 0 460 450" fill="none">
      <g stroke="var(--border-strong)" strokeWidth="1">
        <path d="M40 50v360h370M40 350h370M40 290h370M40 230h370M40 170h370M40 110h370M100 50v360M160 50v360M220 50v360M280 50v360M340 50v360M400 50v360" strokeDasharray="2 7" />
        <circle cx="250" cy="203" r="144" strokeDasharray="3 7" />
        <path d="m130 95 188 54-60 221Z" />
      </g>
      <path className="sketch-path" d="M60 350C170 350 136 109 260 112S330 271 415 56" stroke="var(--accent)" strokeWidth="2" pathLength="1" />
      <path className="sketch-path sketch-delay" d="m85 313 91-135 103 97 106-191" stroke="var(--desk-blue)" strokeWidth="1.5" strokeDasharray="5 5" />
      <g fill="var(--surface)" stroke="var(--accent)" strokeWidth="2"><circle cx="86" cy="343" r="6" /><circle cx="191" cy="183" r="6" /><circle cx="330" cy="180" r="6" /><circle cx="406" cy="83" r="6" /></g>
      <g stroke="var(--desk-pink)"><circle cx="260" cy="112" r="22" /><path d="M260 83v58m-29-29h58" /></g>
      <g fill="var(--muted-2)" fontFamily="monospace" fontSize="12"><text x="56" y="40">y</text><text x="423" y="412">x</text><text x="205" y="65">f(x + h)</text><text x="82" y="385">01</text><text x="181" y="218">02</text><text x="341" y="205">03</text></g>
      <path d="M44 35h-8m4-4v8M420 410h-8m4-4v8" stroke="var(--desk-gold)" />
      <g fill="var(--text)" fontFamily="Vazirmatn" fontSize="12"><text x="273" y="330">بفهم.</text><text x="308" y="352">حل کن.</text><text x="337" y="374">جلو برو.</text></g>
    </svg>
    <span className="sketch-caption">از سؤال تا بینش</span>
  </div>;
}

export default function Landing({ nav }: { nav: NavFn }) {
  return <div className="desk-landing">
    <header className="landing-masthead"><div><img src="/karzar-shield-detailed.png" alt="نشان سپر کارزار" width="38" height="38" /><strong>بوم</strong><span>همراه مسیر کنکور</span></div><button onClick={() => nav("login")}>ورود به حساب <span aria-hidden="true">←</span></button></header>
    <div className="landing-main">
      <div className="landing-copy">
        <span className="desk-eyebrow">مطالعه، با نگاه یک حل‌کننده</span>
        <h1>فقط بیشتر نخوان.<br /><em>عمیق‌تر</em> یاد بگیر.</h1>
        <p>برنامه‌ات، کتاب‌هایت و نتیجهٔ تمرین‌هایت،<br />کنار هم؛ برای فهمیدن قدم بعدی.</p>
        <div className="desk-hero-actions"><button className="desk-primary" onClick={() => nav("signup")}>ایجاد حساب کاربری <span aria-hidden="true">←</span></button><button className="desk-text-link" onClick={() => nav("login")}>ادامهٔ مسیر من</button></div>
        <div className="landing-note"><span />برنامه‌ای که با مسیر یادگیری تو تغییر می‌کند.</div>
      </div>
      <LearningSketch />
    </div>
    <section className="landing-chapters" aria-label="ابزارهای مطالعه">
      {[{kind:"plan" as const,n:"۰۱",title:"نقشهٔ هفته",body:"زمان آزاد، تکالیف و آزمون پیش‌رو را در یک برنامه کنار هم ببین."},
        {kind:"discrete" as const,n:"۰۲",title:"پیوند مفاهیم",body:"مبحث‌ها و پیش‌نیازهایشان را در نقشهٔ یادگیری دنبال کن."},
        {kind:"award" as const,n:"۰۳",title:"میدان تمرین",body:"آزمون بده، اشتباه‌هایت را بشناس و در کولوسئوم رقابت کن."}].map(item =>
        <article key={item.n}><div><StudySymbol kind={item.kind} size={22} /><span>{item.n}</span></div><h2>{item.title}</h2><p>{item.body}</p></article>)}
    </section>
    <footer className="landing-footer"><span>بوم · برای مسیر کنکور تو</span></footer>
  </div>;
}
