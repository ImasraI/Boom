const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(name, extra = {}) {
  const values = new Map();
  let reloads = 0;
  const sessionStorage = {getItem:k=>values.get(k) ?? null, setItem:(k,v)=>values.set(k,v), removeItem:k=>values.delete(k)};
  const output = ts.transpileModule(fs.readFileSync(path.join(__dirname, 'src', name+'.ts'), 'utf8').replaceAll('import.meta.env', '({})'), {
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
  }).outputText;
  const exports = {};
  vm.runInNewContext(output, {exports, Error, Headers, AbortController, setTimeout, clearTimeout,
    localStorage:{getItem:()=>null}, sessionStorage, navigator:{onLine:true},
    window:{location:{reload(){reloads++}}}, ...extra});
  return {exports, values, reloads:()=>reloads};
}

test('evaluation is absent from every navigation panel and cannot resume', () => {
  const {exports:nav} = load('navConfig');
  assert.equal(nav.panelOf('evaluation'), null);
  assert.ok(Object.values(nav.PANELS).every(panel => panel.items.every(item => item.screen !== 'evaluation')));
  const recovery = load('pageRecovery');
  recovery.values.set('boom-page-resume', 'evaluation');
  assert.equal(recovery.exports.consumeResumePage(), null);
});

test('calendar colors distinguish mocks, subject practice and old saved classes', () => {
  const {exports:colors} = load('scheduleColors');
  assert.equal(colors.scheduleColor({type:'class',color:'#0000ff'}),colors.CLASS_COLOR);
  assert.equal(colors.scheduleColor({type:'test',source_ref:'weekly-mock',color:'#9B7AAD'}),colors.MOCK_COLOR);
  assert.equal(colors.scheduleColor({type:'test',subject:'ریاضی'}),colors.PRACTICE_COLOR);
  assert.equal(colors.scheduleColor({type:'study',task_type:'practice'}),colors.PRACTICE_COLOR);
  assert.equal(colors.scheduleActivity({type:'study',subject:'آزمون',source_ref:'weekly-correction'}),'other');
  assert.notEqual(colors.MOCK_COLOR,colors.PRACTICE_COLOR);
});

test('mock generation polls until verified results are ready using short requests', async () => {
  const calls = [];
  const replies = [{job_id:'own-job',status:'running'}, {job_id:'own-job',status:'running'},
    {job_id:'own-job',status:'ready',result:{mock_id:42,total_questions:3}}];
  const h = load('mockGeneration', {
    DOMException, require:()=>({apiJson:async (...args)=>{calls.push(args); return replies.shift()}}),
    setTimeout:callback=>setTimeout(callback,1),
  });
  const controller = new AbortController();
  const result = await h.exports.requestMockGeneration({mode:'practice'},controller.signal);
  assert.equal(result.mock_id,42);
  assert.equal(calls.length,3);
  assert.equal(calls[0][0],'/api/mocks/generation');
  assert.equal(JSON.parse(calls[0][1].body).mode,'practice');
  assert.equal(calls[1][0],'/api/mocks/generation/own-job');
  assert.ok(calls.every(call=>call[1].signal===controller.signal));
});

test('leaving mock generation aborts polling without requesting another booklet', async () => {
  const controller = new AbortController();
  let calls = 0;
  const h = load('mockGeneration', {
    DOMException, require:()=>({apiJson:async ()=>{
      calls++; queueMicrotask(()=>controller.abort());
      return {job_id:'own-job',status:'running'};
    }}),
  });
  await assert.rejects(h.exports.requestMockGeneration({},controller.signal),{name:'AbortError'});
  assert.equal(calls,1);
});

test('mock status preserves provider errors and rejects a missing result', async () => {
  const quota = new Error('verification quota exhausted');
  let calls = 0;
  const h = load('mockGeneration', {
    DOMException, require:()=>({apiJson:async ()=>{
      if(calls++) throw quota;
      return {job_id:'own-job',status:'running'};
    }}),
    setTimeout:callback=>setTimeout(callback,1),
  });
  await assert.rejects(h.exports.requestMockGeneration({},new AbortController().signal),error=>error===quota);
  const invalid = load('mockGeneration', {
    DOMException, require:()=>({apiJson:async ()=>({job_id:'own-job',status:'ready'})}),
  });
  await assert.rejects(invalid.exports.requestMockGeneration({},new AbortController().signal),/دفترچه آماده نشد/);
});

