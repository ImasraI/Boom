import assert from 'node:assert/strict';
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
