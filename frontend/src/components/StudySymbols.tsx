import { useId, type ReactNode, type SVGProps } from "react";

type SymbolKind = "math" | "geometry" | "statistics" | "discrete" | "physics" | "chemistry" |
  "biology" | "humanities" | "art" | "language" | "document" | "plan" | "streak" | "award";
interface SymbolProps extends SVGProps<SVGSVGElement> { size?: number; title?: string }

/** Fixed geometry and currentColor keep the marks consistent across themes and platforms. */
function SymbolFrame({ size = 20, title, children, ...props }: SymbolProps & { children: ReactNode }) {
  const id = useId();
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" focusable="false"
    aria-hidden={title ? undefined : true} role={title ? "img" : undefined}
    aria-labelledby={title ? id : undefined} {...props}>
    {title && <title id={id}>{title}</title>}{children}
  </svg>;
}

const shapes: Record<SymbolKind, ReactNode> = {
  math: <><path d="M4 3v17h17M6 17c4 0 3-10 6-10s2 10 7 10" /><path d="M3 7h2M3 12h2M3 17h2M9 19v2M14 19v2M19 19v2" opacity=".45" /></>,
  geometry: <><circle cx="12" cy="5" r="2" /><path d="m11 7-6 14M13 7l6 14M7 15a8 8 0 0 0 10 0M12 1v2" /></>,
  statistics: <><path d="M3 3v18h18M7 17v-5M12 17V8M17 17V4" /><path d="m6 7 5-3 4 1 5-3" opacity=".45" /></>,
  discrete: <><circle cx="5" cy="6" r="2.5" /><circle cx="19" cy="7" r="2.5" /><circle cx="11" cy="19" r="2.5" /><path d="m7.5 6.2 9 .6M6 8.3l4 8.4M17.5 9.2l-5 7.7" /></>,
  physics: <><path d="M3 12h2l3-7 4 14 4-10 2 3h3" /><path d="M3 3v18h18" opacity=".4" /></>,
  chemistry: <><path d="M9 3h6M10 3v6L4.8 18a2 2 0 0 0 1.7 3h11a2 2 0 0 0 1.7-3L14 9V3M8 14h8" /><circle cx="10" cy="17" r=".6" fill="currentColor" stroke="none" /><circle cx="14" cy="18" r=".6" fill="currentColor" stroke="none" /></>,
  biology: <><path d="M7 2c0 8 10 12 10 20M17 2C17 10 7 14 7 22M7.5 4h9M9 8h6M9 16h6M7.5 20h9" /><path d="M10 12h4" opacity=".5" /></>,
  humanities: <><path d="M3 7 12 3l9 4H3ZM4 21h16M5 18h14M6 9v7M10 9v7M14 9v7M18 9v7" /></>,
  art: <><path d="m5 19 2-6L17 3l4 4-10 10-6 2ZM14 6l4 4M7 13l4 4M3 21h18" /><circle cx="4" cy="6" r="1.5" /><path d="M5.5 6h4" opacity=".45" /></>,
  language: <><path d="M3 5h12M9 3v2M5 8c1 3 4 6 8 8M12 5c0 5-4 9-9 11M13 21l4-10 4 10M14.5 18h5" /></>,
  document: <><path d="M6 3h9l4 4v14H6V3ZM15 3v5h4M9 12h7M9 16h7" /><path d="m3 13 1 1" opacity=".45" /></>,
  plan: <><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M7 2v4M17 2v4M3 9h18m-13 6 3 3 5-6" /></>,
  streak: <><path d="M4 20h16M7 17v-4M12 17V9M17 17V5" /><path d="m4 9 4-3 4 1 7-5" /><path d="M16 2h3v3" /></>,
  award: <><path d="M12 2 20 5v6c0 5-8 10-8 10S4 16 4 11V5l8-3Z" fill="currentColor" fillOpacity=".07" /><path d="m8 11 3 3 5-6" /></>,
};

export function StudySymbol({ kind, ...props }: SymbolProps & { kind: SymbolKind }) {
  return <SymbolFrame {...props}>{shapes[kind]}</SymbolFrame>;
}

function subjectKind(subject: string): SymbolKind {
  const s = subject.replace(/ي/g, "ی").replace(/ك/g, "ک").toLowerCase();
  if (/هندسه|geometry/.test(s)) return "geometry";
  if (/آمار|احتمال|statistics/.test(s)) return "statistics";
  if (/گسسته|جبر|discrete/.test(s)) return "discrete";
  if (/ریاضی|حسابان|math|calculus/.test(s)) return "math";
  if (/فیزیک|physics/.test(s)) return "physics";
  if (/شیمی|chemistry/.test(s)) return "chemistry";
  if (/زیست|تجربی|biology/.test(s)) return "biology";
  if (/انسانی|ادبیات|تاریخ|فلسفه|humanities/.test(s)) return "humanities";
  if (/هنر|art/.test(s)) return "art";
  if (/زبان|عربی|انگلیسی|language/.test(s)) return "language";
  return "document";
}

export function SubjectSymbol({ subject, ...props }: SymbolProps & { subject: string }) {
  return <StudySymbol kind={subjectKind(subject)} {...props} />;
}

export function GradeSymbol({ grade, ...props }: SymbolProps & { grade: string }) {
  if (grade === "فارغ‌التحصیل") return <StudySymbol kind="award" {...props} />;
  const step = grade === "دهم" ? 1 : grade === "یازدهم" ? 2 : 3;
  return <SymbolFrame {...props}>
    <path d="M3 21h18" />
    {[7, 12, 17].map((height, index) => <rect key={height} x={4 + index * 6} y={20 - height}
      width="4" height={height} rx=".6" fill="currentColor" stroke="none" fillOpacity={index < step ? .85 : .16} />)}
  </SymbolFrame>;
}

export function RankSymbol({ rank, ...props }: SymbolProps & { rank: number }) {
  return <SymbolFrame {...props}>
    <path d="M12 3 18 5v6c0 4-6 7-6 7s-6-3-6-7V5l6-2Z" fill="currentColor" fillOpacity=".08" />
    <path d="M4 8c-2 5 0 10 4 12M20 8c2 5 0 10-4 12M3 13l3 1M4 17l3 1M21 13l-3 1M20 17l-3 1M9 21h6" opacity=".65" />
    <text x="12" y="12.8" textAnchor="middle" fill="currentColor" stroke="none" fontSize="8" fontWeight="700"
      style={{ fontFamily: "Vazirmatn, sans-serif" }}>{rank.toLocaleString("fa-IR")}</text>
  </SymbolFrame>;
}
