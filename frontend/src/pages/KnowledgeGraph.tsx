import { useEffect, useMemo, useState } from "react";
import { apiUrl, authHeaders } from "../api";
import type { NavFn, SignupData } from "../types";

interface GraphNode {
  id: string;
  kind: "subject" | "lesson";
  subject: string;
  title: string;
  year: number;
  importance: number;
  opened: boolean;
  available: boolean;
  attempted: number;
  correct: number;
  wrong: number;
  accuracy: number | null;
}

interface GraphEdge { source: string; target: string; kind: string }
interface GraphData { major: string; nodes: GraphNode[]; edges: GraphEdge[] }

const YEAR_LABELS: Record<number, string> = { 10: "دهم", 11: "یازدهم", 12: "دوازدهم" };
const SUBJECT_COLORS: Record<string, string> = {
  "حسابان": "#5C8BA8", "ریاضی": "#5C8BA8", "جبر و گسسته": "#7467A8",
  "هندسه": "#7A9BB8", "فیزیک": "#5D9974", "شیمی": "#A176B5",
  "زیست‌شناسی": "#569D6A", "ادبیات فارسی": "#B18B2E", "عربی": "#C4714A",
  "زبان انگلیسی": "#7184B0", "تاریخ": "#A06F5F", "جغرافیا": "#668F7B",
  "اقتصاد": "#8AAA60", "منطق و فلسفه": "#9682A8", "علوم اجتماعی": "#6F9AA0",
};

// Layout metrics. Lessons stack per (subject, year) column and each
// subject's band height comes from its tallest year column, so a subject
// with many lessons in one year can never overlap the next subject's rows.
const NODE_W = 170;
const NODE_H = 50;
const LESSON_GAP = 12;
const BAND_GAP = 30;
const COL_W = 260;
const LESSON_X0 = 245;

// Default panel = the core subjects (calculus/math, geometry, statistics,
// discrete, physics, chemistry, biology); everything else lives behind the
// "other subjects" tab. Matched as substrings so "جبر و گسسته" or a future
// "ریاضی و آمار" land in the right tab without a rename.
const MAIN_SUBJECT_PATTERNS = ["شیمی", "زیست", "حسابان", "ریاضی", "فیزیک", "هندسه", "آمار", "گسسته"];
function isMainSubject(subject: string) { return MAIN_SUBJECT_PATTERNS.some(pattern => subject.includes(pattern)); }

function subjectColor(subject: string) { return SUBJECT_COLORS[subject] || "#8A7A6A"; }
function masteryColor(node: GraphNode) {
  if (!node.opened) return "#9B948D";
  if (node.accuracy == null) return "#5C8BA8";
  if (node.accuracy >= 0.8) return "#4F9B68";
  if (node.accuracy >= 0.6) return "#C39435";
  return "#C45C59";
}
function fa(value: number) { return value.toLocaleString("fa-IR"); }

