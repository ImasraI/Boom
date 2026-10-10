export interface QuestionFigureData {
  type: "none" | "function_plot" | "geometry" | "bar_chart" | "coordinate_plane"
  data: Record<string, unknown>
}

export type Point = {
  x: number
  y: number
  label?: string
}
export type FigureModel = {
  type: "geometry"
  points: Point[]
  data: Record<string, unknown>
} | {
  type: "bar_chart"
  categories: string[]
  values: number[]
  data: Record<string, unknown>
} | {
  type: "coordinate_plane"
  points: Point[]
  lines: { from: Point; to: Point; label?: string }[]
  xRange: number[]
  yRange: number[]
} | {
  type: "function_plot"
  points: Point[]
  highlights: Point[]
  xRange: number[]
  yRange: number[]
  data: Record<string, unknown>
}

export const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
const number = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && Math.abs(value) <= 1e9
const pair = (value: unknown): number[] | null =>
  Array.isArray(value) && value.length === 2 && value.every(number)
    ? value
    : null
const range = (value: unknown): number[] | null => {
  const p = pair(value)
  return p && p[1] > p[0] ? p : null
}
const label = (value: unknown): string =>
  typeof value === "string" ? value.slice(0, 80) : ""
function point(value: unknown): Point | null {
  const p = record(value)
  return number(p.x) && number(p.y)
    ? { x: p.x, y: p.y, label: label(p.label) }
    : null
}
export function extent(values: number[]): number[] {
  const min = Math.min(...values),
    max = Math.max(...values)
  const padding =
    max === min ? Math.max(1, Math.abs(min) * 0.15) : (max - min) * 0.15
  return [min - padding, max + padding]
}

/** Parse a small mathematical grammar. Model output is never executed as JS. */
export function compileExpression(
  expression: unknown,
): ((x: number) => number) | null {
  if (typeof expression !== "string" || expression.length > 200) return null
  const tokens =
    expression.match(
      /(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|\*\*|[a-zA-Z_]+|[()+\-*/]/g,
    ) || []
  if (tokens.join("") !== expression.replace(/\s/g, "") || tokens.length > 100)
    return null
  let at = 0
  type Fn = (x: number) => number
  const functions: Record<string, Fn> = {
    sin: Math.sin,
    cos: Math.cos,
    sqrt: Math.sqrt,
    abs: Math.abs,
  }
  const take = (token: string) => {
    if (tokens[at] !== token) throw Error("Invalid expression")
    at++
  }
  function atom(): Fn {
    const token = tokens[at++]
    if (token === "x") return (x) => x
    if (token && /^(?:\d|\.)/.test(token)) {
      const n = Number(token)
      if (!number(n)) throw Error("Invalid number")
      return () => n
    }
    if (token === "(") {
      const fn = sum()
      take(")")
      return fn
    }
    if (Object.prototype.hasOwnProperty.call(functions, token)) {
      take("(")
      const fn = sum()
      take(")")
      return (x) => functions[token](fn(x))
    }
    throw Error("Unsupported expression")
  }
  function power(): Fn {
    const left = atom()
    if (tokens[at] === "**") {
      at++
      const right = unary()
      return (x) => left(x) ** right(x)
    }
    return left
  }
  function unary(): Fn {
    if (tokens[at] === "+" || tokens[at] === "-") {
      const negative = tokens[at++] === "-"
      const fn = unary()
      return (x) => (negative ? -fn(x) : fn(x))
    }
    return power()
  }
  function product(): Fn {
    let fn = unary()
    while (tokens[at] === "*" || tokens[at] === "/") {
      const op = tokens[at++],
        left = fn,
        right = unary()
      fn = (x) => (op === "*" ? left(x) * right(x) : left(x) / right(x))
    }
    return fn
  }
  function sum(): Fn {
    let fn = product()
    while (tokens[at] === "+" || tokens[at] === "-") {
      const op = tokens[at++],
        left = fn,
        right = product()
      fn = (x) => (op === "+" ? left(x) + right(x) : left(x) - right(x))
    }
    return fn
  }
  try {
    const fn = sum()
    return at === tokens.length ? fn : null
  } catch {
    return null
  }
}

export function figureModel(value: unknown): FigureModel | null {
  const figure = record(value),
    data = record(figure.data)
  if (figure.type === "geometry") {
    const rows = Object.entries(record(data.points))
    if (rows.length < 2 || rows.length > 30 || rows.some(([, p]) => !pair(p)))
      return null
    const points = rows.map(([name, p]) => ({
      x: (p as number[])[0],
      y: (p as number[])[1],
      label: name.slice(0, 40),
    }))
    if (new Set(points.map((p) => `${p.x},${p.y}`)).size !== points.length)
      return null
    if (data.shape === "circle") return null
    return { type: "geometry", points, data }
  }
  if (figure.type === "bar_chart") {
    if (
      !Array.isArray(data.categories) ||
      !Array.isArray(data.values) ||
      !data.values.length ||
      data.values.length > 24 ||
      data.categories.length !== data.values.length ||
      !data.values.every(number) ||
      !data.categories.every((c) => typeof c === "string" || number(c))
    )
      return null
    return {
      type: "bar_chart",
      categories: data.categories.map((c) => String(c).slice(0, 80)),
      values: data.values as number[],
      data,
    }
  }
  if (figure.type === "coordinate_plane") {
    const xRange = range(data.x_range),
      yRange = range(data.y_range)
    if (
      !xRange ||
      !yRange ||
      (data.points !== undefined && !Array.isArray(data.points)) ||
      (data.lines !== undefined && !Array.isArray(data.lines))
    )
      return null
    const rawPoints = data.points as unknown[] || [],
      rawLines = data.lines as unknown[] || []
    if (
      rawPoints.length + rawLines.length > 50 ||
      rawPoints.some((p) => !point(p))
    )
      return null
    const lines = rawLines.map((l) => {
      const d = record(l),
        from = pair(d.from),
        to = pair(d.to)
      return from && to
        ? {
            from: { x: from[0], y: from[1] },
            to: { x: to[0], y: to[1] },
            label: label(d.label),
          }
        : null
    })
    if (lines.some((l) => !l) || (!rawPoints.length && !lines.length))
      return null
    return {
      type: "coordinate_plane",
      points: rawPoints.map((p) => point(p)!),
      lines: lines as { from: Point; to: Point; label?: string }[],
      xRange,
      yRange,
    }
  }
  if (figure.type === "function_plot") {
    const fn = compileExpression(data.expression),
      xRange = range(data.domain)
    if (!fn || !xRange || (data.variable && data.variable !== "x")) return null
    const points = Array.from({ length: 301 }, (_, i) => {
      const x = xRange[0] + ((xRange[1] - xRange[0]) * i) / 300
      return { x, y: fn(x) }
    })
    const visible = points.filter((p) => number(p.y))
    if (visible.length < 2) return null
    if (
      data.highlight_points !== undefined &&
      (!Array.isArray(data.highlight_points) ||
        data.highlight_points.length > 30 ||
        data.highlight_points.some((p) => !point(p)))
    )
      return null
    const highlights = ((data.highlight_points || []) as unknown[]).map(
      (p) => point(p)!,
    )
    if (data.y_range !== undefined && !range(data.y_range)) return null
    return {
      type: "function_plot",
      points,
      highlights,
      xRange,
      yRange: range(data.y_range) || extent(visible.map((p) => p.y).concat(0)),
      data,
    }
  }
  return null
}
