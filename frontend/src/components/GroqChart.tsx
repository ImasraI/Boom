import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

const TYPE_COLORS = {
  study: "#e2c983",
  test: "#9B7AAD",
  class: "#5C8BA8",
  break: "#97b094",
};

export default function GroqChart({
  blocks,
}: {
  blocks: Array<{ day: number; type: string; title: string; duration: number }>;
}) {
  const dayLabels = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];

  const data = dayLabels.map((label, i) => {
    const dayBlocks = blocks.filter((b) => b.day === i);
    return {
      name: label,
      study: dayBlocks.filter((b) => b.type === "study").reduce((s, b) => s + b.duration, 0),
      test: dayBlocks.filter((b) => b.type === "test").reduce((s, b) => s + b.duration, 0),
      class: dayBlocks.filter((b) => b.type === "class").reduce((s, b) => s + b.duration, 0),
      break: dayBlocks.filter((b) => b.type === "break").reduce((s, b) => s + b.duration, 0),
    };
  });

  return (
    <div className="w-full bg-[var(--card)] rounded-2xl border border-[var(--border)] p-4">
      <h3 className="font-display text-lg text-[var(--text)] mb-3">توزیع ساعت بر اساس نوع فعالیت</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <XAxis dataKey="name" tick={{ fill: "var(--muted)", fontSize: 12 }} />
          <YAxis tick={{ fill: "var(--muted)", fontSize: 12 }} />
          <Tooltip
            contentStyle={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: "12px",
              color: "var(--text)",
            }}
          />
          <Bar dataKey="study" stackId="a" fill={TYPE_COLORS.study} radius={[0, 0, 0, 0]} />
          <Bar dataKey="test" stackId="a" fill={TYPE_COLORS.test} />
          <Bar dataKey="class" stackId="a" fill={TYPE_COLORS.class} />
          <Bar dataKey="break" stackId="a" fill={TYPE_COLORS.break} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-3 mt-3 justify-center">
        {Object.entries(TYPE_COLORS).map(([key, color]) => (
          <div key={key} className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: color }} />
            <span className="text-[11px] font-bold text-[var(--muted)]">{key}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
