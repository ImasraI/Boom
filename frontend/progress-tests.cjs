const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function harness(fetch = async () => ({ ok: true })) {
  const values = new Map();
  const localStorage = { getItem: k => values.get(k) ?? null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k),
    key: i => [...values.keys()][i] ?? null, get length() { return values.size; } };
  const modules = {};
  function load(name) {
    if (name === './api') return { apiUrl: p => p, authHeaders: token => ({ Authorization: `Bearer ${token}` }) };
    if (modules[name]) return modules[name];
    const exports = {};
    modules[name] = exports;
    const source = fs.readFileSync(path.join(__dirname, 'src', name + '.ts'), 'utf8');
    const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
    vm.runInNewContext(output, { exports, require: load, localStorage, atob, fetch, console, Map, Promise, crypto: require('node:crypto'),
      window: { dispatchEvent() {} }, CustomEvent: class { constructor(type) { this.type = type; } } });
    return exports;
  }
  const token = id => `header.${Buffer.from(JSON.stringify({sub:id})).toString('base64url')}.signature`;
  const login = id => localStorage.setItem('boom-token', token(id));
  return { load, localStorage, login, token };
}
const update = status => ({client_ref:'one', date:'2026-09-28', subject:'math', topic:'limits', task_type:'study', planned_minutes:60, actual_minutes:status === 'completed' ? 60 : 0, status});

test('browser-only signup preferences initialize an empty server profile once', async () => {
  const calls = [];
  const h = harness(async (url, options = {}) => {
    calls.push(options);
    const profile = options.method === 'PATCH'
      ? { ...JSON.parse(options.body), version: 1 }
      : { version: 0, major: null, grade: null, study_hours: null, test_exams: [] };
    return { ok: true, status: 200, json: async () => ({ profile }) };
  });
  h.login(1);
  const sync = h.load('./profileSync');
  const base = { major: 'ریاضی', grade: 'دوازدهم', studyHours: '8', testExams: ['ماز'] };
  const saved = await sync.hydrateServerProfile(base);
  assert.equal(saved.study_hours, '8');
  assert.equal(JSON.parse(calls[1].body).version, 0);
  assert.deepEqual(JSON.parse(calls[1].body).test_exams, ['ماز']);
});

test('existing server preferences win and switching accounts prevents migration', async () => {
  let writes = 0;
  const h = harness(async (url, options = {}) => {
    if (options.method === 'PATCH') writes++;
    return { ok: true, status: 200, json: async () => ({ profile: { version: 3, study_hours: '6' } }) };
  });
  h.login(1);
  const base = { major: 'ریاضی', grade: 'دوازدهم', studyHours: '8', testExams: [] };
  assert.equal((await h.load('./profileSync').hydrateServerProfile(base)).study_hours, '6');
  assert.equal(writes, 0);
  let release;
  const slow = harness((url, options = {}) => {
    if (options.method === 'PATCH') writes++;
    return new Promise(resolve => { release = resolve; });
  });
  slow.login(1);
  const pending = slow.load('./profileSync').hydrateServerProfile(base);
  slow.login(2);
  release({ok:true,json:async()=>({profile:{version:0}})});
  assert.equal(await pending, null);
  assert.equal(writes, 0);
});

test('profile defaults retain the signup goal and explicit rest days', () => {
  const sync = harness().load('./profileSync');
  const days = ['شنبه', 'یکشنبه', 'دوشنبه', 'سهشنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه'];
  assert.equal(sync.initialDailyHours({studyHours:'۸ ساعت'}, days)['شنبه'], 8);
  const resolved = sync.initialDailyHours({studyHours:'8', dailyHours:{'جمعه':0,'0':6,'سه شنبه':5}}, days);
  assert.equal(resolved['جمعه'], 0);
  assert.equal(resolved['دوشنبه'], 6);
  assert.equal(resolved['سهشنبه'], 5);
  assert.equal(resolved['شنبه'], 8);
});

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

test('numeric and padded JWT subjects select the same account namespace', () => {
  const h = harness(); h.login(7);
  const account = h.load('./accountStorage');
  assert.equal(account.accountId(), '7');
  account.accountStorage.setItem('plan', 'seven');
  h.login('7'); assert.equal(account.accountStorage.getItem('plan'), 'seven');
});

