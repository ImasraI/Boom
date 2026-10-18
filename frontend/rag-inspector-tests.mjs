import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
test.after(() => vite.close());
const map = await vite.ssrLoadModule('/src/components/RagPipelineMap.tsx');
const { RagRequestFence } = await vite.ssrLoadModule('/src/components/ragRequestFence.ts');
const { TraceView } = await vite.ssrLoadModule('/src/components/RagInspector.tsx');
const stage = (name, meta = {}, rows = []) => ({ name, label: name, ms: 10, meta, rows, columns: [], text: {}, command: '' });
const trace = stages => ({ id: 'test-trace', kind: 'playground', kind_label: 'بررسی دستی', question: 'تابع چیست؟',
  user_id: 1, created_at: 1700000000, duration_ms: 20, total_stage_ms: 40, status: 'ok', summary: {}, error: '', stages });

test('actual outputs win over sampled rows and requested candidate limits', () => {
  const t = trace([
    stage('books · semantic_search', { hits: 100 }, [{ doc: 'book', chunk: 0, rank: 1 }]),
    stage('books · lexical_search', { hits: 70 }, []),
    stage('books · rrf_fusion', { output_count: 4, candidates_kept: 20 }, []),
    stage('books · rerank', { skipped: 'RERANK_ENABLED=false' }),
    stage('retrieval_assembly', { final_chunks: 4 }),
  ]);
  const graph = map.buildPipelineGraph(t);
  assert.deepEqual(graph.nodes.map(n => n.selected), [100, 70, 4, 4, 4]);
  assert.equal(graph.nodes[0].sampled, 1);
  assert.equal(graph.nodes.at(-1).role, 'context');
  assert.equal(graph.nodes.at(-1).lane, 4);
  assert.deepEqual(graph.funnels[0].steps.map(step => step.count), [100, 70, 4, 4]);
  assert.equal(map.stageOutput(stage('books · rrf_fusion', { candidates_kept: 20 })).known, false);
});

test('playground final assembly participates in source coverage without inventing citations', () => {
  const row = { id: 'actual-chunk-id', doc: 'کتاب.pdf', chunk: 9, rank: 1, preview: 'متن اصلی' };
  const t = trace([stage('books · semantic_search', { hits: 10 }, [row]), stage('retrieval_assembly', { final_chunks: 1 }, [row])]);
  const chart = map.buildRankChart(t);
  assert.equal(chart.tracks.length, 1);
  assert.equal(chart.tracks[0].cited, true); // Legacy internal name: supplied context.
  assert.equal(chart.tracks[0].referenced, false);
  assert.deepEqual(chart.tracks[0].grid, [1, 1]);
  assert.equal(map.buildDocumentCoverage(t, chart)[0].cited, 1);
  const html = renderToStaticMarkup(React.createElement(map.default, { trace: t }));
  assert.match(html, /منبع ۱ در بافت مدل/);
  assert.doesNotMatch(html, /در پاسخ ارجاع شده|ارجاع شماره‌دار در پاسخ/);
  const answered = trace([...t.stages, stage('final_answer', { source_semantics: 'supplied_context' }, [{ ...row, cited: true }])]);
  assert.equal(map.buildRankChart(answered).tracks[0].referenced, true);
});

test('chunk IDs distinguish same-named document chunks and ranks above30 are not clipped', () => {
  const t = trace([stage('books · semantic_search', { hits: 250 }, [
    { id: 'first-complete-id', doc: 'same.pdf', chunk: 0, rank: 250 },
    { id: 'second-complete-id', doc: 'same.pdf', chunk: 0, rank: 200 },
  ])]);
  const chart = map.buildRankChart(t);
  assert.equal(chart.tracks.length, 2);
  assert.equal(chart.maxRank, 250);
  const html = renderToStaticMarkup(React.createElement(map.ChunkRankChart, { chart, onSelectDoc() {} }));
  assert.match(html, /رتبه ۲۵۰/);
  assert.match(html, /role="button" tabindex="0"/);
});

