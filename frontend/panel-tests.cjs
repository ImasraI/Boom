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
