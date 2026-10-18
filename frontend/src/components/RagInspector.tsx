import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { apiJson } from "../api";
import RagVisualMap, { roleOf, stageOutput } from "./RagPipelineMap";
import type { EmbeddingMapPayload } from "./RagPipelineMap";
import { RagRequestFence } from "./ragRequestFence";
import { SettingsIcon } from "./icons";
import "./rag-inspector.css";

/**
 * Display preferences of the RAG tab, owned by the settings button in its top
 * toolbar. They only decide how much of a recorded run is drawn: no value here
 * changes retrieval, and the diagrams keep saying what they left out.
 */
export interface RagViewSettings {
  /** Documents the source mind map draws before it reports the rest as hidden. */
  docCap: number;
  /** Chunk leaves drawn under one document; `0` keeps the documents only. */
  chunksPerDoc: number;
  /** Start every stage card expanded instead of only the selected stage. */
  openStageDetails: boolean;
}

export const DEFAULT_RAG_VIEW_SETTINGS: RagViewSettings = { docCap: 12, chunksPerDoc: 3, openStageDetails: false };

const VIEW_SETTINGS_KEY = "boom.rag-inspector.view.v1";

/**
 * Read the stored preferences, tolerating anything: a corrupt or partially
 * written value falls back to the defaults instead of breaking the panel.
 */
function readViewSettings(): RagViewSettings {
  try {
    const stored = JSON.parse(window.localStorage.getItem(VIEW_SETTINGS_KEY) ?? "{}") as Partial<RagViewSettings>;
    const number = (value: unknown, fallback: number) =>
      typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.round(value)) : fallback;
    return {
      docCap: number(stored.docCap, DEFAULT_RAG_VIEW_SETTINGS.docCap),
      chunksPerDoc: number(stored.chunksPerDoc, DEFAULT_RAG_VIEW_SETTINGS.chunksPerDoc),
      openStageDetails: stored.openStageDetails === true,
    };
  } catch { return DEFAULT_RAG_VIEW_SETTINGS; }
}

/**
 * RAG inspector ("بررسی RAG").
 *
 * Renders the in-memory traces recorded by the backend (app/rag/trace.py):
 * one row per pipeline run, and for each run the ordered stages with their
 * latency, the low-level command each stage ran, the per-stage metadata, the
 * chunk tables (vector / BM25 / RRF / rerank / sources) and the exact prompts.
 *
 * The playground runs retrieval for an arbitrary question WITHOUT calling the
 * answering model, so an admin can re-ask "why these chunks?" cheaply.
 */

interface StageColumn { key: string; label: string }
export interface TraceStage {
  name: string; label: string; ms: number; command: string;
  meta: Record<string, unknown>;
  columns: StageColumn[];
  rows: Record<string, unknown>[];
  text: Record<string, string>;
}
export interface TraceRecord {
  id: string; kind: string; kind_label: string; title: string; question: string;
  user_id: number | null; created_at: number; duration_ms: number;
  status: string; error: string;
  summary: Record<string, unknown>;
  stages: TraceStage[];
  total_stage_ms: number;
  payload_characters?: number;
}
interface TraceListPayload {
  traces: TraceRecord[]; counts: Record<string, number>;
  limit: number; kinds: Record<string, string>;
}
interface RagConfig {
  default_user_id: number; top_k: number; image_top_k: number;
  embedding_provider: string; embedding_model: string;
  llm_provider: string; llm_model: string;
  vision_provider: string; vision_model: string;
  rerank_enabled: boolean; rerank_available: boolean; rerank_state?: RerankState;
  rerank_model: string; rerank_candidates: number;
  chunk_size: number; chunk_overlap: number; trace_limit: number;
  kinds: Record<string, string>; notice: string;
}

/**
 * Reranker state as the backend reports it without loading the model:
 * reading configuration must never pull the cross-encoder into memory.
 */
type RerankState = "disabled" | "unloaded" | "loaded" | "failed";
const RERANK_STATE_FA: Record<RerankState, string> = {
  disabled: "غیرفعال (RERANK_ENABLED=false)",
  unloaded: "مدل بارگذاری نشده (در نخستین جست‌وجو بارگذاری می‌شود)",
  loaded: "مدل بارگذاری‌شده",
  failed: "بارگذاری مدل ناموفق بود؛ نتیجهٔ بازیابی بی‌بازرتبه‌بندی است",
};

