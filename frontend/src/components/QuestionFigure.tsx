import { useId, useMemo, type ReactNode } from "react"
import { extent, figureModel, record, type Point } from "../questionFigures"

const WIDTH = 440,
  HEIGHT = 280,
  LEFT = 48,
  TOP = 28,
  RIGHT = 412,
  BOTTOM = 236
const accent = "var(--accent, #ca854c)",
  ink = "var(--text, #241b14)",
  muted = "var(--muted, #8c8177)"
const names: Record<string, string> = {
  geometry: "شکل هندسی",
  function_plot: "نمودار تابع",
  bar_chart: "نمودار ستونی",
  coordinate_plane: "دستگاه مختصات",
}
const numeric = (n: number) => Number(n.toPrecision(4)).toString()
const text = (value: unknown) =>
  typeof value === "string" || typeof value === "number"
    ? String(value).slice(0, 80)
    : ""
function ticks(range: number[]) {
  const target = (range[1] - range[0]) / 5,
    unit = 10 ** Math.floor(Math.log10(target)),
    ratio = target / unit
  if (!Number.isFinite(target) || !unit) return range
  const step = (ratio <= 1 ? 1 : ratio <= 2 ? 2 : ratio <= 5 ? 5 : 10) * unit
  const start = Math.ceil(range[0] / step) * step
  return Array.from(
    {
      length: Math.min(
        12,
        Math.max(0, Math.floor((range[1] - start) / step + 1e-9) + 1),
      ),
    },
    (_, i) => start + i * step,
  )
}

function coordinates(xRange: number[], yRange: number[]) {
  return {
    x: (n: number) =>
      LEFT + ((n - xRange[0]) / (xRange[1] - xRange[0])) * (RIGHT - LEFT),
    y: (n: number) =>
      BOTTOM - ((n - yRange[0]) / (yRange[1] - yRange[0])) * (BOTTOM - TOP),
  }
}
function Axes({
  xRange,
  yRange,
  xLabel = "x",
  yLabel = "y",
}: {
  xRange: number[]
  yRange: number[]
  xLabel?: string
  yLabel?: string
}) {
  const map = coordinates(xRange, yRange)
  const xZero = map.x(Math.max(xRange[0], Math.min(xRange[1], 0)))
  const yZero = map.y(Math.max(yRange[0], Math.min(yRange[1], 0)))
  return (
    <g fontSize="14" fill={muted}>
      {ticks(xRange).map((x, i) => (
        <g key={`x${i}`}>
          <path
            d={`M ${map.x(x)} ${TOP} V ${BOTTOM}`}
            stroke="var(--border, #ddd)"
            strokeDasharray="3 5"
            fill="none"
          />
          <text x={map.x(x)} y={BOTTOM + 19} textAnchor="middle">
            {numeric(x)}
          </text>
        </g>
      ))}
      {ticks(yRange).map((y, i) => (
        <g key={`y${i}`}>
          <path
            d={`M ${LEFT} ${map.y(y)} H ${RIGHT}`}
            stroke="var(--border, #ddd)"
            strokeDasharray="3 5"
            fill="none"
          />
          <text x={LEFT - 9} y={map.y(y) + 4} textAnchor="end">
            {numeric(y)}
          </text>
        </g>
      ))}
      <path
        d={`M ${LEFT} ${yZero} H ${RIGHT} M ${xZero} ${TOP} V ${BOTTOM}`}
        stroke={muted}
        fill="none"
      />
      <text x={RIGHT + 12} y={yZero - 8} textAnchor="middle" fill={ink}>
        {xLabel}
      </text>
      <text x={xZero + 12} y={TOP - 10} fill={ink}>
        {yLabel}
      </text>
    </g>
  )
}
function Dot({
  point,
  map,
  label = point.label,
}: {
  point: Point
  map: ReturnType<typeof coordinates>
  label?: string
}) {
  return (
    <g>
      <circle cx={map.x(point.x)} cy={map.y(point.y)} r="3.5" fill={accent} />
      {label && (
        <text
          x={map.x(point.x) + 9}
          y={map.y(point.y) - 10}
          fontSize="15"
          fill={ink}
        >
          {label}
        </text>
      )}
    </g>
  )
}