test('recurrence expands custom intervals, weekdays and end conditions', () => {
  const h = harness(), expand = h.load('./recurrence').expandTemplates;
  const base = {id:'series',date:'2026-10-03',startHour:9,duration:1,title:'class',type:'class'};
  const days = rule => Array.from(expand([{...base,recurrence:rule}], '2026-10-03'), b => b.day);
  assert.deepEqual(days({frequency:'daily',interval:2}), [0,2,4,6]);
  assert.deepEqual(days({frequency:'daily',interval:1,count:3}), [0,1,2]);
  assert.deepEqual(days({frequency:'daily',interval:1,until:'2026-10-05'}), [0,1,2]);
  assert.deepEqual(days({frequency:'weekly',interval:1,weekdays:[0,3]}), [0,3]);
  assert.equal(expand([{...base,recurrence:{frequency:'weekly',interval:2,weekdays:[0,3]}}], '2026-10-10').length, 0);
  const monthly = {...base,date:'2026-01-31',recurrence:{frequency:'monthly',interval:1}};
  assert.equal(expand([monthly], '2026-02-28').length, 0);
  assert.deepEqual(Array.from(expand([monthly], '2026-03-28'), b => b.day), [3]);
});

test('converting an activity to and from a repeat series changes both stores atomically', () => {
  const h = harness(); h.login('one'); const schedule = h.load('./scheduleStore');
  const week = '2026-10-03';
  const block = {id:'activity',day:0,startHour:9,duration:1,title:'class',type:'class',origin:'manual'};
  schedule.saveCalendarWeek(week,[block],[]);
  const template = {...block, day:undefined,date:week,recurrence:{frequency:'weekly',interval:1,weekdays:[0]}};
  schedule.saveCalendarWeek(week,[],[template]);
  assert.equal(schedule.loadWeekBlocks(week).length,0);
  assert.equal(schedule.staticBlocksForWeek(week).length,1);
  schedule.saveCalendarWeek(week,[block],[]);
  assert.equal(schedule.loadWeekBlocks(week)[0].id,block.id);
  assert.equal(schedule.staticBlocksForWeek(week).length,0);
});

test('calendar saves serialize rapid edits and retain the original account after logout', async () => {
  const requests = []; let release; let version = 0;
  const h = harness(async (_url,args) => {
    requests.push({auth:args.headers.Authorization, body:JSON.parse(args.body)});
    const body = JSON.parse(args.body);
    if (requests.length === 1) await new Promise(resolve => { release = resolve; });
    return {ok:true,json:async () => ({weeks:body.weeks,statics:[],version:++version})};
  });
  h.login('one'); const cache = h.load('./accountStorage').accountStorageFor();
  cache.setItem('boom-calendar-version','0');
  const sync = h.load('./calendarSync'), week = '2026-10-03';
  sync.queueCalendar({weeks:{[week]:[{id:'first'}]}});
  await new Promise(setImmediate);
  sync.queueCalendar({weeks:{[week]:[{id:'second'}]}});
  h.login('two'); release();
  assert.equal(await sync.flushCalendar(h.token('one')), true);
  assert.deepEqual(requests.map(r => r.body.version), [0,1]);
  assert.deepEqual(requests.map(r => r.auth), [`Bearer ${h.token('one')}`,`Bearer ${h.token('one')}`]);
  assert.equal(h.load('./accountStorage').accountStorage.getItem('boom-weekly-schedule:'+week), null);
  assert.equal(JSON.parse(cache.getItem('boom-weekly-schedule:'+week))[0].id, 'second');
});

test('late calendar fetch cannot populate another account and fetch wins over stale caches', async () => {
  let release;
  const h = harness(async () => { await new Promise(resolve => {release=resolve;});
    return {ok:true,json:async () => ({weeks:{'2026-10-03':[{id:'server'}]},statics:[],version:2})}; });
  h.login('one'); const sync = h.load('./calendarSync');
  const pending = sync.pullCalendar();
  h.login('two'); release(); assert.equal(await pending, true);
  assert.equal(h.load('./accountStorage').accountStorage.getItem('boom-weekly-schedule:2026-10-03'), null);
  h.login('one'); assert.equal(JSON.parse(h.load('./accountStorage').accountStorage.getItem('boom-weekly-schedule:2026-10-03'))[0].id, 'server');
});

