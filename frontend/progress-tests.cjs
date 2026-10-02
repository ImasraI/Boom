const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function harness(fetch = async () => ({ ok: true })) {
  const values = new Map();
  const localStorage = { getItem: k => values.get(k) ?? null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k) };
  const modules = {};
  function load(name) {
    if (name === './api') return { apiUrl: p => p, authHeaders: token => ({ Authorization: `Bearer ${token}` }) };
    if (modules[name]) return modules[name];
    const exports = {};
    modules[name] = exports;
    const source = fs.readFileSync(path.join(__dirname, 'src', name + '.ts'), 'utf8');
    const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
    vm.runInNewContext(output, { exports, require: load, localStorage, atob, fetch, console, Map, Promise });
    return exports;
  }
  const token = id => `header.${Buffer.from(JSON.stringify({sub:id})).toString('base64url')}.signature`;
  const login = id => localStorage.setItem('boom-token', token(id));
  return { load, localStorage, login, token };
}
const update = status => ({client_ref:'one', date:'2026-09-28', subject:'math', topic:'limits', task_type:'study', planned_minutes:60, actual_minutes:status === 'completed' ? 60 : 0, status});

test('account caches isolate two students and late writes stay with original account', () => {
  const h = harness(); h.login('one');
  const storage = h.load('./accountStorage');
  const captured = storage.accountStorageFor();
  captured.setItem('plan', 'student one');
  h.login('two');
  assert.equal(storage.accountStorage.getItem('plan'), null);
  captured.setItem('plan', 'late response');
  storage.accountStorage.setItem('plan', 'student two');
  h.login('one'); assert.equal(storage.accountStorage.getItem('plan'), 'late response');
  h.localStorage.removeItem('boom-token');
  storage.accountStorage.setItem('plan', 'anonymous');
  assert.equal(storage.accountStorage.getItem('plan'), null);
});

test('rapid completion and undo reach server in order', async () => {
  const requests = []; let release;
  const h = harness(async (_url, args) => {
    requests.push(JSON.parse(args.body));
    if (requests.length === 1) await new Promise(resolve => { release = resolve; });
    return {ok:true};
  });
  h.login('one'); const sync = h.load('./progressSync');
  sync.queueProgress(update('completed'));
  await new Promise(setImmediate);
  sync.queueProgress(update('planned'));
  assert.equal(requests.length, 1);
  release(); await sync.flushProgress();
  assert.deepEqual(requests.map(r => r.status), ['completed', 'planned']);
  assert.equal(h.load('./accountStorage').accountStorage.getItem('study-progress-outbox'), '{}');
});

test('failed progress remains queued and successful retry removes it', async () => {
  let ok = false;
  const h = harness(async () => ({ok})); h.login('one');
  const sync = h.load('./progressSync'); sync.queueProgress(update('completed'));
  assert.equal(await sync.flushProgress(), false);
  assert.match(h.load('./accountStorage').accountStorage.getItem('study-progress-outbox'), /completed/);
  ok = true; assert.equal(await sync.flushProgress(), true);
  assert.equal(h.load('./accountStorage').accountStorage.getItem('study-progress-outbox'), '{}');
});

test('queued progress retains original authentication after switching accounts', async () => {
  const requests = [];
  const h = harness(async (_url,args) => { requests.push(args.headers.Authorization); return {ok:true}; });
  h.login('one'); const sync = h.load('./progressSync');
  sync.queueProgress(update('completed')); h.login('two');
  await new Promise(setImmediate);
  assert.deepEqual(requests, [`Bearer ${h.token('one')}`]);
  assert.equal(h.load('./accountStorage').accountStorage.getItem('study-progress-outbox'), null);
});
