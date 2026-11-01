/**
 * F2 — authoring review screen (standalone view, synthetic data first).
 *
 * Read-only by default. Human decision entry appears only when a decision API is
 * injected; there is deliberately no "approve all", no eligibility override and
 * no client-side bypass of revision/hash binding.
 *
 * Safety rules implemented here:
 * - every string from data is rendered as a React text node (never raw HTML);
 * - images resolve only through the bundled approved-source registry, so record
 *   ids can never select an arbitrary URL or file path;
 * - evidence states are derived from bound receipts, and model agreement can
 *   only ever produce "model_only", never a human verification.
 */

import { useContext, useEffect, useId, useMemo, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { SourceResolverContext } from "./approvedSources";
import {
  DECISION_OPTIONS,
  submitDecision,
  type DecisionForm,
  type ReviewDecisionApi,
} from "./decisions";
import {
  BINDING_FIELD_LABELS,
  EVIDENCE_STATE_LABELS,
  ZOOM_MIN,
  describeEvidenceState,
  dimensionLabel,
  evidenceStateFor,
  faNum,
  formatZoom,
  isFormControl,
  isReceiptCurrent,
  nextRecordIndex,
  outcomeLabel,
  receiptBindingGaps,
  shortHash,
  summarize,
  zoomBy,
} from "./model";
import {
  EVIDENCE_DIMENSIONS,
  type EvidenceDimension,
  type EvidenceState,
  type ReviewDataset,
  type ReviewRecord,
  type TextSegment,
} from "./types";
import "./authoring-review.css";
import { directionRuns } from "./textDirection";

const STATE_TONE: Record<EvidenceState, string> = {
  verified_human: "ok",
  rejected: "bad",
  model_only: "model",
  stale: "warn",
  missing: "bad",
  disagreement: "bad",
  unresolved: "neutral",
};

const TRANSCRIPTION_LABEL: Record<ReviewRecord["transcriptionState"], string> = {
  verbatim: "بازخوانی کلمه‌به‌کلمه",
  candidate: "بازخوانی پیشنهادی",
  uncertain: "بازخوانی نامطمئن",
};

const ANSWER_LABEL: Record<ReviewRecord["answer"]["state"], string> = {
  candidate: "پاسخ پیشنهادی",
  unresolved: "بدون پاسخ قطعی",
  disagreement: "اختلاف پاسخ",
  verified_human: "تأیید انسانی",
};

const TAG_LABEL: Record<ReviewRecord["curriculum"]["tags"][number]["state"], string> = {
  confirmed: "نگاشت فهرست",
  inferred: "برچسب استنباطی",
  unmapped: "بدون نگاشت",
};

const DIFFICULTY_LABEL: Record<NonNullable<ReviewRecord["curriculum"]["intendedDifficulty"]>, string> = {
  easy: "آسان",
  konkur: "کنکوری",
  hard: "دشوار",
  extreme: "بسیار دشوار",
};

const STAGE_LABEL: Record<"given" | "constructed" | "requested", string> = {
  given: "داده‌شده",
  constructed: "ساخته‌شده",
  requested: "خواسته‌شده",
};

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return faNum(date.toISOString().slice(0, 10));
}

function toneClass(kind: string): string {
  return `ar-badge ar-badge--${kind}`;
}

/* ------------------------------- small parts ------------------------------ */

function Badge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={toneClass(tone)}>{children}</span>;
}

function ApprovedImage({
  imageId,
  label,
  zoom = 1,
}: {
  imageId: string | null;
  label: string;
  zoom?: number;
}) {
  const source = useContext(SourceResolverContext)(imageId);
  if (!source) {
    return (
      <div className="ar-missing" role="note">
        <strong>تصویر تأییدشده در دسترس نیست</strong>
        <p>{label}</p>
        <p className="ar-missing-meta">شناسهٔ منبع تأیید نشده است؛ هیچ درخواست تصویری ارسال نمی‌شود.</p>
      </div>
    );
  }
  return (
    <figure className="ar-figure">
      <div
        className="ar-image-scroll"
        tabIndex={0}
        role="group"
        aria-label={`${label} — برای پیمایش با کلیدهای جهت‌دار`}
      >
        <img
          src={source.src}
          alt={source.alt}
          width={source.width}
          height={source.height}
          style={{ width: `${Math.round(zoom * 100)}%` }}
        />
      </div>
      <figcaption>{label}</figcaption>
    </figure>
  );
}

function TranscriptionText({ segments }: { segments: TextSegment[] }) {
  if (segments.length === 0) {
    return <p className="ar-empty">هیچ متنی برای این رکورد استخراج نشده است.</p>;
  }
  return (
    <p className="ar-transcription">
      {segments.map((segment, index) =>
        segment.kind === "math" ? (
          <bdi key={index} className="ar-math" dir="ltr">
            {segment.value}
          </bdi>
        ) : (
          <span key={index}>{directionRuns(segment.value).map((run,i)=>run.ltr ? <bdi key={i} className="ar-ltr-run" dir="ltr">{run.value}</bdi> : <span key={i}>{run.value}</span>)}</span>
        ),
      )}
    </p>
  );
}

