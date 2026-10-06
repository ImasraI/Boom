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

export async function readApiError(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json();
    return formatApiDetail(data?.detail, fallback);
  } catch {
    return fallback;
  }
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
    const headers = new Headers(authHeaders());
    new Headers(init.headers).forEach((value, key) => headers.set(key, value));
    const response = await fetch(apiUrl(path), { ...init, headers, signal: controller.signal });
    if (!response.ok) {
      const fallback = response.status === 401 ? "نشست ورود منقضی شده است؛ دوباره وارد حساب شو." : "دریافت اطلاعات ناموفق بود؛ دوباره تلاش کن.";
      throw new Error(await readApiError(response, fallback));
    }
    return await response.json() as T;
  } catch (error) {
    if (timedOut) throw new Error("پاسخ سرور دیر رسید؛ اتصال را بررسی کن و دوباره تلاش کن.");
    throw error;
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener("abort", cancel);
  }
}
