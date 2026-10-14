import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

/**
 * The UI draws its marks - right/wrong answers, trend and repeat arrows, the
 * flag on the report link, feature icons, the pipeline-map legend swatch - as
 * inline SVG from src/components/icons.tsx. Emoji and dingbat characters are
 * banned from the interface: they render at the operating system's whim (colour
 * emoji boxes, monochrome fallbacks, or tofu) and cannot inherit the theme.
 *
 * These tests hold that line: the sources contain none of those code points,
 * every mark is real <svg> markup that colours itself with `currentColor`, and
 * the screens render emoji-free markup. Typographic arrows stay - they are text
 * separators inside Persian prose (`کتاب -> صفحه`), not pictographs.
 */

const vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
test.after(async () => { await vite.close(); });

/** Emoji, dingbats, geometric shapes, enclosed letters, variation selectors. */
const FORBIDDEN = /[\u{1F000}-\u{1FAFF}\u{1F1E6}-\u{1F1FF}\u{2300}-\u{23FF}\u{25A0}-\u{25FF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{3030}\u{303D}\u{3297}\u{3299}\u{00A9}\u{00AE}\u{203C}\u{2049}\u{2116}\u{2122}\u{2139}\u{24C2}\u{200D}\u{FE0F}\u{20E3}]/u;
/** Plain arrows (U+2190-U+21FF) are allowed: prose separators, not pictographs. */
const TYPOGRAPHIC_ARROW = /[\u2190-\u21FF]/u;

const SRC = path.join(import.meta.dirname, 'src');

function sourceFiles(dir = SRC) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sourceFiles(full));
    else if (/\.(tsx?|css|json|html)$/.test(entry.name)) out.push(full);
  }
  return out;
}

test('no emoji or symbol glyph is left anywhere in the frontend sources', () => {
  const offenders = [];
  for (const file of sourceFiles()) {
    const text = fs.readFileSync(file, 'utf8');
    text.split('\n').forEach((line, index) => {
      if (FORBIDDEN.test(line)) {
        const codes = [...new Set([...line].filter(ch => FORBIDDEN.test(ch)))]
          .map(ch => `U+${ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0')}`).join(' ');
        offenders.push(`${path.relative(SRC, file)}:${index + 1} [${codes}]`);
      }
    });
  }
  assert.deepEqual(offenders, [], `emoji/dingbat glyphs must not ship in the UI:\n${offenders.join('\n')}`);
});

test('the check marks, arrows and flag icons render as inline SVG in currentColor', async () => {
  const icons = await vite.ssrLoadModule('/src/components/icons.tsx');
  const names = ['CheckMark', 'CrossMark', 'CloseIcon', 'TrendUpIcon', 'RepeatIcon',
    'FlagIcon', 'AssistantIcon', 'CalendarIcon', 'TargetIcon', 'SettingsIcon'];
  for (const name of names) {
    assert.equal(typeof icons[name], 'function', `${name} must be exported`);
    const html = renderToStaticMarkup(React.createElement(icons[name]));
    assert.match(html, /^<svg /, `${name} must render an <svg>`);
    assert.match(html, /stroke="currentColor"/, `${name} must inherit the surrounding colour`);
    assert.match(html, /<path|<rect|<circle/, `${name} must draw a shape`);
    assert.doesNotMatch(html, FORBIDDEN, `${name} must not contain an emoji glyph`);
    // Square and sized by the caller, so a badge/row keeps its old footprint.
    assert.match(html, /width="\d+" height="\d+"/, `${name} must be sized`);
  }
  const check = renderToStaticMarkup(React.createElement(icons.CheckMark, { size: 20 }));
  assert.match(check, /width="20" height="20"/);
});

test('screens render markup without emoji glyphs', async () => {
  globalThis.localStorage ??= {
    getItem: () => null, setItem: () => {}, removeItem: () => {},
    key: () => null, get length() { return 0; },
  };
  const pages = {
    Landing: {},
    Mock: { userData: null },
    Exams: {},
    Streak: {},
    Arena: { userData: null },
  };
  for (const [name, props] of Object.entries(pages)) {
    const { default: Page } = await vite.ssrLoadModule(`/src/pages/${name}.tsx`);
    const html = renderToStaticMarkup(React.createElement(Page, { nav() {}, ...props }));
    assert.doesNotMatch(html, FORBIDDEN, `${name} rendered an emoji glyph`);
    assert.doesNotMatch(html, /✓|✗|✕|⚑|🏆/, `${name} rendered a removed mark glyph`);
  }
});

test('the pipeline map marks roles with CSS swatches and moves with an SVG arrow', async () => {
  const map = await vite.ssrLoadModule('/src/components/RagPipelineMap.tsx');
  const trace = {
    id: 'emoji-map', kind: 'chat', kind_label: 'گفتگوی کاربر', title: 'نیم‌ساز',
    question: 'نیم‌ساز چیست؟', user_id: 1, created_at: 0, duration_ms: 10, status: 'ok',
    error: '', summary: {}, total_stage_ms: 9,
    stages: [
      { name: 'embed_query', label: 'بردارسازی پرسش (Embedding)', ms: 1, command: '', meta: {}, columns: [], rows: [], text: {} },
      { name: 'books · semantic_search', label: 'جست‌وجوی برداری (Chroma)', ms: 2, command: '', meta: {},
        columns: [{ key: 'rank', label: 'رتبه' }],
        rows: [{ rank: 1, doc: 'هندسه ۲.pdf', chunk: 9, score: .8, preview: 'نه' },
               { rank: 2, doc: 'فیزیک ۱.pdf', chunk: 4, score: .7, preview: 'چهار' }], text: {} },
      { name: 'books · rerank', label: 'بازرتبه‌بندی (Cross-Encoder)', ms: 3, command: '', meta: {},
        columns: [{ key: 'rank', label: 'رتبه' }],
        rows: [{ rank: 1, old_rank: 2, move: 1, doc: 'فیزیک ۱.pdf', chunk: 4, rerank_score: .9 },
               { rank: 2, old_rank: 1, move: -1, doc: 'هندسه ۲.pdf', chunk: 9, rerank_score: .1 }], text: {} },
    ],
  };
  const graph = map.buildPipelineGraph(trace);

  const strip = renderToStaticMarkup(React.createElement(map.FunnelStrip, { graph }));
  assert.doesNotMatch(strip, /■/, 'the legend swatch must not be a text glyph');
  assert.match(strip, /inline-block w-1\.5 h-1\.5/, 'the legend swatch must be a CSS box');

  const chart = map.buildRankChart(trace);
  const promoted = chart.tracks.find(track => track.rerankMove > 0);
  assert.ok(promoted, 'the fixture must promote a chunk through the reranker');
  const chartHtml = renderToStaticMarkup(
    React.createElement(map.ChunkRankChart, { chart, docFilter: '', onSelectDoc() {} }));
  assert.match(chartHtml, /<svg/, 'the rank chart draws the moves');

  // The per-chunk rows carry the promotion badge and the stage trail.
  const docs = map.buildDocumentCoverage(trace, chart);
  const panel = renderToStaticMarkup(
    React.createElement(map.DocumentChunkPanel, { docs, selectedDoc: '', onSelectDoc() {} }));
  assert.doesNotMatch(panel, /↑/, 'the promotion badge must not be an arrow glyph');
  assert.match(panel, /<svg/, 'the promotion badge must be an SVG arrow');
  assert.match(panel, /رتبه/, 'the promotion badge still names the rank move');
  assert.match(panel, TYPOGRAPHIC_ARROW, 'arrows inside the stage trail stay text');
});
