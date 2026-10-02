import { useEffect, useState } from "react";
import { apiUrl, authHeaders } from "../api";
import { SUBJECT_COLORS } from "../data";

interface WeakTopic {
  topic: string;
  wrong_count: number;
  blanks: number;
  wrongness: number; // 0..1, relative to the worst topic in the same subject
}

interface WeakSubject {
  subject: string;
  wrong_count: number;
  topics: WeakTopic[];
}

interface WeaknessData {
  days: number;
  total_wrong: number;
  subjects: WeakSubject[];
}

const DAYS = 90;

function faNum(n: number): string {
  return n.toLocaleString("fa-IR");
}

function getSubjectColor(subject: string): string {
  const key = Object.keys(SUBJECT_COLORS).find(k => subject.includes(k));
  return SUBJECT_COLORS[key ?? "default"];
}

/** Cell tint: the subject color at an intensity driven by wrongness, so the
 * worst topic in a subject reads as the hottest cell. Kept in the 0.10-0.72
 * alpha band so the topic label stays readable in light AND dark mode. */
function cellStyle(color: string, wrongness: number): React.CSSProperties {
  const alpha = (0.10 + 0.62 * Math.min(1, Math.max(0, wrongness))).toFixed(3);
  return { backgroundColor: `color-mix(in srgb, ${color} ${Math.round(parseFloat(alpha) * 100)}%, transparent)` };
}

function TopicCell({ topic, color }: { topic: WeakTopic; color: string }) {
  return (
    <div
      className="relative rounded-xl px-2.5 py-2 border border-black/5 dark:border-white/5 transition-transform hover:scale-[1.03]"
      style={cellStyle(color, topic.wrongness)}
      title={`${topic.topic}: ${topic.wrong_count} غلط`}
    >
      <p className="text-[11.5px] font-bold text-[var(--text)] leading-tight truncate max-w-[110px]">
        {topic.topic}
      </p>
      <div className="flex items-center gap-1 mt-1">
        <span className="text-[10px] font-bold text-[var(--text-strong)] tabular-nums">
          {faNum(topic.wrong_count)} غلط
        </span>
        {topic.blanks > 0 && (
          <span className="text-[9px] font-medium text-[var(--text-strong)] opacity-70 tabular-nums">
            · {faNum(topic.blanks)} نزده
          </span>
        )}
      </div>
      {/* Intensity bar: normalized weakness 0..1 */}
      <div className="mt-1 h-[3px] rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${Math.max(8, topic.wrongness * 100)}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

export default function WeaknessMap() {
  const [data, setData] = useState<WeaknessData | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(apiUrl(`/api/insights/weakness-map?days=${DAYS}`), {
      headers: authHeaders(),
    })
      .then(res => (res.ok ? res.json() : null))
      .then(d => {
        if (!cancelled && d && Array.isArray(d.subjects)) setData(d as WeaknessData);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data) return null;

  return (
    <div
      id="weakness-map"
      className="bg-[var(--card)] p-5"
    >
      {/* Header: title right, total-wrong badge left (RTL) */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2 rounded-xl bg-[var(--accent-soft)] border border-[var(--accent-soft-border)] px-2.5 py-1">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span className="text-[11px] font-bold text-[var(--accent)] tabular-nums">
            {faNum(data.total_wrong)} غلط
          </span>
        </div>
        <div>
          <h3 className="font-display text-[16px] text-[var(--text)] leading-tight">نقشه ضعف‌ها</h3>
          <p className="text-[10px] text-[var(--muted-2)] font-medium mt-0.5">
            بر اساس غلط‌های {faNum(DAYS)} روز اخیر
          </p>
        </div>
      </div>

      {data.subjects.length === 0 ? (
        <div className="mt-4 py-3 text-center">
          <p className="text-[12.5px] font-semibold text-[var(--muted)]">هنوز داده‌ای نیست</p>
          <p className="text-[11px] text-[var(--muted-2)] mt-1 leading-relaxed">
            غلط‌های آزمون‌های هوشمند و دوئل‌ها همین‌جا به شکل نقشه ضعف نشان داده می‌شوند.
          </p>
        </div>
      ) : (
        <>
          {/* One heatmap row per subject: subject chip on the right (RTL),
              topic cells colored by weakness intensity flowing left. */}
          <div className="mt-4 space-y-3.5">
            {data.subjects.map(subject => {
              const color = getSubjectColor(subject.subject);
              return (
                <div key={subject.subject}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    <span className="text-[12px] font-bold text-[var(--text-strong)]">
                      {subject.subject}
                    </span>
                    <span className="text-[10px] font-medium text-[var(--muted-2)] tabular-nums">
                      {faNum(subject.wrong_count)} غلط
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {subject.topics.map(t => (
                      <TopicCell key={t.topic} topic={t} color={color} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Legend: intensity = weakness within the subject */}
          <div className="mt-4 pt-3 border-t border-[var(--border)] flex items-center justify-between">
            <span className="text-[10px] text-[var(--muted-2)] font-medium">شدت رنگ = میزان ضعف در آن مبحث</span>
            <div
              className="w-20 h-1.5 rounded-full"
              style={{ background: "linear-gradient(to left, rgba(196,113,74,0.10), rgba(196,113,74,0.72))" }}
            />
          </div>
        </>
      )}
    </div>
  );
}
