/**
 * Synthetic review fixture — F2.
 *
 * Nothing here comes from a real exam, booklet, student or answer key. Text is
 * invented to exercise layout and state handling: missing images, a continuation
 * without its next page, unreadable symbols, stale receipts, conflicting answer
 * keys, a model-only judgment, and a dataset with zero eligible records.
 */

import type {
  EvidenceBinding,
  EvidenceDimension,
  EvidenceReceipt,
  ReviewDataset,
  ReviewRecord,
  TextSegment,
} from "./types";

const t = (value: string): TextSegment => ({ kind: "text", value });
const m = (value: string): TextSegment => ({ kind: "math", value });

const POLICY = "review-policy-v0.1";
const TAXONOMY = "st-0.1";

type ReceiptInit = {
  id: string;
  dimension: EvidenceDimension;
  outcome?: EvidenceReceipt["outcome"];
  reviewerKind?: EvidenceReceipt["reviewerKind"];
  reviewerIdentifier: string;
  model?: string | null;
  promptVersion?: string | null;
  at: string;
  binding: EvidenceBinding;
  supersedes?: string[];
};

function receipt(init: ReceiptInit): EvidenceReceipt {
  return {
    receiptId: init.id,
    dimension: init.dimension,
    outcome: init.outcome ?? "passed",
    reviewerKind: init.reviewerKind ?? "model",
    reviewerIdentifier: init.reviewerIdentifier,
    model: init.model ?? null,
    promptVersion: init.promptVersion ?? null,
    timestamp: init.at,
    binding: init.binding,
    supersedes: init.supersedes ?? [],
    synthetic: true,
  };
}

const HASH_Q1 = "sha256:0f4c1a92be77d310";
const HASH_Q2 = "sha256:7b81de33c4a09512";
const HASH_Q3 = "sha256:2c6e90f5ab14d807";
const HASH_Q4_OLD = "sha256:5aa0c71d9e3b2846";
const HASH_Q4 = "sha256:e13f70bc58a2d694";
const HASH_Q5 = "sha256:98d2b4f0c6e71935";

const CATALOGUE = "curriculum-synthetic-0.3";
const DOC_REV = "doc-rev:1";
/** Synthetic hashes of the approved page/crop/figure images the fixtures show. */
const IMG_PAGE_SYNTH = "sha256:aa11ce0000000001";
const IMG_CROP_Q1 = "sha256:bb22ce0000000002";
const IMG_CROP_Q5 = "sha256:cc33ce0000000003";
const IMG_FIGURE_PARABOLA = "sha256:dd44ce0000000004";
const IMG_CROP_Q4_OLD = "sha256:ee55ce0000000005";

/*
 * Evidence bindings: every receipt and decision covers exactly this evidence
 * set (S0 v0.1 review receipt). Image hashes are null only where the approved
 * set genuinely has no image.
 */
