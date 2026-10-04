import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true }, appType: "custom" });
const { default: ChatMarkdown } = await vite.ssrLoadModule("/src/components/ChatMarkdown.tsx");

test.after(async () => { await vite.close(); });

function render(text) {
  return renderToStaticMarkup(React.createElement(ChatMarkdown, { text }));
}

test("assistant schedule renders as a table followed by its note", () => {
  const sample = `**برنامه امروز (شنبه — day = 0)**
| زمان | عنوان | نوع |
|------|--------|------|
| 13:30 – 15:00 | مطالعه ریاضی: مرور مباحث (بخش 1/3) | study |
| 15:30 – 17:00 | مطالعه ریاضی: مرور مباحث (بخش 2/3) | study |
| 16:30 – 18:00 | مطالعه ریاضی: مرور مباحث (بخش 3/3) | study |
| 18:30 – 20:00 | مطالعه شیمی: مرور مباحث (بخش 1/3) | study |
*توجه:* بین هر بلوک 30 دقیقه استراحت.`;
  const html = render(sample);
  assert.match(html, /<strong>برنامه امروز/);
  assert.equal((html.match(/<tr>/g) ?? []).length, 5);
  assert.match(html, /<th>زمان<\/th>/);
  assert.match(html, /<td>18:30 – 20:00<\/td>/);
  assert.match(html, /<\/table><\/div>\s*<p><em>توجه:<\/em>/);
  assert.doesNotMatch(html, /<td>.*توجه:/);
});

test("assistant rich text renders lists, code and math without raw HTML", () => {
  const html = render("## مرور\n- **تابع**\n- حد\n\n`x = 1`\n\n$$x^2 + 1$$\n\n<script>alert(1)</script>");
  assert.match(html, /<h2>مرور<\/h2>/);
  assert.match(html, /<li><strong>تابع<\/strong><\/li>/);
  assert.match(html, /<code>x = 1<\/code>/);
  assert.match(html, /class="katex/);
  assert.doesNotMatch(html, /<script>/);
});
