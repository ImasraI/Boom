/** Shared frontend API helpers. Prefer relative /api so Vite proxy works. */
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "";

export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${p}`;
}

export function authHeaders(token?: string | null): HeadersInit {
  const t = token ?? localStorage.getItem("boom-token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export const SESSION_EXPIRED = "boom:session-expired";
export const SESSION_EXPIRED_MESSAGE = "نشست ورود پایان یافته است. دوباره وارد حسابت شو.";

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(authHeaders());
  new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  const authorization = headers.get("Authorization");
  const response = await fetch(apiUrl(path), { ...init, headers });

  const current = localStorage.getItem("boom-token");
  // A late response for an old account cannot invalidate a newer sign-in.
  if (response.status === 401 && current && authorization === "Bearer " + current) {
    localStorage.removeItem("boom-token");
    window.dispatchEvent(new Event(SESSION_EXPIRED));
  }
  return response;
}

/** FastAPI may return detail as string or validation error array. */
export function formatApiDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return null;
      })
      .filter(Boolean);
    if (parts.length) return parts.join(" · ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return fallback;
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) {
    super(message)
    this.name = "ApiError"
  }
}

async function apiFailure(res: Response, fallback: string): Promise<ApiError> {
  try {
    const data = await res.json();
    const detail = data?.detail;
    return new ApiError(formatApiDetail(detail, fallback), res.status,
      typeof detail?.code === "string" ? detail.code : undefined);
  } catch {
    return new ApiError(fallback, res.status);
  }
}

export async function readApiError(res: Response, fallback: string): Promise<string> {
  return (await apiFailure(res, fallback)).message;
}

/** Bound panel requests so a broken connection cannot leave a spinner forever. */
export async function apiJson<T>(path: string, init: RequestInit = {}, timeoutMs = 20000): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  const cancel = () => controller.abort();
  init.signal?.addEventListener("abort", cancel, { once: true });
  if (init.signal?.aborted) controller.abort();
  try {
    const response = await authFetch(path, { ...init, signal: controller.signal });
    if (response.status === 401) throw new ApiError(SESSION_EXPIRED_MESSAGE, 401);
    if (!response.ok) throw await apiFailure(response, "دریافت اطلاعات ناموفق بود؛ دوباره تلاش کن.");
    return await response.json() as T;
  } catch (error) {
    if (timedOut) throw new Error("پاسخ سرور دیر رسید؛ اتصال را بررسی کن و دوباره تلاش کن.");
    throw error;
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener("abort", cancel);
  }
}
