/**
 * Pure helpers for the authoring review screen.
 *
 * Kept free of React and browser APIs so the same rules are unit-testable and
 * cannot drift between the rendered component and its tests.
 */

import {
  EVIDENCE_DIMENSIONS,
  type EvidenceBinding,
  type EvidenceBindingKey,
  type EvidenceDimension,
  type EvidenceReceipt,
  type EvidenceState,
  type FigureInfo,
  type ReviewRecord,
} from "./types";

const FA_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

/** Convert Latin digits to Persian digits for display. */
export function faNum(value: number | string): string {
  return String(value).replace(/[0-9]/g, (digit) => FA_DIGITS[Number(digit)]);
}

export const ZOOM_MIN = 1;
export const ZOOM_MAX = 2.5;
export const ZOOM_STEP = 0.25;

export function clampZoom(value: number): number {
  if (!Number.isFinite(value)) return ZOOM_MIN;
  const rounded = Math.round(value * 100) / 100;
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, rounded));
}

/** direction 1 zooms in, -1 zooms out, 0 resets to 100%. */
export function zoomBy(current: number, direction: -1 | 0 | 1): number {
  if (direction === 0) return ZOOM_MIN;
  return clampZoom(current + direction * ZOOM_STEP);
}

export function formatZoom(zoom: number): string {
  return `${faNum(Math.round(clampZoom(zoom) * 100))}٪`;
}

/**
 * Roving record navigation: arrows and j/k move by one without wrapping,
 * Home/End jump to the ends. Unknown keys leave the selection unchanged.
 */
export function nextRecordIndex(current: number, count: number, key: string): number {
  if (count <= 0) return 0;
  const safeCurrent = Math.min(count - 1, Math.max(0, current));
  switch (key) {
    case "ArrowDown":
    case "j":
    case "J":
      return Math.min(count - 1, safeCurrent + 1);
    case "ArrowUp":
    case "k":
    case "K":
      return Math.max(0, safeCurrent - 1);
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return safeCurrent;
  }
}

export function isFormControl(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return Boolean(
    target.closest("input, textarea, select, option, [contenteditable='true']"),
  );
}

/** Human-facing label for every binding field (stale-receipt explanations). */
export const BINDING_FIELD_LABELS: Record<EvidenceBindingKey, string> = {
  evidenceToken: "نسخهٔ بسته و پیوند پاسخ",
  questionId: "شناسهٔ پرسش",
  questionRevision: "نسخهٔ پرسش",
  contentHash: "هش محتوا",
  documentId: "شناسهٔ سند",
  documentRevision: "نسخهٔ سند",
  pageImageHash: "هش تصویر صفحه",
  cropImageHash: "هش تصویر برش",
  figureImageHash: "هش تصویر شکل",
  catalogueVersion: "نسخهٔ فهرست درسی",
};

const BINDING_KEYS = Object.keys(BINDING_FIELD_LABELS) as EvidenceBindingKey[];

/** A binding value is missing when it is absent, empty or of the wrong type. */
function isMissingBindingValue(key: EvidenceBindingKey, value: unknown): boolean {
  if (key === "evidenceToken") return value !== undefined && (typeof value !== "string" || value.length === 0);
  if (key === "questionRevision") {
    return !Number.isInteger(value) || (value as number) < 0;
  }
  if (key === "pageImageHash" || key === "cropImageHash" || key === "figureImageHash") {
    if (value === undefined || value === null) return value === undefined;
    return typeof value !== "string" || value.trim() === "";
  }
  return typeof value !== "string" || value.trim() === "";
}

/**
 * Hash an image reference must carry for the binding to be complete.
 * Returns null only when the image genuinely does not exist in the approved
 * set (`src:missing…` ids / absent figure), and undefined when a referenced
 * image has no hash — an incomplete binding that must never count as current.
 */
function imageHashFor(
  imageId: string | null,
  hash: string | null | undefined,
): string | null | undefined {
  if (imageId === null || imageId.startsWith("src:missing")) {
    return hash == null ? null : undefined;
  }
  if (typeof hash !== "string" || hash.trim() === "") return undefined;
  return hash;
}

function figureHashFor(figure: FigureInfo): string | null | undefined {
  return imageHashFor(figure.imageId, figure.imageHash);
}