function SourceViewer({
  record,
  zoom,
  onZoom,
}: {
  record: ReviewRecord;
  zoom: number;
  onZoom: (next: number) => void;
}) {
  const [panel, setPanel] = useState<"crop" | "page" | "figure">("crop");

  useEffect(() => {
    setPanel("crop");
  }, [record.questionId]);

  const panels = [
    { id: "crop" as const, label: "برش پرسش", imageId: record.source.cropImageId },
    { id: "page" as const, label: "صفحهٔ کامل", imageId: record.source.pageImageId },
  ];
  const figureMissing = record.figure.expected && !record.figure.imageId;

  return (
    <section className="ar-panel ar-viewer" aria-labelledby="ar-source-heading">
      <div className="ar-panel-head">
        <h2 id="ar-source-heading">منبع اصلی</h2>
        <div className="ar-zoom" role="group" aria-label="بزرگ‌نمایی منبع">
          <button
            type="button"
            className="ar-icon-btn"
            onClick={() => onZoom(zoomBy(zoom, -1))}
            disabled={zoom <= ZOOM_MIN}
            aria-label="کوچک‌نمایی"
          >
            −
          </button>
          <span className="ar-zoom-value" aria-live="polite">
            {formatZoom(zoom)}
          </span>
          <button
            type="button"
            className="ar-icon-btn"
            onClick={() => onZoom(zoomBy(zoom, 1))}
            disabled={zoom >= 2.5}
            aria-label="بزرگ‌نمایی"
          >
            +
          </button>
          <button type="button" className="ar-text-btn" onClick={() => onZoom(1)}>
            اندازهٔ اصلی
          </button>
        </div>
      </div>

      <div className="ar-segmented" role="group" aria-label="انتخاب تصویر منبع">
        {panels.map((entry) => (
          <button
            key={entry.id}
            type="button"
            aria-pressed={panel === entry.id}
            onClick={() => setPanel(entry.id)}
          >
            {entry.label}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={panel === "figure"}
          onClick={() => setPanel("figure")}
        >
          شکل
          {record.figure.expected ? "" : " (ندارد)"}
        </button>
      </div>

      {panel === "figure" ? (
        record.figure.imageId ? (
          <ApprovedImage
            imageId={record.figure.imageId}
            label={record.figure.label ?? "شکل پرسش"}
            zoom={zoom}
          />
        ) : figureMissing ? (
          <div className="ar-missing" role="note">
            <strong>شکل ادعا شده اما تصویر تأییدشده‌ای ثبت نشده است</strong>
            <p>{record.figure.label ?? "برچسب شکل نیز ثبت نشده است."}</p>
            <p className="ar-missing-meta">این رکورد تا پیوست تصویر تأییدشده بازبینی‌پذیر نیست.</p>
          </div>
        ) : (
          <p className="ar-empty">{record.figure.expected===null ? "وضعیت شکل هنوز بررسی نشده است.":"این پرسش شکل ندارد."}</p>
        )
      ) : (
        <ApprovedImage
          imageId={panel === "crop" ? record.source.cropImageId : record.source.pageImageId}
          label={panel === "crop" ? (record.synthetic ? "برش پرسش (ساختگی)":"برش اصلی پرسش") : (record.synthetic ? "صفحهٔ کامل (ساختگی)":"صفحهٔ کامل")}
          zoom={zoom}
        />
      )}

      <p
        className={`ar-figure-status${record.figure.expected && !record.figure.imageId ? " is-missing" : ""}`}
        role="note"
      >
        {record.figure.expected ? (
          <>
            <span className="ar-figure-status-label">شکل:</span>
            {record.figure.imageId ? (
              <span>{record.figure.label ?? "شکل تأییدشده"}</span>
            ) : (
              <span>
                ادعا شده اما تصویر تأییدشده‌ای ثبت نشده است.
                {record.figure.label ? ` ${record.figure.label}` : ""}
              </span>
            )}
          </>
        ) : (
          <span>{record.figure.expected===null ? "وضعیت شکل هنوز بررسی نشده است.":"این پرسش شکل ندارد."}</span>
        )}
      </p>

      <dl className="ar-source-meta">
        <div>
          <dt>سند</dt>
          <dd>{record.source.documentLabel}</dd>
        </div>
        <div>
          <dt>نشست / دفترچه</dt>
          <dd>
            {record.source.session} · {record.source.booklet}
          </dd>
        </div>
        <div>
          <dt>صفحهٔ PDF / چاپی</dt>
          <dd>
            {faNum(record.source.pdfPage)} /{" "}
            {record.source.printedPage === null ? "نامشخص" : faNum(record.source.printedPage)}
          </dd>
        </div>
        <div>
          <dt>شناسهٔ سند</dt>
          <dd className="ar-mono" dir="ltr">
            {record.source.documentId}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function EvidenceDetails({ record }: { record: ReviewRecord }) {
  return (
    <ul className="ar-evidence">
      {EVIDENCE_DIMENSIONS.map((dimension) => {
        const state = evidenceStateFor(record, dimension.id);
        const receipts = record.receipts.filter((entry) => entry.dimension === dimension.id);
        return (
          <li key={dimension.id} className={`ar-evidence-row ar-evidence-row--${STATE_TONE[state]}`}>
            <div className="ar-evidence-head">
              <span className="ar-evidence-label">{dimension.label}</span>
              <Badge tone={STATE_TONE[state]}>{EVIDENCE_STATE_LABELS[state]}</Badge>
            </div>
            <p className="ar-evidence-note">{describeEvidenceState(state, receipts)}</p>
            {receipts.length > 0 && (
              <details className="ar-receipts">
                <summary>
                  رسیدها ({faNum(receipts.length)})
                  {state === "model_only" && " — فقط مدل"}
                </summary>
                <ul>
                  {receipts.map((receipt) => {
                    const current = isReceiptCurrent(record, receipt);
                    const gaps = current ? [] : receiptBindingGaps(record, receipt);
                    const superseded = receipts.some(
                      (other) =>
                        other.receiptId !== receipt.receiptId &&
                        other.reviewerKind === receipt.reviewerKind &&
                        isReceiptCurrent(record, other) &&
                        (other.supersedes ?? []).includes(receipt.receiptId),
                    );
                    const binding = receipt.binding ?? null;
                    return (
                      <li key={receipt.receiptId} className={current ? "" : "is-stale"}>
                        <div className="ar-receipt-head">
                          <span>{outcomeLabel(receipt.outcome)}</span>
                          <span>
                            {receipt.reviewerKind === "human"
                              ? "بازبین انسانی"
                              : `مدل ${receipt.model ?? receipt.reviewerIdentifier}`}
                          </span>
                          {!current && <Badge tone="warn">منقضی</Badge>}
                          {current && superseded && <Badge tone="neutral">جایگزین‌شده</Badge>}
                        </div>
                        <p className="ar-receipt-meta">
                          {formatTimestamp(receipt.timestamp)} · نسخهٔ{" "}
                          {binding ? faNum(binding.questionRevision) : "ناموجود"} · هش{" "}
                          <span className="ar-mono">
                            {binding ? shortHash(binding.contentHash) : "—"}
                          </span>
                          {binding
                            ? ` · سند ${binding.documentId} (${binding.documentRevision}) · فهرست ${binding.catalogueVersion}`
                            : " · شواهد ثبت نشده"}
                          {receipt.promptVersion ? ` · ${receipt.promptVersion}` : ""}
                          {receipt.reviewerKind === "human" ? ` · ${receipt.reviewerIdentifier}` : ""}
                        </p>
                        {receipt.note && <p>{receipt.note}</p>}
                        {superseded && current && (
                          <p className="ar-receipt-warning">
                            این رسید با رسیدِ جایگزینِ همان نوع باطل شده است؛ برای تاریخچه می‌ماند و در
                            وضعیت شواهد دخالت ندارد.
                          </p>
                        )}
                        {!current && (
                          <p className="ar-receipt-warning">
                            این رسید به نسخه/هش فعلی بسته نیست
                            {gaps.length > 0
                              ? ` (${gaps.map((key) => BINDING_FIELD_LABELS[key]).join("، ")})`
                              : ""}{" "}
                            و به‌عنوان شاهد پذیرفته نمی‌شود.
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </details>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function DecisionPanel({
  record,
  api,
}: {
  record: ReviewRecord;
  api?: ReviewDecisionApi;
}) {
  const [form, setForm] = useState<DecisionForm>({
    dimension: "extraction",
    decision: "pass",
    reviewerIdentifier: "",
    note: "",
  });
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    setResult(null);
  }, [record.questionId]);

  if (!api) {
    if (!record.synthetic) return <section className="ar-panel"><h2>بازبینی علمی جداگانه</h2><p>ثبت نظر دربارهٔ تطبیق متن در بخش اصلی صفحه فعال است. داوری علمی مستقل، ابتدا حل بدون مشاهدهٔ پاسخ می‌خواهد؛ این مرحله برای بررسی متن لازم نیست.</p></section>;
    return (
      <section className="ar-panel ar-decision" aria-labelledby="ar-decision-heading">
        <h2 id="ar-decision-heading">ثبت تصمیم انسانی</h2>
        <div className="ar-dependency" role="status">
          <strong>وابستگی: قرارداد داوری سمت سرور در دسترس نیست.</strong>
          <p>
            این صفحه فقط‌خواندنی است. هیچ دکمهٔ تأیید، «قبول همه» یا تغییر وضعیت واجدشرایطی
            وجود ندارد و این نمای مستقل هیچ درخواستی به سرور نمی‌فرستد.
          </p>
          <p className="ar-dependency-sub">
            برای فعال‌شدن ثبت تصمیم، مسیر زیر باید توسط مالک سرور پیاده‌سازی و مجوزدهی شود:
          </p>
          <ul>
            <li>
              <code dir="ltr">POST /api/authoring/reviews/&#123;question_id&#125;/decisions</code> با
              بدنهٔ <code dir="ltr">&#123;question_revision, content_hash, evidence_binding: &#123;document_id, document_revision, page_image_hash, crop_image_hash, figure_image_hash, catalogue_version&#125;, dimension, decision, reviewer_kind: "human", note&#125;</code>
            </li>
            <li>هویت بازبین از نشست سرور خوانده شود؛ شناسهٔ اعلامی کاربر جای احراز هویت را نمی‌گیرد.</li>
            <li>
              سرور باید همهٔ فیلدهای <code dir="ltr">evidence_binding</code> را اتمیک با رکورد
              ذخیره‌شده تطبیق دهد؛ هر ناسازگاریِ شناسه/نسخه/هش/سند/تصویر/فهرست با ۴۰۹ رد شود.
            </li>
            <li>هر تصمیم فقط یک بُعد را ثبت کند؛ پذیرش رکورد، محاسبهٔ واجدشرایطی و وضعیت انتشار سمت سرور بماند.</li>
          </ul>
        </div>
      </section>
    );
  }

  const submitApi = api;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    const response = await submitDecision(submitApi, record, form);
    setPending(false);
    setResult(
      response.ok
        ? { ok: true, text: `رسید ثبت شد: ${response.receiptId}` }
        : { ok: false, text: response.message },
    );
  }

  return (
    <section className="ar-panel ar-decision" aria-labelledby="ar-decision-heading">
      <h2 id="ar-decision-heading">ثبت تصمیم انسانی</h2>
      <p className="ar-panel-note">
        هر تصمیم فقط برای همین نسخه ({faNum(record.questionRevision)})، همین هش
        (<span className="ar-mono">{shortHash(record.contentHash)}</span>) و همین شواهد — سند و
        نسخهٔ سند، هش تصاویر صفحه/برش/شکل و نسخهٔ فهرست درسی — ارسال می‌شود و سرور همه را دوباره
        با رکورد ذخیره‌شده تطبیق می‌دهد. هویت و مجوز شما سمت سرور بررسی می‌شود؛ این فرم فقط
        انتساب ثبت می‌کند.
      </p>
      <form className="ar-decision-form" onSubmit={onSubmit}>
        <label>
          بُعد
          <select
            value={form.dimension}
            onChange={(event) =>
              setForm((previous) => ({
                ...previous,
                dimension: event.target.value as EvidenceDimension,
              }))
            }
          >
            {EVIDENCE_DIMENSIONS.map((dimension) => (
              <option key={dimension.id} value={dimension.id}>
                {dimension.label}
              </option>
            ))}
          </select>
        </label>
        <fieldset>
          <legend>تصمیم</legend>
          {DECISION_OPTIONS.map((option) => (
            <label key={option.value} className="ar-radio">
              <input
                type="radio"
                name="decision"
                value={option.value}
                checked={form.decision === option.value}
                onChange={() =>
                  setForm((previous) => ({ ...previous, decision: option.value }))
                }
              />
              {option.label}
            </label>
          ))}
        </fieldset>
        <label>
          شناسهٔ بازبین (اعلامی)
          <input
            type="text"
            value={form.reviewerIdentifier}
            onChange={(event) =>
              setForm((previous) => ({ ...previous, reviewerIdentifier: event.target.value }))
            }
            autoComplete="off"
            placeholder="شناسهٔ سازمانی خود را وارد کنید"
            required
          />
        </label>
        <label>
          یادداشت قابل‌بررسی
          <textarea
            value={form.note}
            onChange={(event) => setForm((previous) => ({ ...previous, note: event.target.value }))}
            rows={3}
            placeholder="چه شاهدی دیدید و چرا این تصمیم را می‌گیرید؟"
            required
          />
        </label>
        <button type="submit" className="ar-primary" disabled={pending}>
          {pending ? "در حال ثبت…" : "ثبت تصمیم برای این بُعد"}
        </button>
      </form>
      {result && (
        <p role="status" className={result.ok ? "ar-result ar-result--ok" : "ar-result ar-result--bad"}>
          {result.text}
        </p>
      )}
    </section>
  );
}

/* --------------------------------- screen -------------------------------- */

export type AuthoringReviewScreenProps = {
  dataset: ReviewDataset;
  /** Absent in this workspace: the screen stays read-only. */
  decisionApi?: ReviewDecisionApi;
  initialQuestionId?: string;
};

export default function AuthoringReviewScreen({
  dataset,
  decisionApi,
  initialQuestionId,
}: AuthoringReviewScreenProps) {
  const headingId = useId();
  const records = dataset.records;
  const [activeId, setActiveId] = useState(() =>
    initialQuestionId && records.some((record) => record.questionId === initialQuestionId)
      ? initialQuestionId
      : records[0]?.questionId ?? "",
  );
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [zoom, setZoom] = useState(1);
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const visible = useMemo(
    () =>
      attentionOnly
        ? records.filter((record) => summarize([record]).needsDecision > 0)
        : records,
    [records, attentionOnly],
  );
  const datasetSummary = useMemo(() => summarize(records), [records]);
  const activeIndex = Math.max(
    0,
    visible.findIndex((record) => record.questionId === activeId),
  );
  const active = visible[activeIndex] ?? records[0];

  useEffect(() => {
    if (visible.length > 0 && !visible.some((record) => record.questionId === activeId)) {
      setActiveId(visible[0].questionId);
    }
  }, [visible, activeId]);

  function selectIndex(index: number) {
    const next = visible[index];
    if (!next) return;
    setActiveId(next.questionId);
    buttonRefs.current[index]?.focus();
  }

  function onListKeyDown(event: ReactKeyboardEvent<HTMLOListElement>) {
    if (isFormControl(event.target)) return;
    // RTL layout: ArrowRight is "back", ArrowLeft is "forward".
    const translated =
      event.key === "ArrowRight"
        ? "ArrowUp"
        : event.key === "ArrowLeft"
          ? "ArrowDown"
          : event.key;
    const next = nextRecordIndex(activeIndex, visible.length, translated);
    if (next === activeIndex) return;
    event.preventDefault();
    selectIndex(next);
  }

  if (!active) {
    return (
      <div className="authoring-review" dir="rtl">
        <div className="ar-eligible" role="note">
          <strong>هیچ رکوردی برای نمایش نیست</strong>
          <p>این بسته هیچ رکوردی ندارد؛ فهرست و شمارش واجدشرایطی فقط از سرور می‌آید.</p>
        </div>
      </div>
    );
  }

  const verifiedCount = EVIDENCE_DIMENSIONS.filter(
    (dimension) => evidenceStateFor(active, dimension.id) === "verified_human",
  ).length;

  return (
    <div className="authoring-review" dir="rtl">
      <a className="ar-skip" href="#ar-main">
        پرش به محتوای بازبینی
      </a>

      <header className="ar-header">
        <div>
          <p className="ar-kicker">بازبینی نویسندگی آزمون · نمای مستقل F2</p>
          <h1 id={headingId}>{dataset.title}</h1>
          <p className="ar-subtitle">
            {dataset.synthetic ? "پیش‌نمایش با دادهٔ ساختگی؛ هیچ رکوردی از آزمون واقعی نمایش داده نمی‌شود.":"جزئیات منبع واقعی و رسیدهای مستقلِ هر بُعد."}
          </p>
        </div>
        <dl className="ar-header-meta">
          <div>
            <dt>نسخهٔ عکس فوری</dt>
            <dd className="ar-mono" dir="ltr">
              {dataset.snapshotVersion}
            </dd>
          </div>
          <div>
            <dt>سیاست بازبینی</dt>
            <dd className="ar-mono" dir="ltr">
              {dataset.policyVersion}
            </dd>
          </div>
          <div>
            <dt>ساخته‌شده</dt>
            <dd>{formatTimestamp(dataset.generatedAt)}</dd>
          </div>
        </dl>
      </header>

      <div className="ar-synthetic" role="note">
        <Badge tone="model">{dataset.synthetic ? "دادهٔ ساختگی" : "منبع واقعی — در انتظار بازبینی"}</Badge>
        <p>{dataset.synthetic ? "شواهد ساختگی‌اند؛ این بسته تأیید انسانی واقعی ندارد." : "متن پیشنهادی است. تصاویر، برش‌های اصلی به ترتیب صفحات هستند؛ تصویر کامل صفحه نیستند. ثبت تصمیم مجوز انتشار ایجاد نمی‌کند."}</p>
      </div>

      <div className="ar-eligible" role="note">
        <strong>{faNum(dataset.eligibleCount)} رکورد واجد شرایط</strong>
        <ul>
          {dataset.eligibilityNotes.map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      </div>

      <div className="ar-workspace">
        <aside className="ar-rail" aria-label="فهرست رکوردهای بازبینی">
          <div className="ar-filter" role="group" aria-label="صافی فهرست">
            <button
              type="button"
              aria-pressed={!attentionOnly}
              onClick={() => setAttentionOnly(false)}
            >
              همه ({faNum(records.length)})
            </button>
            <button
              type="button"
              aria-pressed={attentionOnly}
              onClick={() => setAttentionOnly(true)}
            >
              نیازمند تصمیم ({faNum(datasetSummary.needsDecision)})
            </button>
          </div>

          <ul className="ar-counts" aria-label="شمارش وضعیت‌ها">
            <li>
              <span>رسید منقضی</span>
              <strong>{faNum(datasetSummary.stale)}</strong>
            </li>
            <li>
              <span>اختلاف</span>
              <strong>{faNum(datasetSummary.disagreement)}</strong>
            </li>
            <li>
              <span>تصویر ناموجود</span>
              <strong>{faNum(datasetSummary.missingImages)}</strong>
            </li>
          </ul>

          {visible.length === 0 ? (
            <p className="ar-empty">هیچ رکوردی با این صافی مطابقت ندارد.</p>
          ) : (
            <ol
              className="ar-record-list"
              onKeyDown={onListKeyDown}
              aria-label="رکوردها؛ با کلیدهای بالا و پایین جابه‌جا شوید"
            >
              {visible.map((record, index) => {
                const selected = record.questionId === active.questionId;
                const itemSummary = summarize([record]);
                return (
                  <li key={record.questionId}>
                    <button
                      type="button"
                      ref={(element) => {
                        buttonRefs.current[index] = element;
                      }}
                      tabIndex={selected ? 0 : -1}
                      aria-current={selected ? "true" : undefined}
                      className={selected ? "is-active" : ""}
                      onClick={() => selectIndex(index)}
                    >
                      <span className="ar-record-id ar-mono" dir="ltr">
                        {record.questionId}
                      </span>
                      <span className="ar-record-page">
                        صفحهٔ {faNum(record.source.pdfPage)}
                      </span>
                      <span className="ar-record-flags">
                        {itemSummary.needsDecision > 0 && <Badge tone="warn">نیازمند تصمیم</Badge>}
                        {itemSummary.stale > 0 && <Badge tone="warn">منقضی</Badge>}
                        {itemSummary.disagreement > 0 && <Badge tone="bad">اختلاف</Badge>}
                        {itemSummary.missingImages > 0 && <Badge tone="bad">تصویر ندارد</Badge>}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          )}

          <div className="ar-step-buttons">
            <button
              type="button"
              className="ar-text-btn"
              onClick={() => selectIndex(Math.max(0, activeIndex - 1))}
              disabled={activeIndex === 0}
            >
              رکورد قبلی
            </button>
            <button
              type="button"
              className="ar-text-btn"
              onClick={() => selectIndex(Math.min(visible.length - 1, activeIndex + 1))}
              disabled={activeIndex >= visible.length - 1}
            >
              رکورد بعدی
            </button>
          </div>

          <p className="ar-hint">
            <kbd>↑</kbd> <kbd>↓</kbd> یا <kbd>j</kbd> <kbd>k</kbd> برای جابه‌جایی؛ در چیدمان
            راست‌به‌چپ <kbd>←</kbd> رکورد بعد و <kbd>→</kbd> رکورد قبل است.
          </p>
        </aside>

        <main id="ar-main" className="ar-reader" aria-labelledby={headingId}>
          <p className="ar-sr" role="status" aria-live="polite">
            رکورد {active.questionId} نمایش داده می‌شود.
          </p>

          <div className="ar-record-head">
            <div>
              <p className="ar-kicker">رکورد فعال</p>
              <h2 className="ar-mono" dir="ltr">
                {active.questionId}
              </h2>
            </div>
            <div className="ar-record-badges">
              <Badge tone={active.synthetic ? "model" : "neutral"}>
                {active.synthetic ? "ساختگی" : "واقعی"}
              </Badge>
              <Badge tone="neutral">نسخهٔ {faNum(active.questionRevision)}</Badge>
              <Badge tone="neutral">
                هش <span className="ar-mono">{shortHash(active.contentHash)}</span>
              </Badge>
              <Badge tone={active.transcriptionState === "verbatim" ? "ok" : "warn"}>
                {TRANSCRIPTION_LABEL[active.transcriptionState]}
              </Badge>
              {active.continuation && <Badge tone="warn">ادامه‌دار</Badge>}
              {active.figure.expected && <Badge tone="neutral">شکل‌دار</Badge>}
            </div>
          </div>

          <div className="ar-split">
            <SourceViewer record={active} zoom={zoom} onZoom={setZoom} />

            <section className="ar-panel ar-transcription-panel" aria-labelledby="ar-transcription-heading">
              <div className="ar-panel-head">
                <h2 id="ar-transcription-heading">بازخوانی فارسی</h2>
                <Badge
                  tone={active.transcriptionState === "verbatim" ? "ok" : active.transcriptionState === "candidate" ? "warn" : "bad"}
                >
                  {TRANSCRIPTION_LABEL[active.transcriptionState]}
                </Badge>
              </div>
              <TranscriptionText segments={active.transcription} />

              {active.continuation && (
                <div className="ar-continuation" role="note">
                  <strong>
                    بخش {faNum(active.continuation.part)} از {faNum(active.continuation.total)}
                  </strong>
                  <p>{active.continuation.note}</p>
                </div>
              )}

              <div className="ar-subsection">
                <h3>نمادهای نامطمئن</h3>
                {active.uncertainSymbols.length === 0 ? (
                  <p className="ar-empty">نماد نامطمئنی ثبت نشده است.</p>
                ) : (
                  <ul className="ar-symbols">
                    {active.uncertainSymbols.map((symbol, index) => (
                      <li key={index}>
                        <code dir="auto">{symbol.marker}</code>
                        <span>{symbol.note}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="ar-subsection">
                <h3>گزینه‌ها (به ترتیب چاپ)</h3>
                {active.options.length === 0 ? (
                  <p className="ar-empty">هیچ گزینه‌ای استخراج نشده است.</p>
                ) : (
                  <ol className="ar-options">
                    {active.options.map((option) => {
                      const claimed =
                        active.answer.state !== "unresolved" &&
                        active.answer.state !== "disagreement" &&
                        active.answer.normalizedIndex === option.index;
                      return (
                        <li
                          key={option.index}
                          className={claimed ? "is-claimed" : ""}
                        >
                          <span className="ar-option-index">{faNum(option.index + 1)}</span>
                          <span className="ar-option-text">{option.text}</span>
                          {option.uncertain && <Badge tone="warn">ناخوانا</Badge>}
                          {claimed && <Badge tone="neutral">گزینهٔ ادعاشده</Badge>}
                        </li>
                      );
                    })}
                  </ol>
                )}
              </div>
            </section>
          </div>

          <div className="ar-split ar-split--even">
            <section className="ar-panel" aria-labelledby="ar-answer-heading">
              <div className="ar-panel-head">
                <h2 id="ar-answer-heading">منبع پاسخ</h2>
                <Badge
                  tone={
                    active.answer.state === "verified_human"
                      ? "ok"
                      : active.answer.state === "disagreement"
                        ? "bad"
                        : active.answer.state === "unresolved"
                          ? "neutral"
                          : "warn"
                  }
                >
                  {ANSWER_LABEL[active.answer.state]}
                </Badge>
              </div>
              <p className="ar-answer-line">
                {active.answer.normalizedIndex === null
                  ? "هیچ گزینه‌ای به‌عنوان پاسخ قطعی ثبت نشده است."
                  : `گزینهٔ ${faNum(active.answer.normalizedIndex + 1)}`}
                {active.answer.rawKey && (
                  <span className="ar-raw-key" dir="auto">
                    کلید خام: {active.answer.rawKey}
                  </span>
                )}
              </p>
              <p className="ar-answer-source">{active.answer.sourceLabel}</p>
              {active.answer.documentId && (
                <p className="ar-mono ar-answer-source" dir="ltr">
                  {active.answer.documentId}
                </p>
              )}
              {active.answer.imageId && (
                <ApprovedImage imageId={active.answer.imageId} label={active.synthetic ? "برگهٔ کلید (ساختگی)":"پاسخ ناشر"} />
              )}
              {active.answer.claims.length === 0 ? (
                <p className="ar-empty">ادعای پاسخی برای این رکورد ثبت نشده است.</p>
              ) : (
                <ul className="ar-claims">
                  {active.answer.claims.map((claim, index) => (
                    <li key={index}>
                      <div className="ar-claim-head">
                        <span>{claim.source}</span>
                        {claim.modelOnly && <Badge tone="model">پیشنهاد مدل</Badge>}
                      </div>
                      <p>{claim.note}</p>
                    </li>
                  ))}
                </ul>
              )}
              <p className="ar-panel-note">
                کلید خام و نگاشت آن جدا نگه داشته می‌شوند؛ نگاشت پیشنهادی مدل تأیید انسانی نیست.
              </p>
            </section>

            <section className="ar-panel" aria-labelledby="ar-curriculum-heading">
              <div className="ar-panel-head">
                <h2 id="ar-curriculum-heading">برچسب‌های برنامهٔ درسی</h2>
                <Badge tone="neutral">فهرست {active.curriculum.catalogueVersion}</Badge>
              </div>
              {active.curriculum.tags.length === 0 ? (
                <p className="ar-empty">هیچ برچسبی ثبت نشده است.</p>
              ) : (
                <ul className="ar-tags">
                  {active.curriculum.tags.map((tag) => (
                    <li key={tag.id}>
                      <span>{tag.label}</span>
                      <Badge tone={tag.state === "inferred" ? "model" : tag.state === "unmapped" ? "neutral" : "ok"}>
                        {TAG_LABEL[tag.state]}
                      </Badge>
                      <span className="ar-mono ar-tag-id" dir="ltr">
                        {tag.id}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <dl className="ar-difficulty">
                <div>
                  <dt>دشواری هدفمند</dt>
                  <dd>
                    {active.curriculum.intendedDifficulty
                      ? DIFFICULTY_LABEL[active.curriculum.intendedDifficulty]
                      : "ثبت نشده"}
                  </dd>
                </div>
                <div>
                  <dt>دشواری تجربی</dt>
                  <dd>{active.curriculum.empiricalDifficulty === null ? "ثبت نشده" : "—"}</dd>
                </div>
              </dl>
              <p className="ar-panel-note">
                «برچسب استنباطی» پیشنهاد مدل است و داوری انسانی یا تأیید علمی محسوب نمی‌شود.
              </p>
            </section>
          </div>

          <section className="ar-panel" aria-labelledby="ar-evidence-heading">
            <div className="ar-panel-head">
              <h2 id="ar-evidence-heading">وضعیت شواهد</h2>
              <Badge tone={verifiedCount === EVIDENCE_DIMENSIONS.length ? "ok" : "warn"}>
                {faNum(verifiedCount)} از {faNum(EVIDENCE_DIMENSIONS.length)} بُعد تأیید انسانی
              </Badge>
            </div>
            <p className="ar-panel-note">
              هر بُعد وضعیت جداگانه دارد. توافق مدل‌ها «تأیید انسانی» نیست و رسید فقط برای همان
              نسخه و هش معتبر است.
            </p>
            <EvidenceDetails record={active} />
          </section>

          <section className="ar-panel" aria-labelledby="ar-annotations-heading">
            <div className="ar-panel-head">
              <h2 id="ar-annotations-heading">برچسب‌های استنباطی و مسیر حل</h2>
              <Badge tone="model">مدل‌محور</Badge>
            </div>
            {active.annotations === null ? (
              <p className="ar-empty">هیچ برچسب یا مسیر حلی برای این رکورد ثبت نشده است.</p>
            ) : (
              <>
                <div className="ar-annotation-meta">
                  <Badge tone={active.annotations.annotationState === "unresolved" ? "warn" : "model"}>
                    {active.annotations.annotationState === "unresolved" ? "حل‌نشده" : "پیشنهادی"}
                  </Badge>
                  <span>
                    {active.annotations.annotator.kind === "human"
                      ? `بازبین انسانی: ${active.annotations.annotator.identifier}`
                      : `برچسب‌زن مدل: ${active.annotations.annotator.model ?? active.annotations.annotator.identifier}`}
                  </span>
                  <span className="ar-mono" dir="ltr">
                    {active.annotations.taxonomyVersion}
                  </span>
                  {active.annotations.annotator.promptVersion && (
                    <span className="ar-mono" dir="ltr">
                      {active.annotations.annotator.promptVersion}
                    </span>
                  )}
                </div>
                {active.annotations.objective && (
                  <p className="ar-objective">
                    هدف: {active.annotations.objective.label}{" "}
                    <span className="ar-mono" dir="ltr">
                      {active.annotations.objective.id}
                    </span>
                  </p>
                )}
                <div className="ar-subsection">
                  <h3>نمایش‌ها</h3>
                  <ul className="ar-representations">
                    {active.annotations.representations.map((item) => (
                      <li key={item.id}>
                        <span>{item.label}</span>
                        <Badge tone="neutral">{STAGE_LABEL[item.stage]}</Badge>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="ar-subsection">
                  <h3>مسیرهای حل</h3>
                  <ul className="ar-routes">
                    {active.annotations.routes.map((route) => (
                      <li key={route.id}>
                        <div className="ar-route-head">
                          <span className="ar-mono" dir="ltr">
                            {route.id}
                          </span>
                          <Badge tone={route.role === "primary" ? "model" : "neutral"}>
                            {route.role === "primary" ? "مسیر اصلی" : "مسیر جایگزین"}
                          </Badge>
                        </div>
                        <ul>
                          {route.techniques.map((technique) => (
                            <li key={technique.id}>
                              <span>{technique.evidence}</span>
                              <span className="ar-mono ar-tech-id" dir="ltr">
                                {technique.id}
                              </span>
                              <Badge tone="neutral">
                                {technique.role === "primary"
                                  ? "اصلی"
                                  : technique.role === "supporting"
                                    ? "پشتیبان"
                                    : "بررسی"}
                              </Badge>
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </div>
                <p className="ar-panel-note">
                  این برچسب‌ها از سوی مدل پیشنهاد شده‌اند و تأیید علمی یا انسانی نیستند.
                </p>
              </>
            )}
          </section>

          {active.disagreements.length > 0 && (
            <section className="ar-panel ar-disagreement" aria-labelledby="ar-disagreement-heading">
              <h2 id="ar-disagreement-heading">اختلاف‌ها</h2>
              <ul>
                {active.disagreements.map((entry) => (
                  <li key={entry.dimension}>
                    <div className="ar-claim-head">
                      <Badge tone="bad">{dimensionLabel(entry.dimension)}</Badge>
                      <span>{entry.summary}</span>
                    </div>
                    <ul className="ar-claims">
                      {entry.claims.map((claim, index) => (
                        <li key={index}>
                          <strong>{claim.source}</strong>
                          <p>{claim.statement}</p>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
              <p className="ar-panel-note">اختلاف تا داوری انسانی حل‌شده محسوب نمی‌شود.</p>
            </section>
          )}

          <section className="ar-panel" aria-labelledby="ar-issues-heading">
            <h2 id="ar-issues-heading">مسائل ثبت‌شده</h2>
            {active.issues.length === 0 ? (
              <p className="ar-empty">هیچ مسئله‌ای برای این رکورد ثبت نشده است.</p>
            ) : (
              <ul className="ar-issues">
                {active.issues.map((issue, index) => (
                  <li key={index}>{issue}</li>
                ))}
              </ul>
            )}
            <div className="ar-eligibility">
              <h3>وضعیت واجدشرایطی (سمت سرور)</h3>
              <p>
                <Badge tone="neutral">نگه‌داشته‌شده</Badge>
                {active.eligibility.policyVersion && (
                  <span className="ar-mono" dir="ltr">
                    {active.eligibility.policyVersion}
                  </span>
                )}
              </p>
              <ul>
                {active.eligibility.reasons.map((reason, index) => (
                  <li key={index}>{reason}</li>
                ))}
              </ul>
              <p className="ar-panel-note">
                این صفحه وضعیت واجدشرایطی را تغییر نمی‌دهد و راهی برای دور زدن آن ندارد.
              </p>
            </div>
          </section>

          <DecisionPanel record={active} api={decisionApi} />
        </main>
      </div>
    </div>
  );
}
