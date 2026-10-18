import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

const vite = await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
test.after(async () => {await vite.close();});

test('weakness map distinguishes no answers from no mistakes and explains blanks', async () => {
  const {WeaknessMapContent} = await vite.ssrLoadModule('/src/components/WeaknessMap.tsx');
  const render = total_answered => renderToStaticMarkup(React.createElement(WeaknessMapContent, {
    data:{days:90,total_wrong:0,total_answered,subjects:[]},
  }));
  assert.match(render(0), /هنوز پاسخی برای ارزیابی ضعف‌ها ثبت نشده/);
  assert.match(render(3), /پاسخ غلطی در مباحث کتاب‌ها ثبت نشده/);
  assert.match(render(0), /سؤال‌های نزده غلط محسوب نمی‌شوند/);
  assert.doesNotMatch(render(0), /انتگرال|۱۳ غلط/);
});

test('Mock page and its shared math/report modules load with an empty profile', async () => {
  const {default:Mock} = await vite.ssrLoadModule('/src/pages/Mock.tsx');
  const html = renderToStaticMarkup(React.createElement(Mock, {nav(){},userData:null}));
  assert.match(html, /تمرین از سوال‌های قبلی/);
  assert.match(html, /ساخت دفترچه آزمون/);
  assert.match(html, /آزمون کامل کنکور/);
  assert.match(html, /سخت‌ترین سطح/);
  assert.doesNotMatch(html, /تعداد کل سوال‌ها|مباحث هدف/);
  assert.doesNotMatch(html, /صفحه آماده نشد/);
});

test('Ranked page loads its controls before account and filter requests finish', async () => {
  const {default:Arena} = await vite.ssrLoadModule('/src/pages/Arena.tsx');
  const html = renderToStaticMarkup(React.createElement(Arena, {nav(){},userData:null}));
  assert.match(html, /۱۰ سوال از آزمون آیندهٔ ماز/);
  assert.match(html, /در حال دریافت اطلاعات کولوسئوم/);
  assert.doesNotMatch(html, /فیلتر دروس|type="checkbox"/);
  assert.doesNotMatch(html, /صفحه آماده نشد/);
});

test('Full mock failure offers an explicit short practice selection without silently starting it', async () => {
  const {ConfigView} = await vite.ssrLoadModule('/src/pages/Mock.tsx');
  let started=false;
  const html=renderToStaticMarkup(React.createElement(ConfigView, {
    onStart(){started=true},onBack(){},error:'دفترچهٔ کامل آماده نیست',
  }));
  assert.match(html,/انتخاب تمرین ۱۰ سوالی/);
  assert.match(html,/جای دفترچهٔ کامل کنکور را نمی‌گیرد/);
  assert.match(html,/موجودی همین سطح دشواری/);
  assert.equal(started,false);
});

test('Colosseum clearly labels a previous Maze batch instead of presenting it as upcoming', async () => {
  const {WeeklyStockNotice} = await vite.ssrLoadModule('/src/pages/Arena.tsx');
  const html=renderToStaticMarkup(React.createElement(WeeklyStockNotice,{weekly:{
    available:true,stock_available:true,fallback:true,date:'2026-10-09',requested_date:'2026-10-23',
    message:'این مسابقه از نسخهٔ تأییدشدهٔ آزمون قبلی ماز است.',
  }}));
  assert.match(html,/نسخهٔ موجود از آزمون ماز/);
  assert.match(html,/آزمون قبلی ماز/);
  assert.doesNotMatch(html,/آزمون آینده:/);
});

test('Admin pool renders unlimited and targeted production controls', async () => {
  const {default:Admin} = await vite.ssrLoadModule('/src/pages/Admin.tsx');
  const html = renderToStaticMarkup(React.createElement(Admin, {nav(){}}));
  assert.match(html, /ذخیره بدون سقف/);
  assert.match(html, /کولوسئوم \+ آزمون آزمایشی و تمرین/);
  assert.match(html, /دفترچه کامل رشته/);
  assert.match(html, /سخت‌ترین سطح/);
  assert.match(html, /بخش‌های مدیریت/);
  assert.match(html, /id="admin-generation"/);
  assert.match(html, /id="admin-bank" hidden/);
  assert.match(html, /id="admin-keys" hidden/);
  assert.match(html, /id="admin-users" hidden/);
  assert.match(html, /id="admin-sms" hidden/);
  assert.match(html, /راه‌اندازی مجدد سرور ادامه می‌دهد/);
  assert.match(html, /موجودی سوال‌های قابل استفاده/);
  assert.match(html, /کلیدهای سرویس ساخت آزمون/);
  assert.match(html, /Gemini — بررسی پاسخ/);
  assert.match(html, /Groq — تولید سؤال/);
  assert.match(html, /type="password"/);
  assert.match(html, /افزودن کلید/);
});

