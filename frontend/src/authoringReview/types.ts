/**
 * Types for the F2 authoring review screen.
 *
 * These mirror the review-relevant parts of CONTRACTS.md v0.1 and the ST
 * reasoning annotation contract 0.1. Everything here is presentation data;
 * approval remains a server-side, receipt-backed decision.
 */

export const EVIDENCE_DIMENSIONS = [
  { id: "extraction", label: "استخراج" },
  { id: "answer_association", label: "پیوند پاسخ" },
  { id: "curriculum", label: "برنامهٔ درسی" },
  { id: "science", label: "درستی علمی" },
  { id: "editorial", label: "ویرایش" },
  { id: "figure_fidelity", label: "وفاداری شکل" },
  { id: "intended_difficulty", label: "دشواری هدفمند" },
] as const;

export type EvidenceDimension = (typeof EVIDENCE_DIMENSIONS)[number]["id"];

/** Evidence is never inferred from model agreement; each state is explicit. */
export type EvidenceState =
  | "verified_human"
  | "rejected"
  | "model_only"
  | "stale"
  | "missing"
  | "disagreement"
  | "unresolved";

/** Persian prose and isolated LTR mathematics are separate segments. */
export type TextSegment = { kind: "text" | "math"; value: string };

export type TranscriptionState = "verbatim" | "candidate" | "uncertain";

export type ReviewOption = {
  /** Zero-based printed order. */
  index: number;
  text: string;
  uncertain?: boolean;
};

/**
 * Exact evidence a receipt (or a decision) covers — mirrors the S0 v0.1
 * review-receipt contract: question id/revision, literal content hash, exact
 * source/figure image hashes, document identity/revision and the applicable
 * curriculum catalogue version. A receipt or decision that omits any of these
 * fields is treated as unbound, never as current.
 *
 * `figureImageHash` is null only when the record has no figure image; a record
 * that expects a figure without a hash has an incomplete binding.
 */
export type EvidenceBinding = {
  /** SR additive binding: includes answer/pairing and whole source-packet revision. */
  evidenceToken?: string;
  questionId: string;
  questionRevision: number;
  contentHash: string;
  documentId: string;
  documentRevision: string;
  /** Hash of the original page image the reviewer saw (null: no approved page image exists). */
  pageImageHash: string | null;
  /** Hash of the question crop the reviewer saw (null: no approved crop exists). */
  cropImageHash: string | null;
  figureImageHash: string | null;
  catalogueVersion: string;
};

export type EvidenceBindingKey = keyof EvidenceBinding;

export type EvidenceReceipt = {
  note?: string;
  receiptId: string;
  dimension: EvidenceDimension;
  outcome: "passed" | "failed" | "unresolved";
  reviewerKind: "human" | "model";
  reviewerIdentifier: string;
  model: string | null;
  promptVersion: string | null;
  timestamp: string;
  /** Binding: a receipt only covers this exact evidence set (see EvidenceBinding). */
  binding: EvidenceBinding;
  /**
   * Receipt IDs this receipt explicitly replaces (S0 `supersedes`). Superseded
   * receipts stay visible for history but are never operative evidence.
   */
  supersedes: string[];
  synthetic: boolean;
};

export type AnswerClaim = {
  source: string;
  /** Zero-based normalized option index. */
  normalizedIndex: number;
  rawKey: string;
  note: string;
  modelOnly: boolean;
};

export type AnswerState =
  | "candidate"
  | "unresolved"
  | "disagreement"
  | "verified_human";

export type ReviewAnswer = {
  state: AnswerState;
  /** Zero-based normalized option index, or null when unresolved. */
  normalizedIndex: number | null;
  rawKey: string | null;
  documentId: string | null;
  sourceLabel: string;
  /** Approved source id resolved by the screen; never a caller-supplied path. */
  imageId: string | null;
  claims: AnswerClaim[];
};

export type CurriculumTag = {
  id: string;
  label: string;
  state: "confirmed" | "inferred" | "unmapped";
};

export type ReviewCurriculum = {
  catalogueVersion: string;
  tags: CurriculumTag[];
  intendedDifficulty: "easy" | "konkur" | "hard" | "extreme" | null;
  /** Never populated from tags or model agreement. */
  empiricalDifficulty: null;
};

export type FigureInfo = {
  expected: boolean | null;
  /** Approved source id; null when the source has no recorded figure. */
  imageId: string | null;
  /** Hash of the figure image; null only when no figure image exists. */
  imageHash: string | null;
  label: string | null;
};

export type ReviewSource = {
  documentId: string;
  /** Document revision: changed PDF bytes mean a new SHA and document id (S0 v0.1). */
  documentRevision: string;
  documentLabel: string;
  session: string;
  booklet: string;
  /** One-based PDF page. */
  pdfPage: number;
  printedPage: number | null;
  pageImageId: string;
  /** Hash of the original page image; null only when no approved page image exists. */
  pageImageHash: string | null;
  cropImageId: string;
  /** Hash of the crop image; null only when no approved crop exists. */
  cropImageHash: string | null;
};

export type RouteTechnique = {
  id: string;
  role: "primary" | "supporting" | "check";
  evidence: string;
};

export type ReviewRoute = {
  id: string;
  role: "primary" | "alternative";
  techniques: RouteTechnique[];
};

export type ReviewAnnotations = {
  annotationState: "candidate" | "unresolved";
  taxonomyVersion: string;
  annotator: {
    kind: "model" | "human";
    identifier: string;
    model: string | null;
    promptVersion: string | null;
  };
  objective: { id: string; label: string } | null;
  representations: {
    id: string;
    label: string;
    stage: "given" | "constructed" | "requested";
  }[];
  routes: ReviewRoute[];
};

export type Disagreement = {
  dimension: EvidenceDimension;
  summary: string;
  claims: { source: string; statement: string }[];
};

export type Eligibility = {
  /** This screen can only render held records; eligibility is a server decision. */
  state: "held";
  reasons: string[];
  policyVersion: string | null;
};

export type ReviewRecord = {
  evidenceToken?: string;
  synthetic: boolean;
  questionId: string;
  questionRevision: number;
  contentHash: string;
  source: ReviewSource;
  transcriptionState: TranscriptionState;
  transcription: TextSegment[];
  continuation: { part: number; total: number; note: string } | null;
  uncertainSymbols: { marker: string; note: string }[];
  options: ReviewOption[];
  answer: ReviewAnswer;
  figure: FigureInfo;
  curriculum: ReviewCurriculum;
  evidenceMissing: EvidenceDimension[];
  disagreements: Disagreement[];
  receipts: EvidenceReceipt[];
  annotations: ReviewAnnotations | null;
  issues: string[];
  eligibility: Eligibility;
};

export type ReviewDataset = {
  datasetId: string;
  title: string;
  snapshotVersion: string;
  policyVersion: string;
  generatedAt: string;
  /** Synthetic fixtures only; a live dataset must arrive from an authorized API. */
  synthetic: boolean;
  /** Server-side count. The preview never recomputes, raises or grants eligibility. */
  eligibleCount: number;
  eligibilityNotes: string[];
  records: ReviewRecord[];
};

export type ApprovedSource = {
  id: string;
  kind: "page" | "crop" | "figure" | "answer";
  src: string;
  alt: string;
  width: number;
  height: number;
};
