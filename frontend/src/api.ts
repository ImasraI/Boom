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