test('old unverified pool booklets are described as unavailable, not awaiting approval', async () => {
  const {PoolStockNotice} = await vite.ssrLoadModule('/src/pages/Admin.tsx');
  const html = renderToStaticMarkup(React.createElement(PoolStockNotice, {unavailable:3}));
  assert.match(html, /۳ دفترچه آماده نیست/);
  assert.match(html, /این عدد صف تأیید خودکار نیست/);
  assert.match(html, /بانک برای ساخت آزمون با تعداد دلخواه/);
  const empty = renderToStaticMarkup(React.createElement(PoolStockNotice, {unavailable:0}));
  assert.doesNotMatch(empty, /دفترچه آماده نیست/);
});

test('pool credentials identify verifier quota as the blocker despite available Groq keys', async () => {
  const {PoolCredentialBlocker} = await vite.ssrLoadModule('/src/components/PoolCredentials.tsx');
  const html = renderToStaticMarkup(React.createElement(PoolCredentialBlocker, {
    health:{blocked:true,provider:'gemini',stage:'verification',retry_at:'2026-10-11T07:00:00Z'},
  }));
  assert.match(html, /تولید منتظر بررسی پاسخ با Gemini/);
  assert.match(html, /افزودن کلید Groq این توقف را برطرف نمی‌کند/);
  assert.match(html, /بررسی دوباره پس از/);
  assert.equal(renderToStaticMarkup(React.createElement(PoolCredentialBlocker, {health:{blocked:false}})), '');
});

test('durable draft queue distinguishes pending candidates from verified usable stock', async () => {
  const {default:PoolDraftQueue} = await vite.ssrLoadModule('/src/components/PoolDraftQueue.tsx');
  const html = renderToStaticMarkup(React.createElement(PoolDraftQueue, {
    queue:{enabled:true,capacity:20,pending_booklets:3,pending_questions:22,drafting_booklets:1,
      verifying_booklets:1,completed_booklets:2,rejected_booklets:0,verified_questions:17,rejected_questions:2},
    drafting:{status:'generating',provider:'groq'},verification:{status:'verifying',provider:'groq',fallback:true},running:true,
  }));
  assert.match(html,/صف پیش‌نویس‌های آزمون/);
  assert.match(html,/تا تأیید وارد تمرین یا رنکینگ نمی‌شوند/);
  assert.match(html,/سؤال منتظر بررسی/);
  assert.match(html,/در حال طراحی سؤال/);
  assert.match(html,/در حال بررسی پاسخ/);
  assert.match(html,/پشتیبان/);
});

test('credentials explain that Groq fallback continues verification while Gemini is unavailable', async () => {
  const {PoolCredentialBlocker} = await vite.ssrLoadModule('/src/components/PoolCredentials.tsx');
  const html = renderToStaticMarkup(React.createElement(PoolCredentialBlocker, {
    health:{blocked:false,provider:'groq',stage:'verification',fallback:true},
  }));
  assert.match(html,/بررسی پاسخ با Groq پشتیبان انجام می‌شود/);
  assert.doesNotMatch(html,/تولید منتظر بررسی پاسخ/);
});

test('Knowledge graph loads without a profile and describes book-sourced titles', async () => {
  const {default:KnowledgeGraph} = await vite.ssrLoadModule('/src/pages/KnowledgeGraph.tsx');
  const html = renderToStaticMarkup(React.createElement(KnowledgeGraph, {nav(){},userData:null}));
  assert.match(html, /مباحث استخراج‌شده از کتاب‌ها/);
  assert.match(html, /در حال دریافت نقشه کتاب‌ها/);
  assert.doesNotMatch(html, /پیش‌نیازهای واقعی|صفحه آماده نشد/);
});

