import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

const tableDivider = /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/;

// Some model replies place a note immediately after the last table row. GFM
// otherwise treats that note as another cell, so separate table boundaries.
export function prepareChatMarkdown(source: string): string {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const result: string[] = [];
  let fenced = false;
  let inTable = false;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^\s*(```|~~~)/.test(line)) {
      fenced = !fenced;
      inTable = false;
      result.push(line);
      continue;
    }
    if (fenced) {
      result.push(line);
      continue;
    }

    const startsTable = line.includes("|") && tableDivider.test(lines[index + 1] ?? "");
    if (startsTable && result.length > 0 && result[result.length - 1].trim()) result.push("");
    if (inTable && line.trim() && !line.includes("|")) {
      result.push("");
      inTable = false;
    }
    result.push(line);
    if (startsTable) inTable = true;
    if (!line.trim()) inTable = false;
  }
  return result.join("\n");
}

export default function ChatMarkdown({ text }: { text: string }) {
  return (
    <div className="chat-markdown" dir="rtl">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          table: ({ children }) => <div className="chat-table-scroll" role="region" aria-label="جدول پاسخ" tabIndex={0}><table>{children}</table></div>,
          a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
        }}
      >
        {prepareChatMarkdown(text)}
      </ReactMarkdown>
    </div>
  );
}