/** Meta keys the backend emits, in Persian, so the panel reads like the app. */
const META_FA: Record<string, string> = {
  provider: "سرویس‌دهنده", model: "مدل", base_url: "آدرس سرویس", tokens: "توکن‌ها",
  chain: "زنجیرهٔ سرویس‌دهنده‌ها", dimensions: "ابعاد بردار", input: "ورودی",
  input_characters: "کاراکتر ورودی", original: "پرسش اصلی", rewritten: "بازنویسی‌شده",
  fallback: "جایگزین", provider_error: "خطای سرویس‌دهنده", error: "خطا",
  hits: "تعداد نتیجه", candidates_requested: "کاندیدهای درخواستی",
  embedding_dimensions: "ابعاد بردار پرسش", collection: "مجموعه",
  score: "امتیاز", indexed_chunks: "تکه‌های فهرست‌شده", query: "پرسش جست‌وجو",
  query_tokens: "توکن‌های پرسش", k1: "k1", b: "b",
  average_chunk_tokens: "میانگین توکن تکه", term_idf: "IDF هر واژه",
  terms_not_in_corpus: "واژه‌های بی‌سابقه", scored_chunks: "تکه‌های امتیازدار",
  rrf_k: "k در RRF", list_1: "فهرست اول", list_2: "فهرست دوم",
  semantic_hits: "نتیجهٔ برداری", lexical_hits: "نتیجهٔ واژگانی",
  unique_chunks: "تکه‌های یکتا", candidates_kept: "کاندیدهای نگه‌داشته‌شده",
  top_k_after_rerank: "نتیجهٔ نهایی", candidate_pairs: "جفت‌های بررسی‌شده",
  kept: "نگه‌داشته‌شده", skipped: "اجرا نشد", k: "k", source: "منبع تصویر",
  categories: "دسته‌ها", batch: "دسته", sees: "ورودی حل‌کننده",
  batch_first_question: "شروع دسته", batch_size: "اندازهٔ دسته",
  total_questions: "کل سؤال‌ها", batch_timeout: "مهلت دسته", refused: "رد شد",
  subject: "درس", target_questions: "هدف سؤال", produced: "تولیدشده",
  topics: "مباحث", grade: "پایه", difficulty: "دشواری", usage_stage: "مرحلهٔ مصرف",
  prompt_characters: "کاراکتر پرامپت", output_characters: "کاراکتر خروجی",
  stored_chunks: "ذخیره‌شده", document: "سند", chunks: "تکه‌ها",
  chunk_size: "اندازهٔ تکه", chunk_overlap: "هم‌پوشانی", questions: "سؤال‌ها",
  max_regens: "حد بازسازی", timeout: "مهلت", verified: "تأییدشده",
  discarded: "ردشده", audit: "نتیجهٔ بازبینی", audit_reason: "دلیل بازبینی",
  question: "سؤال", stored_answer: "کلید ذخیره‌شده",
  answer_characters: "کاراکتر پاسخ", confidence_level: "سطح اطمینان",
  confidence_score: "امتیاز اطمینان", confidence_label: "برچسب اطمینان",
  sources: "منابع", search_query: "پرسش جست‌وجو", top_k: "top-k", rerank: "بازرتبه‌بندی",
  simple: "پیام ساده", retrieval_skipped: "بازیابی اجرا نشد", reason: "دلیل",
  characters: "کاراکتر", matched: "تطبیق", prompt_messages: "پیام‌های پرامپت",
  images_attached: "تصاویر پیوست", shortcut: "میان‌بر", streaming: "استریم",
  confidence: "اطمینان", empty_answer: "پاسخ مدل خالی بود",
  // Raw text blocks (stage.text keys).
  prompt: "پرامپت ارسالی", answer: "پاسخ مدل", raw: "خروجی خام مدل",
  output_count: "تعداد خروجی واقعی", final_chunks: "تکه‌های بافت نهایی", source_semantics: "نوع منابع",
  cited_sources: "ارجاع‌های شماره‌دار پاسخ", from_question_bank: "از بانک سؤال", from_books: "از کتاب‌ها",
  deduplicated_chunks: "تکه‌های تکراری حذف‌شده", payload_truncated: "دادهٔ رد محدود شده",
  omitted_stages: "مرحله‌های ثبت‌نشده به دلیل سقف حافظه", truncated_meta: "مشخصات محدود شده",
  truncated_rows: "ردیف‌ها محدود شده", truncated_text: "متن محدود شده", truncated_columns: "ستون‌ها محدود شده",
};

const NUMERIC_KEYS = new Set([
  "ms", "rank", "old_rank", "move", "score", "rerank_score", "hybrid_score", "rrf",
  "part_vector", "part_lexical", "rank_vector", "rank_lexical", "chunk", "n", "pos",
  "solver", "stored", "answer",
]);

const STATUS_FA: Record<string, string> = { ok: "موفق", error: "خطا", running: "در حال اجرا" };

