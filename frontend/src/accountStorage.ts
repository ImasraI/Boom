/** Per-account caches. JWT decoding selects a namespace, never authorizes an API call. */
export function accountId(token = localStorage.getItem("boom-token")): string | null {
  try {
    const segment = token?.split(".")[1];
    if (!segment) return null;
    const payload = JSON.parse(atob(segment.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.sub === "string" && payload.sub ? payload.sub : null;
  } catch { return null; }
}

/** Capture the account before starting asynchronous work; a late response must
 * never write into a different student's cache after logout/login. Unscoped
 * legacy caches are preserved on disk but never attributed to a new account. */
export function accountStorageFor(token = localStorage.getItem("boom-token")) {
  const id = accountId(token);
  const keyFor = (key: string) => `boom-account:${encodeURIComponent(id || "")}:${key}`;
  return {
    getItem: (key: string) => id ? localStorage.getItem(keyFor(key)) : null,
    setItem: (key: string, value: string) => { if (id) localStorage.setItem(keyFor(key), value); },
    removeItem: (key: string) => { if (id) localStorage.removeItem(keyFor(key)); },
  };
}

export const accountStorage = {
  getItem: (key: string) => accountStorageFor().getItem(key),
  setItem: (key: string, value: string) => accountStorageFor().setItem(key, value),
  removeItem: (key: string) => accountStorageFor().removeItem(key),
};