test('a stale calendar write preserves the local outbox for recovery', async () => {
  const h = harness(async () => ({ok:false,status:409})); h.login('one');
  const cache = h.load('./accountStorage').accountStorageFor(); cache.setItem('boom-calendar-version','1');
  const sync = h.load('./calendarSync'); sync.queueCalendar({weeks:{'2026-10-03':[{id:'mine'}]}});
  assert.equal(await sync.flushCalendar(), false);
  assert.match(cache.getItem('boom-calendar-outbox'), /mine/);
  assert.match(sync.calendarSyncError(), /دستگاه دیگری/);
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

test('weekly schedule rejects overlaps without overwriting the saved plan', () => {
  const h = harness(); h.login('one');
  const schedule = h.load('./scheduleStore');
  const week = '2026-10-03';
  schedule.saveStaticTemplates([{day:0,startHour:9,duration:1,title:'class',type:'class'}]);
  const block = {day:0,startHour:10,duration:1.5,title:'chemistry',type:'test',resource:'book',question_start:30,question_end:49};
  schedule.saveWeekBlocks(week,[block]);
  assert.throws(() => schedule.saveWeekBlocks(week,[{...block,startHour:9.5}]), /تداخل/);
  assert.throws(() => schedule.saveWeekBlocks(week,[block,{...block,startHour:11}]), /تداخل/);
  assert.equal(schedule.loadWeekBlocks(week)[0].startHour,10);
  assert.equal(schedule.loadWeekBlocks(week)[0].question_start,30);
  assert.equal(schedule.hasScheduleOverlap([block,{...block,startHour:11.5}]),false);
});

test('annual commitments are included only in the week where they recur', () => {
  const h = harness(); h.login('one');
  const schedule = h.load('./scheduleStore');
  schedule.saveStaticTemplates([{date:'2025-12-31',startHour:9,duration:1,title:'annual',type:'class'}]);
  assert.equal(schedule.staticBlocksForWeek('2026-12-26').length,1);
  assert.equal(schedule.staticBlocksForWeek('2026-10-03').length,0);
});

test('postponing practice finds a free slot and keeps its book assignment', () => {
  const h = harness(); h.login('one');
  const schedule = h.load('./scheduleStore');
  const tasks = h.load('./homeTasks');
  const date = '2026-10-03';
  const week = schedule.getWeekISO(schedule.fromISO(date));
  const block = {id:'chem',day:0,startHour:9,duration:1,title:'practice',type:'test',resource:'book',question_start:30,question_end:49};
  schedule.saveWeekBlocks(week,[block,{...block,id:'other',day:1,duration:2,title:'physics'}]);
  schedule.saveStaticTemplates([{day:1,startHour:11,duration:1,title:'class',type:'class'}]);
  tasks.postponeToTomorrow(date,tasks.homeTasksForDate(date)[0]);
  const moved = schedule.loadWeekBlocks(week).find(row => row.day === 1 && row.origin === 'manual');
  assert.ok(moved.id && moved.id !== block.id);
  assert.equal(moved.startHour,12);
  assert.equal(moved.question_start,30);
  assert.equal(schedule.hasScheduleOverlap(schedule.loadWeekBlocks(week),schedule.staticBlocksForWeek(week)),false);
});

test('completion reports preserve practice ranges and update the same task record', async () => {
  const requests=[];
  const h=harness(async (_url,args)=>{requests.push(JSON.parse(args.body));return {ok:true};}); h.login('one');
  const schedule=h.load('./scheduleStore'); const tasks=h.load('./homeTasks');
  schedule.saveWeekBlocks('2026-10-03',[{id:'chem',day:0,startHour:9,duration:1,title:'practice',type:'test',subject:'chemistry',resource:'book',question_start:30,question_end:49}]);
  const task=tasks.homeTasksForDate('2026-10-03')[0];
  tasks.reportTaskActual('2026-10-03',task,{status:'partially_completed',actualMinutes:30});
  await h.load('./progressSync').flushProgress();
  tasks.toggleDone('2026-10-03',task,true);
  await h.load('./progressSync').flushProgress();
  assert.equal(requests[0].client_ref,requests[1].client_ref);
  assert.equal(requests[0].resource,'book');
  assert.equal(requests[1].question_start,30);
});