export default function QuestionFigure({ figure }: { figure?: unknown }) {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "")
  const model = useMemo(() => figureModel(figure), [figure])
  const raw = record(figure)
  if (!raw.type || raw.type === "none") return null
  if (!model)
    return (
      <p
        role="status"
        className="text-xs text-[var(--muted)] border-s-2 border-amber-500 ps-3 my-4"
      >
        شکل این سؤال قابل نمایش نیست؛ لطفاً مشکل شکل را گزارش کن.
      </p>
    )
  const clip = `question-figure-${id}`
  let drawing: ReactNode
  if (model.type === "geometry") {
    const { points, data } = model
    const xr = extent(points.map((p) => p.x)),
      yr = extent(points.map((p) => p.y))
    const scale = Math.min(
      (RIGHT - LEFT) / (xr[1] - xr[0]),
      (BOTTOM - TOP) / (yr[1] - yr[0]),
    )
    const centerX = (xr[0] + xr[1]) / 2,
      centerY = (yr[0] + yr[1]) / 2
    const centroid = {
      x: points.reduce((sum, p) => sum + p.x, 0) / points.length,
      y: points.reduce((sum, p) => sum + p.y, 0) / points.length,
    }
    const map = {
      x: (n: number) => (LEFT + RIGHT) / 2 + (n - centerX) * scale,
      y: (n: number) => (TOP + BOTTOM) / 2 - (n - centerY) * scale,
    }
    const labels = record(data.labels),
      sides = record(data.side_lengths),
      angles = record(data.angles),
      marks = record(data.marks)
    const byName = Object.fromEntries(points.map((p) => [p.label!, p]))
    const edges = points.slice(1).map((p, i) => [points[i], p])
    if (
      points.length > 2 &&
      !["line", "segment", "polyline"].includes(String(data.shape))
    )
      edges.push([points[points.length - 1], points[0]])
    const edgePoints = (value: unknown) => {
      if (typeof value !== "string") return null
      return (
        edges.find(
          ([a, b]) =>
            (a.label ?? "") + (b.label ?? "") === value ||
            (b.label ?? "") + (a.label ?? "") === value,
        ) || null
      )
    }
    const ticks = Array.isArray(marks.equal_sides)
      ? marks.equal_sides.map(edgePoints).filter((e) => !!e)
      : []
    const parallel = Array.isArray(marks.parallel_pairs)
      ? marks.parallel_pairs.slice(0, 15).flatMap((pair, i) =>
          Array.isArray(pair)
            ? pair
                .map(edgePoints)
                .filter((e) => !!e)
                .map((edge) => ({ edge: edge!, count: i + 1 }))
            : [],
        )
      : []
    const right =
      typeof marks.right_angle_at === "string"
        ? byName[marks.right_angle_at]
        : null
    const adjacent = right
      ? edges
          .filter((e) => e.includes(right))
          .map((e) => e.find((p) => p !== right)!)
      : []
    let rightMark = ""
    if (right && adjacent.length === 2) {
      const rx = map.x(right.x),
        ry = map.y(right.y)
      const vectors = adjacent.map((p) => {
        const dx = map.x(p.x) - rx,
          dy = map.y(p.y) - ry,
          len = Math.hypot(dx, dy)
        return { x: (dx / len) * 12, y: (dy / len) * 12 }
      })
      rightMark = `M ${rx + vectors[0].x} ${ry + vectors[0].y} l ${vectors[1].x} ${vectors[1].y} l ${-vectors[0].x} ${-vectors[0].y}`
    }
    drawing = (
      <g>
        {edges.map(([a, b], i) => (
          <g key={i}>
            <line
              x1={map.x(a.x)}
              y1={map.y(a.y)}
              x2={map.x(b.x)}
              y2={map.y(b.y)}
              stroke={accent}
              strokeWidth="2.3"
            />
            {sides[a.label! + b.label!] !== undefined ||
            sides[b.label! + a.label!] !== undefined ? (
              <text
                x={(map.x(a.x) + map.x(b.x)) / 2 + 9}
                y={(map.y(a.y) + map.y(b.y)) / 2 - 9}
                fontSize="16"
                fill={ink}
              >
                {text(sides[a.label! + b.label!] ?? sides[b.label! + a.label!])}
              </text>
            ) : null}
          </g>
        ))}
        {ticks.map((edge, i) => {
          const [a, b] = edge!,
            dx = map.x(b.x) - map.x(a.x),
            dy = map.y(b.y) - map.y(a.y),
            len = Math.hypot(dx, dy),
            mx = (map.x(a.x) + map.x(b.x)) / 2,
            my = (map.y(a.y) + map.y(b.y)) / 2
          return len > 0 ? (
            <line
              key={i}
              x1={mx - (dy / len) * 5}
              y1={my + (dx / len) * 5}
              x2={mx + (dy / len) * 5}
              y2={my - (dx / len) * 5}
              stroke={ink}
              strokeWidth="1.5"
            />
          ) : null
        })}
        {parallel.map(({ edge: [a, b], count }, i) => {
          let dx = map.x(b.x) - map.x(a.x),
            dy = map.y(b.y) - map.y(a.y)
          const len = Math.hypot(dx, dy)
          if (dx < 0 || (dx === 0 && dy < 0)) {
            dx = -dx
            dy = -dy
          }
          const ux = dx / len,
            uy = dy / len,
            mx = (map.x(a.x) + map.x(b.x)) / 2,
            my = (map.y(a.y) + map.y(b.y)) / 2
          return (
            <g key={i}>
              {Array.from({ length: Math.min(count, 3) }, (_, j) => {
                const offset = (j - (Math.min(count, 3) - 1) / 2) * 7,
                  x = mx + ux * offset,
                  y = my + uy * offset
                return (
                  <path
                    key={j}
                    d={`M ${x - ux * 4 - uy * 4} ${y - uy * 4 + ux * 4} L ${x + ux * 2} ${y + uy * 2} L ${x - ux * 4 + uy * 4} ${y - uy * 4 - ux * 4}`}
                    fill="none"
                    stroke={ink}
                  />
                )
              })}
            </g>
          )
        })}
        {rightMark && <path d={rightMark} fill="none" stroke={ink} />}
        {points.map((p, i) => {
          const dx = map.x(p.x) - map.x(centroid.x),
            dy = map.y(p.y) - map.y(centroid.y),
            len = Math.hypot(dx, dy) || 1
          return (
            <g key={i}>
              <Dot point={p} map={map} label="" />
              <text
                x={map.x(p.x) + (dx / len) * 17}
                y={map.y(p.y) + (dy / len) * 17 + 5}
                textAnchor={dx < 0 ? "end" : "start"}
                fontSize="15"
                fill={ink}
              >
                {text(labels[p.label!]) || p.label}
              </text>
              {angles[p.label!] !== undefined && (
                <text
                  x={map.x(p.x) + 13}
                  y={map.y(p.y) + 19}
                  fontSize="14"
                  fill={muted}
                >
                  {text(angles[p.label!])}°
                </text>
              )}
            </g>
          )
        })}
      </g>
    )
  } else if (model.type === "bar_chart") {
    const { values, categories, data } = model
    const yr = extent(values.concat(0))
    if (values.every((v) => v >= 0)) yr[0] = 0
    if (values.every((v) => v <= 0)) yr[1] = 0
    if (yr[0] === yr[1]) yr[1] = yr[0] + 1
    const map = coordinates([0, values.length], yr),
      zero = map.y(0),
      slot = (RIGHT - LEFT) / values.length
    drawing = (
      <g>
        {ticks(yr).map((v, i) => (
          <g key={i}>
            <line
              x1={LEFT}
              x2={RIGHT}
              y1={map.y(v)}
              y2={map.y(v)}
              stroke="var(--border, #ddd)"
            />
            <text
              x={LEFT - 8}
              y={map.y(v) + 4}
              textAnchor="end"
              fontSize="14"
              fill={muted}
            >
              {numeric(v)}
            </text>
          </g>
        ))}
        <line x1={LEFT} x2={RIGHT} y1={zero} y2={zero} stroke={muted} />
        {values.map((v, i) => (
          <g key={i}>
            <rect
              x={LEFT + slot * (i + 0.2)}
              width={slot * 0.6}
              y={Math.min(zero, map.y(v))}
              height={Math.max(0, Math.abs(zero - map.y(v)))}
              fill={accent}
              fillOpacity=".8"
            />
            <text
              x={LEFT + slot * (i + 0.5)}
              y={map.y(v) + (v < 0 ? 15 : -8)}
              textAnchor="middle"
              fontSize="14"
              fill={ink}
            >
              {v}
            </text>
            <text
              x={LEFT + slot * (i + 0.5)}
              y={BOTTOM + 19}
              textAnchor="middle"
              fontSize="14"
              fill={ink}
            >
              {categories[i]}
            </text>
          </g>
        ))}
        <text
          x={(LEFT + RIGHT) / 2}
          y={HEIGHT - 5}
          fontSize="12"
          textAnchor="middle"
          fill={muted}
        >
          {text(data.x_label)}
        </text>
        <text x={LEFT} y={TOP - 12} fontSize="12" fill={muted}>
          {text(data.y_label)}
        </text>
      </g>
    )
  } else {
    const map = coordinates(model.xRange, model.yRange)
    const labels =
      model.type === "function_plot" ? record(model.data.labels) : {}
    let path = "",
      pen = false,
      previousY = 0
    if (model.type === "function_plot")
      for (const p of model.points) {
        const x = map.x(p.x),
          y = map.y(p.y)
        if (
          !Number.isFinite(y) ||
          y < TOP - (BOTTOM - TOP) ||
          y > BOTTOM + (BOTTOM - TOP)
        ) {
          pen = false
          continue
        }
        if (pen && Math.abs(y - previousY) > BOTTOM - TOP) pen = false
        path += `${pen ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)} `
        pen = true
        previousY = y
      }
    drawing = (
      <g>
        <Axes
          xRange={model.xRange}
          yRange={model.yRange}
          xLabel={text(labels.x_axis) || "x"}
          yLabel={text(labels.y_axis) || "y"}
        />
        <g clipPath={`url(#${clip})`}>
          {model.type === "function_plot" ? (
            <>
              <path d={path} fill="none" stroke={accent} strokeWidth="2.5" />
              {model.highlights.map((p, i) => (
                <Dot key={i} point={p} map={map} />
              ))}
            </>
          ) : (
            <>
              {model.lines.map((line, i) => (
                <g key={i}>
                  <line
                    x1={map.x(line.from.x)}
                    y1={map.y(line.from.y)}
                    x2={map.x(line.to.x)}
                    y2={map.y(line.to.y)}
                    stroke={accent}
                    strokeWidth="2"
                  />
                  {line.label && (
                    <text
                      x={(map.x(line.from.x) + map.x(line.to.x)) / 2 + 8}
                      y={(map.y(line.from.y) + map.y(line.to.y)) / 2 - 8}
                      fontSize="13"
                      fill={ink}
                    >
                      {line.label}
                    </text>
                  )}
                </g>
              ))}
              {model.points.map((p, i) => (
                <Dot key={i} point={p} map={map} />
              ))}
            </>
          )}
        </g>
      </g>
    )
  }
  return (
    <figure
      className="my-4 w-full overflow-hidden border-y border-[var(--border)] bg-[var(--surface-2)] py-2"
      aria-label={names[model.type]}
    >
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-labelledby={`${clip}-title`}
        className="block w-full max-w-[520px] mx-auto"
        style={{ direction: "ltr", fontFamily: "inherit" }}
      >
        <title id={`${clip}-title`}>{names[model.type]}</title>
        <defs>
          <clipPath id={clip}>
            <rect x={LEFT} y={TOP} width={RIGHT - LEFT} height={BOTTOM - TOP} />
          </clipPath>
        </defs>
        {drawing}
      </svg>
    </figure>
  )
}