test('embedding map exposes actual dimensions, relationships and missing-coordinate limitation', () => {
  const t = trace([
    stage('embed_query', { model: 'gemini-embedding', dimensions: 1536, input: 'تابع چیست؟' }),
    stage('books · semantic_search', { collection: 'shared-books', hits: 40 }, []),
  ]);
  const html = renderToStaticMarkup(React.createElement(map.EmbeddingProvenance, { trace: t }));
  assert.match(html, /gemini-embedding/);
  assert.match(html, /۱٬۵۳۶ بُعد/);
  assert.match(html, /shared-books/);
  assert.match(html, /فاصلهٔ شکل‌ها فاصلهٔ معنایی نیست/);
  assert.match(html, /۴۰ نتیجه/);
});

test('pipeline stage nodes expose keyboard activation and unambiguous selection', () => {
  const graph = map.buildPipelineGraph(trace([stage('books · semantic_search', { output_count: 25 })]));
  const html = renderToStaticMarkup(React.createElement(map.PipelineMap, { graph, selectedStage: 0, onSelectStage() {} }));
  assert.match(html, /role="button" tabindex="0" aria-pressed="true"/);
  assert.match(html, /۲۵ مورد/);
});

test('source atlas identifies recorded chunks and context without claiming vector distances or citations', () => {
  const source={id:'chunk-unique',doc:'حسابان <script>.pdf',chunk:4,rank:1,preview:'متن کتاب'};
  const t=trace([stage('books · semantic_search',{hits:90},[source]),stage('retrieval_assembly',{final_chunks:1},[source])]);
  const docs=map.buildDocumentCoverage(t,map.buildRankChart(t));
  const html=renderToStaticMarkup(React.createElement(map.SourceMindMap,{trace:t,docs,selectedDoc:source.doc,onSelectDoc(){}}));
  assert.match(html,/role="button" tabindex="0" aria-pressed="true"/);
  assert.match(html,/۱ تکهٔ ثبت‌شده، ۱ تکه در بافت مدل/);
  assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<script>|۹۰ تکه|ارجاع شماره‌دار در پاسخ/);
  assert.match(html,/فاصله/);
});

test('run totals use recorded full context counts and identify skipped rerank with pass-through output', () => {
  const t=trace([
    stage('books · rerank',{skipped:'disabled',output_count:25}),
    stage('retrieval_assembly',{final_chunks:25},[{id:'one',doc:'book',chunk:1,rank:1}]),
  ]);
  const html=renderToStaticMarkup(React.createElement(map.default,{trace:t}));
  assert.match(html,/تکه در بافت مدل<\/span><strong[^>]*>۲۵<\/strong>/);
  assert.match(html,/بازرتبه‌بندی<\/span><strong[^>]*>اجرا نشد<\/strong>/);
  const unfinished=renderToStaticMarkup(React.createElement(map.default,{trace:trace([])}));
  assert.match(unfinished,/تکه در بافت مدل<\/span><strong[^>]*>ثبت نشده<\/strong>/);
});

test('trace view identifies truncated data and inclusive timers', () => {
  const t = trace([stage('books · semantic_search', { hits: 80, truncated_rows: true })]);
  t.summary.payload_truncated = true;
  const html = renderToStaticMarkup(React.createElement(TraceView, { trace: t }));
  assert.match(html, /زمان کل اجرا/);
  assert.match(html, /جمع این زمان‌ها مدت کل اجرا نیست/);
  assert.match(html, /جدول‌ها ممکن است تنها نمونه‌ای/);
  assert.match(html, /مرحلهٔ انتخاب‌شده/);
});

test('late A cannot overwrite selectedB, even if transport ignores abort', async () => {
  const fence = new RagRequestFence();
  const results = [];
  let finishA;
  const a = fence.begin('detail');
  const pendingA = new Promise(resolve => { finishA = resolve; }).then(value => { if (a.current()) results.push(value); });
  const b = fence.begin('detail');
  if (b.current()) results.push('B');
  finishA('A');
  await pendingA;
  assert.deepEqual(results, ['B']);
  assert.equal(a.signal.aborted, true);
});