function fa(value: number, digits = 0): string {
  return value.toLocaleString("fa-IR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function cell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "بله" : "خیر";
  if (typeof value === "number") return Number.isInteger(value) ? fa(value) : fa(value, 2);
  if (Array.isArray(value)) return value.length ? value.map(v => String(v)).join("، ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function metaLabel(key: string): string {
  return META_FA[key] ?? key;
}

function stamp(seconds: number): string {
  const when = new Date(seconds * 1000);
  return `${when.toLocaleDateString("fa-IR")} ${when.toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
}

function StageTable({ stage }: { stage: TraceStage }) {
  return (
    <div className="overflow-x-auto mt-2">
      <table className="w-full text-[11px]">
        <caption className="text-start text-[var(--muted-2)] mb-1">
          {fa(stage.rows.length)} ردیف · {fa(stage.columns.length)} ستون
        </caption>
        <thead>
          <tr>
            {stage.columns.map(column => (
              <th key={column.key} scope="col" className="text-start py-1.5 px-2 border-b border-[var(--border)] font-medium whitespace-nowrap">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {stage.rows.map((row, index) => (
            <tr key={index}>
              {stage.columns.map(column => {
                const value = row[column.key];
                const flag = column.key === "match" ? (value ? "text-emerald-400" : "text-red-400") : "";
                return (
                  <td key={column.key}
                    className={`py-1.5 px-2 border-b border-[var(--border)] align-top ${flag} ${NUMERIC_KEYS.has(column.key) ? "tabular-nums" : ""}`}
                    dir={typeof value === "number" || column.key === "id" ? "ltr" : "auto"}>
                    {cell(value)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StageCard({ stage, index, max, selected, openAll, onSelect, id }: {
  stage: TraceStage; index: number; max: number; selected: boolean;
  openAll?: boolean; onSelect: () => void; id: string;
}) {
  const width = Math.max(2, Math.round((stage.ms / max) * 100));
  const meta = Object.entries(stage.meta ?? {});
  const texts = Object.entries(stage.text ?? {});
  return (
    <li id={id} className="rag-stage-card border border-[var(--border)] bg-[var(--surface-2)]/40" aria-current={selected}>
      <details open={selected || !!openAll}>
        <summary onClick={event => { event.preventDefault(); onSelect(); }} className="cursor-pointer list-none px-3 py-2.5 space-y-2">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-[10px] text-[var(--muted-2)] tabular-nums" dir="ltr">{index + 1}</span>
            <span className="text-xs font-bold text-[var(--text)]">{stage.label}</span>
            <span className="text-[10px] text-[var(--muted-2)]" dir="ltr">{stage.name}</span>
            <span className="ms-auto text-[11px] tabular-nums text-[var(--muted)]" dir="ltr">{fa(stage.ms, 1)} ms</span>
          </div>
          <div className="h-1.5 rounded-full bg-[var(--surface)] overflow-hidden">
            <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${width}%` }} />
          </div>
          {(stage.rows.length > 0 || meta.length > 0) && (
            <p className="text-[10px] text-[var(--muted-2)]">
              {stage.rows.length > 0 ? `${fa(stage.rows.length)} ردیف` : ""}
              {stage.rows.length > 0 && meta.length > 0 ? " · " : ""}
              {meta.length > 0 ? `${fa(meta.length)} مشخصه` : ""}
              {texts.length > 0 ? ` · ${fa(texts.length)} متن` : ""}
            </p>
          )}
        </summary>
        <div className="px-3 pb-3 space-y-3">
          {stage.meta?.provider_error ? <p role="alert" className="rag-error text-xs">{cell(stage.meta.provider_error)}</p> : null}
          {Object.keys(stage.meta ?? {}).some(key => key.startsWith("truncated_") && stage.meta[key]) &&
            <p className="rag-warning">بخشی از جزئیات این مرحله برای محدود کردن حافظه حذف شده است؛ نبود ردیف به معنی نبود نتیجه نیست.</p>}
          {stage.command && (
            <div>
              <div className="text-[10px] text-[var(--muted-2)] mb-1">دستوری که اجرا شد</div>
              <pre dir="ltr" className="text-[10px] leading-relaxed whitespace-pre-wrap break-words bg-[var(--surface)] border border-[var(--border)] rounded-xl p-2 text-[var(--muted)]">{stage.command}</pre>
            </div>
          )}
          {meta.length > 0 && (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
              {meta.map(([key, value]) => (
                <div key={key} className="min-w-0">
                  <dt className="text-[10px] text-[var(--muted-2)]">{metaLabel(key)}</dt>
                  <dd className="text-[var(--text)] break-words" dir="auto">{cell(value)}</dd>
                </div>
              ))}
            </dl>
          )}
          {stage.columns.length > 0 && stage.rows.length > 0 && <StageTable stage={stage} />}
          {texts.map(([key, value]) => (
            <div key={key}>
              <div className="text-[10px] text-[var(--muted-2)] mb-1">{metaLabel(key)}</div>
              <pre dir="auto" className="text-[11px] leading-relaxed whitespace-pre-wrap break-words bg-[var(--surface)] border border-[var(--border)] rounded-xl p-2 max-h-72 overflow-auto">{value}</pre>
            </div>
          ))}
        </div>
      </details>
    </li>
  );
}

/**
 * Only a run that recorded cosine-scored vector rows can have a vector map:
 * the map is derived from those rows' similarities and the stored vectors.
 */
export function traceHasSemanticRows(trace: TraceRecord): boolean {
  return (trace.stages ?? []).some(stage => stage.name.endsWith("semantic_search")
    && (stage.rows?.length ?? 0) >= 3);
}

export function TraceView({ trace, settings, embeddingMap }: {
  trace: TraceRecord; settings?: RagViewSettings; embeddingMap?: EmbeddingMapPayload;
}) {
  return <TraceViewBody key={trace.id} trace={trace} settings={settings} embeddingMap={embeddingMap} />;
}

/**
 * The two ways of reading one run: the pictures, and the stage-by-stage record
 * the pictures are derived from. The tabs keep both in the document (the
 * inactive panel is `hidden`, so it is out of the layout and the accessibility
 * tree) - switching tabs then never remounts the stage tables.
 */
const TRACE_TABS = [
  { id: "visual", label: "نقشه و تصویرسازی", hint: "نقشهٔ منابع، جریان خط، سرنوشت تکه‌ها" },
  { id: "stages", label: "مرحله‌ها و جدول‌ها", hint: "زمان، دستور، جدول و پرامپت هر مرحله" },
] as const;

