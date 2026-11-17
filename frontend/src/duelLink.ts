export function duelCode(): string | null {
  if (typeof window === "undefined") return null
  const code = new URLSearchParams(window.location.search).get("duel")
  return code && /^[a-zA-Z0-9_-]{24}$/.test(code) ? code : null
}

export function roomUrl(code: string | null) {
  const url = new URL(window.location.href)
  if (code) url.searchParams.set("duel", code)
  else url.searchParams.delete("duel")
  url.hash = ""
  return url
}

export function forgetDuelLink() {
  if (duelCode()) window.history.replaceState(null, "", roomUrl(null))
}

