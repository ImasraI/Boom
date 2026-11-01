/**
 * Human decision entry — proposed contract for Sol's decision API.
 *
 * No endpoint exists in the repository yet, so the screen treats this as an
 * optional dependency: without it the review UI stays read-only. These helpers
 * only build and submit one dimension-bound receipt; there is deliberately no
 * "approve all", eligibility override or bulk mutation.
 */

import { bindingFor } from "./model";
import type { EvidenceBinding, EvidenceDimension, ReviewRecord } from "./types";

export type DecisionKind = "pass" | "fail" | "unresolved" | "hold";

export const DECISION_OPTIONS: { value: DecisionKind; label: string }[] = [
  { value: "pass", label: "قبول این بُعد" },
  { value: "fail", label: "رد این بُعد" },
  { value: "unresolved", label: "حل‌نشده" },
  { value: "hold", label: "نگه‌داشتن برای بررسی بیشتر" },
];

export type DecisionForm = {
  dimension: EvidenceDimension;
  decision: DecisionKind;
  reviewerIdentifier: string;
  note: string;
};

/**
 * Exactly what the server must bind and re-authorize: the identity of the
 * question plus the complete evidence set (content hash, document, source and
 * figure image hashes, catalogue version) the reviewer was looking at. The
 * eventual server must reauthorize the reviewer's identity from the session and
 * recheck every binding against its stored record atomically (409 on any
 * mismatch) before recording a receipt. `reviewerIdentifier` is attribution
 * only — it never authenticates anyone.
 */
export type ReviewDecisionInput = {
  evidenceToken?: string;
  questionId: string;
  dimension: EvidenceDimension;
  decision: DecisionKind;
  reviewerKind: "human";
  reviewerIdentifier: string;
  note: string;
  synthetic: boolean;
  binding: EvidenceBinding;
};

export type DecisionApiResult =
  | { ok: true; receiptId: string; recordedAt: string }
  | { ok: false; message: string };

export type ReviewDecisionApi = {
  submitDecision(input: ReviewDecisionInput): Promise<DecisionApiResult>;
};

export const MIN_NOTE_LENGTH = 10;

export type DecisionValidation =
  | { ok: true }
  | { ok: false; message: string };

export function validateDecisionForm(form: DecisionForm): DecisionValidation {
  if (!form.reviewerIdentifier.trim()) {
    return {
      ok: false,
      message: "شناسهٔ بازبین انسانی لازم است؛ این فرم هویت شما را از خود نمی‌سازد.",
    };
  }
  if (form.note.trim().length < MIN_NOTE_LENGTH) {
    return {
      ok: false,
      message: `یادداشت باید دست‌کم ${MIN_NOTE_LENGTH} نویسه و قابل‌بررسی باشد.`,
    };
  }
  return { ok: true };
}

/**
 * Bind the decision to the exact evidence the reviewer is looking at. Refuses
 * to build a payload when the record's own binding is incomplete — a decision
 * can never travel without its question/source/image/catalogue evidence.
 */
export function buildDecisionInput(
  record: ReviewRecord,
  form: DecisionForm,
): ReviewDecisionInput {
  const validation = validateDecisionForm(form);
  if (!validation.ok) {
    throw new Error(validation.message);
  }
  const binding = bindingFor(record);
  if (!binding) {
    throw new Error(
      "شواهد این رکورد ناقص است (سند/تصویر/فهرست درسی بسته نشده)؛ تصمیمی ارسال نمی‌شود.",
    );
  }
  return {
    questionId: record.questionId,
    ...(record.evidenceToken ? { evidenceToken: record.evidenceToken } : {}),
    dimension: form.dimension,
    decision: form.decision,
    reviewerKind: "human",
    reviewerIdentifier: form.reviewerIdentifier.trim(),
    note: form.note.trim(),
    synthetic: record.synthetic,
    binding,
  };
}

export async function submitDecision(
  api: ReviewDecisionApi,
  record: ReviewRecord,
  form: DecisionForm,
): Promise<DecisionApiResult> {
  let input: ReviewDecisionInput;
  try {
    input = buildDecisionInput(record, form);
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "ورودی تصمیم نامعتبر است.",
    };
  }
  try {
    return await api.submitDecision(input);
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "ثبت تصمیم انجام نشد.",
    };
  }
}
