import { accountStorage, accountStorageFor } from "./accountStorage";
/**
 * Server-side profile sync (growth-readiness project 1).
 *
 * The DB row (student_profiles) is the source of truth; localStorage stays
 * as the offline cache. Writes carry the version they were based on, so a
 * second device can never be silently overwritten (409 -> server state wins
 * locally, explicitly - never a blind clobber in either direction).
 */
import { apiUrl, authHeaders } from "./api";
import type { SignupData } from "./types";

const VERSION_KEY = "boom-profile-version";

export interface ServerProfile {
  name?: string | null;
  major?: string | null;
  grade?: string | null;
  exam_year?: string | null;
  target_rank?: string | null;
  study_hours?: string | null;
  test_exams?: string[] | null;
  availability?: {
    wake?: string;
    sleep?: string;
    sleep_hours?: number;
    daily_hours?: Record<string, number>;
    preferences?: Partial<SignupData>;
  } | null;
  version: number;
  updated_at?: string | null;
}

export function storedVersion(): number | null {
  const v = accountStorage.getItem(VERSION_KEY);
  const n = v ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
}

/** Server profile -> SignupData patch (server fields win when non-null). */
export function toSignupData(p: ServerProfile | null, base: SignupData): SignupData {
  if (!p) return base;
  return {
    ...base,
    ...p.availability?.preferences,
    name: p.name ?? base.name,
    major: p.major ?? base.major,
    grade: p.grade ?? base.grade,
    examYear: p.exam_year ?? base.examYear,
    targetRank: p.target_rank ?? base.targetRank,
    studyHours: p.study_hours ?? base.studyHours,
    testExams: Array.isArray(p.test_exams) && (p.version > 0 || p.test_exams.length > 0) ? p.test_exams : base.testExams,
    wakeTime: p.availability?.wake ?? base.wakeTime,
    sleepHours: p.availability?.sleep_hours ?? base.sleepHours,
    dailyHours: p.availability?.daily_hours ?? base.dailyHours,
  };
}

function toPayload(d: SignupData) {
  return {
    name: d.name || null,
    major: d.major || null,
    grade: d.grade || null,
    exam_year: d.examYear || null,
    target_rank: d.targetRank || null,
    study_hours: d.studyHours || null,
    test_exams: d.testExams,
    availability: {
      preferences: { completion: d.completion, confidence: d.confidence, maxConsec: d.maxConsec,
        breakStyle: d.breakStyle, studyStyle: d.studyStyle, strictness: d.strictness },
      wake: d.wakeTime || undefined,
      sleep_hours: d.sleepHours ?? undefined,
      daily_hours: d.dailyHours && Object.keys(d.dailyHours).length ? d.dailyHours : undefined,
    },
  };
}

/** Pull the authoritative profile (boot-time cache refresh). */
export async function pullServerProfile(): Promise<ServerProfile | null> {
  const cache = accountStorageFor();
  try {
    const res = await fetch(apiUrl("/api/profile"), { headers: authHeaders() });
    if (!res.ok) return null;
    const data = await res.json();
    const p = data?.profile as ServerProfile | undefined;
    if (p?.version != null) cache.setItem(VERSION_KEY, String(p.version));
    return p ?? null;
  } catch {
    return null; // offline: the localStorage cache keeps serving
  }
}

/** Preserve existing server settings; migrate a complete browser-only signup once. */
export async function hydrateServerProfile(base: SignupData): Promise<ServerProfile | null> {
  const token = localStorage.getItem("boom-token");
  const server = await pullServerProfile();
  if (!token || localStorage.getItem("boom-token") !== token) return null;
  const empty = server?.version === 0 && !server.major && !server.grade && !server.study_hours;
  if (empty && base.major?.trim() && base.grade?.trim() && base.studyHours?.trim()) {
    const saved = await pushProfile(base);
    if (localStorage.getItem("boom-token") !== token) return null;
    return saved.profile ?? server;
  }
  return server;
}

/**
 * Push a local save to the server with optimistic concurrency.
 * On 409 the SERVER state is returned and adopted (the other device won);
 * this is an explicit, documented choice - never a silent overwrite.
 */
export async function pushProfile(
  data: SignupData,
): Promise<{ ok: boolean; conflict?: boolean; profile?: ServerProfile }> {
  const cache = accountStorageFor();
  try {
    const res = await fetch(apiUrl("/api/profile"), {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ ...toPayload(data), version: storedVersion() }),
    });
    if (res.status === 409) {
      const body = await res.json().catch(() => null);
      const p = (body?.detail?.profile ?? null) as ServerProfile | null;
      if (p?.version != null) cache.setItem(VERSION_KEY, String(p.version));
      return { ok: false, conflict: true, profile: p ?? undefined };
    }
    if (!res.ok) return { ok: false };
    const out = await res.json();
    const p = out?.profile as ServerProfile | undefined;
    if (p?.version != null) cache.setItem(VERSION_KEY, String(p.version));
    return { ok: true, profile: p };
  } catch {
    return { ok: false }; // offline save stays in localStorage for now
  }
}