test('clear and unmount invalidate pending detail/list/config ownership', () => {
  const fence = new RagRequestFence();
  const detail = fence.begin('detail');
  const list = fence.begin('list');
  fence.invalidate('detail'); fence.invalidate('list');
  assert.equal(detail.current(), false);
  assert.equal(list.current(), false);
  const config = fence.begin('config');
  fence.dispose(); fence.activate();
  assert.equal(config.current(), false);
  assert.equal(config.signal.aborted, true);
  assert.equal(fence.begin('config').current(), true);
});

/** Two shelves, a reranked book chunk and a four-chunk question-bank page. */
const mindTrace = () => trace([
  stage('embed_query', { model: 'gemini-embedding', dimensions: 1024, input: 'نیم‌ساز چیست؟' }),
  stage('books · semantic_search', { collection: 'books', hits: 2 }, [
    { id: 'b1', doc: 'فیزیک ۱.pdf', chunk: 4, rank: 1, preview: 'چهار' },
    { id: 'b2', doc: 'هندسه ۲.pdf', chunk: 9, rank: 2, preview: 'نه' },
  ]),
  stage('books · rerank', { kept: 2 }, [{ id: 'b2', doc: 'هندسه ۲.pdf', chunk: 9, rank: 1, move: 1, preview: 'نه' }]),
  stage('qbank · semantic_search', { collection: 'questions', hits: 4 }, [
    { id: 'q1', doc: 'فیزیک ۱ ریاضی خیلی سبز::p40', chunk: 7, rank: 1, preview: 'چهل' },
    { id: 'q2', doc: 'فیزیک ۱ ریاضی خیلی سبز::p40', chunk: 12, rank: 2, preview: 'چهل و یک' },
    { id: 'q3', doc: 'فیزیک ۱ ریاضی خیلی سبز::p40', chunk: 13, rank: 3, preview: 'چهل و دو' },
    { id: 'q4', doc: 'فیزیک ۱ ریاضی خیلی سبز::p40', chunk: 14, rank: 4, preview: 'چهل و سه' },
  ]),
  stage('qbank_search', { hits: 1, output_count: 1 }, [{ id: 'q1', doc: 'فیزیک ۱ ریاضی خیلی سبز::p40', chunk: 7, rank: 1 }]),
  stage('retrieval_assembly', { final_chunks: 1 }, [{ id: 'b1', doc: 'فیزیک ۱.pdf', chunk: 4, rank: 1 }]),
]);

const mindHtml = (options = {}) => {
  const t = mindTrace();
  const docs = map.buildDocumentCoverage(t, map.buildRankChart(t));
  return renderToStaticMarkup(React.createElement(map.SourceMindMap,
    { trace: t, docs, selectedDoc: '', onSelectDoc() {}, ...options }));
};

test('the source map groups documents under the shelf that retrieved them', () => {
  const chunk = (group) => ({ group, chunk: '1', preview: '', stages: [], bestRank: 1, cited: false, citedRank: null, rerankMove: 0, referenced: false, key: 'k' });
  assert.equal(map.shelfKeyOf({ doc: 'x.pdf', chunks: [chunk('books')], cited: 0, selectedIn: 1 }), 'books');
  assert.equal(map.shelfKeyOf({ doc: 'x::p3', chunks: [chunk('qbank'), chunk('qbank')], cited: 0, selectedIn: 2 }), 'qbank');
  // A chunk only the final context named has no shelf: no group is invented.
  assert.equal(map.shelfKeyOf({ doc: 'x.pdf', chunks: [chunk('')], cited: 1, selectedIn: 1 }), '');
  assert.equal(map.shelfLabelOf('books'), 'کتاب‌ها');
  assert.equal(map.shelfLabelOf('').includes('بدون'), true);

  const html = mindHtml();
  assert.match(html, /کتاب‌ها · ۲ سند/);
  assert.match(html, /بانک سؤال · ۱ سند/);
  // Leaves are one circle per recorded chunk, and the page marker keeps the
  // book's own chunks apart from its transcribed question-bank page.
  assert.match(html, /تکهٔ ۴ از فیزیک ۱\.pdf/);
  assert.match(html, /تکهٔ ۷ از فیزیک ۱ ریاضی خیلی سبز::p40/);
  assert.doesNotMatch(html, /undefined/);
});

