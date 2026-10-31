import { ApiError, apiJson } from "./api"
import { requestMockGeneration } from "./mockGeneration"

export interface PreviousMazeMock {
  exam_date: string
  title: string
  total_questions: number
  difficulty: string
  topics?: Record<string, string[]>
  legacy?: boolean
}

type Student = { major?: string; grade?: string }

export async function fetchPreviousMaze(student: Student, signal?: AbortSignal): Promise<PreviousMazeMock[]> {
  const query = new URLSearchParams({ major: student.major || "", grade: student.grade || "" })
  try {
    const data = await apiJson<{ items: PreviousMazeMock[] }>(`/api/mocks/previous-maze?${query}`, { signal })
    return data.items
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) throw error
    // Older backends already expose the available previous scope through ranked filters.
    const data = await apiJson<{ weekly?: {
      fallback?: boolean; stock_available?: boolean; date?: string; topics?: Record<string, string[]>
    } }>(`/api/arena/filters?${query}`, { signal })
    const weekly = data.weekly
    if (!weekly?.fallback || !weekly.stock_available || !weekly.date || !weekly.topics) return []
    return [{ exam_date: weekly.date, title: `تمرین از مباحث آزمون قبلی ماز — ${weekly.date}`,
      total_questions: 10, difficulty: "konkur", topics: weekly.topics, legacy: true }]
  }
}

export async function openPreviousMaze<T extends { mock_id: number }>(
  item: PreviousMazeMock, student: Student, signal: AbortSignal,
): Promise<T> {
  if (!item.legacy) return apiJson<T>("/api/mocks/previous-maze", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ exam_date: item.exam_date, student }), signal,
  })
  // This older API supports a ten-question topic practice, not an archive snapshot.
  // Use its complete selection mode so previously used questions alone cannot
  // produce a partial eight-question paper when enough shared stock exists.
  const topics = [...new Set(Object.values(item.topics || {}).flat().flatMap(topic =>
    [topic, topic.replace(/\u200c/g, " "), topic.replace(/\u200c/g, "")]))]
  if (!topics.length) throw new Error("مباحث آزمون قبلی در دسترس نیست؛ فهرست را تازه کن.")
  const data = await requestMockGeneration<T>({ mode: "general", total_questions: 10,
    stock_only: true, difficulty: "konkur", topics, student }, signal)
  return { ...data, title: item.title }
}