/**
 * The exact evidence set the record currently presents to a reviewer, or null
 * when the record itself is incomplete (e.g. an image without a hash) — in
 * that case no receipt can be proven current and none may approve.
 */
export function bindingFor(record: ReviewRecord): EvidenceBinding | null {
  const candidate = {
    ...(record.evidenceToken ? { evidenceToken: record.evidenceToken } : {}),
    questionId: record.questionId,
    questionRevision: record.questionRevision,
    contentHash: record.contentHash,
    documentId: record.source.documentId,
    documentRevision: record.source.documentRevision,
    pageImageHash: imageHashFor(record.source.pageImageId, record.source.pageImageHash),
    cropImageHash: imageHashFor(record.source.cropImageId, record.source.cropImageHash),
    figureImageHash: figureHashFor(record.figure),
    catalogueVersion: record.curriculum.catalogueVersion,
  } as EvidenceBinding;
  for (const key of BINDING_KEYS) {
    if (isMissingBindingValue(key, candidate[key])) return null;
  }
  return candidate;
}

/**
 * Binding fields of this receipt that are missing, empty or different from the
 * record's current evidence. Non-empty means the receipt may not be treated as
 * evidence for this record ("reject stale/missing bindings rather than assume
 * current").
 */
export function receiptBindingGaps(
  record: ReviewRecord,
  receipt: EvidenceReceipt,
): EvidenceBindingKey[] {
  const expected = bindingFor(record);
  const actual = receipt.binding as EvidenceBinding | undefined;
  const gaps: EvidenceBindingKey[] = [];
  for (const key of BINDING_KEYS) {
    const want: unknown = expected ? expected[key] : undefined;
    const got: unknown = actual ? actual[key] : undefined;
    if (isMissingBindingValue(key, want) || isMissingBindingValue(key, got) || want !== got) {
      gaps.push(key);
    }
  }
  return gaps;
}

/**
 * A receipt covers only the exact evidence set it was recorded against:
 * question id + revision + content hash + document identity/revision +
 * source/figure image hashes + catalogue version. Anything missing or changed
 * makes it stale.
 */
export function isReceiptCurrent(record: ReviewRecord, receipt: EvidenceReceipt): boolean {
  return receiptBindingGaps(record, receipt).length === 0;
}

/**
 * Derive one dimension's state from bound receipts and explicit record flags.
 *
 * Rules, in order:
 * - an explicit record disagreement always wins;
 * - only receipts bound to the record's full evidence set participate, and a
 *   receipt explicitly superseded by a current same-kind receipt is kept for
 *   history but is not operative;
 * - conflicting current human judgments (pass + fail, including a failure
 *   recorded after a pass) surface as "disagreement" — an explicit failure
 *   never disappears behind a pass;
 * - a lone current human failure is "rejected", never "verified_human";
 * - model agreement can only reach "model_only", never human verification.
 */
export function evidenceStateFor(
  record: ReviewRecord,
  dimension: EvidenceDimension,
): EvidenceState {
  if (record.disagreements.some((entry) => entry.dimension === dimension)) {
    return "disagreement";
  }

  const receipts = record.receipts.filter((receipt) => receipt.dimension === dimension);
  const current = receipts.filter((receipt) => isReceiptCurrent(record, receipt));

  // Supersession only applies between current receipts of the same kind, so a
  // model receipt can never erase a human judgment (or vice versa).
  const byId = new Map(record.receipts.map((receipt) => [receipt.receiptId, receipt]));
  const supersededIds = new Set<string>();
  for (const receipt of current) {
    for (const id of receipt.supersedes ?? []) {
      if (id === receipt.receiptId) continue;
      const target = byId.get(id);
      if (target && target.reviewerKind === receipt.reviewerKind) {
        supersededIds.add(id);
      }
    }
  }
  const operative = current.filter((receipt) => !supersededIds.has(receipt.receiptId));

  const human = operative.filter((receipt) => receipt.reviewerKind === "human");
  const humanPassed = human.some((receipt) => receipt.outcome === "passed");
  const humanFailed = human.some((receipt) => receipt.outcome === "failed");
  const humanUnresolved = human.some((receipt) => receipt.outcome === "unresolved");
  if (humanFailed && humanPassed) return "disagreement";
  if (humanFailed) return "rejected";
  if (humanUnresolved) return "unresolved";
  if (humanPassed) return "verified_human";

  const model = operative.filter((receipt) => receipt.reviewerKind === "model");
  const modelPassed = model.some((receipt) => receipt.outcome === "passed");
  const modelFailed = model.some((receipt) => receipt.outcome === "failed");
  if (modelFailed && modelPassed) return "disagreement";
  if (modelPassed) return "model_only";
  if (modelFailed) return "unresolved";

  if (receipts.length > 0 && current.length === 0) {
    return "stale";
  }
  if (record.evidenceMissing.includes(dimension)) {
    return "missing";
  }
  return "unresolved";
}