test('the source map draws only what it was asked to and reports the rest', () => {
  // Three leaves of the four-chunk page, with an expand control for the fourth.
  const collapsed = mindHtml();
  assert.match(collapsed, /تکهٔ ۱۳ از فیزیک ۱ ریاضی خیلی سبز::p40/);
  assert.doesNotMatch(collapsed, /تکهٔ ۱۴ از فیزیک ۱ ریاضی خیلی سبز::p40/);
  assert.match(collapsed, /۴ تکهٔ این سند؛ نمایش تکه‌های بیشتر/);

  // "Documents only" is a real setting, not a hidden default.
  const noLeaves = mindHtml({ chunksPerDoc: 0 });
  assert.doesNotMatch(noLeaves, /تکهٔ ۷ از/);
  assert.match(noLeaves, /فیزیک ۱ ریاضی خیلی سبز/);

  // A cap never hides records silently: the note says how many were drawn.
  const capped = mindHtml({ docCap: 1 });
  assert.match(capped, /۱ از ۳ سند رسم شده/);
  assert.doesNotMatch(capped, /هندسه ۲/);
});

test('the source layout wraps documents into rows inside its own width', () => {
  const shelf = { key: 'books', label: 'کتاب‌ها', cited: 0,
    docs: Array.from({ length: 5 }, (_, index) => ({ doc: `b${index}.pdf`, chunks: [], cited: 0, selectedIn: 0 })) };
  const layout = map.buildMindLayout([shelf], 3);
  assert.equal(layout.perRow, 3);
  assert.equal(layout.bands[0].cards.length, 5);
  assert.equal(layout.bands[0].busY.length, 2);
  assert.ok(layout.bands[0].cards.every(card => card.x >= 0 && card.x + 204 <= layout.cardRight));
  assert.ok(layout.height > 0 && layout.trunkBottom > layout.rootY);
  // Documents only: the leaf row disappears from the geometry too.
  assert.ok(map.buildMindLayout([shelf], 0).height < layout.height);
  assert.equal(map.buildMindLayout([], 3).bands.length, 0);
});

test('labels are trimmed to the width of the box they are drawn in', () => {
  const long = 'ریاضی خیلی سبز دوازدهم تجربی جلد اول پاسخ‌های تشریحی.pdf';
  // A long name is cut with an ellipsis and the result always fits the box.
  const fitted = map.fitText(long, 176, 11);
  assert.notEqual(fitted, long);
  assert.ok(fitted.endsWith('…'));
  assert.ok(fitted.length < long.length);
  assert.ok(map.textWidth(fitted, 11) <= 176,
    `the trimmed label must fit: ${map.textWidth(fitted, 11)} > 176`);
  // Short labels are never touched, and no width is ever exceeded.
  assert.equal(map.fitText('هندسه ۲.pdf', 176, 11), 'هندسه ۲.pdf');
  for (const [value, width, size] of [[long, 88, 10.5], [long, 148, 10], [long, 19, 8.5], ['', 20, 9]]) {
    assert.ok(map.textWidth(map.fitText(value, width, size), size) <= width,
      `${value.slice(0, 10)} did not fit ${width}px at ${size}px`);
  }
});

test('a long document name is trimmed inside its card, not through the border', () => {
  // Real corpora carry names far longer than the fixture's; the card must hold
  // them rather than letting the text run out of the box.
  const name = 'ریاضی خیلی سبز دوازدهم تجربی جلد اول پاسخ‌های تشریحی.pdf';
  const t = trace([
    stage('books · semantic_search', { collection: 'books', hits: 1 },
      [{ id: 'long-1', doc: name, chunk: 3, rank: 1, preview: 'متن' }]),
    stage('retrieval_assembly', { final_chunks: 1 }, [{ id: 'long-1', doc: name, chunk: 3, rank: 1 }]),
  ]);
  const docs = map.buildDocumentCoverage(t, map.buildRankChart(t));
  const html = renderToStaticMarkup(React.createElement(map.SourceMindMap,
    { trace: t, docs, selectedDoc: '', onSelectDoc() {} }));
  const start = html.indexOf('g class="rag-mind-card"');
  const card = html.slice(start, html.indexOf('</g>', start));
  const label = card.match(/font-size="11"[^>]*>([^<]+)</)[1];
  assert.ok(label.endsWith('…'), `the card label must be trimmed: ${label}`);
  assert.ok(map.textWidth(label, 11) <= 204 - 28,
    `the card label must fit the card: ${map.textWidth(label, 11)}`);
  // The card keeps a margin: the label is not jammed edge to edge.
  assert.ok(card.includes('aria-label'), 'the full name stays available to assistive tech');
});