const B_Q1: EvidenceBinding = {
  questionId: "syn-0001-q1",
  questionRevision: 3,
  contentHash: HASH_Q1,
  documentId: "doc:synthetic:math-a",
  documentRevision: DOC_REV,
  pageImageHash: IMG_PAGE_SYNTH,
  cropImageHash: IMG_CROP_Q1,
  figureImageHash: null,
  catalogueVersion: CATALOGUE,
};
const B_Q2: EvidenceBinding = {
  questionId: "syn-0002-q2",
  questionRevision: 1,
  contentHash: HASH_Q2,
  documentId: "doc:synthetic:math-a",
  documentRevision: DOC_REV,
  pageImageHash: null,
  cropImageHash: null,
  figureImageHash: null,
  catalogueVersion: CATALOGUE,
};
const B_Q2_OLD_FIG: EvidenceBinding = {
  ...B_Q2,
  questionRevision: 0,
  contentHash: "sha256:9d10af3c5b7e2248",
};
const B_Q3: EvidenceBinding = {
  questionId: "syn-0003-q3",
  questionRevision: 1,
  contentHash: HASH_Q3,
  documentId: "doc:synthetic:math-a",
  documentRevision: DOC_REV,
  pageImageHash: IMG_PAGE_SYNTH,
  cropImageHash: IMG_CROP_Q1,
  figureImageHash: IMG_FIGURE_PARABOLA,
  catalogueVersion: CATALOGUE,
};
const B_Q4: EvidenceBinding = {
  questionId: "syn-0004-q4",
  questionRevision: 5,
  contentHash: HASH_Q4,
  documentId: "doc:synthetic:math-a",
  documentRevision: DOC_REV,
  pageImageHash: IMG_PAGE_SYNTH,
  cropImageHash: IMG_CROP_Q1,
  figureImageHash: null,
  catalogueVersion: CATALOGUE,
};
const B_Q4_OLD: EvidenceBinding = {
  ...B_Q4,
  questionRevision: 2,
  contentHash: HASH_Q4_OLD,
  cropImageHash: IMG_CROP_Q4_OLD,
};
const B_Q5: EvidenceBinding = {
  questionId: "syn-0005-q5",
  questionRevision: 2,
  contentHash: HASH_Q5,
  documentId: "doc:synthetic:math-b",
  documentRevision: DOC_REV,
  pageImageHash: IMG_PAGE_SYNTH,
  cropImageHash: IMG_CROP_Q5,
  figureImageHash: IMG_FIGURE_PARABOLA,
  catalogueVersion: CATALOGUE,
};
const B_Q6: EvidenceBinding = {
  questionId: "syn-0006-q6",
  questionRevision: 1,
  contentHash: "sha256:0000000000000000",
  documentId: "doc:synthetic:unmapped",
  documentRevision: DOC_REV,
  pageImageHash: null,
  cropImageHash: null,
  figureImageHash: null,
  catalogueVersion: CATALOGUE,
};

