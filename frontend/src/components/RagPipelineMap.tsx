import { useId, useMemo, useState, type ReactNode } from "react";
import type { TraceRecord, TraceStage } from "./RagInspector";
import { TrendUpIcon } from "./icons";

/**
 * Graphical map of one RAG run.
 *
 * The per-stage tables in RagInspector are precise but flat: you have to read
 * five tables to notice that the reranker rescued a chunk the lexical search
 * never returned. This file draws the same trace as pictures instead - a flow
 * diagram of the whole pipeline (which stage fed which, and how many candidates
 * it passed on), a rank chart that follows each chunk across the stages, and a
 * document/chunk panel that lists the files and text actually selected.
 *
 * Everything here is derived from the trace alone; the layout is computed in a
 * fixed coordinate space so the diagram renders identically on the server
 * (panel-render-tests use renderToStaticMarkup) and in the browser.
 *
 * Reading order is right-to-left, like the rest of the app: lane 0 (the
 * question) sits on the right and the answer ends on the left.
 *
 * Text anchoring follows the same direction. SVG resolves `text-anchor`
 * against the inline direction, so in this RTL page a label pinned by its
 * RIGHT edge - what an LTR layout would write as `text-anchor="end"` - is
 * `text-anchor="start"` here, and one that grows rightwards from a left edge
 * is `end`. Do not "fix" this by pinning `direction: ltr` on the maps: that
 * puts a leading number on the wrong end of the line (`۲ تکه در بافت` reads
 * backwards) even though the alignment looks right.
 */

// ---------------------------------------------------------------- formatting

