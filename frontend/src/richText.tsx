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
// The suffix eats plain groups (!=frac{12}{25}, one nesting level so
// !=frac{\sqrt{3}}{4} works) and sub/superscripts (!=\int_{0}^{1}), without
// swallowing a following word: a bare letter only counts when preceded by _
// or ^, so `\Omega و` and `\frac{2}{5}r` keep their trailing prose as text.
// The name guard is `(?![A-Za-z])`, NOT \b: a command followed by a
// subscript (!=\lim_{x \to 2}, \int_{0}^{1}) has no word boundary because
// `_` counts as a word character.
const MATH_SPLIT_RE =
  /(\$\$[\s\S]*?\$\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|\$[^$\n]+?\$|\\(?:d?frac|tfrac|sqrt|times|div|pm|mp|cdot|circ|pi|leq|geq|neq|approx|equiv|infty|to|log|ln|sin|cos|tan|cot|lim|sum|int|prod|binom|vec|bar|hat|overline|Delta|Omega|Phi|Psi|Sigma|Lambda|Theta|Gamma|alpha|beta|gamma|delta|epsilon|theta|kappa|lambda|mu|nu|rho|sigma|tau|phi|chi|psi|omega)(?![A-Za-z])(?:\s*(?:\{(?:[^{}]|\{[^{}]*\})*\}|[_^]\s*(?:\{(?:[^{}]|\{[^{}]*\})*\}|[A-Za-z0-9])))*)/g;

// Same pattern, non-global: only asks "is there any math here?".
// Needed because a string that is ONE whole formula (a very common mock
// option: "$\frac{3}{4}$", "$2\sqrt{5}$", bare "\frac{12}{25}") survives
// String.split as a single part equal to the input, so the old
// `parts[0] === text` check mistook it for plain text and rendered the raw
// LaTeX. Testing the source separately keeps the real plain-text fast path.
const HAS_MATH_RE = new RegExp(MATH_SPLIT_RE.source);

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
  // Fast path (plain text, the common case): one untouched text node so
  // whitespace-pre-wrap parents keep behaving exactly as before.
  if (!HAS_MATH_RE.test(text)) return <>{text}</>;
  const parts = text.split(MATH_SPLIT_RE).filter(p => p !== "");
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
