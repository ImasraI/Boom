/** Offline visual fixture: no authentication, provider calls or student data. */
import { writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const stage = (name, label, meta = {}, rows = [], ms = 12) => ({name, label, meta, rows, ms, columns:[
  {key:'rank',label:'رتبه'}, {key:'doc',label:'سند'}, {key:'chunk',label:'تکه'},
  {key:'score',label:'امتیاز'}, {key:'preview',label:'متن نمونه'}], text:{}, command:''});
const books = [
  {id:'synthetic-math-001',doc:'کتاب آزمایشی ریاضی.pdf',chunk:8,rank:1,score:.87,preview:'تابع: به هر عضو دامنه دقیقاً یک مقدار نسبت داده می‌شود.'},
  {id:'synthetic-math-002',doc:'کتاب آزمایشی ریاضی.pdf',chunk:12,rank:2,score:.79,preview:'ترکیب دو تابع و بررسی دامنهٔ تابع مرکب.'},
  {id:'synthetic-geometry-001',doc:'کتاب آزمایشی هندسه.pdf',chunk:3,rank:3,score:.54,preview:'تقارن مرکزی و انتقال در صفحه.'},
];
const bank = [{id:'synthetic-question-001',doc:'بانک سؤال آزمایشی::p24',chunk:1,rank:1,score:.9,preview:'سؤال نمونهٔ تابع؛ متن صرفاً برای بررسی چیدمان است.'}];
const trace = {
  id:'offline-rag-preview',kind:'playground',kind_label:'بررسی دستی · دادهٔ ساختگی',question:'دامنهٔ تابع مرکب را از کدام بخش کتاب بخوانم؟',
  user_id:null,created_at:1791912600,duration_ms:1834,total_stage_ms:2540,status:'ok',error:'',
  summary:{top_k:4,chunks:4,rerank:true,question_bank:true,images:false},
  stages:[
    stage('query_rewrite','بازنویسی پرسش',{original:'دامنهٔ تابع مرکب را از کدام بخش کتاب بخوانم؟',rewritten:'دامنه و ترکیب توابع',model:'مدل نمونه'},[],82),
    stage('embed_query','بردارسازی پرسش',{provider:'gemini',model:'gemini-embedding',dimensions:1024,input:'دامنه و ترکیب توابع'},[],144),
    stage('books · semantic_search','جست‌وجوی برداری',{collection:'shared-books-demo',hits:80,output_count:80,candidates_requested:100},books,72),
    stage('books · lexical_search','BM25 و واژه‌ها',{indexed_chunks:1909,hits:45,output_count:45,query_tokens:['دامنه','ترکیب','تابع']},books,18),
    stage('books · rrf_fusion','ادغام RRF',{output_count:20,semantic_hits:80,lexical_hits:45,rrf_k:60},books,3),
    stage('books · rerank','بازرتبه‌بندی',{output_count:3,kept:3,candidate_pairs:20,model:'bge-reranker'},books.map((r,i)=>({...r,move:i===0?2:0})),962),
    stage('qbank_search','منابع بانک سؤال',{hits:1,output_count:1},bank,400),
    stage('qbank · embed_query','بردارسازی بانک سؤال',{provider:'gemini',model:'gemini-embedding',dimensions:1024,input:'دامنه و ترکیب توابع'},[],122),
    stage('qbank · semantic_search','بازیابی برداری سؤال',{collection:'questions-demo',hits:12,output_count:12},bank,24),
    stage('qbank · lexical_search','جست‌وجوی متن سؤال',{hits:8,output_count:8},bank,8),
    stage('qbank · rrf_fusion','ادغام بانک سؤال',{output_count:4},bank,2),
    stage('qbank · rerank','بازرتبه‌بندی سؤال',{output_count:1,kept:1,model:'bge-reranker'},bank,244),
    stage('retrieval_assembly','بافت نهایی مدل',{output_count:4,final_chunks:4,from_question_bank:1,from_books:3,deduplicated_chunks:0},[...bank,...books].map((r,i)=>({...r,rank:i+1})),1),
  ],
};
const vite = await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
try {
  const {TraceView} = await vite.ssrLoadModule('/src/components/RagInspector.tsx');
  const html = renderToStaticMarkup(React.createElement(TraceView,{trace}));
  const output = resolve(process.argv[2] ?? 'tmp/rag-visual-preview.html');
  await mkdir(dirname(output),{recursive:true});
  await writeFile(output,`<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>بررسی آفلاین RAG</title><body style="background:var(--bg,#101719);color:var(--text,#e6f2ef);margin:0"><main class="rag-inspector" style="max-width:1180px;padding:24px;margin:auto"><p style="color:var(--muted);margin-bottom:20px;font-size:12px">نمونهٔ آفلاین و ساختگی برای ارزیابی ظاهر؛ هیچ دادهٔ کاربر یا فراخوانی مدل در این صفحه نیست.</p><div id="rag-fixture">${html}</div></main><script type="module">import '/src/index.css';import '/src/components/rag-inspector.css';import React from 'react';import {hydrateRoot} from 'react-dom/client';import {TraceView} from '/src/components/RagInspector.tsx';hydrateRoot(document.getElementById('rag-fixture'),React.createElement(TraceView,{trace:${JSON.stringify(trace).replaceAll('<', '\\u003c')}}));</script></body></html>`,'utf8');
  process.stdout.write(output+'\n');
} finally {await vite.close();}