const q1: ReviewRecord = {
  synthetic: true,
  questionId: "syn-0001-q1",
  questionRevision: 3,
  contentHash: HASH_Q1,
  source: {
    documentId: "doc:synthetic:math-a",
    documentRevision: DOC_REV,
    documentLabel: "دفترچهٔ ساختگی ریاضی A",
    session: "آزمون ساختگی ۱",
    booklet: "A",
    pdfPage: 2,
    printedPage: 2,
    pageImageId: "src:page:synthetic",
    pageImageHash: IMG_PAGE_SYNTH,
    cropImageId: "src:crop:q1",
    cropImageHash: IMG_CROP_Q1,
  },
  transcriptionState: "verbatim",
  transcription: [t("ریشه‌های معادلهٔ زیر کدام‌اند؟"), m("x² − 5x + 6 = 0")],
  continuation: null,
  uncertainSymbols: [],
  options: [
    { index: 0, text: "دو و سه" },
    { index: 1, text: "منفی دو و منفی سه" },
    { index: 2, text: "یک و شش" },
    { index: 3, text: "منفی یک و منفی شش" },
  ],
  answer: {
    state: "candidate",
    normalizedIndex: 0,
    rawKey: "②",
    documentId: "doc:synthetic:key-a",
    sourceLabel: "برگهٔ کلید ساختگی A",
    imageId: "src:answer:key",
    claims: [
      {
        source: "برگهٔ کلید ساختگی A",
        normalizedIndex: 0,
        rawKey: "②",
        note: "کلید چاپی به گزینهٔ دوم نگاشت شده؛ این نگاشت فقط پیشنهاد مدل است.",
        modelOnly: true,
      },
    ],
  },
  figure: { expected: false, imageId: null, imageHash: null, label: null },
  curriculum: {
    catalogueVersion: CATALOGUE,
    tags: [
      { id: "math.quadratic", label: "معادلات درجهٔ دوم", state: "inferred" },
      { id: "math.factoring", label: "تجزیه", state: "inferred" },
      { id: "math.roots", label: "ریشه‌یابی", state: "unmapped" },
    ],
    intendedDifficulty: "konkur",
    empiricalDifficulty: null,
  },
  evidenceMissing: ["figure_fidelity"],
  disagreements: [],
  receipts: [
    receipt({
      id: "rcp-q1-extraction",
      dimension: "extraction",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-20T08:12:00Z",
      binding: B_Q1,
    }),
    receipt({
      id: "rcp-q1-answer",
      dimension: "answer_association",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-a",
      promptVersion: "answer-link-v0.2",
      at: "2026-10-20T08:14:00Z",
      binding: B_Q1,
    }),
    receipt({
      id: "rcp-q1-science",
      dimension: "science",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-b",
      promptVersion: "science-check-v0.1",
      at: "2026-10-20T08:15:00Z",
      binding: B_Q1,
    }),
    receipt({
      id: "rcp-q1-editorial",
      dimension: "editorial",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-20T08:20:00Z",
      binding: B_Q1,
    }),
    receipt({
      id: "rcp-q1-curriculum",
      dimension: "curriculum",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-a",
      promptVersion: "tag-v0.3",
      at: "2026-10-20T08:22:00Z",
      binding: B_Q1,
    }),
  ],
  annotations: {
    annotationState: "candidate",
    taxonomyVersion: TAXONOMY,
    annotator: {
      kind: "model",
      identifier: "model:fixture-local",
      model: "fixture-model-a",
      promptVersion: "st-annotate-v0.1",
    },
    objective: { id: "solve-quadratic", label: "حل معادلهٔ درجهٔ دوم" },
    representations: [{ id: "equation", label: "معادله", stage: "given" }],
    routes: [
      {
        id: "route-factoring",
        role: "primary",
        techniques: [
          { id: "factor-trinomial", role: "primary", evidence: "تجزیهٔ سه‌جمله‌ای" },
          { id: "substitute-roots", role: "check", evidence: "جای‌گذاری ریشه‌ها" },
        ],
      },
    ],
  },
  issues: ["نگاشت پاسخ به گزینه فقط از سوی مدل پیشنهاد شده است."],
  eligibility: {
    state: "held",
    reasons: ["بازبینی انسانیِ ابعاد باقی‌مانده انجام نشده است."],
    policyVersion: POLICY,
  },
};

const q2: ReviewRecord = {
  synthetic: true,
  questionId: "syn-0002-q2",
  questionRevision: 1,
  contentHash: HASH_Q2,
  source: {
    documentId: "doc:synthetic:math-a",
    documentRevision: DOC_REV,
    documentLabel: "دفترچهٔ ساختگی ریاضی A",
    session: "آزمون ساختگی ۱",
    booklet: "A",
    pdfPage: 4,
    printedPage: null,
    pageImageId: "src:missing:page:syn-0002",
    pageImageHash: null,
    cropImageId: "src:missing:crop:syn-0002",
    cropImageHash: null,
  },
  transcriptionState: "candidate",
  transcription: [t("مقدار عبارت زیر را بیابید."), m("√(۲ + √۳)")],
  continuation: {
    part: 1,
    total: 2,
    note: "ادامهٔ صورت پرسش در صفحهٔ بعد است؛ تصویر صفحهٔ بعد در بسته نیست.",
  },
  uncertainSymbols: [{ marker: "√", note: "علامت رادیکال در برش مبهم است." }],
  options: [
    { index: 0, text: "دو" },
    { index: 1, text: "یک" },
    { index: 2, text: "گزینهٔ سوم ناخوانا", uncertain: true },
    { index: 3, text: "صفر" },
  ],
  answer: {
    state: "unresolved",
    normalizedIndex: null,
    rawKey: null,
    documentId: null,
    sourceLabel: "کلیدی برای این پرسش در بسته نیست",
    imageId: null,
    claims: [],
  },
  figure: {
    expected: true,
    imageId: null,
    imageHash: null,
    label: "شکل ادعایی؛ هیچ تصویر تأییدشده‌ای ثبت نشده است.",
  },
  curriculum: {
    catalogueVersion: CATALOGUE,
    tags: [{ id: "math.radicals", label: "رادیکال‌ها", state: "inferred" }],
    intendedDifficulty: null,
    empiricalDifficulty: null,
  },
  evidenceMissing: [
    "extraction",
    "figure_fidelity",
    "editorial",
    "science",
    "intended_difficulty",
  ],
  disagreements: [],
  receipts: [
    receipt({
      id: "rcp-q2-extraction",
      dimension: "extraction",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-a",
      promptVersion: "ocr-audit-v0.1",
      at: "2026-10-21T11:02:00Z",
      binding: B_Q2,
    }),
    receipt({
      id: "rcp-q2-figure-stale",
      dimension: "figure_fidelity",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-18T09:30:00Z",
      binding: B_Q2_OLD_FIG,
    }),
  ],
  annotations: null,
  issues: [
    "تصویر صفحه و برش در بستهٔ تأییدشده نیست.",
    "ادعای وجود شکل تأیید نشده است.",
  ],
  eligibility: {
    state: "held",
    reasons: ["منبع تصویری تأییدشده موجود نیست.", "ادامهٔ پرسش در بسته نیست."],
    policyVersion: POLICY,
  },
};