export default function KnowledgeGraph({ nav, userData }: { nav: NavFn; userData: SignupData | null }) {
  const [data, setData] = useState<GraphData | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [activeTab, setActiveTab] = useState<"main" | "other">("main");

  useEffect(() => {
    let cancelled = false;
    fetch(apiUrl("/api/insights/knowledge-graph"), { headers: authHeaders() })
      .then(response => {
        if (response.status === 401) {
          localStorage.removeItem("boom-token");
          nav("login");
          throw new Error("session-expired");
        }
        return response.ok ? response.json() : Promise.reject(new Error("graph"));
      })
      .then(graph => { if (!cancelled) setData(graph); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, [userData?.major]);

  // Nodes/edges of the active tab only. Edges crossing between tabs are
  // dropped so the layout never references a position that is not drawn.
  const tabData = useMemo<GraphData | null>(() => {
    if (!data) return null;
    const nodes = data.nodes.filter(node => (activeTab === "main") === isMainSubject(node.subject));
    const visible = new Set(nodes.map(node => node.id));
    const edges = data.edges.filter(edge => visible.has(edge.source) && visible.has(edge.target));
    return { major: data.major, nodes, edges };
  }, [data, activeTab]);

  const layout = useMemo(() => {
    const empty = {
      positions: new Map<string, { x: number; y: number }>(), width: 1050, height: 900,
      containsTargets: new Set<string>(), prerequisitePairs: new Set<string>(),
    };
    if (!tabData) return empty;
    const positions = new Map<string, { x: number; y: number }>();
    const containsTargets = new Set<string>();
    const prerequisitePairs = new Set<string>();
    for (const edge of tabData.edges) {
      if (edge.kind === "prerequisite") prerequisitePairs.add(`${edge.source}->${edge.target}`);
    }
    const subjects = tabData.nodes.filter(node => node.kind === "subject");
    const lessonsBySubject = new Map<string, GraphNode[]>();
    for (const node of tabData.nodes) {
      if (node.kind !== "lesson") continue;
      const list = lessonsBySubject.get(node.subject) ?? [];
      if (list.length === 0) containsTargets.add(node.id); // contains edge anchor per subject
      list.push(node);
      lessonsBySubject.set(node.subject, list);
    }
    let cursor = 20;
    for (const subject of subjects) {
      const byYear = new Map<number, GraphNode[]>();
      for (const lesson of lessonsBySubject.get(subject.subject) ?? []) {
        const list = byYear.get(lesson.year) ?? [];
        list.push(lesson);
        byYear.set(lesson.year, list);
      }
      let bandHeight = NODE_H;
      for (const year of [10, 11, 12]) {
        const count = byYear.get(year)?.length ?? 0;
        bandHeight = Math.max(bandHeight, count * (NODE_H + LESSON_GAP) - LESSON_GAP);
      }
      for (const year of [10, 11, 12]) {
        byYear.get(year)?.forEach((lesson, slot) => positions.set(lesson.id, {
          x: LESSON_X0 + (year - 10) * COL_W,
          y: cursor + slot * (NODE_H + LESSON_GAP),
        }));
      }
      positions.set(subject.id, { x: 35, y: cursor + (bandHeight - NODE_H) / 2 });
      cursor += bandHeight + BAND_GAP;
    }
    const maxY = Math.max(cursor - BAND_GAP, 700);
    return { positions, width: 1050, height: maxY + 60, containsTargets, prerequisitePairs };
  }, [tabData]);

  const selected = tabData?.nodes.find(node => node.id === selectedId) || tabData?.nodes[0];
  const nodeById = new Map(tabData?.nodes.map(node => [node.id, node]) || []);

  return (
    <div className="min-h-screen bg-[var(--surface)] pb-12">
      <header className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--surface)]/95 backdrop-blur-sm">
        <div className="flex items-center gap-3 px-5 pb-3 pt-12">
        <button type="button" onClick={() => nav("home")} aria-label="بازگشت" className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--chip)] text-[var(--muted)]">
          <span aria-hidden="true">‹</span>
        </button>
        <div className="flex-1 text-right">
          <h1 className="font-display text-xl text-[var(--text)]">نقشه مسیر یادگیری</h1>
          <p className="text-[11px] font-medium text-[var(--muted-2)]">سه سال مسیر تو، با پیش‌نیازهای واقعی</p>
        </div>
        </div>
        <div className="flex gap-1 px-5" role="tablist" aria-label="دسته‌بندی درس‌ها">
          {([["main", "دروس تخصصی"], ["other", "دروس عمومی"]] as const).map(([key, label]) => {
            const count = data ? data.nodes.filter(node => node.kind === "subject" && (key === "main") === isMainSubject(node.subject)).length : 0;
            const active = activeTab === key;
            return (
              <button key={key} type="button" role="tab" aria-selected={active} disabled={!data}
                onClick={() => { setActiveTab(key); setSelectedId(null); }}
                className={`flex items-center gap-1.5 rounded-t-xl border-b-2 px-3.5 pb-2 pt-1.5 text-[13px] font-display transition-colors disabled:opacity-50 ${active ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]" : "border-transparent text-[var(--muted)] hover:text-[var(--text)]"}`}>
                {label}
                {data && <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${active ? "bg-[var(--accent)] text-white" : "bg-[var(--chip)] text-[var(--muted-2)]"}`}>{fa(count)}</span>}
              </button>
            );
          })}
        </div>
      </header>

      {error && <div className="mx-5 mt-5 rounded-2xl border border-red-200 bg-red-50 p-4 text-right text-[12px] font-semibold text-red-600">نقشه فعلاً بارگذاری نشد. اتصال را بررسی کن.</div>}
      {!data && !error && <div className="p-8 text-center text-sm text-[var(--muted)]">در حال ساختن مسیر یادگیری...</div>}
      {data && tabData && (
        <>
          <section className="study-section mx-5 mt-5 p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="text-right">
                <p className="text-[11px] font-bold text-[var(--muted-2)]">رشته</p>
                <p className="text-[15px] font-bold text-[var(--text)]">{data.major}</p>
              </div>
              <div className="flex gap-1.5" dir="rtl">
                {[10, 11, 12].map(year => <span key={year} className="rounded-lg bg-[var(--chip)] px-2 py-1 text-[10px] font-bold text-[var(--muted)]">{YEAR_LABELS[year]}</span>)}
              </div>
            </div>
            <div className="flex flex-wrap justify-end gap-x-4 gap-y-2 text-[10px] font-semibold text-[var(--muted-2)]">
              <span><i className="me-1 inline-block h-2.5 w-2.5 rounded-full bg-[#4F9B68]" />دقت بالا</span>
              <span><i className="me-1 inline-block h-2.5 w-2.5 rounded-full bg-[#C39435]" />نیاز به تمرین</span>
              <span><i className="me-1 inline-block h-2.5 w-2.5 rounded-full bg-[#C45C59]" />ضعیف</span>
              <span><i className="me-1 inline-block h-2.5 w-2.5 rounded-full bg-[#9B948D]" />باز نشده</span>
            </div>
          </section>

          {tabData.nodes.length === 0 && (
            <div className="study-section mx-5 mt-4 p-6 text-center text-[12px] font-semibold text-[var(--muted)]">
              در این دسته درسی وجود ندارد.
            </div>
          )}
          <section className={`study-section mx-5 mt-4 overflow-x-auto p-3 ${tabData.nodes.length === 0 ? "hidden" : ""}`} dir="ltr">
            <svg width={layout.width} height={layout.height} viewBox={`0 0 ${layout.width} ${layout.height}`} role="tree" aria-label="درخت کامل مباحث درسی">
              <g opacity=".45">
                {[10, 11, 12].map(year => <line key={year} x1={LESSON_X0 + (year - 10) * COL_W} y1="20" x2={LESSON_X0 + (year - 10) * COL_W} y2={layout.height - 20} stroke="var(--border)" strokeDasharray="4 8" />)}
              </g>
              <g fontSize="13" fontWeight="700" fill="var(--muted)" textAnchor="middle">
                {[10, 11, 12].map(year => <text key={year} x={330 + (year - 10) * 260} y="18">{YEAR_LABELS[year]}</text>)}
              </g>
              <g>
                {tabData.edges.map((edge, index) => {
                  const source = layout.positions.get(edge.source); const target = layout.positions.get(edge.target);
                  if (!source || !target) return null;
                  // Draw "contains" only to each subject's first lesson; the
                  // sequence chain carries the rest, so columns stay readable.
                  if (edge.kind === "contains" && !layout.containsTargets.has(edge.target)) return null;
                  // A sequence edge duplicated by a prerequisite edge would
                  // draw twice on top of itself - keep the solid one only.
                  if (edge.kind === "sequence" && layout.prerequisitePairs.has(`${edge.source}->${edge.target}`)) return null;
                  const sourceNode = nodeById.get(edge.source);
                  const stroke = edge.kind === "prerequisite" ? subjectColor(sourceNode?.subject || "") : "var(--border-strong)";
                  const strokeWidth = edge.kind === "prerequisite" ? 2.5 : 1.2;
                  const dash = edge.kind === "prerequisite" ? "0" : "5 5";
                  if (edge.kind !== "contains" && Math.abs(source.x - target.x) < 1) {
                    // Same year column: bracket down the left gutter so the
                    // line never crosses the lesson boxes between the slots.
                    const railX = source.x - 10;
                    return <path key={`${edge.source}-${edge.target}-${index}`} d={`M ${source.x} ${source.y + 25} L ${railX} ${source.y + 25} L ${railX} ${target.y + 25} L ${target.x} ${target.y + 25}`} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeDasharray={dash} opacity=".7" />;
                  }
                  return <path key={`${edge.source}-${edge.target}-${index}`} d={`M ${source.x + NODE_W} ${source.y + 25} C ${source.x + NODE_W + 40} ${source.y + 25}, ${target.x - 35} ${target.y + 25}, ${target.x} ${target.y + 25}`} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeDasharray={dash} opacity=".7" />;
                })}
              </g>
              <g>
                {tabData.nodes.map(node => {
                  const position = layout.positions.get(node.id); if (!position) return null;
                  const color = node.kind === "subject" ? subjectColor(node.subject) : masteryColor(node);
                  const selectedNode = selected?.id === node.id;
                  return <g key={node.id} role="treeitem" aria-label={node.title} tabIndex={0} onClick={() => setSelectedId(node.id)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") setSelectedId(node.id); }} className="cursor-pointer">
                    <rect x={position.x} y={position.y} width="170" height="50" rx="12" fill={node.opened ? `${color}22` : "#9B948D18"} stroke={selectedNode ? color : node.opened ? color : "#9B948D"} strokeWidth={selectedNode ? 3 : Math.max(1.5, node.importance / 2)} />
                    <circle cx={position.x + 18} cy={position.y + 25} r={node.kind === "subject" ? 7 : 5} fill={color} />
                    <text x={position.x + 34} y={position.y + 22} fontSize="12" fontWeight="700" fill="var(--text)" textAnchor="start">{node.title.slice(0, 20)}</text>
                    <text x={position.x + 34} y={position.y + 39} fontSize="9" fill="var(--muted)" textAnchor="start">{node.kind === "subject" ? "درس" : node.opened ? `${Math.round((node.accuracy ?? 0) * 100)}٪ دقت` : "هنوز باز نشده"}</text>
                  </g>;
                })}
              </g>
            </svg>
          </section>

          {selected && <section className="study-section mx-5 mt-4 p-5 text-right">
            <div className="flex items-start justify-between gap-3">
              <div><p className="text-[10px] font-bold text-[var(--muted-2)]">اهمیت {selected.importance} از ۵</p><h2 className="mt-1 text-lg font-bold text-[var(--text)]">{selected.title}</h2></div>
              <span className="rounded-xl px-3 py-1 text-[11px] font-bold" style={{ color: masteryColor(selected), backgroundColor: `${masteryColor(selected)}18` }}>{selected.opened ? "باز شده" : "قفل مسیر"}</span>
            </div>
            <p className="mt-3 text-[12px] leading-relaxed text-[var(--muted)]">{selected.opened ? `${fa(selected.attempted)} پاسخ ثبت شده، ${fa(selected.wrong)} غلط و ${selected.accuracy == null ? "داده کافی نیست" : `${Math.round(selected.accuracy * 100)}٪ دقت`}.` : "بعد از ثبت یک جلسه مطالعه یا پاسخ‌دادن به تست‌های این مبحث، این گره باز و رنگی می‌شود."}</p>
          </section>}
        </>
      )}
    </div>
  );
}