export const EVIDENCE_STATE_LABELS: Record<EvidenceState, string> = {
  verified_human: "تأیید انسانی",
  rejected: "رد انسانی",
  model_only: "فقط مدل",
  stale: "رسید منقضی",
  missing: "شاهد ناموجود",
  disagreement: "اختلاف",
  unresolved: "داوری‌نشده",
};

export function describeEvidenceState(
  state: EvidenceState,
  receipts: EvidenceReceipt[],
): string {
  switch (state) {
    case "verified_human":
      return "رسید انسانیِ بسته‌شده به همین نسخه، هش، سند، تصاویر و فهرست درسی.";
    case "rejected":
      return "بازبین انسانی این بُعد را برای همین نسخه و شواهد رد کرده است؛ تا تکلیف/داوری صریح پذیرفته نمی‌شود.";
    case "model_only":
      return "پیشنهاد مدل؛ بازبینی انسانی برای این بُعد ثبت نشده است.";
    case "stale":
      return `رسید به شواهد فعلیِ این رکورد بسته نیست (${faNum(receipts.length)} رسید منقضی).`;
    case "missing":
      return "شاهد یا تصویر متناظر در بستهٔ تأییدشده نیست.";
    case "disagreement":
      return "ادعاهای ناسازگار؛ داوری انسانی لازم است.";
    default:
      if (receipts.some((receipt) => receipt.outcome === "failed" && receipt.reviewerKind === "model")) {
        return "مدل این بُعد را رد کرده است؛ هنوز داوری انسانی ثبت نشده است.";
      }
      if (receipts.some((receipt) => receipt.outcome === "unresolved")) {
        return "فقط رسیدِ حل‌نشده ثبت شده است؛ تأیید نهایی وجود ندارد.";
      }
      if (receipts.some((receipt) => receipt.outcome === "passed")) {
        return "تأیید و حل‌نشده همزمان ثبت شده‌اند؛ تا تکلیف صریح، تأیید نهایی نیست.";
      }
      return "هیچ رسید یا داوری‌ای ثبت نشده است.";
  }
}

export function outcomeLabel(outcome: EvidenceReceipt["outcome"]): string {
  switch (outcome) {
    case "passed":
      return "قبول";
    case "failed":
      return "رد";
    default:
      return "حل‌نشده";
  }
}

export function shortHash(hash: string | null): string {
  if (!hash) return "—";
  return hash.slice(0, 12);
}

export function dimensionLabel(dimension: EvidenceDimension): string {
  return EVIDENCE_DIMENSIONS.find((entry) => entry.id === dimension)?.label ?? dimension;
}

export type ReviewSummary = {
  total: number;
  /** Eligibility is a server decision; the preview never accepts one from data. */
  eligible: number;
  needsDecision: number;
  stale: number;
  disagreement: number;
  missingImages: number;
};

export function summarize(records: readonly ReviewRecord[]): ReviewSummary {
  let needsDecision = 0;
  let stale = 0;
  let disagreement = 0;
  let missingImages = 0;

  for (const record of records) {
    if (
      EVIDENCE_DIMENSIONS.some(
        (dimension) => evidenceStateFor(record, dimension.id) !== "verified_human",
      )
    ) {
      needsDecision += 1;
    }
    if (record.receipts.some((receipt) => !isReceiptCurrent(record, receipt))) {
      stale += 1;
    }
    if (record.disagreements.length > 0) {
      disagreement += 1;
    }
    if (
      record.source.pageImageId.startsWith("src:missing") ||
      record.source.cropImageId.startsWith("src:missing") ||
      (record.figure.expected && !record.figure.imageId)
    ) {
      missingImages += 1;
    }
  }

  return {
    total: records.length,
    eligible: 0,
    needsDecision,
    stale,
    disagreement,
    missingImages,
  };
}