const q3: ReviewRecord = {
  synthetic: true,
  questionId: "syn-0003-q3",
  questionRevision: 1,
  contentHash: HASH_Q3,
  source: {
    documentId: "doc:synthetic:math-a",
    documentRevision: DOC_REV,
    documentLabel: "دفترچهٔ ساختگی ریاضی A",
    session: "آزمون ساختگی ۱",
    booklet: "A",
    pdfPage: 5,
    printedPage: 5,
    pageImageId: "src:page:synthetic",
    pageImageHash: IMG_PAGE_SYNTH,
    cropImageId: "src:crop:q1",
    cropImageHash: IMG_CROP_Q1,
  },
  transcriptionState: "uncertain",
  transcription: [t("با توجه به نمودار، عرض رأس سهمی کدام است؟"), m("x_v = ?")],
  continuation: {
    part: 2,
    total: 3,
    note: "بخش دوم از سه بخش؛ بخش سوم در بسته نیست.",
  },
  uncertainSymbols: [
    { marker: "?", note: "عدد در تصویر خوانا نیست." },
    { marker: "x_v", note: "نماد رأس در بازخوانی خودکار با نماد دیگری اشتباه شده است." },
  ],
  options: [
    { index: 0, text: "یک" },
    { index: 1, text: "دو" },
    { index: 2, text: "دو و نیم", uncertain: true },
    { index: 3, text: "سه" },
  ],
  answer: {
    state: "candidate",
    normalizedIndex: 1,
    rawKey: "۲",
    documentId: "doc:synthetic:key-a",
    sourceLabel: "برگهٔ کلید ساختگی A",
    imageId: "src:answer:key",
    claims: [
      {
        source: "برگهٔ کلید ساختگی A",
        normalizedIndex: 1,
        rawKey: "۲",
        note: "کلید عددی است و به گزینه نگاشت نشده؛ نگاشت پیشنهادی مدل است.",
        modelOnly: true,
      },
    ],
  },
  figure: {
    expected: true,
    imageId: "src:figure:parabola",
    imageHash: IMG_FIGURE_PARABOLA,
    label: "نمودار سهمی (تصویر ساختگی تأییدشده)",
  },
  curriculum: {
    catalogueVersion: CATALOGUE,
    tags: [
      { id: "math.parabola", label: "سهمی", state: "confirmed" },
      { id: "math.vertex", label: "رأس", state: "inferred" },
    ],
    intendedDifficulty: "konkur",
    empiricalDifficulty: null,
  },
  evidenceMissing: ["intended_difficulty"],
  disagreements: [],
  receipts: [
    receipt({
      id: "rcp-q3-extraction",
      dimension: "extraction",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-a",
      promptVersion: "ocr-audit-v0.1",
      at: "2026-10-21T12:40:00Z",
      binding: B_Q3,
    }),
    receipt({
      id: "rcp-q3-editorial",
      dimension: "editorial",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-21T12:55:00Z",
      binding: B_Q3,
    }),
    receipt({
      id: "rcp-q3-figure",
      dimension: "figure_fidelity",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-21T12:58:00Z",
      binding: B_Q3,
    }),
    receipt({
      id: "rcp-q3-answer",
      dimension: "answer_association",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-a",
      promptVersion: "answer-link-v0.2",
      at: "2026-10-21T12:59:00Z",
      binding: B_Q3,
    }),
    receipt({
      id: "rcp-q3-science",
      dimension: "science",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-b",
      promptVersion: "science-check-v0.1",
      at: "2026-10-21T13:00:00Z",
      binding: B_Q3,
    }),
  ],
  annotations: {
    annotationState: "unresolved",
    taxonomyVersion: TAXONOMY,
    annotator: {
      kind: "model",
      identifier: "model:fixture-local",
      model: "fixture-model-b",
      promptVersion: "st-annotate-v0.1",
    },
    objective: { id: "read-vertex", label: "خواندن رأس از نمودار" },
    representations: [
      { id: "graph", label: "نمودار", stage: "given" },
      { id: "equation", label: "معادلهٔ سهمی", stage: "constructed" },
    ],
    routes: [
      {
        id: "route-vertex-form",
        role: "primary",
        techniques: [
          { id: "complete-square", role: "primary", evidence: "تشکیل مربع کامل" },
        ],
      },
      {
        id: "route-graph-read",
        role: "alternative",
        techniques: [
          { id: "read-axis", role: "supporting", evidence: "خواندن محور تقارن" },
        ],
      },
    ],
  },
  issues: [
    "رقم ناخوانا در تصویر؛ بازخوانی قطعی نیست.",
    "بخش سوم پرسش در بسته نیست.",
    "برچسب‌های برنامهٔ درسی از سوی مدل پیشنهاد شده‌اند.",
  ],
  eligibility: {
    state: "held",
    reasons: ["نویسهٔ نامطمئن و ادامهٔ گمشده."],
    policyVersion: POLICY,
  },
};