type TraceTab = typeof TRACE_TABS[number]["id"];

function TraceViewBody({ trace, settings, embeddingMap }: {
  trace: TraceRecord; settings?: RagViewSettings; embeddingMap?: EmbeddingMapPayload;
}) {
  const stages = trace.stages ?? [];
  const view = settings ?? DEFAULT_RAG_VIEW_SETTINGS;
  const [tab, setTab] = useState<TraceTab>("visual");
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [selectedStage, setSelectedStage] = useState<number | null>(() => {
    const failed = stages.findIndex(stage => stage.meta?.provider_error || stage.meta?.error);
    return failed >= 0 ? failed : Math.max(0, stages.findIndex(stage => roleOf(stage.name) === "embed"));
  });
  const max = useMemo(() => Math.max(1, ...stages.map(stage => stage.ms)), [stages]);
  const summary = Object.entries(trace.summary ?? {});

  // Arrow keys move between the tabs like any other tab list. This app reads
  // right to left, so ArrowRight steps back a tab.
  const onTabKeys = (event: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
    const target = event.key === "ArrowRight" ? index - 1 : event.key === "ArrowLeft" ? index + 1 : -1;
    if (target < 0 || target >= TRACE_TABS.length) return;
    event.preventDefault();
    setTab(TRACE_TABS[target].id);
    tabRefs.current[target]?.focus();
  };
  // Selecting a node in the map is useful on its own, so the readout and the
  // jump to the stage tables live in the visual tab.
  const openStageDetails = (index: number) => {
    setTab("stages");
    const scroll = () => document.getElementById(`rag-stage-${trace.id}-${index}`)?.scrollIntoView({ block: "nearest", behavior: "auto" });
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => requestAnimationFrame(scroll));
    else scroll();
  };

  return (
    <div className="space-y-3">
      <div className="rag-trace-header">
        <span className="text-xs font-bold text-[var(--text)]">{trace.kind_label}</span>
        <span className={`text-[10px] px-2 py-0.5 rounded-full border ${trace.status === "error" ? "border-red-400/60 text-red-400" : "border-[var(--border)] text-[var(--muted)]"}`}>
          {STATUS_FA[trace.status] ?? trace.status}
        </span>
        <span className="text-[10px] text-[var(--muted-2)]">{stamp(trace.created_at)}</span>
        <span className="text-[11px] text-[var(--muted)] tabular-nums">زمان کل اجرا: <span dir="ltr">{fa(trace.duration_ms, 1)} ms</span></span>
      </div>

      {trace.question && (
        <p className="text-sm text-[var(--text)] leading-relaxed">«{trace.question}»</p>
      )}

      {summary.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {summary.map(([key, value]) => (
            <span key={key} className={`text-[10px] px-2 py-0.5 rounded-full border ${key === "empty_answer"
              ? "bg-amber-400/10 border-amber-400/60 text-amber-400"
              : "bg-[var(--surface-2)] border-[var(--border)] text-[var(--muted)]"}`}>
              {metaLabel(key)}: {cell(value)}
            </span>
          ))}
        </div>
      )}

      {trace.error && <p role="alert" className="text-xs text-red-400">{trace.error}</p>}
      {Boolean(trace.summary?.payload_truncated) && <p className="rag-warning">این رد برای حفظ حافظه محدود شده است. تعداد خروجی واقعی را از مشخصات مرحله بخوانید؛ جدول‌ها ممکن است تنها نمونه‌ای از نتیجه‌ها باشند.</p>}
      <p className="rag-note">منابع «در بافت مدل» به مدل ارائه شده‌اند؛ تنها برچسب «ارجاع شماره‌دار در پاسخ» نشان می‌دهد پاسخ به آن منبع اشاره کرده. متن‌ها و جدول‌ها نسخهٔ محدودشدهٔ دادهٔ تشخیصی هستند.</p>

      {stages.length === 0 ? (
        <p className="text-xs text-[var(--muted-2)]">این اجرا هنوز مرحله‌ای ثبت نکرده است.</p>
      ) : (
        <>
          <div className="rag-tabs" role="tablist" aria-label="نماهای این اجرا">
            {TRACE_TABS.map((item, index) => (
              <button key={item.id} type="button" role="tab"
                id={`rag-tab-${item.id}-${trace.id}`} aria-controls={`rag-panel-${item.id}-${trace.id}`}
                aria-selected={tab === item.id} tabIndex={tab === item.id ? 0 : -1}
                ref={node => { tabRefs.current[index] = node; }}
                onKeyDown={event => onTabKeys(event, index)} onClick={() => setTab(item.id)}
                className={`rag-tab ${tab === item.id ? "is-active" : ""}`}>
                <span className="rag-tab-label">{item.label}</span>
                <span className="rag-tab-hint">{item.id === "stages" ? `${fa(stages.length)} مرحله · ${item.hint}` : item.hint}</span>
              </button>
            ))}
          </div>

          <section className="rag-tab-panel" role="tabpanel" id={`rag-panel-visual-${trace.id}`}
            aria-labelledby={`rag-tab-visual-${trace.id}`} hidden={tab !== "visual"}>
            {selectedStage !== null && stages[selectedStage] && <div className="rag-stage-selection">
              <strong>مرحلهٔ انتخاب‌شده: {stages[selectedStage].label}</strong>
              <span>{stageOutput(stages[selectedStage]).known ? `${fa(stageOutput(stages[selectedStage]).count)} خروجی واقعی / ` : "تعداد خروجی در رد مشخص نشده / "}{fa(stages[selectedStage].rows?.length ?? 0)} ردیف ثبت‌شده</span>
              <button type="button" onClick={() => openStageDetails(selectedStage)}>جزئیات مرحله</button>
            </div>}
            <RagVisualMap trace={trace} selectedStage={selectedStage ?? undefined} onSelectStage={setSelectedStage}
              docCap={view.docCap} chunksPerDoc={view.chunksPerDoc} embeddingMap={embeddingMap} />
          </section>

          <section className="rag-tab-panel" role="tabpanel" id={`rag-panel-stages-${trace.id}`}
            aria-labelledby={`rag-tab-stages-${trace.id}`} hidden={tab !== "stages"}>
            <div className="flex items-baseline justify-between text-[10px] text-[var(--muted-2)] mb-1.5">
              <span>نمودار زمان مرحله‌ها (شامل زیرمرحله‌ها)</span>
              <span className="tabular-nums" dir="ltr">
                {fa(trace.total_stage_ms, 1)} ms / {stages.length} مرحله
              </span>
            </div>
            <p className="rag-note">جمع این زمان‌ها مدت کل اجرا نیست: مرحلهٔ والد زمان فرزندانش را هم شامل می‌شود. برای سرعت پاسخ، «زمان کل اجرا» را مقایسه کنید.</p>
            <ol className="space-y-1.5">
              {stages.map((stage, index) => (
                <li key={`${stage.name}-${index}`} className="grid grid-cols-[minmax(4rem,7rem)_1fr_4.5rem] items-center gap-2 text-[10px]">
                  <button type="button" aria-pressed={selectedStage === index} onClick={() => setSelectedStage(index)} className="text-start text-[var(--muted)] truncate" title={`${stage.label} · ${stage.name}`}>{stage.label}</button>
                  <span className="h-2 rounded-full bg-[var(--surface-2)] overflow-hidden">
                    <span className="block h-full rounded-full bg-[var(--accent)]"
                      style={{ width: `${Math.max(2, Math.round((stage.ms / max) * 100))}%` }} />
                  </span>
                  <span className="text-end tabular-nums text-[var(--muted-2)]" dir="ltr">{fa(stage.ms, 1)} ms</span>
                </li>
              ))}
            </ol>
            <ul className="space-y-2 mt-3">
              {stages.map((stage, index) => (
                <StageCard key={`${stage.name}-${index}`} id={`rag-stage-${trace.id}-${index}`} stage={stage} index={index}
                  max={max} selected={selectedStage === index} openAll={view.openStageDetails}
                  onSelect={() => setSelectedStage(selectedStage === index ? null : index)} />
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

export default function RagInspector() {
  const [config, setConfig] = useState<RagConfig | null>(null);
  const [traces, setTraces] = useState<TraceRecord[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [kinds, setKinds] = useState<Record<string, string>>({});
  const [kind, setKind] = useState("all");
  const [selected, setSelected] = useState<TraceRecord | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [embeddingMap, setEmbeddingMap] = useState<EmbeddingMapPayload | null>(null);
  const [listErr, setListErr] = useState("");
  const requests = useRef(new RagRequestFence());
  const activeKind = useRef("all");
  const activeTrace = useRef("");

  // Playground inputs
  const [question, setQuestion] = useState("");
  const [targetUser, setTargetUser] = useState("");
  const [topK, setTopK] = useState("");
  const [rewrite, setRewrite] = useState(false);
  const [questionBank, setQuestionBank] = useState(true);
  const [images, setImages] = useState(false);

  // The top toolbar's settings button owns both the server configuration
  // summary and the display preferences. Preferences are read after mount, so
  // the first render (and the server render) is always the default one.
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [view, setView] = useState<RagViewSettings>(DEFAULT_RAG_VIEW_SETTINGS);

  const loadList = useCallback(async (which: string) => {
    const request = requests.current.begin("list");
    setListErr("");
    try {
      const data = await apiJson<TraceListPayload>(`/api/admin/rag/traces?kind=${encodeURIComponent(which)}&limit=50`, { signal: request.signal });
      if (!request.current()) return;
      setTraces(data.traces); setCounts(data.counts);
      if (data.kinds) setKinds(data.kinds);
    } catch (error) {
      if (request.current()) setListErr(error instanceof Error ? error.message : "دریافت ردها ناموفق بود");
    }
  }, []);

  useEffect(() => {
    const fence = requests.current;
    fence.activate();
    const request = fence.begin("config");
    void (async () => {
      try {
        const data = await apiJson<RagConfig>("/api/admin/rag/config", { signal: request.signal });
        if (!request.current()) return;
        setConfig(data); setKinds(data.kinds ?? {});
        setTargetUser(String(data.default_user_id)); setTopK(String(data.top_k));
      } catch (error) {
        if (request.current()) setErr(error instanceof Error ? error.message : "تنظیمات RAG دریافت نشد");
      }
    })();
    void loadList("all");
    return () => fence.dispose();
  }, [loadList]);

  useEffect(() => { setView(readViewSettings()); }, []);
  useEffect(() => {
    try { window.localStorage.setItem(VIEW_SETTINGS_KEY, JSON.stringify(view)); } catch { /* private mode */ }
  }, [view]);

  /**
   * The vector map of one run, read lazily when the run is opened.
   *
   * It costs a Chroma read and a projection, so it is never built for the list
   * and never on the chat path. A failure is not surfaced: the component that
   * renders without coordinates is already the honest fallback.
   */
  const loadEmbeddingMap = useCallback(async (id: string) => {
    const request = requests.current.begin("map");
    try {
      const data = await apiJson<EmbeddingMapPayload>(
        `/api/admin/rag/traces/${encodeURIComponent(id)}/embedding-map`, { signal: request.signal });
      if (!request.current() || activeTrace.current !== id) return;
      setEmbeddingMap(data);
    } catch {
      if (request.current() && activeTrace.current === id) setEmbeddingMap(null);
    }
  }, []);

  const openTrace = useCallback(async (id: string, refresh = false) => {
    const request = requests.current.begin("detail");
    activeTrace.current = id; setSelectedId(id);
    if (!refresh) { setSelected(null); setEmbeddingMap(null); setErr(""); setDetailLoading(true); }
    try {
      const data = await apiJson<{ trace: TraceRecord }>(`/api/admin/rag/traces/${encodeURIComponent(id)}`, { signal: request.signal });
      if (!request.current() || activeTrace.current !== id) return;
      setSelected(data.trace);
      // Fire-and-forget: the stage record is readable while the map is built.
      if (traceHasSemanticRows(data.trace)) void loadEmbeddingMap(id);
      else setEmbeddingMap(null);
    } catch (error) {
      if (!request.current() || activeTrace.current !== id) return;
      if (!refresh) setSelected(null);
      setErr(error instanceof Error ? error.message : "این رد در دسترس نیست");
    } finally {
      if (request.current()) setDetailLoading(false);
    }
  }, [loadEmbeddingMap]);

  // Poll only the selected running trace, after each response has finished.
  // A slow endpoint is never aborted merely because another poll is due.
  useEffect(() => {
    if (!selected || selected.status !== "running" || busy) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const id = selected.id;
    const poll = async () => {
      if (!alive || activeTrace.current !== id) return;
      await openTrace(id, true);
      if (alive && activeTrace.current === id) timer = setTimeout(poll, 5000);
    };
    timer = setTimeout(poll, 5000);
    return () => { alive = false; clearTimeout(timer); };
  }, [selected?.id, selected?.status, busy, openTrace]);

  async function refresh() {
    const id = activeTrace.current;
    await Promise.all([loadList(activeKind.current), id ? openTrace(id, true) : Promise.resolve()]);
  }

  async function clearTraces() {
    const request = requests.current.begin("mutation");
    requests.current.invalidate("detail"); requests.current.invalidate("list");
    requests.current.invalidate("map");
    activeTrace.current = "";
    setSelected(null); setSelectedId(""); setEmbeddingMap(null); setDetailLoading(false);
    setBusy(true); setErr("");
    try {
      await apiJson(`/api/admin/rag/traces?kind=${encodeURIComponent(activeKind.current)}`, { method: "DELETE", signal: request.signal });
      if (!request.current()) return;
      await loadList(activeKind.current);
    } catch (error) {
      if (request.current()) setErr(error instanceof Error ? error.message : "پاک‌کردن ردها ناموفق بود");
    } finally { if (request.current()) setBusy(false); }
  }

  async function runPlayground() {
    const request = requests.current.begin("mutation");
    requests.current.invalidate("detail");
    setBusy(true); setErr(""); setDetailLoading(false);
    try {
      const body: Record<string, unknown> = {
        question: question.trim(), rewrite,
        include_question_bank: questionBank, include_images: images,
      };
      if (targetUser.trim()) body.user_id = Number(targetUser);
      if (topK.trim()) body.top_k = Number(topK);
      const data = await apiJson<{ trace: TraceRecord; error?: string }>("/api/admin/rag/playground", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body), signal: request.signal,
      }, 120000);
      if (!request.current()) return;
      activeTrace.current = data.trace.id; setSelected(data.trace); setSelectedId(data.trace.id);
      if (data.error) setErr(data.error);
      await loadList(activeKind.current); // List failures never erase a playground failure.
    } catch (error) {
      if (request.current()) setErr(error instanceof Error ? error.message : "اجرای بازیابی ناموفق بود");
    } finally { if (request.current()) setBusy(false); }
  }

  const kindOptions = Object.entries(kinds).length
    ? Object.entries(kinds)
    : [["all", "همه"], ["chat", "گفتگوی کاربر"], ["mock", "ساخت دفترچه"],
       ["evaluation", "ارزیابی سؤال"], ["playground", "بررسی دستی"], ["ingest", "بارگذاری سند"]];

  return (
    <div className="rag-inspector space-y-6">
      <section className="study-section p-4">
        <div className="rag-topbar">
          <div className="min-w-0">
            <h2 className="font-bold text-sm mb-2">تنظیمات فعلی مسیر بازیابی (RAG)</h2>
            <p className="text-xs text-[var(--muted)] leading-relaxed">{config?.notice}</p>
          </div>
          <div className="rag-topbar-actions">
            <button type="button" aria-expanded={settingsOpen} aria-controls="rag-settings"
              onClick={() => setSettingsOpen(open => !open)} className="rag-settings-toggle">
              <SettingsIcon size={13} />
              {settingsOpen ? "بستن تنظیمات" : "تنظیمات"}
            </button>
            <button type="button" onClick={refresh} disabled={busy}
              className="text-[11px] px-3 py-1.5 rounded-xl bg-[var(--surface-2)] border border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-40">
              به‌روزرسانی
            </button>
            <button type="button" onClick={clearTraces} disabled={busy || !traces.length}
              className="text-[11px] px-3 py-1.5 rounded-xl border border-red-400/60 text-red-400 hover:bg-red-400/10 disabled:opacity-40">
              پاک‌کردن
            </button>
          </div>
        </div>

        <div id="rag-settings" className="rag-settings" hidden={!settingsOpen}>
          {config ? (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-[11px]">
              {[
                ["سرویس بردارسازی", `${config.embedding_provider} · ${config.embedding_model}`],
                ["سرویس پاسخ‌دهی", `${config.llm_provider} · ${config.llm_model}`],
                ["سرویس بینایی (تصویر صفحه)", `${config.vision_provider} · ${config.vision_model}`],
                ["بازرتبه‌بندی", `${config.rerank_enabled ? "فعال" : "غیرفعال"} · ${RERANK_STATE_FA[config.rerank_state ?? (config.rerank_available ? "loaded" : "unloaded")]} · ${config.rerank_model}`],
                ["کاندیدهای بازرتبه‌بندی", fa(config.rerank_candidates)],
                ["top-k پاسخ", `${fa(config.top_k)} تکه · تصویر: ${fa(config.image_top_k)}`],
                ["تکه‌بندی سند", `${fa(config.chunk_size)} کاراکتر · هم‌پوشانی ${fa(config.chunk_overlap)}`],
                ["گنجایش ردها", `${fa(config.trace_limit)} مورد در حافظه`],
              ].map(([label, value]) => (
                <div key={label} className="min-w-0">
                  <dt className="text-[10px] text-[var(--muted-2)]">{label}</dt>
                  <dd className="text-[var(--text)] break-words" dir="auto">{value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-xs text-[var(--muted-2)]">در حال دریافت تنظیمات…</p>
          )}

          <div className="rag-settings-group">
            <h3 className="text-xs font-bold text-[var(--text)]">نمایش تصویرسازی‌ها</h3>
            <p className="text-[10px] text-[var(--muted-2)] leading-relaxed">
              این‌ها فقط نما را تغییر می‌دهند و روی بازیابی، سهمیهٔ مدل یا دادهٔ ثبت‌شده اثری ندارند.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px] mt-2">
              <label className="text-[var(--muted)]">سند در نقشهٔ منابع
                <select value={view.docCap} aria-label="گنجایش سند در نقشهٔ منابع"
                  onChange={event => setView(current => ({ ...current, docCap: Number(event.target.value) }))}
                  className="block w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-xl px-2 py-1.5 text-[var(--text)] mt-1">
                  <option value={8}>۸ سند (نقشهٔ سبک)</option>
                  <option value={12}>۱۲ سند</option>
                  <option value={24}>۲۴ سند</option>
                  <option value={0}>بدون سقف</option>
                </select>
              </label>
              <label className="text-[var(--muted)]">تکه زیر هر سند
                <select value={view.chunksPerDoc} aria-label="تکه زیر هر سند"
                  onChange={event => setView(current => ({ ...current, chunksPerDoc: Number(event.target.value) }))}
                  className="block w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-xl px-2 py-1.5 text-[var(--text)] mt-1">
                  <option value={0}>فقط اسناد</option>
                  <option value={2}>۲ تکه</option>
                  <option value={3}>۳ تکه</option>
                  <option value={5}>۵ تکه</option>
                  <option value={8}>۸ تکه</option>
                </select>
              </label>
            </div>
            <label className="flex items-center gap-2 text-[11px] text-[var(--muted)] mt-3">
              <input type="checkbox" checked={view.openStageDetails}
                onChange={event => setView(current => ({ ...current, openStageDetails: event.target.checked }))} />
              جزئیات فنی همهٔ مرحله‌ها از ابتدا باز باشد (پیش‌فرض: فقط مرحلهٔ انتخابی)
            </label>
            <button type="button" onClick={() => setView(DEFAULT_RAG_VIEW_SETTINGS)}
              className="mt-3 text-[11px] px-3 py-1.5 rounded-xl bg-[var(--surface-2)] border border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)]">
              بازگردانی پیش‌فرض‌های نمایش
            </button>
          </div>
        </div>
      </section>

      <section className="study-section p-4 space-y-3">
        <h2 className="font-bold text-sm">اجرای دستی بازیابی (بدون تولید پاسخ)</h2>
        <p className="text-xs text-[var(--muted)] leading-relaxed">
          همین زنجیرهٔ واقعی چت اجرا می‌شود — بازنویسی پرسش، بردارسازی، جست‌وجوی برداری، BM25،
          ادغام RRF و بازرتبه‌بندی — اما هیچ پاسخی از مدل گرفته نمی‌شود.
        </p>
        <textarea aria-label="پرسش برای بررسی بازیابی" rows={2} value={question}
          onChange={event => setQuestion(event.target.value)}
          placeholder="مثلاً: نیم‌ساز زاویه را از کدام صفحه بخوانم؟"
          className="w-full px-3 py-2 rounded-2xl bg-[var(--surface-2)] border border-[var(--border)] text-sm text-[var(--text)] outline-none focus:border-[var(--accent)]" />
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
          <label className="text-[var(--muted)]">شناسهٔ کاربر
            <input aria-label="شناسه کاربر" inputMode="numeric" dir="ltr" value={targetUser}
              onChange={event => setTargetUser(event.target.value.replace(/[^0-9]/g, ""))}
              className="block w-full bg-transparent border-b border-[var(--border-strong)] py-1.5 text-[var(--text)]" />
          </label>
          <label className="text-[var(--muted)]">top-k
            <input aria-label="top-k" inputMode="numeric" dir="ltr" value={topK}
              onChange={event => setTopK(event.target.value.replace(/[^0-9]/g, ""))}
              className="block w-full bg-transparent border-b border-[var(--border-strong)] py-1.5 text-[var(--text)]" />
          </label>
          <div className="flex flex-col gap-1.5 pt-4">
            <label className="flex items-center gap-2 text-[var(--muted)]">
              <input type="checkbox" checked={rewrite} onChange={event => setRewrite(event.target.checked)} />
              بازنویسی پرسش با LLM
            </label>
            <label className="flex items-center gap-2 text-[var(--muted)]">
              <input type="checkbox" checked={questionBank} onChange={event => setQuestionBank(event.target.checked)} />
              بانک سؤال
            </label>
            <label className="flex items-center gap-2 text-[var(--muted)]">
              <input type="checkbox" checked={images} onChange={event => setImages(event.target.checked)} />
              تصویر صفحات
            </label>
          </div>
        </div>
        <button type="button" onClick={runPlayground} disabled={busy || !question.trim()}
          className="text-sm px-4 py-2 rounded-2xl bg-[var(--accent)] text-[var(--surface)] font-bold disabled:opacity-40">
          {busy ? "در حال اجرا…" : "اجرای بازیابی"}
        </button>
        <p className="text-[10px] text-[var(--muted-2)]">
          بازنویسی پرسش یک فراخوانی مدل زبانی است؛ اگر سهمیهٔ روزانه محدود است خاموش بگذار.
        </p>
      </section>

      <section className="study-section p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <h2 className="font-bold text-sm">ردهای ثبت‌شده</h2>
          <span className="text-[10px] text-[var(--muted-2)]">
            {fa(traces.length)} مورد {kind === "all" ? "در کل" : "با این نوع"}
          </span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {[["all", "همه"], ...kindOptions.filter(([key]) => key !== "all")].map(([key, label]) => (
            <button key={key} type="button" aria-pressed={kind === key}
              disabled={busy} onClick={() => { activeKind.current = key; setKind(key); void loadList(key); }}
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors ${kind === key ? "border-[var(--accent)] text-[var(--accent)]" : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)]"}`}>
              {label}{counts[key] ? ` (${fa(counts[key])})` : ""}
            </button>
          ))}
        </div>

        {traces.length === 0 ? (
          <p className="text-xs text-[var(--muted-2)]">
            هنوز ردّی ثبت نشده است؛ یک پرسش در چت بپرس، دفترچه بساز یا همین بازیابی دستی را اجرا کن.
          </p>
        ) : (
          <ul className="rag-trace-list">
            {traces.map(trace => (
              <li key={trace.id}>
                <button type="button" disabled={busy} onClick={() => openTrace(trace.id)} aria-pressed={selectedId === trace.id}
                  className={`w-full text-start px-3 py-2 rounded-2xl border transition-colors ${selectedId === trace.id ? "border-[var(--accent)] bg-[var(--surface-2)]" : "border-[var(--border)] hover:bg-[var(--surface-2)]/50"}`}>
                  <span className="flex items-baseline gap-2 flex-wrap">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-md border ${trace.status === "error" ? "border-red-400/60 text-red-400" : "border-[var(--border)] text-[var(--muted)]"}`}>
                      {trace.kind_label}
                    </span>
                    <span className="text-xs text-[var(--text)] truncate max-w-full">{trace.title || trace.question || trace.id}</span>
                    <span className="ms-auto text-[10px] text-[var(--muted-2)] tabular-nums" dir="ltr">{fa(trace.duration_ms, 1)} ms</span>
                  </span>
                  <span className="block text-[10px] text-[var(--muted-2)] mt-0.5">
                    {stamp(trace.created_at)}
                    {trace.user_id != null ? ` · کاربر #${fa(trace.user_id)}` : ""}
                    {trace.status === "running" ? " · در حال اجرا" : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {listErr && <p role="alert" className="rag-error text-xs">{listErr}</p>}
      {err && <p role="alert" className="rag-error text-xs">{err}</p>}
      {detailLoading && <p role="status" className="rag-detail-loading">در حال دریافت جزئیات رد انتخاب‌شده…</p>}

      {selected && (
        <section className="study-section p-4">
          <h2 className="font-bold text-sm mb-3">جزئیات گام‌به‌گام</h2>
          <TraceView trace={selected} settings={view} embeddingMap={embeddingMap ?? undefined} />
        </section>
      )}
    </div>
  );
}