test('homework intake asks for workload, learning purpose and prerequisite time before scheduling', async () => {
  const {default:HomeworkIntake} = await vite.ssrLoadModule('/src/components/HomeworkIntake.tsx');
  const html = renderToStaticMarkup(React.createElement(HomeworkIntake, {
    draft:{id:'one',status:'draft',details:{subject:'فیزیک',activity:'practice',familiarity:'new',minutes:120}},
    onScheduled(){},onDismiss(){},
  }));
  assert.match(html,/حجم دقیق و منبع/);
  assert.match(html,/این مبحث را چقدر بلدی/);
  assert.match(html,/مطالعهٔ پیش‌نیاز/);
  assert.match(html,/ثبت در برنامه/);
  assert.match(html,/فقط در زمان آزاد اضافه کن/);
  assert.match(html,/جلسهٔ تولیدشدهٔ هم‌درس و هم‌مبحث/);
  assert.doesNotMatch(html,/صفحه آماده نشد/);
});

test('admin wipe uses an in-app type-to-confirm dialog, not window.prompt', async () => {
  const fs = await import('node:fs');
  const admin = fs.readFileSync('src/pages/Admin.tsx', 'utf8');
  assert.match(admin, /WipeUserDialog/);
  assert.doesNotMatch(admin, /window\.prompt\s*\(/);
});

test('wipe dialog blocks the destructive action until the username matches', async () => {
  const {default:WipeUserDialog, wipeConfirmReady} = await vite.ssrLoadModule('/src/components/WipeUserDialog.tsx');
  const render = typed => renderToStaticMarkup(React.createElement(WipeUserDialog, {
    target:{id:9,username:'09120000000'}, typed, busy:false, error:'',
    onTypedChange(){}, onCancel(){}, onConfirm(){},
  }));
  const empty = render('');
  assert.match(empty, /role="dialog"/);
  assert.match(empty, /aria-modal="true"/);
  assert.match(empty, /حذف کامل داده‌های کاربر/);
  assert.match(empty, /09120000000/);
  assert.match(empty, /دکمهٔ حذف فعال نمی‌شود/);
  // Destructive button is disabled while the typed name is empty or wrong.
  // Anchored on its own class: the label mixes ZWNJ characters.
  const confirmButton = html => html.match(/<button[^>]*disabled:cursor-not-allowed[^>]*>/)?.[0] ?? '';
  assert.match(confirmButton(empty), /disabled=""/);
  assert.match(confirmButton(render('0912')), /disabled=""/);
  assert.doesNotMatch(confirmButton(render('09120000000')), /disabled=""/);
  assert.doesNotMatch(render('09120000000'), /دکمهٔ حذف فعال نمی‌شود/);
  // Whitespace around a correct name is still a match, mirroring the backend.
  assert.equal(wipeConfirmReady(' 09120000000 ', '09120000000'), true);
  assert.equal(wipeConfirmReady('', '09120000000'), false);
  assert.equal(wipeConfirmReady('0912000000', '09120000000'), false);
});

test('wipe dialog surfaces the server error instead of closing silently', async () => {
  const {default:WipeUserDialog} = await vite.ssrLoadModule('/src/components/WipeUserDialog.tsx');
  const html = renderToStaticMarkup(React.createElement(WipeUserDialog, {
    target:{id:4,username:'09121111111'}, typed:'09121111111', busy:false,
    error:'متن تایید با نام کاربری مطابقت ندارد',
    onTypedChange(){}, onCancel(){}, onConfirm(){},
  }));
  assert.match(html, /role="alert"/);
  assert.match(html, /متن تایید با نام کاربری مطابقت ندارد/);
});

test('admin exposes the RAG inspector as its own section', async () => {
  const {default:Admin} = await vite.ssrLoadModule('/src/pages/Admin.tsx');
  const html = renderToStaticMarkup(React.createElement(Admin, {nav(){}}));
  assert.match(html, /بررسی RAG/);
  assert.match(html, /id="admin-rag" hidden/);
});

test('RAG inspector renders the playground and the pipeline knobs before any trace arrives', async () => {
  const {default:RagInspector} = await vite.ssrLoadModule('/src/components/RagInspector.tsx');
  const html = renderToStaticMarkup(React.createElement(RagInspector));
  assert.match(html, /تنظیمات فعلی مسیر بازیابی/);
  assert.match(html, /اجرای دستی بازیابی/);
  assert.match(html, /بازنویسی پرسش با LLM/);
  assert.match(html, /بانک سؤال/);
  assert.match(html, /اجرای بازیابی/);
  // Playground is inert until a question is typed: the accent button
  // (the playground action) must carry the disabled attribute.
  const accentButtons = html.match(/<button[^>]*bg-\[var\(--accent\)\][^>]*>/g) ?? [];
  assert.ok(accentButtons.length > 0, 'playground button missing');
  assert.ok(accentButtons.every(button => /disabled=""/.test(button)), accentButtons.join('\n'));
  assert.match(html, /هنوز ردّی ثبت نشده است/);
});

test('trace view shows every stage: command, tables, prompt and waterfall', async () => {
  const {TraceView} = await vite.ssrLoadModule('/src/components/RagInspector.tsx');
  const trace = {
    id:'abc123', kind:'chat', kind_label:'گفتگوی کاربر', title:'نیم‌ساز چیست؟',
    question:'نیم‌ساز چیست؟', user_id:7, created_at:1760000000, duration_ms:2345.6,
    status:'ok', error:'', summary:{sources:1, confidence:'منابع مرتبط کافی', chunks:4},
    total_stage_ms:2300,
    stages:[
      {name:'books · semantic_search', label:'جست‌وجوی برداری (Chroma)', ms:180.4,
       command:'collection.query(query_embeddings=[4 dims], n_results=20, where=…)',
       meta:{collection:'boom_chunks', hits:3, candidates_requested:20},
       columns:[{key:'rank',label:'رتبه'},{key:'doc',label:'سند'},{key:'score',label:'امتیاز'}],
       rows:[{rank:1,doc:'فیزیک ۱ خیلی سبز',score:0.83}], text:{}},
      {name:'books · rerank', label:'بازرتبه‌بندی (Cross-Encoder)', ms:1900,
       command:'encode(query, chunk) pairs -> cross-encoder relevance',
       meta:{model:'BAAI/bge-reranker-base', candidate_pairs:20, kept:4},
       columns:[{key:'rank',label:'رتبه جدید'},{key:'old_rank',label:'رتبه قبل'},{key:'move',label:'جابه‌جایی'}],
       rows:[{rank:1,old_rank:3,move:2}], text:{}},
      {name:'llm_generate', label:'فراخوانی مدل زبانی با منابع', ms:220,
       command:'GroqLLMClient.generate(messages[2])',
       meta:{provider:'groq', model:'llama-3.1-8b-instant'}, columns:[], rows:[],
       text:{prompt:'[system]\nتو بوم هستی\n\n[user]\nمتن‌های مرجع:\n--- [منبع 1] ---', answer:'نیم‌ساز…'}},
    ],
  };
  const html = renderToStaticMarkup(React.createElement(TraceView, {trace}));
  // Waterfall + per-stage timing (fa-IR uses ٬ as the thousands separator).
  assert.match(html, /نمودار زمان مرحله‌ها/);
  assert.match(html, /۱٬۹۰۰٫۰ ms/);
  assert.match(html, /۱۸۰٫۴ ms/);
  // The command each stage actually executed
  assert.match(html, /دستوری که اجرا شد/);
  assert.match(html, /collection\.query\(query_embeddings=\[4 dims\]/);
  assert.match(html, /GroqLLMClient\.generate/);
  // Per-chunk tables: which chunk, from where, which score, how it moved
  assert.match(html, /فیزیک ۱ خیلی سبز/);
  assert.match(html, /جابه‌جایی/);
  assert.match(html, /رتبه قبل/);
  // Persian labels for the raw metadata keys
  assert.match(html, /جفت‌های بررسی‌شده/);
  assert.match(html, /نگه‌داشته‌شده/);
  assert.match(html, /کاندیدهای درخواستی/);
  // The exact prompt sent to the model
  assert.match(html, /متن‌های مرجع:/);
  assert.match(html, /پرامپت ارسالی/);
  assert.match(html, /پاسخ مدل/);
  assert.match(html, /«نیم‌ساز چیست؟»/);
  assert.doesNotMatch(html, /undefined/);
});

test('an empty model answer is flagged next to the zero character count', async () => {
  const {TraceView} = await vite.ssrLoadModule('/src/components/RagInspector.tsx');
  const html = renderToStaticMarkup(React.createElement(TraceView, {trace:{
    id:'empty', kind:'chat', kind_label:'گفتگوی کاربر', title:'پاسخ خالی',
    question:'طبق کتاب فیزیک، جهت نیرو را توضیح بده', user_id:2, created_at:1760000000,
    duration_ms:3400, status:'error',
    error:'مدل زبانی پاسخ خالی برگرداند؛ کاربر پیام جایگزین گرفت. دلیل سرویس‌دهنده در مرحلهٔ «فراخوانی مدل» ثبت شده است.',
    summary:{sources:0, answer_characters:0, empty_answer:true}, total_stage_ms:3300,
    stages:[{name:'vision_generate', label:'فراخوانی مدل بینایی (تصویر صفحه)', ms:28.7,
      command:'GeminiLLMClient.generate(messages[2], images=3)',
      meta:{provider:'gemini', model:'gemini-3.6-flash', answer_characters:0,
            provider_error:'daily quota exhausted'}, columns:[], rows:[],
      text:{prompt:'[system]\nتو بوم هستی', answer:''}}],
  }}));
  assert.match(html, /پاسخ مدل خالی بود/);
  assert.match(html, /کاراکتر پاسخ: ۰/);
  // Amber chip, not the plain muted one, and the reason is spelled out.
  assert.match(html, /border-amber-400\/60/);
  assert.match(html, /پیام جایگزین گرفت/);
  assert.match(html, /daily quota exhausted/);
});

// A trace shaped like a real run: text search in parallel, fusion, a reranker
// that promotes a chunk the vector search missed, a question-bank lookup, and
// a final answer citing three chunks from two files.
const graphTrace = {
  id:'map1', kind:'chat', kind_label:'گفتگوی کاربر', title:'نیم‌ساز', question:'نیم‌ساز چیست؟',
  user_id:2, created_at:1760000000, duration_ms:900, status:'ok', error:'',
  summary:{}, total_stage_ms:880,
  stages:[
    {name:'query_rewrite', label:'بازنویسی پرسش (LLM)', ms:120, command:'', meta:{}, columns:[], rows:[], text:{}},
    {name:'embed_query', label:'بردارسازی پرسش (Embedding)', ms:90, command:'', meta:{}, columns:[], rows:[], text:{}},
    {name:'books · semantic_search', label:'جست‌وجوی برداری (Chroma)', ms:40, command:'', meta:{},
     columns:[{key:'rank',label:'رتبه'}],
     rows:[{rank:1,doc:'فیزیک ۱.pdf',chunk:4,score:.9,preview:'چهار'},
           {rank:2,doc:'هندسه ۲.pdf',chunk:9,score:.8,preview:'نه'}], text:{}},
    {name:'books · lexical_search', label:'جست‌وجوی واژگانی (BM25)', ms:1, command:'', meta:{},
     columns:[{key:'rank',label:'رتبه'}],
     rows:[{rank:1,doc:'هندسه ۲.pdf',chunk:9,score:3.1,preview:'نه'},
           {rank:2,doc:'فیزیک ۱.pdf',chunk:4,score:2.2,preview:'چهار'}], text:{}},
    {name:'books · rrf_fusion', label:'ادغام رتبه‌ها (RRF)', ms:0.5, command:'', meta:{},
     columns:[{key:'rank',label:'رتبه'}],
     rows:[{rank:1,doc:'هندسه ۲.pdf',chunk:9,rrf:.032},
           {rank:2,doc:'فیزیک ۱.pdf',chunk:4,rrf:.031}], text:{}},
    {name:'books · rerank', label:'بازرتبه‌بندی (Cross-Encoder)', ms:300, command:'', meta:{},
     columns:[{key:'rank',label:'رتبه'}],
     rows:[{rank:1,old_rank:2,move:1,doc:'فیزیک ۱.pdf',chunk:4,rerank_score:.8},
           {rank:2,old_rank:1,move:-1,doc:'هندسه ۲.pdf',chunk:9,rerank_score:.2}], text:{}},
    {name:'qbank_search', label:'بانک سؤال (تکه‌های ساخت‌یافته)', ms:60, command:'', meta:{},
     columns:[{key:'rank',label:'رتبه'}],
     rows:[{rank:1,doc:'فیزیک ۱ ریاضی خیلی سبز::p40',chunk:7,score:.02,preview:'صفحه ۴۰'}], text:{}},
    // The question bank runs the same search stack as the books: same labels,
    // different shelf - the chart and the lanes have to keep them apart.
    {name:'qbank · semantic_search', label:'جست‌وجوی برداری (Chroma)', ms:30, command:'', meta:{},
     columns:[{key:'rank',label:'رتبه'}],
     rows:[{rank:1,doc:'فیزیک ۱ ریاضی خیلی سبز::p40',chunk:7,score:.03,preview:'صفحه ۴۰'},
           {rank:2,doc:'فیزیک ۱ ریاضی خیلی سبز::p40',chunk:12,score:.02,preview:'صفحه ۴۱'}], text:{}},
    {name:'qbank · lexical_search', label:'جست‌وجوی واژگانی (BM25)', ms:1, command:'', meta:{},
     columns:[{key:'rank',label:'رتبه'}],
     rows:[{rank:1,doc:'فیزیک ۱ ریاضی خیلی سبز::p40',chunk:12,score:1.7,preview:'صفحه ۴۱'},
           {rank:2,doc:'فیزیک ۱ ریاضی خیلی سبز::p40',chunk:7,score:1.4,preview:'صفحه ۴۰'}], text:{}},
    {name:'qbank · rrf_fusion', label:'ادغام رتبه‌ها (RRF)', ms:.4, command:'', meta:{},
     columns:[{key:'rank',label:'رتبه'}],
     rows:[{rank:1,doc:'فیزیک ۱ ریاضی خیلی سبز::p40',chunk:12,rrf:.030},
           {rank:2,doc:'فیزیک ۱ ریاضی خیلی سبز::p40',chunk:7,rrf:.029}], text:{}},
    {name:'qbank · rerank', label:'بازرتبه‌بندی (Cross-Encoder)', ms:120, command:'', meta:{},
     columns:[{key:'rank',label:'رتبه'}],
     rows:[{rank:1,old_rank:2,move:1,doc:'فیزیک ۱ ریاضی خیلی سبز::p40',chunk:7,rerank_score:.7},
           {rank:2,old_rank:1,move:-1,doc:'فیزیک ۱ ریاضی خیلی سبز::p40',chunk:12,rerank_score:.3}], text:{}},
    {name:'llm_generate', label:'فراخوانی مدل زبانی با منابع', ms:200, command:'GroqLLMClient.generate(messages[2])',
     meta:{provider:'groq'}, columns:[], rows:[], text:{prompt:'[system]\nتو بوم هستی', answer:'نیم‌ساز…'}},
    {name:'final_answer', label:'پاسخ نهایی و منابع آن', ms:0.2, command:'', meta:{sources:3},
     columns:[{key:'rank',label:'منبع'}],
     rows:[{rank:1,doc:'فیزیک ۱.pdf',chunk:4,score:.8,preview:'چهار'},
           {rank:2,doc:'هندسه ۲.pdf',chunk:9,score:.2,preview:'نه'},
           {rank:3,doc:'فیزیک ۱ ریاضی خیلی سبز::p40',chunk:7,score:.02,preview:'صفحه ۴۰'}], text:{}},
  ],
};

test('pipeline map flows parallel searches into fusion and counts candidates per edge', async () => {
  const {buildPipelineGraph, funnelClusters} = await vite.ssrLoadModule('/src/components/RagPipelineMap.tsx');
  const graph = buildPipelineGraph(graphTrace);
  const byName = Object.fromEntries(graph.nodes.map(node => [node.name, node]));

  // Both searches point at the fusion stage, not at each other.
  const vector = byName['books · semantic_search'];
  const lexical = byName['books · lexical_search'];
  const fusion = byName['books · rrf_fusion'];
  const edgesFrom = id => graph.edges.filter(edge => edge.from === id).map(edge => edge.to);
  assert.deepEqual(edgesFrom(vector.id), [fusion.id]);
  assert.deepEqual(edgesFrom(lexical.id), [fusion.id]);
  // Edge width is the candidate count the stage handed on.
  assert.equal(graph.edges.find(e => e.from === vector.id).count, 2);
  assert.equal(graph.edges.find(e => e.from === fusion.id).count, 2);

  // Lanes place the question rightmost and the answer last.
  assert.equal(vector.lane, 1);
  assert.equal(fusion.lane, 2);
  assert.equal(byName['llm_generate'].lane, 4);
  assert.deepEqual(graph.lanes.map(lane => lane.title).slice(0, 3),
    ['پرسش و بازنویسی','جست‌وجوی کتاب','ادغام و بازترتیب']);

  // Each node knows which files and chunks it selected.
  assert.deepEqual(vector.docs, ['فیزیک ۱.pdf','هندسه ۲.pdf']);
  assert.equal(byName['final_answer'].selected, 3);

  // The funnel reads like the pipeline: two searches in, two fused, two reranked.
  const funnel = graph.funnels[0];
  assert.equal(funnel.group, 'books');
  assert.deepEqual(funnel.steps.map(step => step.count), [2, 2, 2, 2]);
  // The two searches are parallel sources for the same fusion, not two steps in
  // a row, so they share one cluster and only real hand-offs get an arrow.
  assert.deepEqual(funnelClusters(funnel.steps).map(cluster => cluster.map(step => step.role)),
    [['vector', 'lexical'], ['fusion'], ['rerank']]);
  // The question-bank shelf keeps its own funnel instead of merging with books,
  // and the wrapper stage is left out of it: it reports the shelf's *output*,
  // which would otherwise sit in front of its own input.
  assert.deepEqual(graph.funnels.map(item => item.group), ['books', 'qbank']);
  const qbankFunnel = graph.funnels.find(item => item.group === 'qbank');
  assert.deepEqual(qbankFunnel.steps.map(step => step.count), [2, 2, 2, 2]);
  assert.ok(!qbankFunnel.steps.some(step => step.label.includes('بانک سؤال (تکه')));
  // The whole question-bank stack stays in the question-bank lane: its
  // vector/lexical/fusion stages must not bleed into the book column.
  const qbankLane = graph.lanes.find(lane => lane.title === 'بانک سؤال و تصویر');
  assert.deepEqual(qbankLane.nodes.map(node => node.role),
    ['qbank', 'vector', 'lexical', 'fusion', 'rerank']);
  assert.ok(graph.lanes.find(lane => lane.title === 'جست‌وجوی کتاب').nodes
    .every(node => node.name.startsWith('books · ')));
});

test('rank chart follows each chunk across stages and flags the promoted one', async () => {
  const {buildRankChart, buildDocumentCoverage} = await vite.ssrLoadModule('/src/components/RagPipelineMap.tsx');
  const chart = buildRankChart(graphTrace);
  assert.deepEqual(chart.steps.map(step => step.name),
    ['books · semantic_search','books · lexical_search','books · rrf_fusion','books · rerank',
     'qbank · semantic_search','qbank · lexical_search','qbank · rrf_fusion','qbank · rerank','final_answer']);
  // Identical stage labels are disambiguated by their shelf on the axis.
  assert.equal(chart.steps[0].label, 'کتاب‌ها · جست‌وجوی برداری (Chroma)');
  assert.equal(chart.steps[4].label, 'بانک سؤال · جست‌وجوی برداری (Chroma)');
  assert.equal(new Set(chart.steps.map(step => step.label)).size, chart.steps.length);

  const promoted = chart.tracks.find(track => track.chunk === '4');
  assert.equal(promoted.grid[0], 1);      // rank 1 in the vector search
  assert.equal(promoted.grid[3], 1);      // still 1 after reranking
  assert.equal(promoted.cited, true);     // and it is cited as source 1
  assert.equal(promoted.citedRank, 1);
  assert.equal(promoted.rerankMove, 1);   // the reranker lifted it one place

  const demoted = chart.tracks.find(track => track.chunk === '9');
  assert.equal(demoted.rerankMove, -1);
  assert.equal(demoted.cited, true);

  // A chunk that only the question bank returned is still tracked and cited.
  const qbank = chart.tracks.find(track => track.chunk === '7');
  assert.equal(qbank.citedRank, 3);

  // Filtering by file narrows the chart instead of hiding the control.
  assert.equal(buildRankChart(graphTrace, 'هندسه ۲.pdf').tracks.length, 1);

  const docs = buildDocumentCoverage(graphTrace, chart);
  const physics = docs.find(doc => doc.doc === 'فیزیک ۱.pdf');
  assert.equal(physics.selectedIn, 1);
  assert.equal(physics.cited, 1);
  assert.equal(physics.chunks[0].chunk, '4');
  assert.deepEqual(physics.chunks[0].stages,
    ['کتاب‌ها · جست‌وجوی برداری (Chroma)','کتاب‌ها · جست‌وجوی واژگانی (BM25)',
     'کتاب‌ها · ادغام رتبه‌ها (RRF)','کتاب‌ها · بازرتبه‌بندی (Cross-Encoder)','پاسخ نهایی و منابع آن']);
  // Two sources of the same book stay apart: the file list keys on the raw
  // name, so the book's text chunks and its transcribed question-bank page are
  // two entries, one cited and one not.
  const qbankDoc = docs.find(doc => doc.doc.includes('خیلی سبز::p40'));
  assert.equal(qbankDoc.selectedIn, 2);
  assert.equal(qbankDoc.cited, 1);

  // A question-bank-only chunk is still tracked: the book search never saw it,
  // its own shelf places it first, and it ends up cited as source 3.
  const qbankTrack = chart.tracks.find(track => track.key.includes('خیلی سبز::p40') && track.chunk === '7');
  assert.equal(chart.steps[4].name, 'qbank · semantic_search');
  assert.equal(qbankTrack.grid[0], null);   // books · semantic_search
  assert.equal(qbankTrack.grid[4], 1);      // qbank · semantic_search
  assert.equal(qbankTrack.grid[8], 3);      // final_answer cites it as source 3
  // The question bank's own reranker lifted it, and that shelf's table is the
  // only one that knows it: the books rerank table has no row for this chunk.
  assert.equal(qbankTrack.rerankMove, 1);
  const qbankDemoted = chart.tracks.find(track => track.chunk === '12');
  assert.equal(qbankDemoted.rerankMove, -1);
  assert.equal(qbankDemoted.cited, false);
});

test('the map, the rank chart and the file panel render files and chunk text', async () => {
  const RagVisualMap = (await vite.ssrLoadModule('/src/components/RagPipelineMap.tsx')).default;
  const html = renderToStaticMarkup(React.createElement(RagVisualMap, {trace: graphTrace}));

  // The diagram: lane titles, node labels, per-stage timing and edge counts.
  assert.match(html, /نقشهٔ خط بازیابی/);
  assert.match(html, /جست‌وجوی کتاب/);
  assert.match(html, /بازرتبه‌بندی \(Cross-Encoder\)/);
  assert.match(html, /ضخامت هر پیکان/);
  assert.match(html, /role="img"/);
  // Rank trajectory + the reranker legend.
  assert.match(html, /سرنوشت تکه‌ها در مرحله‌ها/);
  assert.match(html, /صورتی = بازرتبه‌بندی بالا آورده/);
  assert.match(html, /تکه 4/);
  // Files and the text that was selected.
  assert.match(html, /اسناد و متن تکه‌های انتخاب‌شده/);
  assert.match(html, /فیزیک ۱/);
  assert.match(html, /هندسه ۲/);
  // The page marker survives shortening, so the book's page is not confused
  // with the book's own text chunks.
  assert.match(html, /فیزیک ۱ ریاضی خیلی سبز · ص ۴۰/);
  assert.match(html, /منبع ۱/);
  assert.match(html, /بهترین رتبه ۱/);
  assert.doesNotMatch(html, /undefined/);
});

test('trace view reports a failed run with its reason and no stage rows', async () => {
  const {TraceView} = await vite.ssrLoadModule('/src/components/RagInspector.tsx');
  const html = renderToStaticMarkup(React.createElement(TraceView, {trace:{
    id:'err', kind:'chat', kind_label:'گفتگوی کاربر', title:'خطا', question:'خطا',
    user_id:1, created_at:1760000000, duration_ms:12, status:'error',
    error:'ZeroDivisionError: division by zero', summary:{}, stages:[], total_stage_ms:0,
  }}));
  assert.match(html, /role="alert"/);
  assert.match(html, /ZeroDivisionError/);
  assert.match(html, /خطا/);
  assert.match(html, /این اجرا هنوز مرحله‌ای ثبت نکرده است/);
});