const q4: ReviewRecord = {
  synthetic: true,
  questionId: "syn-0004-q4",
  questionRevision: 5,
  contentHash: HASH_Q4,
  source: {
    documentId: "doc:synthetic:math-a",
    documentRevision: DOC_REV,
    documentLabel: "دفترچهٔ ساختگی ریاضی A",
    session: "آزمون ساختگی ۱",
    booklet: "A",
    pdfPage: 6,
    printedPage: 6,
    pageImageId: "src:page:synthetic",
    pageImageHash: IMG_PAGE_SYNTH,
    cropImageId: "src:crop:q1",
    cropImageHash: IMG_CROP_Q1,
  },
  transcriptionState: "verbatim",
  transcription: [
    t("تعداد ریشه‌های حقیقی معادلهٔ زیر چند است؟"),
    m("x² + 2x + 1 = 0"),
  ],
  continuation: null,
  uncertainSymbols: [],
  options: [
    { index: 0, text: "صفر" },
    { index: 1, text: "یک" },
    { index: 2, text: "دو" },
    { index: 3, text: "بی‌شمار" },
  ],
  answer: {
    state: "candidate",
    normalizedIndex: 1,
    rawKey: "۱",
    documentId: "doc:synthetic:key-a",
    sourceLabel: "برگهٔ کلید ساختگی A (نسخهٔ قدیمی)",
    imageId: "src:answer:key",
    claims: [
      {
        source: "برگهٔ کلید ساختگی A",
        normalizedIndex: 1,
        rawKey: "۱",
        note: "کلید چاپی؛ نسخهٔ کلید پیش از بازنگری صورت پرسش ثبت شده است.",
        modelOnly: false,
      },
    ],
  },
  figure: { expected: false, imageId: null, imageHash: null, label: null },
  curriculum: {
    catalogueVersion: CATALOGUE,
    tags: [
      { id: "math.quadratic", label: "معادلات درجهٔ دوم", state: "confirmed" },
      { id: "math.discriminant", label: "مبیّن", state: "inferred" },
    ],
    intendedDifficulty: "easy",
    empiricalDifficulty: null,
  },
  evidenceMissing: [],
  disagreements: [],
  receipts: [
    receipt({
      id: "rcp-q4-extraction-old",
      dimension: "extraction",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-14T10:00:00Z",
      binding: B_Q4_OLD,
    }),
    receipt({
      id: "rcp-q4-science-old",
      dimension: "science",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-b",
      promptVersion: "science-check-v0.1",
      at: "2026-10-14T10:05:00Z",
      binding: B_Q4_OLD,
    }),
    receipt({
      id: "rcp-q4-curriculum-old",
      dimension: "curriculum",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-14T10:07:00Z",
      binding: B_Q4_OLD,
    }),
    receipt({
      id: "rcp-q4-editorial-old",
      dimension: "editorial",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-14T10:09:00Z",
      binding: B_Q4_OLD,
    }),
    receipt({
      id: "rcp-q4-answer-current",
      dimension: "answer_association",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-a",
      promptVersion: "answer-link-v0.2",
      at: "2026-10-22T07:40:00Z",
      binding: B_Q4,
    }),
  ],
  annotations: {
    annotationState: "candidate",
    taxonomyVersion: TAXONOMY,
    annotator: {
      kind: "human",
      identifier: "بازبین-ساختگی",
      model: null,
      promptVersion: null,
    },
    objective: { id: "count-real-roots", label: "شمارش ریشه‌های حقیقی" },
    representations: [{ id: "equation", label: "معادله", stage: "given" }],
    routes: [
      {
        id: "route-discriminant",
        role: "primary",
        techniques: [{ id: "compute-delta", role: "primary", evidence: "محاسبهٔ مبیّن" }],
      },
    ],
  },
  issues: [
    "رسیدهای قبلی به نسخهٔ ۲ بسته‌اند و برای نسخهٔ ۵ معتبر نیستند.",
    "هیچ رسید فعلی برای استخراج وجود ندارد.",
  ],
  eligibility: {
    state: "held",
    reasons: ["رسیدها منقضی شده‌اند و باید از نو گرفته شوند."],
    policyVersion: POLICY,
  },
};