test('the source map canvas clears the deepest chunk dot it draws', () => {
  const html = mindHtml();
  const start = html.indexOf('rag-source-map');
  const svg = html.slice(start, html.indexOf('</svg>', start));
  const height = Number(svg.match(/viewBox="0 0 \d+ ([\d.]+)"/)[1]);
  const dots = [...svg.matchAll(/<circle cx="[-\d.]+" cy="([-\d.]+)" r="([\d.]+)"/g)]
    .map(match => Number(match[1]) + Number(match[2]));
  assert.ok(dots.length > 0, 'the fixture must draw chunk dots');
  // The dots hang below their cards. If the canvas ignores them the last row
  // is cut off by the SVG viewport, which is invisible in the markup alone.
  assert.ok(Math.max(...dots) <= height,
    `the deepest dot (${Math.max(...dots)}) must fit the canvas (${height})`);
});

test('the RAG maps keep the page direction instead of pinning their own', () => {
  // SVG resolves `text-anchor` against the inline direction. Pinning the maps
  // to `ltr` aligns the labels but reorders every label that starts with a
  // number - the number jumps to the other end of the line and the label reads
  // backwards. The maps must inherit the page's RTL direction and use the
  // anchors that go with it.
  const css = readFileSync(new URL('./src/components/rag-inspector.css', import.meta.url), 'utf8');
  assert.doesNotMatch(css, /\.rag-inspector svg\s*\{[^}]*direction:/,
    'the RAG svgs must not pin their own direction');
});

test('right-aligned map labels use the anchor that the RTL page resolves to it', () => {
  // In RTL, `start` is the right edge. The card title is pinned by its right
  // edge inside the card; writing `end` there (the LTR spelling) would push the
  // label out of the card and off the canvas.
  const html = mindHtml();
  const start = html.indexOf('g class="rag-mind-card"');
  const card = html.slice(start, html.indexOf('</g>', start));
  const title = card.match(/<text[^>]*font-size="11"[^>]*>/)[0];
  assert.match(title, /text-anchor="start"/);
  // The chart is the other way round: its track label grows rightwards from the
  // first point, so it is anchored by its left edge - `end` in RTL.
  const t = mindTrace();
  const chart = map.buildRankChart(t);
  const chartHtml = renderToStaticMarkup(
    React.createElement(map.ChunkRankChart, { chart, docFilter: '', onSelectDoc() {} }));
  const track = chartHtml.match(/<text[^>]*font-size="9"[^>]*>[^<]*تکه[^<]*<\/text>/)[0];
  assert.match(track, /text-anchor="end"/);
});

test('the RAG tab carries a settings button at the top that owns the config', async () => {
  const { default: RagInspector } = await vite.ssrLoadModule('/src/components/RagInspector.tsx');
  const html = renderToStaticMarkup(React.createElement(RagInspector));
  // The button is above the playground it configures, and it is collapsed by
  // default: the panel is in the document but out of the layout.
  assert.ok(html.indexOf('rag-settings-toggle') < html.indexOf('اجرای دستی بازیابی'));
  assert.match(html, /type="button" aria-expanded="false" aria-controls="rag-settings" class="rag-settings-toggle"/);
  assert.match(html, /<button[^>]*rag-settings-toggle[^>]*><svg /);
  assert.match(html, /id="rag-settings" class="rag-settings" hidden=""/);
  assert.match(html, /تنظیمات فعلی مسیر بازیابی/);
  // The display preferences the visualisations read are real controls.
  assert.match(html, /aria-label="گنجایش سند در نقشهٔ منابع"/);
  assert.match(html, /aria-label="تکه زیر هر سند"/);
  assert.match(html, /جزئیات فنی همهٔ مرحله‌ها از ابتدا باز باشد/);
  assert.match(html, /بازگردانی پیش‌فرض‌های نمایش/);
});

