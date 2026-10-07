import { apiJson } from "./api"

type Job<T> = { job_id: string; status: "running" | "ready"; result?: T }

/** Poll short requests instead of holding a Cloudflare connection during drafting. */
export async function requestMockGeneration<T extends { mock_id: number }>(
  payload: Record<string, unknown>, signal: AbortSignal,
): Promise<T> {
  if (signal.aborted) throw new DOMException("Aborted", "AbortError")
  let job = await apiJson<Job<T>>("/api/mocks/generation", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload), signal,
  })
  while (job.status === "running") {
    await new Promise<void>((resolve, reject) => {
      const cancel = () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")) }
      const timer = setTimeout(() => { signal.removeEventListener("abort", cancel); resolve() }, 2000)
      signal.addEventListener("abort", cancel, { once: true })
      if (signal.aborted) cancel()
    })
    job = await apiJson<Job<T>>(`/api/mocks/generation/${job.job_id}`, { signal })
  }
  if (!job.result?.mock_id) throw new Error("دفترچه آماده نشد؛ دوباره تلاش کنید.")
  return job.result
}