const q5: ReviewRecord = {
  synthetic: true,
  questionId: "syn-0005-q5",
  questionRevision: 2,
  contentHash: HASH_Q5,
  source: {
    documentId: "doc:synthetic:math-b",
    documentRevision: DOC_REV,
    documentLabel: "دفترچهٔ ساختگی ریاضی B",
    session: "آزمون ساختگی ۲",
    booklet: "B",
    pdfPage: 8,
    printedPage: 8,
    pageImageId: "src:page:synthetic",
    pageImageHash: IMG_PAGE_SYNTH,
    cropImageId: "src:crop:q5",
    cropImageHash: IMG_CROP_Q5,
  },
  transcriptionState: "verbatim",
  transcription: [
    t("با توجه به نمودار، کمینهٔ تابع کدام است؟"),
    m("y = (x − 2)² − 1"),
  ],
  continuation: null,
  uncertainSymbols: [],
  options: [
    { index: 0, text: "منفی یک" },
    { index: 1, text: "یک" },
    { index: 2, text: "دو" },
    { index: 3, text: "منفی دو" },
  ],
  answer: {
    state: "disagreement",
    normalizedIndex: 1,
    rawKey: "②",
    documentId: "doc:synthetic:key-a",
    sourceLabel: "دو کلید ناسازگار: برگهٔ کلید A و کلید بازبینی دوم",
    imageId: "src:answer:key",
    claims: [
      {
        source: "برگهٔ کلید A",
        normalizedIndex: 1,
        rawKey: "②",
        note: "کلید چاپی گزینهٔ دوم را نشان می‌دهد.",
        modelOnly: false,
      },
      {
        source: "کلید بازبینی دوم",
        normalizedIndex: 0,
        rawKey: "①",
        note: "کلید دوم گزینهٔ اول را نشان می‌دهد؛ تناقض حل نشده است.",
        modelOnly: false,
      },
    ],
  },
  figure: {
    expected: true,
    imageId: "src:figure:parabola",
    imageHash: IMG_FIGURE_PARABOLA,
    label: "نمودار ساختگی سهمی",
  },
  curriculum: {
    catalogueVersion: CATALOGUE,
    tags: [
      { id: "math.parabola", label: "سهمی", state: "confirmed" },
      { id: "math.minimum", label: "کمینه", state: "inferred" },
    ],
    intendedDifficulty: "konkur",
    empiricalDifficulty: null,
  },
  evidenceMissing: [],
  disagreements: [
    {
      dimension: "answer_association",
      summary: "دو کلید به دو گزینهٔ متفاوت اشاره می‌کنند.",
      claims: [
        { source: "برگهٔ کلید A", statement: "گزینهٔ دوم درست است." },
        { source: "کلید بازبینی دوم", statement: "گزینهٔ اول درست است." },
      ],
    },
    {
      dimension: "science",
      summary: "دو ادعای مدل دربارهٔ مقدار کمینه ناسازگارند.",
      claims: [
        { source: "مدل الف", statement: "کمینهٔ تابع منفی یک است." },
        { source: "مدل ب", statement: "کمینهٔ تابع یک است." },
      ],
    },
  ],
  receipts: [
    receipt({
      id: "rcp-q5-extraction",
      dimension: "extraction",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-22T09:10:00Z",
      binding: B_Q5,
    }),
    receipt({
      id: "rcp-q5-answer",
      dimension: "answer_association",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-a",
      promptVersion: "answer-link-v0.2",
      at: "2026-10-22T09:12:00Z",
      binding: B_Q5,
    }),
    receipt({
      id: "rcp-q5-science",
      dimension: "science",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-b",
      promptVersion: "science-check-v0.1",
      at: "2026-10-22T09:14:00Z",
      binding: B_Q5,
    }),
    receipt({
      id: "rcp-q5-figure",
      dimension: "figure_fidelity",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-22T09:20:00Z",
      binding: B_Q5,
    }),
    receipt({
      id: "rcp-q5-editorial",
      dimension: "editorial",
      reviewerKind: "human",
      reviewerIdentifier: "بازبین-ساختگی",
      at: "2026-10-22T09:22:00Z",
      binding: B_Q5,
    }),
    receipt({
      id: "rcp-q5-curriculum",
      dimension: "curriculum",
      reviewerIdentifier: "model:fixture-local",
      model: "fixture-model-a",
      promptVersion: "tag-v0.3",
      at: "2026-10-22T09:24:00Z",
      binding: B_Q5,
    }),
  ],
  annotations: {
    annotationState: "candidate",
    taxonomyVersion: TAXONOMY,
    annotator: {
      kind: "model",
      identifier: "model:fixture-local",
      model: "fixture-model-a",
      promptVersion: "st-annotate-v0.1",
    },
    objective: { id: "identify-minimum", label: "تشخیص کمینهٔ سهمی" },
    representations: [
      { id: "graph", label: "نمودار", stage: "given" },
      { id: "equation", label: "معادلهٔ رأس", stage: "given" },
    ],
    routes: [
      {
        id: "route-vertex",
        role: "primary",
        techniques: [{ id: "read-vertex", role: "primary", evidence: "خواندن رأس از فرم استاندارد" }],
      },
      {
        id: "route-candidates",
        role: "alternative",
        techniques: [{ id: "test-options", role: "check", evidence: "آزمودن گزینه‌ها" }],
      },
    ],
  },
  issues: [
    "دو کلید پاسخ ناسازگارند.",
    "اختلاف دو مدل دربارهٔ مقدار کمینه ثبت شده است.",
  ],
  eligibility: {
    state: "held",
    reasons: ["اختلاف پاسخ حل نشده است."],
    policyVersion: POLICY,
  },
};