test('the trace view opens on the visualisation tab and keeps the stage record mounted', async () => {
  const t = trace([
    stage('embed_query', { model: 'gemini-embedding', dimensions: 1024 }),
    stage('books · semantic_search', { hits: 2 }, [{ id: 'b1', doc: 'فیزیک ۱.pdf', chunk: 4, rank: 1 }]),
  ]);
  t.stages[1].command = 'collection.query(query_embeddings=[1024 dims], n_results=2)';
  const html = renderToStaticMarkup(React.createElement(TraceView, { trace: t }));
  assert.match(html, /role="tablist" aria-label="نماهای این اجرا"/);
  assert.match(html, /role="tab" id="rag-tab-visual-test-trace" aria-controls="rag-panel-visual-test-trace" aria-selected="true"/);
  assert.match(html, /role="tab" id="rag-tab-stages-test-trace" aria-controls="rag-panel-stages-test-trace" aria-selected="false"/);
  assert.doesNotMatch(html, /id="rag-panel-visual-test-trace"[^>]*hidden/);
  assert.match(html, /id="rag-panel-stages-test-trace"[^>]* hidden=""/);
  // Hidden, not unmounted: the tables are still there for the second tab.
  assert.match(html, /دستوری که اجرا شد/);
  assert.match(html, /collection\.query\(query_embeddings=\[1024 dims\]/);
  // The figures lead the tab, and the selected stage can jump to its record.
  assert.match(html, /نقشهٔ خط بازیابی/);
  assert.match(html, /نمایش همهٔ تکه‌ها|تکه در بافت مدل/);
  assert.match(html, /جزئیات مرحله/);
});

test('opening every stage card is a display setting, not the new default', async () => {
  const t = trace([stage('a', { x: 1 }), stage('b', { y: 2 })]);
  const closed = renderToStaticMarkup(React.createElement(TraceView, { trace: t }));
  const opened = renderToStaticMarkup(React.createElement(TraceView, { trace: t,
    settings: { docCap: 12, chunksPerDoc: 3, openStageDetails: true } }));
  const openDetails = html => (html.match(/<details open=""/g) ?? []).length;
  assert.ok(openDetails(opened) > openDetails(closed), 'the setting must open more than the selected stage');
  // Trimming the map is the other half of the setting and reaches the map.
  const trimmed = renderToStaticMarkup(React.createElement(TraceView, { trace: t,
    settings: { docCap: 0, chunksPerDoc: 0, openStageDetails: false } }));
  assert.match(trimmed, /نقشهٔ خط بازیابی/);
});

// ------------------------------------------------------- semantic vector map

/** A payload shaped exactly like GET /api/admin/rag/traces/{id}/embedding-map. */
const embeddingMap = (points, overrides = {}) => ({
  trace_id: 'test-trace',
  maps: [{
    stage: 'books · semantic_search', collection: 'shared-books-demo', shelf: 'books',
    shelf_label: 'کتاب‌ها', point_count: points.length, recorded_rows: points.length,
    missing_vectors: 0, unscored_rows: 0, dimensions: 1024, metric: 'cosine',
    components: 2, explained_variance_ratio: [0.4, 0.25],
    query: { x: 1.2, y: -0.4 }, points, ...overrides,
  }],
  skipped: [], limitations: ['محدودیت نمونه برای آزمون'], notice: 'بردارها از مجموعه خوانده می‌شوند.',
});
const vectorPoint = (id, x, y, score, rank) => ({ id, x, y, doc: 'کتاب آزمایشی.pdf',
  chunk: rank, rank, score, preview: `متن نمونه ${id}` });
const vectorRows = [
  { id: 'a', rank: 1, score: 0.9, doc: 'کتاب آزمایشی.pdf', chunk: 1, preview: 'یک' },
  { id: 'b', rank: 2, score: 0.8, doc: 'کتاب آزمایشی.pdf', chunk: 2, preview: 'دو' },
  { id: 'c', rank: 3, score: 0.7, doc: 'کتاب آزمایشی.pdf', chunk: 3, preview: 'سه' },
];
const vectorTrace = () => trace([
  stage('embed_query', { model: 'gemini-embedding', dimensions: 1024, input: 'نیم‌ساز چیست؟' }),
  stage('books · semantic_search', { collection: 'shared-books-demo', hits: 80 }, vectorRows),
]);

test('the vector map keeps every point and the query inside its frame', () => {
  const points = [vectorPoint('a', -2, 1, 0.9, 1), vectorPoint('b', 0, -1, 0.7, 2),
    vectorPoint('c', 3, 0.5, 0.5, 3), vectorPoint('d', 1, 2, 0.2, 4)];
  const g = map.scatterGeometry(embeddingMap(points).maps[0]);
  const inside = node => node.cx >= g.left && node.cx <= g.right && node.cy >= g.top && node.cy <= g.bottom;

  assert.equal(g.points.length, 4);
  assert.ok(g.points.every(inside), 'every point must be drawn inside the frame');
  assert.ok(inside(g.query), 'the query marker must be drawn inside the frame');
  // The extents are the data's (query included), not a fixed scale.
  assert.deepEqual(g.extent.x, [-2, 3]);
  assert.deepEqual(g.extent.y, [-1, 2]);
  // The first principal axis grows leftwards, like every other map in the panel.
  assert.ok(g.points.find(p => p.id === 'c').cx < g.points.find(p => p.id === 'a').cx);
  // The three highest similarities are the emphasised ones, not the first three.
  assert.equal(g.strongest, 3);
  assert.deepEqual(g.points.filter(p => p.strongest).map(p => p.id).sort(), ['a', 'b', 'c']);
});

test('a degenerate cloud is centred instead of dividing by a zero span', () => {
  const flat = map.scatterGeometry({ points: [vectorPoint('a', 0, 0, 0.5, 1), vectorPoint('b', 0, 0, 0.4, 2),
    vectorPoint('c', 0, 0, 0.3, 3)], query: null });
  assert.equal(flat.query, null);
  assert.ok(flat.points.every(point => Number.isFinite(point.cx) && Number.isFinite(point.cy)));
  const alone = map.scatterGeometry({ points: [vectorPoint('a', 1, 1, 0.5, 1)], query: null });
  assert.ok(alone.points[0].cx > alone.left && alone.points[0].cx < alone.right);
  assert.ok(alone.points[0].cy > alone.top && alone.points[0].cy < alone.bottom);
  // A coordinate that is not a number is dropped, not drawn at the origin.
  const broken = map.scatterGeometry({ points: [vectorPoint('a', 0, 0, 0.5, 1), vectorPoint('b', 1, 1, 0.4, 2),
    { ...vectorPoint('c', 2, 2, 0.3, 3), x: Number.NaN }], query: null });
  assert.deepEqual(broken.points.map(point => point.id), ['a', 'b']);
});

test('a plotted vector map replaces the no-coordinates diagram and stays selectable', () => {
  const points = [vectorPoint('a', -2, 1, 0.9, 1), vectorPoint('b', 0, -1, 0.7, 2), vectorPoint('c', 3, 0.5, 0.5, 3)];
  const html = renderToStaticMarkup(React.createElement(map.EmbeddingProvenance,
    { trace: vectorTrace(), map: embeddingMap(points), onSelectDoc() {} }));

  assert.match(html, /rag-embedding-map/);
  assert.match(html, /بردار پرسش/);
  assert.match(html, /بالاترین شباهت/);
  assert.match(html, /۴۰٪/);                       // the recorded variance share
  assert.match(html, /۱۰۲۴|۱٬۰۲۴/);                // the real vector size
  assert.match(html, /۳ بردار بازیابی‌شده/);
  // The fallback diagram claims no coordinates; it must be gone once one exists.
  assert.doesNotMatch(html, /مختصات و بردارها در این رد ذخیره نشده/);
  assert.doesNotMatch(html, /نقشهٔ روابط ثبت‌شده/);
  // One reachable node per chunk, plus the query marker's two circles.
  assert.equal((html.match(/rag-scatter-point/g) ?? []).length, points.length);
  assert.equal((html.match(/<circle /g) ?? []).length, points.length + 2);
  assert.match(html, /role="button" tabindex="0"/);
});

test('a map without a plane, and the reasons why, fall back instead of being invented', () => {
  const two = embeddingMap([vectorPoint('a', 0, 0, 0.9, 1), vectorPoint('b', 1, 1, 0.8, 2)]);
  const fallback = renderToStaticMarkup(React.createElement(map.EmbeddingProvenance,
    { trace: vectorTrace(), map: two }));
  assert.doesNotMatch(fallback, /rag-embedding-map/);
  assert.match(fallback, /مختصات و بردارها در این رد ذخیره نشده/);

  const withSkips = embeddingMap([vectorPoint('a', 0, 0, 0.9, 1), vectorPoint('b', 1, 1, 0.8, 2),
    vectorPoint('c', 2, 2, 0.7, 3)]);
  withSkips.skipped = [{ collection: 'questions-demo', stage: 'qbank · semantic_search',
    reason: 'کمتر از سه بردار ذخیره‌شده پیدا شد', found_vectors: 0, recorded_rows: 2 }];
  const html = renderToStaticMarkup(React.createElement(map.EmbeddingProvenance,
    { trace: vectorTrace(), map: withSkips, onSelectDoc() {} }));
  assert.match(html, /کمتر از سه بردار ذخیره‌شده پیدا شد/);
  assert.match(html, /محدودیت نمونه برای آزمون/);
  assert.match(html, /بردارها از مجموعه خوانده می‌شوند/);

  const nothing = renderToStaticMarkup(React.createElement(map.EmbeddingProvenance,
    { trace: vectorTrace(), map: { trace_id: 't', maps: [], skipped: [], limitations: [], reason: 'دلیل نمونه برای نبود نقشه' } }));
  assert.match(nothing, /دلیل نمونه برای نبود نقشه/);
  assert.match(nothing, /مختصات و بردارها در این رد ذخیره نشده/);
});

test('the inspector asks for a vector map only for runs that recorded one', async () => {
  const { traceHasSemanticRows } = await vite.ssrLoadModule('/src/components/RagInspector.tsx');
  const withRows = stage('books · semantic_search', { hits: 80 }, vectorRows);
  assert.equal(traceHasSemanticRows(trace([withRows])), true);
  // Fewer than three vectors cannot make a plane, so no request is worth it.
  assert.equal(traceHasSemanticRows(trace([stage('books · semantic_search', { hits: 80 }, vectorRows.slice(0, 2))])), false);
  assert.equal(traceHasSemanticRows(trace([stage('books · lexical_search', { hits: 80 }, vectorRows)])), false);
  assert.equal(traceHasSemanticRows(trace([])), false);

  const html = renderToStaticMarkup(React.createElement(TraceView, { trace: vectorTrace(),
    embeddingMap: embeddingMap(vectorRows.map(row => vectorPoint(row.id, row.rank, row.rank, row.score, row.rank))) }));
  assert.match(html, /rag-embedding-map/);
});

test('the map request the inspector makes is the route the backend serves', () => {
  // The map is fetched lazily and a failure is silent by design (the diagram
  // without coordinates is the fallback), so a typo in the URL would simply
  // never show a map. Pin the two sides together here.
  const inspector = readFileSync(new URL('./src/components/RagInspector.tsx', import.meta.url), 'utf8');
  const called = inspector.match(/`(\/api\/admin\/rag\/[^`]*embedding-map)`/);
  assert.ok(called, 'the inspector must request the trace embedding map');
  const route = called[1].replace('${encodeURIComponent(id)}', '{trace_id}');
  const backend = readFileSync(new URL('../backend/app/routers/rag_trace.py', import.meta.url), 'utf8');
  // The router declares its prefix once, so the route the frontend calls is
  // the prefix plus the decorator's own path.
  const prefix = backend.match(/APIRouter\(prefix="([^"]+)"/)?.[1];
  assert.ok(prefix && route.startsWith(prefix),
    `the map route ${route} must live under the router prefix ${prefix}`);
  assert.ok(backend.includes(`"${route.slice(prefix.length)}"`), `the backend must serve ${route}`);
});