function fa(value: number, digits = 0): string {
  return value.toLocaleString("fa-IR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function text(value: unknown): string {
  return value == null ? "" : String(value);
}

/**
 * A readable file label, with the page marker kept.
 *
 * Book text chunks are named "<book>.pdf" while their transcribed pages and the
 * question bank are "<book>::p<page>". Dropping the marker would make two
 * different sources of the same book (its text index and one of its pages)
 * render as one label with two contradictory chunk counts.
 */
function shortName(name: string, limit = 26): string {
  const page = name.match(/::p(\d+)$/i);
  const book = name.replace(/\.pdf$/i, "").replace(/::p\d+$/i, "");
  const suffix = page ? ` · ص ${fa(Number(page[1]))}` : "";
  const room = Math.max(8, limit - suffix.length);
  return (book.length <= room ? book : `${book.slice(0, room - 1)}…`) + suffix;
}

/**
 * Rough advance width of `value` at `fontSize`, in SVG user units. Persian
 * letterforms and Arabic-Indic digits are narrower than Latin ones and spaces
 * are narrower still; the estimate leans wide so a label that fits here always
 * fits on screen.
 */
export function textWidth(value: string, fontSize: number): number {
  let units = 0;
  for (const ch of value) {
    if (ch === " ") units += 0.3;
    else if (/[\u0660-\u0669\u06F0-\u06F9]/.test(ch)) units += 0.48;
    else if (/[\u0600-\u06FF\u200c]/.test(ch)) units += 0.5;
    else if (/[A-Za-z0-9]/.test(ch)) units += 0.56;
    else units += 0.42;
  }
  return units * fontSize;
}

/**
 * Trim `value` to the widest prefix that fits `maxWidth` at `fontSize`, ending
 * in an ellipsis. SVG text cannot wrap, so a label that is merely sliced by
 * character count is drawn straight through its box border instead.
 */
export function fitText(value: string, maxWidth: number, fontSize: number): string {
  if (textWidth(value, fontSize) <= maxWidth) return value;
  let out = "";
  for (const ch of value) {
    if (textWidth(`${out}${ch}…`, fontSize) > maxWidth) break;
    out += ch;
  }
  return `${out.trimEnd()}…`;
}

// ------------------------------------------------------- stage classification

export type StageRole =
  | "gate" | "rewrite" | "embed" | "vector" | "lexical" | "fusion" | "rerank"
  | "qbank" | "image" | "context" | "generate" | "vision" | "answer" | "audit" | "other";

const ROLE_BY_SUFFIX: Record<string, StageRole> = {
  simple_message_gate: "gate",
  query_rewrite: "rewrite",
  embed_query: "embed",
  semantic_search: "vector",
  lexical_search: "lexical",
  rrf_fusion: "fusion",
  rerank: "rerank",
  qbank_search: "qbank",
  image_search: "image",
  llm_generate: "generate",
  vision_generate: "vision",
  final_answer: "answer",
  retrieval_assembly: "context",
  verify_batch: "audit",
  verify_llm: "audit",
  quality_audit: "audit",
  ingest_embed: "other",
};

/** Review and transcription roles share the "other" lane but keep their label. */
export function roleOf(name: string): StageRole {
  const suffix = name.split("·").pop()?.trim() ?? name;
  if (suffix in ROLE_BY_SUFFIX) return ROLE_BY_SUFFIX[suffix];
  if (suffix.startsWith("verify") || suffix.includes("audit")) return "audit";
  return "other";
}

/** "books · rerank" → "books"; a plain stage name has no group. */
export function groupOf(name: string): string {
  const parts = name.split("·");
  return parts.length > 1 ? parts[0].trim() : "";
}

/** Shelf/group keys only ever appear in stage names, so they need a label too. */
export const GROUP_FA: Record<string, string> = {
  books: "کتاب‌ها",
  qbank: "بانک سؤال",
  image: "تصویر صفحه",
};

export const LANES = [
  "پرسش و بازنویسی",
  "جست‌وجوی کتاب",
  "ادغام و بازترتیب",
  "بانک سؤال و تصویر",
  "پاسخ",
  "بازبینی و بارگذاری",
] as const;

const LANE_BY_ROLE: Record<StageRole, number> = {
  gate: 0, rewrite: 0, embed: 0,
  vector: 1, lexical: 1,
  fusion: 2, rerank: 2,
  qbank: 3, image: 3,
  context: 4, generate: 4, vision: 4, answer: 4,
  audit: 5, other: 5,
};

/**
 * The stages a funnel may be built from: the ones that report how many
 * candidates a search stack carried. The question bank's outer `qbank_search`
 * stage (role "qbank") is deliberately absent - it reports the hits the whole
 * wrapper finished with, so including it would put the shelf's *output*
 * (4 hits) in front of its own *input* (20 candidates) and read backwards.
 */
const FUNNEL_ROLES: StageRole[] = ["vector", "lexical", "fusion", "rerank"];

/**
 * Which shelf a retrieval stage belongs to ("books", "qbank", …).
 *
 * The book search and the question-bank search run the same stack, but the
 * question bank's outer `qbank_search` stage has no "·" prefix (it is the
 * wrapper that opens the retrieval, not a tagged sub-stage), so it must not
 * fall through to the books shelf its untagged siblings use.
 */
export function shelfOf(name: string, role: StageRole): string {
  const group = groupOf(name);
  if (group) return group;
  if (role === "qbank") return "qbank";
  if (role === "image") return "image";
  return "books";
}

/**
 * A lane is a stage of the pipeline, not a shelf: the question bank's own
 * vector/lexical/fusion stages stay in the question-bank lane, so its shelf
 * reads as one column instead of bleeding into the book column.
 */
export function laneOf(name: string, role: StageRole): number {
  return groupOf(name) === "qbank" ? 3 : LANE_BY_ROLE[role];
}

/** Rows a retrieval stage actually selected, and which files/chunks they were. */
export interface SelectedRow {
  id: string; doc: string; chunk: string; rank: number; score: number | null; preview: string; referenced: boolean;
  /** Reranker places gained (+) or lost (-) on this chunk; 0 in other stages. */
  move: number;
}

export interface MapNode {
  id: string; name: string; label: string; role: StageRole; lane: number; index: number;
  ms: number; selected: number; skippedReason: string;
  sampled: number; countKnown: boolean; meta: Record<string, unknown>; error: string; truncated: boolean;
  docs: string[]; rows: SelectedRow[];
}

export interface MapEdge { from: string; to: string; count: number; known?: boolean }

export interface PipelineGraph {
  nodes: MapNode[];
  edges: MapEdge[];
  lanes: { title: string; nodes: MapNode[] }[];
  /** Candidate counts per retrieval group, in flow order: books, then qbank. */
  funnels: { group: string; steps: { label: string; role: StageRole; count: number; known?: boolean }[] }[];
  width: number; height: number;
}

const NODE_W = 178;
const NODE_H = 58;
/** Room a node's labels have: its width less the inset and the accent bar. */
const NODE_TEXT_W = NODE_W - 22;
const COL_W = 212;
const ROW_GAP = 28;
const PAD = 22;
const LANE_TITLE_H = 24;

function rowsOf(stage: TraceStage): SelectedRow[] {
  return (stage.rows ?? []).map((row, index) => ({
    id: text(row.id),
    doc: text(row.doc ?? row.document ?? row.name),
    chunk: text(row.chunk ?? row.n ?? row.id ?? index + 1),
    rank: Number(row.rank ?? index + 1) || index + 1,
    score: typeof row.score === "number" ? row.score
      : typeof row.rerank_score === "number" ? row.rerank_score : null,
    preview: text(row.preview ?? row.text ?? ""),
    referenced: row.cited === true,
    move: Number(row.move ?? 0) || 0,
  }));
}

/** Counts are outputs, not requested top-k limits or the sampled table size. */
export function stageOutput(stage: TraceStage): { count: number; known: boolean } {
  const meta = stage.meta ?? {};
  const keys = ["output_count", "kept", "hits", "final_chunks", "sources", "stored_chunks"];
  for (const key of keys) {
    if (typeof meta[key] === "number" && Number.isFinite(meta[key]) && Number(meta[key]) >= 0) {
      return { count: Number(meta[key]), known: true };
    }
  }
  return { count: stage.rows?.length ?? 0, known: false };
}

/**
 * Stages that were deliberately not run report why in `meta.skipped` / `reason`.
 * Surfacing it on the diagram keeps "no chunks" from looking like "no data".
 */
function skippedReason(stage: TraceStage): string {
  const meta = stage.meta ?? {};
  if (meta.retrieval_skipped) return text(meta.reason) || "بازیابی اجرا نشد";
  return text(meta.skipped ?? "");
}

export function buildPipelineGraph(trace: TraceRecord): PipelineGraph {
  const stages = trace.stages ?? [];
  const nodes: MapNode[] = stages.map((stage, index) => {
    const rows = rowsOf(stage);
    const role = roleOf(stage.name);
    let output = stageOutput(stage);
    if (role === "rerank" && stage.meta?.skipped && !output.known) {
      const previous = stages.slice(0, index).reverse().find(candidate =>
        roleOf(candidate.name) === "fusion" && groupOf(candidate.name) === groupOf(stage.name));
      if (previous) output = stageOutput(previous);
    }
    return {
      id: `${stage.name}-${index}`,
      name: stage.name, label: stage.label, role, index,
      lane: laneOf(stage.name, role),
      ms: Number(stage.ms) || 0,
      selected: output.count, sampled: rows.length, countKnown: output.known,
      meta: stage.meta ?? {},
      error: text(stage.meta?.provider_error ?? stage.meta?.error ?? ""),
      truncated: Object.keys(stage.meta ?? {}).some(key => key.startsWith("truncated_") && stage.meta[key]),
      skippedReason: skippedReason(stage),
      docs: [...new Set(rows.map(row => row.doc).filter(Boolean))],
      rows,
    };
  });

  // Retrieval branches feed their own fusion; edges describe dependencies,
  // not concurrency or vector distances. Wrapper stages report child output.
  const fusionTarget = (node: MapNode): MapNode | null => {
    const group = groupOf(node.name);
    return nodes.find(other =>
      other.index > node.index && other.role === "fusion" && groupOf(other.name) === group) ?? null;
  };
  const edges: MapEdge[] = [];
  nodes.forEach(node => {
    if (node.role === "vector" || node.role === "lexical") {
      const target = fusionTarget(node) ?? nodes[node.index + 1];
      if (target && target !== node) edges.push({ from: node.id, to: target.id, count: node.selected, known: node.countKnown });
      return;
    }
    if (node.role === "embed") {
      const branches = nodes.filter(other => other.index > node.index &&
        ["vector", "lexical"].includes(other.role) && shelfOf(other.name, other.role) === shelfOf(node.name, node.role));
      const vector = branches.find(other => other.role === "vector");
      const lexical = branches.find(other => other.role === "lexical");
      if (vector || lexical) {
        [vector, lexical].forEach(target => { if (target) edges.push({ from: node.id, to: target.id, count: 0 }); });
        return;
      }
    }
    if (node.role === "qbank") {
      const context = nodes.find(other => other.role === "context") ?? nodes.find(other => ["generate", "vision"].includes(other.role));
      if (context) edges.push({ from: node.id, to: context.id, count: node.selected, known: node.countKnown });
      return;
    }
    if (node.role === "rerank") {
      const target = groupOf(node.name) === "qbank" ? nodes.find(other => other.role === "qbank") :
        nodes.find(other => other.role === "context") ?? nodes.find(other => ["generate", "vision"].includes(other.role));
      if (target) { edges.push({ from: node.id, to: target.id, count: node.selected, known: node.countKnown }); return; }
    }
    const next = nodes[node.index + 1];
    if (next) edges.push({ from: node.id, to: next.id, count: node.selected, known: node.countKnown });
  });

  const lanes = LANES.map((title, lane) => ({ title, nodes: nodes.filter(node => node.lane === lane) }));
  const lanes_used = lanes.filter(lane => lane.nodes.length > 0);
  const tallest = Math.max(1, ...lanes_used.map(lane => lane.nodes.length));
  const width = PAD * 2 + Math.max(lanes_used.length, 1) * COL_W;
  const height = PAD * 2 + LANE_TITLE_H + tallest * (NODE_H + ROW_GAP) - ROW_GAP;

  const groups = [...new Set(nodes.filter(n => FUNNEL_ROLES.includes(n.role))
    .map(n => shelfOf(n.name, n.role)))];
  const funnels = groups.map(group => ({
    group,
    steps: nodes
      .filter(n => FUNNEL_ROLES.includes(n.role) && shelfOf(n.name, n.role) === group)
      .map(n => ({ label: n.label, role: n.role, count: n.selected, known: n.countKnown })),
  })).filter(funnel => funnel.steps.length > 1);

  return { nodes, edges, lanes: lanes_used, funnels, width, height };
}

// ------------------------------------------------------------ rank evolution

export interface RankStep { name: string; label: string }

export interface ChunkTrack {
  key: string; group: string; doc: string; chunk: string; preview: string;
  /** stage name → rank in that stage (1 = best). */
  ranks: Record<string, number>;
  grid: (number | null)[];
  cited: boolean;
  citedRank: number | null;
  referenced: boolean;
  rerankMove: number;
}

export interface RankChart { steps: RankStep[]; tracks: ChunkTrack[]; maxRank: number }

const RANKED_ROLES: StageRole[] = ["vector", "lexical", "fusion", "rerank"];

export function buildRankChart(trace: TraceRecord, docFilter = ""): RankChart {
  const stages = (trace.stages ?? []).filter(
    stage => RANKED_ROLES.includes(roleOf(stage.name)) || ["answer", "context"].includes(roleOf(stage.name)));
  if (stages.length === 0) return { steps: [], tracks: [], maxRank: 1 };

  // The book search and the question-bank search share stage labels (both have
  // a "semantic_search"), so the group is part of the readable label.
  const steps: RankStep[] = stages.map(stage => {
    const group = groupOf(stage.name);
    return { name: stage.name, label: group ? `${GROUP_FA[group] ?? group} · ${stage.label}` : stage.label };
  });
  const byKey = new Map<string, ChunkTrack>();

  stages.forEach((stage, stepIndex) => {
    rowsOf(stage).forEach(row => {
      if (!row.doc) return;
      const fallback = `${row.doc}||${row.chunk}`;
      const candidates = [...byKey.values()].filter(track => track.doc === row.doc && track.chunk === row.chunk);
      const key = row.id ? `id:${row.id}` : candidates.length === 1 ? candidates[0].key : fallback;
      const track = byKey.get(key) ?? {
        key, group: groupOf(stage.name), doc: row.doc, chunk: row.chunk,
        preview: row.preview, ranks: {}, grid: steps.map(() => null),
        cited: false, citedRank: null, referenced: false, rerankMove: 0,
      };
      track.grid[stepIndex] = row.rank;
      track.ranks[stage.name] = row.rank;
      if (!track.preview && row.preview) track.preview = row.preview;
      if (["context", "answer"].includes(roleOf(stage.name))) {
        // Legacy `cited` property means supplied context. Explicit row.cited is
        // the only evidence of a numbered reference in the generated answer.
        track.cited = true; track.citedRank = row.rank;
        track.referenced = row.referenced;
      }
      byKey.set(key, track);
    });
  });

  // Each shelf runs its own reranker and each one's table is the honest source
  // for "moved up/down": a row position in the books table says nothing about
  // what the question-bank reranker did to its own hits.
  stages.filter(stage => roleOf(stage.name) === "rerank").forEach(stage => {
    rowsOf(stage).forEach(row => {
      const track = row.id ? byKey.get(`id:${row.id}`) : [...byKey.values()].find(item => item.doc === row.doc && item.chunk === row.chunk);
      if (track && row.move) track.rerankMove = row.move;
    });
  });

  let tracks = [...byKey.values()];
  if (docFilter) tracks = tracks.filter(track => track.doc === docFilter);
  tracks.sort((a, b) => Number(b.cited) - Number(a.cited) || a.doc.localeCompare(b.doc) || a.chunk.localeCompare(b.chunk));

  const maxRank = Math.max(1, ...tracks.flatMap(track => track.grid.map(rank => rank ?? 0)));
  return { steps, tracks, maxRank };
}

// --------------------------------------------------------- document coverage

export interface DocChunk {
  key: string; chunk: string; preview: string;
  stages: string[]; bestRank: number; cited: boolean; citedRank: number | null; rerankMove: number;
  referenced: boolean;
  /**
   * Shelf the chunk's first search came from ("books", "qbank", "image").
   * Taken from the stage names that ranked this chunk, so the mind map can
   * group documents by shelf instead of guessing it from the file name.
   * Empty when only the final context named the chunk.
   */
  group: string;
}

export interface DocCoverage { doc: string; chunks: DocChunk[]; cited: number; selectedIn: number }

export function buildDocumentCoverage(trace: TraceRecord, rank: RankChart): DocCoverage[] {
  const byDoc = new Map<string, DocChunk[]>();
  rank.tracks.forEach(track => {
    const ranked = rank.steps.filter(step => track.ranks[step.name] != null);
    const stages = ranked.map(step => step.label);
    const shelves = ranked.map(step => groupOf(step.name)).filter(Boolean);
    const best = Math.min(...track.grid.filter((value): value is number => value != null));
    const chunk: DocChunk = {
      key: track.key, chunk: track.chunk, preview: track.preview,
      stages, bestRank: Number.isFinite(best) ? best : 0,
      cited: track.cited, citedRank: track.citedRank, referenced: track.referenced, rerankMove: track.rerankMove,
      group: shelves[0] ?? "",
    };
    byDoc.set(track.doc, [...(byDoc.get(track.doc) ?? []), chunk]);
  });
  // Files that were only ever cited (never in a search table) still matter.
  const answer = (trace.stages ?? []).find(stage => ["answer", "context"].includes(roleOf(stage.name)));
  rowsOf(answer ?? { rows: [], meta: {} } as unknown as TraceStage).forEach(row => {
    if (!row.doc) return;
    const list = byDoc.get(row.doc) ?? [];
    if (!list.some(chunk => chunk.chunk === row.chunk)) {
      list.push({ key: `${row.doc}||${row.chunk}`, chunk: row.chunk, preview: row.preview,
        stages: ["بافت نهایی مدل"], bestRank: row.rank, cited: true, referenced: row.referenced,
        citedRank: row.rank, rerankMove: 0, group: "" });
      byDoc.set(row.doc, list);
    }
  });

  return [...byDoc.entries()].map(([doc, chunks]) => ({
    doc,
    chunks: [...chunks].sort((a, b) => a.bestRank - b.bestRank),
    cited: chunks.filter(chunk => chunk.cited).length,
    selectedIn: chunks.length,
  })).sort((a, b) => b.cited - a.cited || b.selectedIn - a.selectedIn || a.doc.localeCompare(b.doc));
}

// ------------------------------------------------------------------ diagram

function nodePosition(node: MapNode, graph: PipelineGraph): { x: number; y: number; lane: number } {
  const laneIndex = graph.lanes.findIndex(lane => lane.title === LANES[node.lane]);
  const positionInLane = graph.lanes[laneIndex].nodes.findIndex(candidate => candidate.id === node.id);
  return {
    x: graph.width - PAD - laneIndex * COL_W - NODE_W - (COL_W - NODE_W) / 2,
    y: PAD + LANE_TITLE_H + positionInLane * (NODE_H + ROW_GAP),
    lane: laneIndex,
  };
}

const ROLE_COLOR: Record<StageRole, string> = {
  gate: "var(--muted-2)", rewrite: "var(--syntax-purple)", embed: "var(--syntax-blue)",
  vector: "var(--syntax-blue)", lexical: "var(--syntax-orange)", fusion: "var(--syntax-purple)", rerank: "var(--syntax-magenta)",
  qbank: "var(--syntax-green)", image: "var(--syntax-teal)", generate: "var(--syntax-green)", vision: "var(--syntax-teal)",
  context: "var(--syntax-teal)", answer: "var(--syntax-green)", audit: "var(--syntax-orange)", other: "var(--muted-2)",
};

export function PipelineMap({ graph, selectedDoc, onSelectDoc, selectedStage, onSelectStage }: {
  graph: PipelineGraph;
  selectedDoc?: string;
  onSelectDoc?: (doc: string) => void;
  selectedStage?: number;
  onSelectStage?: (index: number) => void;
}) {
  const markerId = `rag-flow-${useId().replace(/:/g, "")}`;
  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number; lane: number }>();
    graph.nodes.forEach(node => map.set(node.id, nodePosition(node, graph)));
    return map;
  }, [graph]);

  const laneTitles = useMemo(() => graph.lanes.map((lane, index) => ({
    title: lane.title,
    x: graph.width - PAD - index * COL_W - NODE_W / 2 - (COL_W - NODE_W) / 2,
  })), [graph]);

  return (
    <svg className="rag-flow-map" viewBox={`0 0 ${graph.width} ${graph.height}`} role="group"
      aria-label="نقشه جریان خط بازیابی؛ برای بررسی جزئیات یک مرحله را انتخاب کنید">
      <defs>
        <marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5"
          markerHeight="5" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--muted-2)" />
        </marker>
      </defs>

      {laneTitles.map(lane => (
        <text key={lane.title} x={lane.x} y={PAD} fontSize="11" fontWeight="700"
          fill="var(--muted-2)" textAnchor="middle">{fitText(lane.title, COL_W - 12, 11)}</text>
      ))}

      {graph.edges.map(edge => {
        const from = positions.get(edge.from); const to = positions.get(edge.to);
        if (!from || !to) return null;
        const path = from.lane === to.lane
          ? (to.y < from.y
            ? `M ${from.x + NODE_W} ${from.y + NODE_H / 2} C ${from.x + NODE_W + 24} ${from.y + NODE_H / 2}, ${to.x + NODE_W + 24} ${to.y + NODE_H / 2}, ${to.x + NODE_W} ${to.y + NODE_H / 2}`
            : `M ${from.x + NODE_W / 2} ${from.y + NODE_H} L ${to.x + NODE_W / 2} ${to.y}`)
          : `M ${from.x} ${from.y + NODE_H / 2} C ${from.x - 46} ${from.y + NODE_H / 2}, ${to.x + NODE_W + 46} ${to.y + NODE_H / 2}, ${to.x + NODE_W} ${to.y + NODE_H / 2}`;
        const width = Math.max(1.2, Math.min(9, edge.count / 3));
        const midX = from.lane === to.lane ? from.x + NODE_W / 2 + 6
          : (from.x + to.x + NODE_W) / 2;
        const midY = from.lane === to.lane ? (from.y + NODE_H + to.y) / 2
          : (from.y + to.y + NODE_H) / 2 - 5;
        return (
          <g key={`${edge.from}->${edge.to}`}>
            <path d={path} fill="none" stroke="var(--muted-2)" strokeWidth={width}
              strokeDasharray={edge.count === 0 ? "3 5" : undefined} opacity={edge.count === 0 ? 0.4 : 0.55}
              markerEnd={`url(#${markerId})`} />
            <text x={midX} y={midY} fontSize="9" fill="var(--muted-2)" textAnchor="middle">
              {edge.count > 0 || edge.known ? `${edge.known ? "" : "≥"}${fa(edge.count)}` : ""}
            </text>
          </g>
        );
      })}

      {graph.nodes.map(node => {
        const position = positions.get(node.id);
        if (!position) return null;
        const color = ROLE_COLOR[node.role];
        const isSelected = selectedStage === node.index || (!!selectedDoc && node.docs.includes(selectedDoc));
        const select = () => {
          onSelectStage?.(node.index);
          if (!onSelectStage && node.docs.length === 1) onSelectDoc?.(node.docs[0]);
        };
        const interactive = !!onSelectStage || (!!onSelectDoc && node.docs.length === 1);
        return (
          <g key={node.id} role={interactive ? "button" : "group"} tabIndex={interactive ? 0 : undefined}
            aria-pressed={interactive ? isSelected : undefined} className={interactive ? "rag-map-node" : undefined}
            onClick={interactive ? select : undefined}
            onKeyDown={interactive ? event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } } : undefined}
            aria-label={`${node.label} · ${node.countKnown ? "" : "حداقل "}${fa(node.selected)} مورد · ${fa(node.ms, 1)} میلی‌ثانیه${node.error ? " · خطا" : ""}`}>
            <title>{`${node.label} (${node.name}) — ${fa(node.selected)} مورد در ${fa(node.ms, 1)} ms`
              + `${node.skippedReason ? ` · ${node.skippedReason}` : ""}`
              + `${node.docs.length ? `\nاسنادی که این مرحله انتخاب کرد:\n${node.docs.slice(0, 8).map(doc => shortName(doc, 46)).join("\n")}` : ""}`}</title>
            <rect x={position.x} y={position.y} width={NODE_W} height={NODE_H} rx="13"
              fill={`color-mix(in srgb, ${color} 10%, transparent)`} stroke={node.error ? "var(--syntax-magenta)" : isSelected ? color : "var(--border)"}
              strokeWidth={isSelected ? 2 : 1} />
            <rect x={position.x} y={position.y} width="4" height={NODE_H} rx="2" fill={color} />
            <text x={position.x + NODE_W - 10} y={position.y + 20} fontSize="10.5" fontWeight="700"
              fill="var(--text)" textAnchor="start">{fitText(node.label, NODE_TEXT_W, 10.5)}</text>
            <text x={position.x + NODE_W - 10} y={position.y + 36} fontSize="9.5"
              fill="var(--muted)" textAnchor="start">
              {node.skippedReason ? fitText(node.skippedReason, NODE_TEXT_W, 9.5)
                : fitText(`${fa(node.ms, 1)} ms${node.selected || node.countKnown ? ` · ${node.countKnown ? "" : "≥"}${fa(node.selected)} مورد` : ""}`, NODE_TEXT_W, 9.5)}
            </text>
            <text x={position.x + NODE_W - 10} y={position.y + 50} fontSize="9"
              fill="var(--muted-2)" textAnchor="start">
              {fitText(node.name, NODE_TEXT_W, 9)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Roles that feed the next stage side by side rather than one after another. */
const PARALLEL_ROLES: StageRole[] = ["vector", "lexical"];

interface FunnelStep { label: string; role: StageRole; count: number; known?: boolean }

/**
 * Group a shelf's counts into hand-off clusters: the two searches of one stack
 * run in parallel and both feed the fusion, so they belong in one cluster and
 * no arrow may sit between them (20 ← 3 ← 20 would read as a sequence).
 */
export function funnelClusters(steps: FunnelStep[]): FunnelStep[][] {
  const clusters: FunnelStep[][] = [];
  steps.forEach(step => {
    const last = clusters[clusters.length - 1];
    if (PARALLEL_ROLES.includes(step.role) && last?.every(other => PARALLEL_ROLES.includes(other.role))) {
      last.push(step);
      return;
    }
    clusters.push([step]);
  });
  return clusters;
}

export function FunnelStrip({ graph }: { graph: PipelineGraph }) {
  if (graph.funnels.length === 0) return null;
  return (
    <div className="space-y-2">
      {graph.funnels.map(funnel => (
        <div key={funnel.group} className="flex items-center gap-1.5 flex-wrap text-[10px]">
          <span className="text-[var(--muted-2)] font-bold">{GROUP_FA[funnel.group] ?? funnel.group}</span>
          {funnelClusters(funnel.steps).map((cluster, index) => (
            <span key={`${cluster[0].label}-${index}`} className="flex items-center gap-1.5">
              {index > 0 && <span className="text-[var(--muted-2)]">←</span>}
              <span className={`flex items-center gap-1.5 ${cluster.length > 1 ? "px-1 py-0.5 rounded-full border border-dashed border-[var(--border-strong)]" : ""}`}
                title={cluster.length > 1 ? "این جست‌وجوها موازی‌اند و هر دو به مرحلهٔ ادغام می‌دهند" : undefined}>
                {cluster.map(step => (
                  <span key={step.label} className="px-2 py-0.5 rounded-full border border-[var(--border)] bg-[var(--surface-2)] text-[var(--muted)]"
                    style={{ borderColor: `color-mix(in srgb, ${ROLE_COLOR[step.role]} 40%, transparent)` }}>
                    <span className="inline-block w-1.5 h-1.5 rounded-[2px]" style={{ backgroundColor: ROLE_COLOR[step.role] }} /> {step.label.split(" (")[0]} {step.known ? "" : "≥"}{fa(step.count)}
                  </span>
                ))}
              </span>
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------- rank chart

const CHART_W = 780;
const CHART_PAD = 74;
/**
 * Right gutter reserved for the per-chunk labels. A label is drawn to the
 * right of its track's first point, so the plot has to stop short of the
 * canvas edge or the label runs off it and the SVG viewport clips the name.
 */
const CHART_LABEL_W = 170;

export function ChunkRankChart({ chart, docFilter, onSelectDoc }: {
  chart: RankChart; docFilter?: string; onSelectDoc?: (doc: string) => void;
}) {
  if (chart.steps.length === 0 || chart.tracks.length === 0) {
    return <p className="text-[11px] text-[var(--muted-2)]">این اجرا مرحلهٔ رتبه‌بندی تکه‌ای ثبت نکرده است.</p>;
  }
  const shown = chart.tracks.slice(0, 14);
  const rowH = 22;
  const height = 40 + shown.length * rowH;
  // Right-to-left: the first search sits at the right edge.
  const plotRight = CHART_W - CHART_LABEL_W;
  const xFor = (index: number) => plotRight - index * ((plotRight - CHART_PAD) / Math.max(1, chart.steps.length - 1));
  const yFor = (rank: number) => 30 + ((rank - 1) / Math.max(1, chart.maxRank - 1)) * (height - 60);

  return (
    <div className="space-y-2">
      <svg className="rag-rank-chart" viewBox={`0 0 ${CHART_W} ${height}`} role="group"
        aria-label="تغییر رتبه هر تکه در مرحله‌های بازیابی" style={{ maxHeight: 520 }}>
        {chart.steps.map((step, index) => (
          <g key={step.name}>
            <line x1={xFor(index)} y1="18" x2={xFor(index)} y2={height - 22} stroke="var(--border)" strokeDasharray="3 6" />
            <text x={xFor(index)} y="12" fontSize="10" fill="var(--muted-2)" textAnchor="middle">{step.label}</text>
          </g>
        ))}
        {[...new Set([1, Math.max(1, Math.round(chart.maxRank / 2)), chart.maxRank])].map(rank => (
          <text key={rank} x={8} y={yFor(rank) + 3} fontSize="9" fill="var(--muted-2)" textAnchor="end">
            رتبه {fa(rank)}
          </text>
        ))}

        {shown.map(track => {
          const points = track.grid.map((rank, index) => rank == null ? null : { x: xFor(index), y: yFor(rank) });
          const segments: string[] = [];
          let current: string[] = [];
          points.forEach(point => {
            if (point) current.push(`${current.length === 0 ? "M" : "L"} ${point.x} ${point.y}`);
            else if (current.length > 1) { segments.push(current.join(" ")); current = []; }
            else current = [];
          });
          if (current.length > 1) segments.push(current.join(" "));
          const colour = track.cited ? "var(--syntax-green)" : track.rerankMove > 0 ? "var(--syntax-magenta)" : "var(--muted-2)";
          const label = `${shortName(track.doc)} · تکه ${track.chunk}`;
          const first = points.find(point => point != null);
          return (
            <g key={track.key} role={onSelectDoc ? "button" : "group"} tabIndex={onSelectDoc ? 0 : undefined}
              aria-label={`${track.doc} · تکه ${track.chunk} · ${track.cited ? "در بافت مدل" : "کاندید بازیابی"}`}
              onKeyDown={onSelectDoc ? event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelectDoc(track.doc); } } : undefined}
              onClick={() => onSelectDoc?.(track.doc)}
              className={onSelectDoc ? "cursor-pointer" : undefined}>
              <title>{`${shortName(track.doc, 46)} · تکه ${track.chunk}${track.cited ? ` · منبع ${track.citedRank} در بافت مدل` : " · کاندید بازیابی"}${track.referenced ? " · ارجاع شماره‌دار در پاسخ" : ""}${track.rerankMove ? ` · جابه‌جایی رتبه ${fa(track.rerankMove)}` : ""}`}</title>
              {segments.map((segment, index) => (
                <path key={index} d={segment} fill="none" stroke={colour}
                  strokeWidth={track.cited ? 2.4 : 1.6} opacity={track.cited ? 1 : 0.75} />
              ))}
              {points.map((point, index) => point && (
                <circle key={index} cx={point.x} cy={point.y} r={track.cited ? 4 : 3}
                  fill={colour} stroke="var(--surface)" strokeWidth="1" />
              ))}
              {first && (
                // Labels live in the right gutter, so they never sit on the lines.
                <text x={first.x + 10} y={first.y + 3} fontSize="9" fill={track.cited ? "var(--text)" : "var(--muted)"} textAnchor="end">
                  {fitText(label, CHART_LABEL_W - 20, 9)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <p className="text-[10px] text-[var(--muted-2)]">
        هر خط یک تکه است. سبز = در بافت مدل، صورتی = بازرتبه‌بندی بالا آورده، طوسی = کاندید بازیابی.
        جای خالی یعنی رتبه در این جدول ثبت نشده؛ به‌تنهایی ثابت نمی‌کند تکه حذف شده است.
        {chart.tracks.length > shown.length ? ` ${fa(shown.length)} از ${fa(chart.tracks.length)} مسیر نمایش داده شده؛ برای بررسی بقیه یک سند را انتخاب کنید.` : ""}
        {docFilter ? ` فیلتر: ${shortName(docFilter, 40)}` : ""}
      </p>
    </div>
  );
}

// ------------------------------------------------------- files and chunk text

export function DocumentChunkPanel({ docs, selectedDoc, onSelectDoc }: {
  docs: DocCoverage[]; selectedDoc?: string; onSelectDoc?: (doc: string) => void;
}) {
  const [openChunk, setOpenChunk] = useState("");
  if (docs.length === 0) {
    return <p className="text-[11px] text-[var(--muted-2)]">هیچ تکه‌ای در این اجرا انتخاب نشد.</p>;
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        <button type="button" aria-pressed={!selectedDoc} onClick={() => onSelectDoc?.("")}
          className={`text-[10px] px-2 py-0.5 rounded-full border ${!selectedDoc
            ? "border-[var(--accent)] text-[var(--accent)]"
            : "border-[var(--border)] text-[var(--muted)]"}`}>
          همهٔ اسناد ({fa(docs.length)})
        </button>
        {docs.map(doc => (
          <button key={doc.doc} type="button" aria-pressed={selectedDoc === doc.doc}
            onClick={() => onSelectDoc?.(selectedDoc === doc.doc ? "" : doc.doc)}
            className={`text-[10px] px-2 py-0.5 rounded-full border ${selectedDoc === doc.doc
              ? "border-[var(--accent)] text-[var(--accent)]"
              : "border-[var(--border)] text-[var(--muted)]"}`}>
            {shortName(doc.doc, 30)} ({fa(doc.selectedIn)} تکه{doc.cited ? `، ${fa(doc.cited)} منبع` : ""})
          </button>
        ))}
      </div>

      {docs.filter(doc => !selectedDoc || doc.doc === selectedDoc).map(doc => (
        <div key={doc.doc} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-2)]/40 p-3 space-y-2">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-xs font-bold text-[var(--text)]">{shortName(doc.doc, 52)}</span>
            <span className="text-[10px] text-[var(--muted-2)]">
              {fa(doc.selectedIn)} تکه ثبت‌شده · {fa(doc.cited)} در بافت مدل
            </span>
          </div>
          <ul className="space-y-1.5">
            {doc.chunks.map(chunk => {
              const open = openChunk === chunk.key;
              return (
                <li key={chunk.key} className="rounded-xl border border-[var(--border)] bg-[var(--surface)]/60">
                  <button type="button" aria-expanded={open}
                    onClick={() => setOpenChunk(open ? "" : chunk.key)}
                    className="w-full text-start px-2.5 py-2 flex items-baseline gap-2 flex-wrap">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-md border ${chunk.cited
                      ? "border-emerald-400/60 text-emerald-400"
                      : "border-[var(--border)] text-[var(--muted-2)]"}`}>
                      {chunk.cited ? `منبع ${fa(chunk.citedRank ?? 0)} در بافت مدل` : "کاندید بازیابی"}
                    </span>
                    <span className="text-[11px] text-[var(--text)]">تکه {chunk.chunk}</span>
                    {chunk.referenced && <span className="text-[10px] text-emerald-400">ارجاع شماره‌دار در پاسخ</span>}
                    <span className="text-[10px] text-[var(--muted-2)]">بهترین رتبه {fa(chunk.bestRank)}</span>
                    {chunk.rerankMove > 0 && (
                      <span className="text-[10px] text-[var(--syntax-magenta)] inline-flex items-center gap-0.5"><TrendUpIcon size={9} />{fa(chunk.rerankMove)} رتبه</span>
                    )}
                    <span className="text-[10px] text-[var(--muted-2)] ms-auto">{chunk.stages.join(" ← ")}</span>
                  </button>
                  {open && (
                    <div className="px-2.5 pb-2.5 space-y-1.5">
                      <p className="text-[11px] leading-relaxed text-[var(--muted)] whitespace-pre-wrap break-words">
                        {chunk.preview || "متن این تکه در رد ثبت نشده است."}
                      </p>
                      <p className="text-[10px] text-[var(--muted-2)]">
                        مرحله‌هایی که این تکه را انتخاب کردند: {chunk.stages.join(" ← ")}
                      </p>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ wrapper

// ------------------------------------------------------------ source mind map

/**
 * Display limits for the source map, owned by the RAG panel's settings button.
 *
 * They only decide how much is *drawn*: every number the map prints still comes
 * from the trace, and the map says how many records it left out.
 */
export interface MindMapOptions {
  /** Documents drawn before the "showing N of M" note; `0` means no limit. */
  docCap?: number;
  /** Chunk leaves drawn under a document before its expand control; `0` hides them. */
  chunksPerDoc?: number;
}

const SHELF_ORDER = ["books", "qbank", "image"];
/** One row of leaves per document, so expanding never re-flows the tree. */
const MAX_LEAVES = 8;

/**
 * The shelf a document was actually retrieved from, read from the stages that
 * ranked its chunks. A book page transcribed into the question bank is stored
 * as `...::p40`, but the file name alone does not prove which shelf found it.
 */
export function shelfKeyOf(doc: DocCoverage): string {
  const counts = new Map<string, number>();
  doc.chunks.forEach(chunk => {
    if (chunk.group) counts.set(chunk.group, (counts.get(chunk.group) ?? 0) + 1);
  });
  let best = "";
  let bestCount = 0;
  counts.forEach((count, key) => { if (count > bestCount) { best = key; bestCount = count; } });
  return best;
}

export function shelfLabelOf(group: string): string {
  return group ? GROUP_FA[group] ?? group : "بدون قفسه";
}

// Fixed geometry (no measured text) keeps the server render identical to the
// browser one: the tree is drawn in a 720-unit coordinate space and scaled by
// the container, exactly like the pipeline map. The width is chosen so the map
// renders close to 1:1 inside the admin panel instead of shrinking its labels.
const M_W = 720;
const M_PAD = 18;
const M_ROOT_W = 268;
const M_ROOT_H = 54;
const M_TRUNK_GAP = 28;
const M_CARD_W = 204;
const M_CARD_H = 56;
const M_CARD_GAP = 12;
const M_CHIP_W = 206;
const M_CHIP_H = 26;
/** A shelf chip holds two labels side by side; this is each one's budget. */
const M_CHIP_LABEL_W = 88;
const M_LEAF_ROW = 38;
/** Distance from a card's bottom edge down to the centre of its chunk dots. */
const M_LEAF_DROP = 19;
/** A chunk dot's radius plus its widest stroke - the canvas must clear it. */
const M_LEAF_R = 11.5;
const M_ROW_GAP = 26;
const M_BAND_GAP = 18;

export interface MindShelf { key: string; label: string; docs: DocCoverage[]; cited: number }

export interface MindBand {
  key: string; label: string; cited: number; chipY: number;
  cards: { doc: DocCoverage; x: number; y: number }[];
  /** Org-chart bus per row: the horizontal line the cards of a row hang from. */
  busY: number[];
}

export interface MindLayout {
  width: number; height: number;
  rootX: number; rootY: number; rootW: number; rootH: number;
  trunkX: number; trunkBottom: number;
  cardRight: number; perRow: number; leaves: boolean;
  bands: MindBand[];
}

/**
 * Lay the tree out right-to-left: the question sits at the top right, every
 * shelf hangs off the trunk below it, and the documents of a shelf wrap into
 * rows under their shelf chip. Deterministic on purpose - no measurement.
 */
export function buildMindLayout(shelves: MindShelf[], chunksPerDoc: number): MindLayout {
  const cardRight = M_W - M_PAD - M_TRUNK_GAP;
  const trunkX = cardRight + M_TRUNK_GAP / 2;
  const perRow = Math.max(1, Math.floor((cardRight - M_PAD + M_CARD_GAP) / (M_CARD_W + M_CARD_GAP)));
  const leaves = chunksPerDoc > 0;
  const rowAdvance = M_CARD_H + (leaves ? M_LEAF_ROW : 0) + M_ROW_GAP;
  const rootY = M_PAD;
  let cursor = rootY + M_ROOT_H + 30;
  const bands: MindBand[] = [];
  shelves.forEach(shelf => {
    const chipY = cursor;
    const cards: MindBand["cards"] = [];
    const busY: number[] = [];
    shelf.docs.forEach((doc, index) => {
      const row = Math.floor(index / perRow);
      const column = index % perRow;
      const y = chipY + M_CHIP_H + 10 + row * rowAdvance;
      cards.push({ doc, x: cardRight - M_CARD_W - column * (M_CARD_W + M_CARD_GAP), y });
      if (busY[row] === undefined) busY[row] = y - 11;
    });
    bands.push({ key: shelf.key, label: shelf.label, cited: shelf.cited, chipY, cards, busY });
    cursor = chipY + M_CHIP_H + 10 +
      Math.max(1, Math.ceil(shelf.docs.length / perRow)) * rowAdvance + M_BAND_GAP;
  });
  const last = bands[bands.length - 1];
  const trunkBottom = !last ? rootY + M_ROOT_H
    : last.cards.length ? Math.max(...last.cards.map(card => card.y + M_CARD_H / 2))
      : last.chipY + M_CHIP_H;
  // The chunk dots hang below their card, so the canvas has to clear the dot's
  // far edge - not just the card's - or the last row is clipped by the viewBox.
  const contentBottom = Math.max(rootY + M_ROOT_H,
    ...bands.map(band => band.cards.reduce(
      (bottom, card) => Math.max(bottom, card.y + M_CARD_H + (leaves ? M_LEAF_DROP + M_LEAF_R : 0)),
      band.chipY + M_CHIP_H)));
  return {
    width: M_W, height: Math.max(rootY + M_ROOT_H + 80, contentBottom + M_PAD),
    rootX: M_W - M_PAD - M_ROOT_W, rootY, rootW: M_ROOT_W, rootH: M_ROOT_H,
    trunkX, trunkBottom, cardRight, perRow, leaves, bands,
  };
}

/**
 * Chunk ids arrive from the trace as text. Numeric ones read better as Persian
 * digits, matching the rest of the panel; anything else stays as recorded.
 */
function digit(value: string): string {
  const parsed = Number(value);
  return value.trim() !== "" && Number.isFinite(parsed) ? fa(parsed) : value;
}

/** Leaves to draw for one document, and how many live in the detail list only. */
function leavesOf(doc: DocCoverage, chunksPerDoc: number, isExpanded: boolean) {
  // "Documents only" means no leaves and no expand control, so nothing in the
  // map changes size when the setting is turned off.
  if (chunksPerDoc <= 0) return { shown: [] as DocChunk[], hidden: 0, more: 0 };
  const limit = isExpanded ? MAX_LEAVES : chunksPerDoc;
  const shown = doc.chunks.slice(0, limit);
  return { shown, hidden: Math.max(0, doc.chunks.length - limit), more: Math.max(0, doc.chunks.length - chunksPerDoc) };
}

export function SourceMindMap({ trace, docs, selectedDoc = "", onSelectDoc, docCap = 12, chunksPerDoc = 3 }: {
  trace: TraceRecord; docs: DocCoverage[]; selectedDoc?: string; onSelectDoc: (doc: string) => void;
} & MindMapOptions) {
  const [search, setSearch] = useState("");
  const [suppliedOnly, setSuppliedOnly] = useState(false);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [focusChunk, setFocusChunk] = useState("");
  const [hovered, setHovered] = useState("");
  const normalize = (value: string) => value.replace(/ي/g, "ی").replace(/ك/g, "ک").replace(/\u200c/g, " ").toLowerCase();
  const query = normalize(search);
  const perChunk = Math.max(0, Math.min(MAX_LEAVES, Math.round(chunksPerDoc)));
  const cap = Math.max(0, Math.round(docCap));
  const matched = docs.filter(doc => (!suppliedOnly || doc.cited > 0) && normalize(doc.doc).includes(query));
  const visible = cap > 0 ? matched.slice(0, cap) : matched;
  const selected = docs.find(doc => doc.doc === selectedDoc);
  const contextChunks = docs.reduce((sum, doc) => sum + doc.cited, 0);
  const recordedChunks = docs.reduce((sum, doc) => sum + doc.chunks.length, 0);

  // Documents are grouped by the shelf that found them, so the map draws the
  // real retrieval path instead of one flat row of files.
  const shelfMap = new Map<string, DocCoverage[]>();
  visible.forEach(doc => { const key = shelfKeyOf(doc); shelfMap.set(key, [...(shelfMap.get(key) ?? []), doc]); });
  const shelves: MindShelf[] = [...shelfMap.entries()]
    .map(([key, group]) => ({ key, label: shelfLabelOf(key), docs: group,
      cited: group.reduce((sum, doc) => sum + doc.cited, 0) }))
    .sort((a, b) => {
      const orderA = SHELF_ORDER.indexOf(a.key), orderB = SHELF_ORDER.indexOf(b.key);
      return (orderA < 0 ? SHELF_ORDER.length : orderA) - (orderB < 0 ? SHELF_ORDER.length : orderB)
        || b.docs.length - a.docs.length || a.key.localeCompare(b.key);
    });
  const layout = buildMindLayout(shelves, perChunk);
  const toggle = (doc: string) => setExpanded(current =>
    current.includes(doc) ? current.filter(item => item !== doc) : [...current, doc]);

  return <section className="rag-source-explorer" aria-label="نقشهٔ ذهنی منابع">
    <div className="rag-section-heading">
      <div><h3>از پرسش تا تکهٔ کتاب</h3></div>
      <span>{`${fa(visible.length)} از ${fa(docs.length)} سند نمایش داده شده · در کل ردیف‌های رد: ${fa(contextChunks)} تکه در بافت مدل، ${fa(recordedChunks)} تکهٔ ثبت‌شده`}</span>
    </div>
    <div className="rag-source-tools">
      <label>پیدا کردن سند<input value={search} onChange={event => setSearch(event.target.value)} placeholder="نام کتاب یا صفحه…" /></label>
      <label><input type="checkbox" checked={suppliedOnly} onChange={event => setSuppliedOnly(event.target.checked)} />فقط منابعِ بافت مدل</label>
      {perChunk > 0 && <button type="button" onClick={() => setExpanded(expanded.length ? [] : matched.map(doc => doc.doc))}>
        {expanded.length ? "بستن تکه‌های اضافه" : "نمایش همهٔ تکه‌ها"}
      </button>}
      {selectedDoc && <button type="button" onClick={() => { onSelectDoc(""); setFocusChunk(""); }}>حذف انتخاب سند</button>}
    </div>
    <div className="rag-source-layout">
      <div className="rag-source-canvas">
        <svg className="rag-source-map" viewBox={`0 0 ${layout.width} ${layout.height}`} role="group"
          aria-label={`نقشهٔ سلسله‌مراتبی منابع: پرسش، ${fa(shelves.length)} قفسه، ${fa(visible.length)} سند و تکه‌هایشان`}>
          <title>مسیر پرسش تا تکه: پرسش ← قفسه ← سند ← تکه</title>
          <g fill="none" stroke="var(--border-strong)" strokeWidth="1">
            <path d={`M ${layout.rootX + layout.rootW} ${layout.rootY + layout.rootH / 2} H ${layout.trunkX} V ${layout.trunkBottom}`} />
            {layout.bands.map(band => <g key={`spine-${band.key}`}>
              <path d={`M ${layout.trunkX} ${band.chipY + M_CHIP_H / 2} H ${layout.cardRight}`} />
              {band.busY.map((bus, row) => {
                const centers = band.cards.filter(card => card.y > bus && card.y < bus + M_ROW_GAP)
                  .map(card => card.x + M_CARD_W / 2);
                if (!centers.length) return null;
                return <path key={`bus-${band.key}-${row}`}
                  d={`M ${layout.cardRight - M_CARD_W / 2} ${bus} H ${Math.min(...centers)}`} />;
              })}
            </g>)}
          </g>
          {layout.bands.map(band => <g key={`drops-${band.key}`} fill="none" stroke="var(--border-strong)" strokeWidth="1">
            {band.cards.map(card => <path key={card.doc.doc} d={`M ${card.x + M_CARD_W / 2} ${card.y - 11} V ${card.y}`} />)}
          </g>)}

          <rect x={layout.rootX} y={layout.rootY} width={layout.rootW} height={layout.rootH} rx="13"
            fill="var(--surface-2)" stroke="var(--accent)" strokeWidth="1.5" />
          <text x={layout.rootX + layout.rootW - 14} y={layout.rootY + 21} textAnchor="start" fontSize="10" fill="var(--accent)">پرسش این اجرا</text>
          <text x={layout.rootX + layout.rootW - 14} y={layout.rootY + 40} textAnchor="start" fontSize="11.5" fill="var(--text)">
            {fitText(trace.question || "پرسش ثبت نشده", M_ROOT_W - 28, 11.5)}
          </text>

          {layout.bands.map(band => <g key={band.key}>
            <rect x={layout.cardRight - M_CHIP_W} y={band.chipY} width={M_CHIP_W} height={M_CHIP_H} rx="13"
              fill="var(--surface-2)" stroke={band.cited > 0 ? "var(--accent)" : "var(--border-strong)"} />
            <text x={layout.cardRight - 12} y={band.chipY + 17} textAnchor="start" fontSize="10.5" fill="var(--text)">
              {fitText(`${band.label} · ${fa(band.cards.length)} سند`, M_CHIP_LABEL_W, 10.5)}
            </text>
            <text x={layout.cardRight - M_CHIP_W + 12} y={band.chipY + 17} textAnchor="end" fontSize="9.5" fill="var(--muted)">
              {fitText(`${fa(band.cited)} تکه در بافت`, M_CHIP_LABEL_W, 9.5)}
            </text>
            {band.cards.map(card => {
              const active = selectedDoc === card.doc.doc;
              const dimmed = !!hovered && hovered !== card.doc.doc && !active;
              const isExpanded = expanded.includes(card.doc.doc);
              const { shown, hidden, more } = leavesOf(card.doc, perChunk, isExpanded);
              const centerX = card.x + M_CARD_W / 2;
              const step = shown.length > 1 ? Math.min(26, (M_CARD_W - 18) / shown.length) : 26;
              const firstLeafX = centerX + ((shown.length - 1) * step) / 2;
              const leafY = card.y + M_CARD_H + M_LEAF_DROP;
              const select = () => { onSelectDoc(active ? "" : card.doc.doc); setFocusChunk(""); };
              return <g key={card.doc.doc} opacity={dimmed ? 0.45 : 1}
                onMouseEnter={() => setHovered(card.doc.doc)} onMouseLeave={() => setHovered("")}>
                <g className="rag-mind-card" role="button" tabIndex={0} aria-pressed={active}
                  aria-label={`${card.doc.doc}، ${fa(card.doc.selectedIn)} تکهٔ ثبت‌شده، ${fa(card.doc.cited)} تکه در بافت مدل`}
                  onClick={select} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } }}>
                  <title>{`${card.doc.doc}\n${fa(card.doc.selectedIn)} تکه در این رد · ${fa(card.doc.cited)} تکه در بافت نهایی`
                    + `\nقفسه: ${band.label}`}</title>
                  <rect x={card.x} y={card.y} width={M_CARD_W} height={M_CARD_H} rx="6"
                    fill={active ? "var(--accent-soft)" : "var(--surface-2)"}
                    stroke={active ? "var(--accent)" : "var(--border-strong)"} />
                  <rect x={card.x + M_CARD_W - 3} y={card.y + 14} width="3" height="28" rx="1" fill="var(--accent)" />
                  <text x={card.x + M_CARD_W - 14} y={card.y + 22} textAnchor="start" fontSize="11" fill="var(--text)">{fitText(shortName(card.doc.doc, 34), M_CARD_W - 28, 11)}</text>
                  <text x={card.x + M_CARD_W - 14} y={card.y + 42} textAnchor="start" fontSize="9" fill="var(--muted)">
                    {fitText(`${fa(card.doc.selectedIn)} تکه در رد · ${fa(card.doc.cited)} در بافت`, M_CARD_W - 28, 9)}
                  </text>
                </g>
                {shown.map((chunk, index) => {
                  const x = firstLeafX - index * step;
                  const focused = focusChunk === chunk.key;
                  const tone = chunk.cited ? "var(--accent)" : "var(--border-strong)";
                  const open = () => { onSelectDoc(card.doc.doc); setFocusChunk(focused ? "" : chunk.key); };
                  return <g key={chunk.key} role="button" tabIndex={0} aria-pressed={focused}
                    aria-label={`تکهٔ ${digit(chunk.chunk)} از ${card.doc.doc} · ${chunk.cited ? `در بافت مدل، منبع ${fa(chunk.citedRank ?? 0)}` : "کاندید بازیابی"} · بهترین رتبه ${fa(chunk.bestRank)}`}
                    onClick={open} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } }}>
                    <title>{`تکه ${digit(chunk.chunk)}\n${chunk.preview || "پیش‌نمایش ذخیره نشده"}`}</title>
                    <circle cx={x} cy={leafY} r="10.5" fill={chunk.cited ? "var(--accent)" : "var(--surface)"}
                      stroke={chunk.rerankMove > 0 ? "var(--syntax-magenta)" : tone} strokeWidth={focused ? 2.6 : chunk.rerankMove > 0 ? 2 : 1.2}
                      strokeDasharray={chunk.cited ? undefined : "2.5 3"} />
                    <text x={x} y={leafY + 3} textAnchor="middle" fontSize="8.5"
                      fill={chunk.cited ? "var(--surface)" : "var(--muted)"}>{fitText(digit(chunk.chunk), 19, 8.5)}</text>
                  </g>;
                })}
                {more > 0 && <g role="button" tabIndex={0} aria-expanded={isExpanded}
                  aria-label={`${fa(card.doc.chunks.length)} تکهٔ این سند؛ ${isExpanded ? "بستن تکه‌های اضافه" : "نمایش تکه‌های بیشتر"}`}
                  onClick={() => toggle(card.doc.doc)}
                  onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(card.doc.doc); } }}>
                  <circle cx={firstLeafX - shown.length * step} cy={leafY} r="9.5" fill="var(--surface)"
                    stroke="var(--border-strong)" strokeDasharray="2.5 3" />
                  <text x={firstLeafX - shown.length * step} y={leafY + 3} textAnchor="middle" fontSize="8.5" fill="var(--muted)">
                    {fitText(isExpanded ? "−" : `+${fa(hidden)}`, 17, 8.5)}
                  </text>
                </g>}
              </g>;
            })}
          </g>)}
        </svg>
        {!matched.length && <p className="rag-note">سندی با این فیلتر در رد ثبت نشده است.</p>}
        {cap > 0 && matched.length > cap && <p className="rag-note">
          {`${fa(cap)} از ${fa(matched.length)} سند رسم شده؛ بقیه را با جست‌وجو یا فهرست تکه‌ها ببین.`}
        </p>}
        <p className="rag-note">
          خط پیوسته: سند در قفسه‌ای که آن را بازیابی کرد · دایره: تکهٔ سند؛ توپر = در بافت مدل،
          خط‌چین = کاندید بازیابی، حاشیهٔ صورتی = بازرتبه‌بندی بالا آورده. عدد داخل دایره شمارهٔ تکه است، نه رتبه.
          جای گره‌ها فقط برای خوانایی است؛ اندازه و فاصلهٔ شکل‌ها فاصلهٔ معنایی یا اندازهٔ کتابخانه را نشان نمی‌دهد.
        </p>
      </div>
      <aside className="rag-source-detail" aria-label="تکه‌های سند انتخاب‌شده">
        {selected ? <><h4>{selected.doc}</h4>
          <p className="rag-note">
            {`${fa(selected.selectedIn)} تکه در این رد · ${fa(selected.cited)} تکه در بافت نهایی`
              + `${selected.cited > 0 ? "" : " · هیچ تکه‌ای از این سند به بافت مدل نرسید"}`
              + ` · قفسه: ${shelfLabelOf(shelfKeyOf(selected))}`}
          </p>
          {focusChunk && <p className="rag-source-focus">تکهٔ نشان‌شده در نقشه روشن شده است.</p>}
          {selected.chunks.map(chunk => <details key={chunk.key} open={focusChunk === chunk.key}>
            <summary>تکهٔ {digit(chunk.chunk)} <span>{chunk.cited ? `بافت #${fa(chunk.citedRank ?? 0)}` : "کاندید"}</span></summary>
            <p>{chunk.preview || "پیش‌نمایش متن ذخیره نشده است."}</p>
            <small>بهترین رتبه {fa(chunk.bestRank)}{chunk.rerankMove ? ` · جابه‌جایی ${fa(chunk.rerankMove)}` : ""}</small>
            {chunk.group && <small>قفسه: {shelfLabelOf(chunk.group)}</small>}
            <small>{chunk.stages.join(" ← ")}</small>
            {chunk.referenced && <strong>ارجاع شماره‌دار در پاسخ</strong>}
          </details>)}
          {perChunk > 0 && selected.chunks.length > MAX_LEAVES && <p className="rag-note">
            {`نقشه تا ${fa(MAX_LEAVES)} تکه از هر سند رسم می‌کند؛ همهٔ ${fa(selected.chunks.length)} تکه در همین فهرست آمده‌اند.`}
          </p>}
        </>
        : <div className="rag-source-empty">
          <svg width="44" height="44" viewBox="0 0 44 44" fill="none" stroke="currentColor">
            <circle cx="22" cy="22" r="6" /><circle cx="22" cy="22" r="17" strokeDasharray="2 4" />
            <path d="M22 0v10m0 24v10M0 22h10m24 0h10" />
          </svg>
          <h4>یک سند را دنبال کن</h4>
          <p>کتاب را از نقشه انتخاب کن تا متن تکه‌ها، رتبه و ورود آن‌ها به بافت مدل روشن شود.</p>
        </div>}
      </aside>
    </div>
  </section>;
}

/**
 * Payload of GET /api/admin/rag/traces/{id}/embedding-map.
 *
 * The backend reads the retrieved chunks' vectors back out of Chroma and works
 * out where the query sits among them; the client infers nothing, and a run
 * that recorded no cosine-scored vector search simply has no `maps`.
 */
export interface EmbeddingMapPoint {
  id: string; x: number; y: number; doc: string;
  chunk: string | number; rank: string | number; score: number;
  preview: string; shelf?: string;
}
export interface EmbeddingMapRecord {
  stage: string; collection: string; shelf: string; shelf_label: string;
  point_count: number; recorded_rows: number; missing_vectors: number;
  dimensions: number; metric: string; components: number;
  explained_variance_ratio: number[];
  query: { x: number; y: number } | null;
  points: EmbeddingMapPoint[];
}
export interface EmbeddingMapSkipped {
  collection: string; stage: string; reason: string;
  found_vectors: number; recorded_rows: number;
}
export interface EmbeddingMapPayload {
  trace_id: string; maps: EmbeddingMapRecord[]; skipped: EmbeddingMapSkipped[];
  limitations: string[]; notice?: string; reason?: string;
}

const SCATTER_W = 760;
const SCATTER_H = 300;
/** Gutter reserved for the axis numbers, so a tick never sits on the plot. */
const SCATTER_FRAME = { left: 42, right: 54, top: 16, bottom: 34 };

/**
 * A recorded candidate, placed in the canvas.
 *
 * `strongest` marks the three highest similarities: the map is a projection, so
 * a compact cluster is what "these chunks are close to each other" looks like,
 * and the top of the ranking is what a reader looks for first.
 */
export interface ScatterPoint extends EmbeddingMapPoint {
  cx: number; cy: number; strongest: boolean;
}
export interface ScatterGeometry {
  width: number; height: number;
  left: number; right: number; top: number; bottom: number;
  points: ScatterPoint[];
  query: { cx: number; cy: number } | null;
  extent: { x: [number, number]; y: [number, number] };
  strongest: number;
}

/**
 * Place the vectors and the query inside the canvas.
 *
 * The extents come from the data (query included, so a query that sits away
 * from its results is drawn where it is instead of being clamped onto the
 * frame). The first principal axis grows leftwards, matching the right-to-left
 * reading order of every other map in the panel.
 */
export function scatterGeometry(
  record: EmbeddingMapRecord, frame = SCATTER_FRAME, width = SCATTER_W, height = SCATTER_H,
): ScatterGeometry {
  const points = (record.points ?? []).filter(point => Number.isFinite(point.x) && Number.isFinite(point.y));
  const query = record.query && Number.isFinite(record.query.x) && Number.isFinite(record.query.y)
    ? record.query : null;
  const bounds = (values: number[]): [number, number] => {
    const low = Math.min(...values), high = Math.max(...values);
    // One point, or several that coincide, still needs a box to sit inside.
    return high - low < 1e-6 ? [low - 1, high + 1] : [low, high];
  };
  const extent = {
    x: bounds(points.map(point => point.x).concat(query ? [query.x] : [])),
    y: bounds(points.map(point => point.y).concat(query ? [query.y] : [])),
  };
  const left = frame.left, right = width - frame.right;
  const top = frame.top, bottom = height - frame.bottom;
  const cx = (value: number) => right - ((value - extent.x[0]) / (extent.x[1] - extent.x[0])) * (right - left);
  const cy = (value: number) => bottom - ((value - extent.y[0]) / (extent.y[1] - extent.y[0])) * (bottom - top);
  const ranked = [...points].sort((a, b) => b.score - a.score).slice(0, 3);
  const strong = new Set(ranked.map(point => point.id));
  return {
    width, height, left, right, top, bottom,
    points: points.map(point => ({ ...point, cx: cx(point.x), cy: cy(point.y), strongest: strong.has(point.id) })),
    query: query ? { cx: cx(query.x), cy: cy(query.y) } : null,
    extent, strongest: ranked.length,
  };
}

/**
 * One collection's vector space: the retrieved chunks and the query among them.
 *
 * Clicking a point selects its document in the source map above, so a dot is
 * never a dead end - the chunk's text and rank stay one step away.
 */
function SemanticScatter({ record, onSelectDoc }: {
  record: EmbeddingMapRecord; onSelectDoc?: (doc: string) => void;
}) {
  const geometry = scatterGeometry(record);
  const variance = record.explained_variance_ratio ?? [];
  const share = (value: number | undefined) => `${fa(Math.round((value ?? 0) * 100))}٪`;
  const shelf = record.shelf_label || GROUP_FA[record.shelf] || "مجموعهٔ برداری";
  const selectable = (doc: string) => onSelectDoc && doc ? onSelectDoc : undefined;
  // The label sits on the left of the marker (right-edge anchored - `start` in
  // this RTL page) unless there is no room there, in which case it flips to the
  // marker's right and is pinned by its left edge (`end`), like the rank chart.
  const roomAtLeft = geometry.query ? geometry.query.cx - 14 > geometry.left + 46 : false;
  const queryLabel: { x: number; y: number; anchor: "start" | "end" } | null = geometry.query
    ? { x: roomAtLeft ? geometry.query.cx - 13 : geometry.query.cx + 13,
        anchor: roomAtLeft ? "start" : "end",
        y: Math.min(Math.max(geometry.query.cy + 3.5, geometry.top + 10), geometry.bottom - 4) }
    : null;
  return <div className="rag-embedding-map-block">
    <div className="rag-section-heading">
      <div><span className="text-[11px] text-[var(--muted-2)]">فضای برداری همین اجرا</span><h3>{shelf} · {fitText(text(record.collection) || "نام مجموعه ثبت نشده", 260, 16)}</h3></div>
      <span>{fa(record.point_count)} بردار بازیابی‌شده از {fa(record.recorded_rows)} ردیف ثبت‌شده · {fa(record.dimensions)} بُعد{record.missing_vectors > 0 ? ` · ${fa(record.missing_vectors)} بردار ذخیره‌نشده` : ""}</span>
    </div>
    <div className="rag-map-scroll">
      <svg className="rag-embedding-map" viewBox={`0 0 ${geometry.width} ${geometry.height}`} role="group"
        aria-label={`نقشهٔ دوبعدی ${fa(record.point_count)} کاندید برداری و بردار پرسش در مجموعهٔ ${text(record.collection)}`}>
        <title>{`دو جهت اصلی نخست همین کاندیدها، با ${share(variance[0])} و ${share(variance[1])} از واریانس`}</title>
        <rect x={geometry.left} y={geometry.top} width={geometry.right - geometry.left}
          height={geometry.bottom - geometry.top} rx="6" fill="var(--surface)" stroke="var(--border)" />
        {/* Axis read-outs at both ends: a projection can be read in reverse, so
            the numbers - not an arrow - are what fixes the orientation. */}
        <text x={geometry.left} y={geometry.bottom + 15} fontSize="9" fill="var(--muted-2)" textAnchor="end">
          {fa(geometry.extent.x[1], 3)}
        </text>
        <text x={geometry.right} y={geometry.bottom + 15} fontSize="9" fill="var(--muted-2)" textAnchor="start">
          {fa(geometry.extent.x[0], 3)}
        </text>
        <text x={geometry.left - 7} y={geometry.top + 10} fontSize="9" fill="var(--muted-2)" textAnchor="start">
          {fa(geometry.extent.y[1], 3)}
        </text>
        <text x={geometry.left - 7} y={geometry.bottom} fontSize="9" fill="var(--muted-2)" textAnchor="start">
          {fa(geometry.extent.y[0], 3)}
        </text>
        {geometry.points.map(point => <g key={point.id} role={onSelectDoc ? "button" : "group"}
          tabIndex={onSelectDoc ? 0 : undefined} aria-label={`${point.doc} · تکه ${point.chunk} · شباهت ${fa(point.score, 3)}`}
          onClick={() => selectable(point.doc)?.(point.doc)}
          onKeyDown={onSelectDoc ? event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelectDoc(point.doc); } } : undefined}
          className={onSelectDoc ? "rag-scatter-point" : undefined}>
          <title>{`${shortName(point.doc, 46)} · تکه ${point.chunk} · شباهت ${fa(point.score, 3)} · رتبه ${point.rank}${point.preview ? `\n${point.preview}` : ""}`}</title>
          <circle cx={point.cx} cy={point.cy} r={point.strongest ? 6 : 4.5}
            fill={point.strongest ? "var(--desk-blue, var(--syntax-blue))" : "var(--surface)"}
            stroke="var(--desk-blue, var(--syntax-blue))" strokeOpacity={point.strongest ? 1 : 0.65} strokeWidth={1.2} />
        </g>)}
        {geometry.query && queryLabel && <g>
          <circle cx={geometry.query.cx} cy={geometry.query.cy} r="11" fill="none" stroke="var(--accent)" strokeWidth="1.6" />
          <circle cx={geometry.query.cx} cy={geometry.query.cy} r="3.2" fill="var(--accent)" />
          <text x={queryLabel.x} y={queryLabel.y} fontSize="10" fill="var(--accent)" textAnchor={queryLabel.anchor}>
            بردار پرسش
          </text>
        </g>}
      </svg>
    </div>
    <ul className="rag-embedding-legend">
      <li><span className="rag-legend-mark is-query" aria-hidden="true" />بردار پرسش، از شباهت‌های ثبت‌شدهٔ همین اجرا</li>
      <li><span className="rag-legend-mark is-strong" aria-hidden="true" />{fa(geometry.strongest)} کاندید با بالاترین شباهت</li>
      <li><span className="rag-legend-mark is-candidate" aria-hidden="true" />بقیهٔ کاندیدهای بازیابی‌شده (برای متن تکه، نقطه را انتخاب کنید)</li>
    </ul>
    <p className="rag-note">
      {`این تصویر ${fa(record.point_count)} تکه از ${fa(record.recorded_rows)} ردیف ثبت‌شدهٔ «${text(record.stage)}» را در ${fa(record.dimensions)} بُعد نشان می‌دهد. `
        + `دو محور، دو جهت اصلی نخست همین تکه‌هاست و مجموعاً ${share((variance[0] ?? 0) + (variance[1] ?? 0))} از پراکندگی آن‌ها را در بر می‌گیرد؛ `
        + "پس فاصلهٔ شکل‌ها تقریبی است. کاندیدهای مجموعه‌های دیگر مجموعهٔ برداری جدا و نقشهٔ جدای خود را دارند."}
    </p>
  </div>;
}

export function EmbeddingProvenance({ trace, map, onSelectDoc }: {
  trace: TraceRecord; map?: EmbeddingMapPayload; onSelectDoc?: (doc: string) => void;
}) {
  const embeds = (trace.stages ?? []).filter(stage => roleOf(stage.name) === "embed");
  const stores = (trace.stages ?? []).filter(stage => roleOf(stage.name) === "vector");
  if (!embeds.length) return <p className="rag-note">این اجرا فراخوانی بردارسازی ثبت نکرده است؛ از نبود رد نمی‌توان نتیجه گرفت بردارسازی انجام شده.</p>;
  const primary = embeds[0];
  const model = text(primary.meta.model) || text(primary.meta.provider) || "مدل ثبت نشده";
  const dims = [...new Set(embeds.map(stage => Number(stage.meta.dimensions)).filter(n => Number.isFinite(n) && n > 0))];
  const inputs = embeds.map(stage => text(stage.meta.input ?? stage.text.input)).filter(Boolean);
  const height = Math.max(250, stores.length * 110 + 30);
  // Only maps with a plane to draw are used: a run whose vectors are gone (or
  // that never recorded a cosine-scored search) keeps the relationship diagram,
  // which claims no coordinates at all.
  const records = (map?.maps ?? []).filter(record => (record.points?.length ?? 0) >= 3);
  const skipped = map?.skipped ?? [];
  return <section className="rag-embedding-pane" aria-label="روابط بردارسازی و منابع واقعی">
    <div className="rag-section-heading">
      <div><h3>بردارسازی و منشأ منابع</h3></div>
      <span>{fa(embeds.length)} فراخوانی ثبت‌شده{records.length ? ` · ${fa(records.length)} نقشهٔ برداری` : ""}</span>
    </div>
    {records.map(record => <SemanticScatter key={`${record.collection}-${record.stage}`} record={record}
      onSelectDoc={onSelectDoc} />)}
    {records.length > 0 && <div className="rag-embedding-notes">
      {map?.notice && <p className="rag-note">{map.notice}</p>}
      {(map?.limitations ?? []).map(line => <p key={line} className="rag-note">{line}</p>)}
      {skipped.map(item => <p key={item.collection} className="rag-warning">
        {`${text(item.collection)}: ${item.reason}`}
      </p>)}
    </div>}
    {records.length === 0 && <>
    <svg viewBox={`0 0 760 ${height}`} role="img" aria-label={`روابط پرسش، بردارساز ${model} و ${stores.length} مجموعه؛ مختصات بردار در دسترس نیست`}>
      <title>نقشهٔ روابط ثبت‌شده، بدون نمایش فاصله یا مختصات بردار</title>
      <line x1="574" y1={height / 2} x2="476" y2={height / 2} stroke="var(--accent)" strokeWidth="2" />
      {stores.map((stage, index) => {
        const y = 20 + index * 110;
        const output = stageOutput(stage);
        const docs = [...new Set(rowsOf(stage).map(row => row.doc).filter(Boolean))];
        return <g key={`${stage.name}-${index}`}>
          <path d={`M 290 ${height / 2} C 235 ${height / 2}, 240 ${y + 43}, 209 ${y + 43}`} fill="none" stroke="var(--desk-blue, var(--syntax-blue))" strokeWidth="1.5" />
          <rect x="18" y={y} width="190" height="86" rx="8" fill="var(--surface-2)" stroke="var(--border)" />
          <text x="194" y={y + 22} textAnchor="start" fill="var(--text)" fontSize="12">{fitText(GROUP_FA[groupOf(stage.name)] ?? "مجموعهٔ بازیابی", 166, 12)}</text>
          <text x="194" y={y + 43} textAnchor="start" fill="var(--desk-blue, var(--syntax-blue))" fontSize="11">{fitText(text(stage.meta.collection) || "نام مجموعه ثبت نشده", 166, 11)}</text>
          <text x="194" y={y + 64} textAnchor="start" fill="var(--muted)" fontSize="10">{fitText((output.known ? fa(output.count) : "حداقل " + fa(output.count)) + " نتیجه · " + fa(docs.length) + " سند در نمونه", 166, 10)}</text>
          <title>{docs.join("\n") || "متن سند در این مرحله ثبت نشده"}</title>
        </g>;
      })}
      <circle cx="383" cy={height / 2} r="82" fill="var(--surface-2)" stroke="var(--accent)" strokeWidth="1.5" />
      <text x="383" y={height / 2 - 28} textAnchor="middle" fill="var(--accent)" fontSize="12">بردارساز پرسش</text>
      <text x="383" y={height / 2 - 2} textAnchor="middle" fill="var(--text)" fontSize="10">{fitText(model, 148, 10)}</text>
      <text x="383" y={height / 2 + 24} textAnchor="middle" fill="var(--muted)" fontSize="11">{dims.length ? `${dims.map(n => fa(n)).join(" / ")} بُعد` : "ابعاد ثبت نشده"}</text>
      <rect x="574" y={height / 2 - 48} width="170" height="96" rx="8" fill="var(--surface-2)" stroke="var(--border)" />
      <text x="730" y={height / 2 - 19} textAnchor="start" fill="var(--text)" fontSize="12">ورودی واقعی جست‌وجو</text>
      <text x="730" y={height / 2 + 7} textAnchor="start" fill="var(--muted)" fontSize="10">{fitText(inputs[0] || trace.question || "ورودی ثبت نشده", 146, 10)}</text>
      <text x="730" y={height / 2 + 29} textAnchor="start" fill="var(--muted-2)" fontSize="10">{fitText("بازنویسی ← بردارسازی ← بازیابی", 146, 10)}</text>
    </svg>
    <p className="rag-note">این نقشه رابطهٔ پرسش، بردارساز و مجموعه‌ها را نشان می‌دهد. مختصات و بردارها در این رد ذخیره نشده‌اند؛ فاصلهٔ شکل‌ها فاصلهٔ معنایی نیست. هر تکه از مسیرهای رتبه‌بندی زیر قابل بررسی است.</p>
    {map?.reason && <p className="rag-note">{map.reason}</p>}
    </>
    }
    {dims.length > 1 && <p className="rag-warning">بیش از یک اندازهٔ بردار ثبت شده است؛ سازگاری هر مدل و مجموعه را در جزئیات مرحله بررسی کنید.</p>}
  </section>;
}

export default function RagVisualMap({ trace, selectedStage, onSelectStage, docCap, chunksPerDoc, embeddingMap }: {
  trace: TraceRecord; selectedStage?: number; onSelectStage?: (index: number) => void;
  embeddingMap?: EmbeddingMapPayload;
} & MindMapOptions) {
  return <RagVisualMapBody key={trace.id} trace={trace} selectedStage={selectedStage}
    onSelectStage={onSelectStage} docCap={docCap} chunksPerDoc={chunksPerDoc} embeddingMap={embeddingMap} />;
}

/**
 * Counts a reader can check at a glance before reading any of the pictures.
 *
 * Every number is read from the trace, and a stage that never ran says so
 * instead of showing a zero that would look like "nothing was found".
 */
function VisualRibbon({ trace, docs }: { trace: TraceRecord; docs: DocCoverage[] }) {
  const stages = trace.stages ?? [];
  const finalContext = [...stages].reverse().find(stage => ["context", "answer"].includes(roleOf(stage.name)));
  const contextOutput = finalContext ? stageOutput(finalContext) : null;
  const sampledContext = docs.reduce((sum, doc) => sum + doc.cited, 0);
  const contextCount = contextOutput?.known ? fa(contextOutput.count)
    : sampledContext ? `حداقل ${fa(sampledContext)}` : "ثبت نشده";
  const dims = [...new Set(stages.filter(stage => roleOf(stage.name) === "embed")
    .map(stage => Number(stage.meta?.dimensions)).filter(n => Number.isFinite(n) && n > 0))];
  const rerank = stages.filter(stage => roleOf(stage.name) === "rerank");
  const rerankState = !rerank.length ? "مرحله‌ای ندارد"
    : rerank.every(stage => stage.meta?.skipped) ? "اجرا نشد"
    : rerank.some(stage => stage.meta?.error || stage.meta?.provider_error) ? "خطا ثبت شده"
    : rerank.some(stage => stage.meta?.skipped) ? "بخشی اجرا شد" : "اجرا شد";
  return <ul className="rag-visual-ribbon" aria-label="شمارش‌های کلیدی این اجرا">
    {([
      ["تکه در بافت مدل", contextCount, false],
      ["اسناد ثبت‌شده", fa(docs.length), false],
      ["مرحله‌ها", fa(stages.length), false],
      ["زمان کل اجرا", `${fa(trace.duration_ms, 1)} ms`, true],
      ["بُعد بردار", dims.length ? dims.map(n => fa(n)).join(" / ") : "ثبت نشده", dims.length > 0],
      ["بازرتبه‌بندی", rerankState, false],
    ] as [string, string, boolean][]).map(([label, value, ltr]) => <li key={label}>
      <span>{label}</span><strong dir={ltr ? "ltr" : undefined}>{value}</strong>
    </li>)}
  </ul>;
}

/**
 * One visualisation of the run. Every block uses the same heading/hint rhythm so
 * the workbench reads as an ordered list instead of a pile of pictures, and each
 * one is a landmark for screen readers.
 */
function VizSection({ title, hint, note, children }: {
  title: string; hint: string; note?: string; children: ReactNode;
}) {
  return <section className="rag-viz-block" aria-label={title}>
    <div className="rag-section-heading">
      <div><h3>{title}</h3></div>
      <span>{hint}</span>
    </div>
    {note && <p className="rag-note">{note}</p>}
    {children}
  </section>;
}

function RagVisualMapBody({ trace, selectedStage, onSelectStage, docCap, chunksPerDoc, embeddingMap }: {
  trace: TraceRecord; selectedStage?: number; onSelectStage?: (index: number) => void;
  embeddingMap?: EmbeddingMapPayload;
} & MindMapOptions) {
  const [selectedDoc, setSelectedDoc] = useState("");
  const graph = useMemo(() => buildPipelineGraph(trace), [trace]);
  const chart = useMemo(() => buildRankChart(trace, selectedDoc), [trace, selectedDoc]);
  const docs = useMemo(() => buildDocumentCoverage(trace, buildRankChart(trace)), [trace]);

  return (
    <div className="rag-visual-workbench">
      <VisualRibbon trace={trace} docs={docs} />
      <SourceMindMap trace={trace} docs={docs} selectedDoc={selectedDoc} onSelectDoc={setSelectedDoc}
        docCap={docCap} chunksPerDoc={chunksPerDoc} />
      <EmbeddingProvenance trace={trace} map={embeddingMap} onSelectDoc={setSelectedDoc} />
      <VizSection title="نقشهٔ خط بازیابی"
        hint="ضخامت هر پیکان = تعداد خروجی ثبت‌شده"
        note="آبی: بازیابی برداری · طلایی: BM25 · بنفش: ادغام · صورتی: بازرتبه‌بندی · سبز: بافت مدل و پاسخ. برای باز کردن جزئیات، مرحله را کلیک کنید یا با Tab و Enter انتخاب کنید. ≥ یعنی فقط تعداد نمونه‌ها ثبت شده است؛ پیکان بدون عدد صرفاً رابطهٔ مرحله‌ها را نشان می‌دهد؛ پیکان‌ها اجرای هم‌زمان را نشان نمی‌دهند.">
        <div className="rag-map-scroll"><PipelineMap graph={graph} selectedDoc={selectedDoc} onSelectDoc={setSelectedDoc} selectedStage={selectedStage} onSelectStage={onSelectStage} /></div>
        <div className="mt-2"><FunnelStrip graph={graph} /></div>
      </VizSection>

      <VizSection title="سرنوشت تکه‌ها در مرحله‌ها"
        hint={selectedDoc ? `فقط ${shortName(selectedDoc, 26)}` : "همهٔ تکه‌های ثبت‌شده"}
        note={selectedDoc
          ? "نمودار به سند انتخاب‌شده محدود شده است؛ برای دیدن همهٔ تکه‌ها انتخاب سند را بردارید."
          : "رتبهٔ هر تکه را در هر مرحله دنبال کنید؛ خطی که بالا می‌رود را بازرتبه‌بندی بالا آورده است."}>
        <div className="rag-map-scroll"><ChunkRankChart chart={chart} docFilter={selectedDoc} onSelectDoc={setSelectedDoc} /></div>
      </VizSection>

      <VizSection title="اسناد و متن تکه‌های انتخاب‌شده"
        hint="روی هر تکه بزن تا متنش باز شود">
        <DocumentChunkPanel docs={docs} selectedDoc={selectedDoc} onSelectDoc={setSelectedDoc} />
      </VizSection>
    </div>
  );
}