const q6: ReviewRecord = {
  synthetic: true,
  questionId: "syn-0006-q6",
  questionRevision: 1,
  contentHash: "sha256:0000000000000000",
  source: {
    documentId: "doc:synthetic:unmapped",
    documentRevision: DOC_REV,
    documentLabel: "برگهٔ بدون منبع تأییدشده",
    session: "—",
    booklet: "—",
    pdfPage: 1,
    printedPage: null,
    pageImageId: "src:missing:page:syn-0006",
    pageImageHash: null,
    cropImageId: "src:missing:crop:syn-0006",
    cropImageHash: null,
  },
  transcriptionState: "uncertain",
  transcription: [],
  continuation: {
    part: 3,
    total: 3,
    note: "بخش پایانی؛ منبع تصویری در بسته نیست.",
  },
  uncertainSymbols: [{ marker: "؟", note: "هیچ متن قابل‌اتکایی استخراج نشده است." }],
  options: [],
  answer: {
    state: "unresolved",
    normalizedIndex: null,
    rawKey: null,
    documentId: null,
    sourceLabel: "بدون کلید در بسته",
    imageId: null,
    claims: [],
  },
  figure: { expected: false, imageId: null, imageHash: null, label: null },
  curriculum: {
    catalogueVersion: CATALOGUE,
    tags: [],
    intendedDifficulty: null,
    empiricalDifficulty: null,
  },
  evidenceMissing: [
    "extraction",
    "answer_association",
    "curriculum",
    "science",
    "editorial",
    "figure_fidelity",
    "intended_difficulty",
  ],
  disagreements: [],
  receipts: [],
  annotations: null,
  issues: [
    "هیچ منبع تصویری تأییدشده یا متن استخراج‌شده‌ای وجود ندارد.",
    "این رکورد برای نمایش حالت خالی نگه داشته شده است.",
  ],
  eligibility: {
    state: "held",
    reasons: [
      "رکورد به دلیل نبود منبع، متن و کلید از پذیرش کنار گذاشته شده است.",
      "تصمیم واجدشرایط بودن فقط سمت سرور است.",
    ],
    policyVersion: POLICY,
  },
};

export const SYNTHETIC_REVIEW_DATASET: ReviewDataset = {
  datasetId: "synthetic-review-v0.2",
  title: "بازبینی نویسندگی آزمون — بستهٔ ساختگی",
  snapshotVersion: "synthetic-snapshot-0.2",
  policyVersion: POLICY,
  generatedAt: "2026-10-23T09:00:00Z",
  synthetic: true,
  eligibleCount: 0,
  eligibilityNotes: [
    "هیچ رکوردی در این بسته واجد شرایط پذیرش نیست؛ شمارش واجدشرط فقط سمت سرور محاسبه می‌شود.",
    "همهٔ تصاویر و متن‌ها ساختگی‌اند و به آزمون واقعی اشاره نمی‌کنند.",
    "تصمیم انسانی تا اتصال قرارداد داوری غیرفعال است.",
  ],
  records: [q1, q2, q3, q4, q5, q6],
};

export const SYNTHETIC_RECORDS: readonly ReviewRecord[] = SYNTHETIC_REVIEW_DATASET.records;
