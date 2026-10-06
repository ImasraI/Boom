import type { Screen } from "./types";

const RETRY_KEY = "boom-page-retry";
const RESUME_KEY = "boom-page-resume";
const PAGES: Screen[] = ["chat", "schedule", "evaluation", "mock", "arena", "leaderboard", "knowledge", "admin"];

export function isPageDownloadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /failed to fetch dynamically imported module|importing a module script failed|error loading dynamically imported module|loading chunk .* failed|unable to preload css/i.test(message);
}

/** A tab opened before deployment may still reference removed Vite chunks. */
export function recoverPageDownload(screen: Screen, error: unknown): boolean {
  if (!isPageDownloadError(error) || !navigator.onLine) return false;
  try {
    const message = error instanceof Error ? error.message : String(error);
    if (sessionStorage.getItem(RETRY_KEY) === message) return false;
    sessionStorage.setItem(RETRY_KEY, message);
    sessionStorage.setItem(RESUME_KEY, screen);
    window.location.reload();
    return true;
  } catch {
    return false;
  }
}

export function consumeResumePage(): Screen | null {
  try {
    const page = sessionStorage.getItem(RESUME_KEY);
    sessionStorage.removeItem(RESUME_KEY);
    return PAGES.includes(page as Screen) ? page as Screen : null;
  } catch {
    return null;
  }
}