test('a missing deployed page reloads once and restores its selected panel', () => {
  const h = load('pageRecovery');
  const e = new TypeError('Failed to fetch dynamically imported module: /assets/Mock-old.js');
  assert.equal(h.exports.recoverPageDownload('mock', e), true);
  assert.equal(h.reloads(), 1);
  assert.equal(h.exports.consumeResumePage(), 'mock');
  assert.equal(h.exports.consumeResumePage(), null);
  assert.equal(h.exports.recoverPageDownload('mock', e), false);
  assert.equal(h.reloads(), 1);
});

test('ordinary render errors and offline failures do not cause automatic reloads', () => {
  const h = load('pageRecovery');
  assert.equal(h.exports.recoverPageDownload('arena', new Error('Cannot read properties of undefined')), false);
  const offline = load('pageRecovery', {navigator:{onLine:false}});
  assert.equal(offline.exports.recoverPageDownload('arena', new Error('Importing a module script failed.')), false);
  assert.equal(offline.reloads(), 0);
  h.values.set('boom-page-resume', 'untrusted-page');
  assert.equal(h.exports.consumeResumePage(), null);
});

test('page recovery handles browsers that disable session storage', () => {
  const h = load('pageRecovery', {sessionStorage:{getItem(){throw new Error('denied')}}});
  assert.equal(h.exports.recoverPageDownload('arena', new Error('Unable to preload CSS for /assets/old.css')), false);
  assert.equal(h.exports.consumeResumePage(), null);
  assert.equal(h.reloads(), 0);
});

test('panel API reads preserve useful quota errors without clearing login', async () => {
  const h = load('api', {fetch:async()=>({ok:false,status:503,json:async()=>({detail:{code:'provider_daily_quota',message:'سهمیه تمام شده'}})})});
  await assert.rejects(h.exports.apiJson('/api/mocks/generate'), /سهمیه تمام شده/);
});

test('panel API preserves the pool-empty error code for archive selection', async () => {
  const h = load('api', {fetch:async()=>({ok:false,status:409,json:async()=>({detail:{code:'pool_empty',message:'آماده نیست'}})})});
  await assert.rejects(h.exports.apiJson('/api/mocks/generate'), error =>
    error instanceof h.exports.ApiError && error.code === 'pool_empty' && error.status === 409);
});

test('previous Maze compatibility offers only an available previous scope on older APIs', async () => {
  class ApiError extends Error { constructor(status) { super('old API'); this.status=status } }
  const calls=[];
  const weekly={fallback:true,stock_available:true,date:'2026-10-23',topics:{'ریاضی':['تابع']}};
  const h=load('previousMaze',{URLSearchParams,require:()=>({ApiError,apiJson:async(path)=>{
    calls.push(path);if(path.startsWith('/api/mocks/previous-maze'))throw new ApiError(404);
    return {weekly};
  }})});
  const items=await h.exports.fetchPreviousMaze({major:'ریاضی فیزیک',grade:'دوازدهم'});
  assert.equal(items.length,1);assert.equal(items[0].exam_date,'2026-10-23');
  assert.equal(items[0].legacy,true);assert.equal(calls.length,2);
  weekly.fallback=false;
  assert.equal((await h.exports.fetchPreviousMaze({})).length,0);
});

test('previous Maze compatibility retains ten-question count, topic filters and stock-only selection', async () => {
  let sent;
  const h=load('previousMaze',{require:()=>({requestMockGeneration:async(payload)=>{
    sent=payload;return {mock_id:42,total_questions:10};
  }})});
  const item={legacy:true,title:'تمرین ماز قبلی',topics:{'شیمی':['مولکول‌ها']}};
  const result=await h.exports.openPreviousMaze(item,{grade:'دوازدهم'},new AbortController().signal);
  assert.equal(sent.total_questions,10);assert.equal(sent.stock_only,true);
  assert.equal(sent.mode,'general');assert.equal(sent.difficulty,'konkur');
  assert.deepEqual(Array.from(sent.topics),['مولکول‌ها','مولکول ها','مولکولها']);
  assert.equal(result.mock_id,42);assert.equal(result.title,item.title);
});

test('a stuck panel request times out with an actionable message', async () => {
  const h = load('api', {fetch:(_, {signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('aborted'))))});
  await assert.rejects(h.exports.apiJson('/api/arena/me', {}, 10), /پاسخ سرور دیر رسید/);
});

test('generation cancellation aborts the request without changing accounts', async () => {
  const h = load('api', {fetch:(_, {signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('aborted'))))});
  const controller = new AbortController();
  const request = h.exports.apiJson('/api/mocks/generate', {signal:controller.signal});
  controller.abort();
  await assert.rejects(request, /aborted/);
});
