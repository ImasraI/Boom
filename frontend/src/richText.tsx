import React from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

// AI question/option/explanation text often contains LaTeX, e.g.
//   $f(x) = \frac{2x+1}{x-1}$, $$...$$, \(...\), \[...\]
// or even a bare \frac{a}{b} with no delimiters at all. Plain-text rendering
// shows that markup raw, so math-looking fragments are rendered with KaTeX
// (same approach as Chat.tsx) and everything else passes through untouched.
const HAS_PERSIAN = /[\u0600-\u06FF]/;

// Split points, in priority order: $$...$$, \(...\), \[...\], $...$,
// then a bare math command (models sometimes forget the delimiters).
const MATH_SPLIT_RE =
  /(\$\$[\s\S]*?\$\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|\$[^$\n]+?\$|\\(?:d?frac|tfrac|sqrt|times|div|pm|cdot|pi|leq|geq|neq|approx|alpha|beta|gamma|theta|lambda|mu|Delta|omega|infty)\b(?:\s*\{[^{}]*\}){0,2})/g;

function MathNode({ latex, display }: { latex: string; display: boolean }) {
  try {
    const html = katex.renderToString(latex, {
      displayMode: display,
      throwOnError: false,
    });
    return (
      <span
        dir="ltr"
        className={display ? "block my-2 overflow-x-auto" : undefined}
        style={display ? undefined : { display: "inline-block" }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  } catch {
    return <span dir="ltr">{latex}</span>;
  }
}

export function RichText({ text }: { text: string }) {
  if (!text) return null;
  const parts = text.split(MATH_SPLIT_RE).filter(p => p !== "");
  // Fast path (plain text, the common case): one untouched text node so
  // whitespace-pre-wrap parents keep behaving exactly as before.
  if (parts.length === 1 && parts[0] === text) return <>{text}</>;
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("$$") && part.endsWith("$$") && part.length > 4) {
          return <MathNode key={i} latex={part.slice(2, -2)} display />;
        }
        if (
          (part.startsWith("\\(") && part.endsWith("\\)")) ||
          (part.startsWith("\\[") && part.endsWith("\\]"))
        ) {
          return <MathNode key={i} latex={part.slice(2, -2)} display={part.startsWith("\\[")} />;
        }
        if (part.startsWith("$") && part.endsWith("$") && part.length > 2) {
          const inner = part.slice(1, -1);
          // Persian prose wrapped in $...$ (delimiters leaked into plain
          // text) is not renderable math - show it without the $ signs.
          if (HAS_PERSIAN.test(inner)) return <React.Fragment key={i}>{inner}</React.Fragment>;
          return <MathNode key={i} latex={inner} display={false} />;
        }
        if (part.startsWith("\\")) {
          // Bare LaTeX command without delimiters, e.g. \frac{2x+1}{x-1}.
          return <MathNode key={i} latex={part} display={false} />;
        }
        return <React.Fragment key={i}>{part}</React.Fragment>;
      })}
    </>
  );
}
