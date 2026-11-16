import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
test.after(async () => { await vite.close(); });
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const views = await vite.ssrLoadModule('/src/components/tournament/TournamentViews.tsx');
const { TournamentAnswerQueue } = await vite.ssrLoadModule('/src/components/tournament/answerSync.ts');
const { loadTournamentDraft } = await vite.ssrLoadModule('/src/components/tournament/TournamentGame.tsx');
const player = (id, name) => ({ id, name });
const match = (id, stage = 'league', slot = 1) => ({ id, round_id: `${stage}-1`, stage, slot, player_a: player(1, 'بازیکن الف'), player_b: player(2, 'بازیکن ب'), score_a: null, score_b: null, winner_id: null, status: 'scheduled' });
const round = (stage, matches, status = 'scheduled') => ({ id: `${stage}-1`, number: 1, stage, label: stage === 'league' ? 'دور اول لیگ' : stage, starts_at: '2026-11-16T14:30:00Z', ends_at: '2026-11-16T14:45:00Z', status, matches });
const blankSession = { tournament_id: 1, match_id: 'league-1-1', title: 'مسابقهٔ آزمایشی', started_at: '2026-11-16T14:30:00Z', deadline_at: '2026-11-16T14:45:00Z', server_now: '2026-11-16T14:30:00Z', submitted: false, score: null, answers_revision: 2, saved_answers: { q1: 0 }, questions: [{ id: 'q1', text: 'دو به علاوهٔ دو؟', options: ['۴', '۵', '۶', '۷'], subject: 'ریاضی', topic: 'جمع' }, { id: 'q2', text: 'سه به علاوهٔ سه؟', options: ['۶', '۷', '۸', '۹'], subject: 'ریاضی', topic: 'جمع' }] };

test('public tournament page renders during loading without browser storage or an enrolled account', async () => {
  const { default: Tournament } = await vite.ssrLoadModule('/src/pages/Tournament.tsx');
  const html = render(Tournament, { nav() {}, userData: null });
  assert.match(html, /تورنومنت/);
  assert.match(html, /در حال دریافت تورنومنت‌ها/);
  assert.match(html, /disabled="">ثبت‌نام به‌زودی/);
  assert.doesNotMatch(html, /پرداخت ورودی|شماره کارت|برنده شدی/);
});

test('no-event preview is honest and keeps league rules immediately after the empty standings table', async () => {
  const { TournamentContent } = await vite.ssrLoadModule('/src/pages/Tournament.tsx');
  const html = render(TournamentContent, { event: null, me: null, authenticated: false, onStart() {}, onLogin() {}, onRetry() {} });
  assert.match(html, /پیش‌نمایش ساختار تورنومنت/);
  assert.match(html, /جدول هنوز بازیکنی ندارد/);
  assert.match(html, /مرحلهٔ حذفی/);
  assert.match(html, /جدول و نمودارها برای همه باز است/);
  assert.ok(html.indexOf('</table>') < html.indexOf('قوانین لیگ و ترتیب هم‌امتیازی'));
  assert.match(html, /برد ۳ امتیاز، مساوی ۱ امتیاز و باخت صفر/);
  assert.match(html, /منفی ۱۰۰/);
  assert.match(html, /حداکثر تا ۳ دقیقه/);
  assert.doesNotMatch(html, /بازیکن الف|بازیکن ب|احمد|محمد|نتیجهٔ ساختگی/);
});

test('standings show server order, full cumulative percentages, unresolved ties and escaped player names', () => {
  const html = render(views.Standings, { myPlayerId: 2, playoffSize: 4, rows: [
    { rank: 1, player_id: 2, name: '<script>alert(1)</script>', played: 5, wins: 5, draws: 0, losses: 0, points: 15, buchholz: 30, score_percent: 500, tied: true },
    { rank: 5, player_id: 1, name: 'بازیکن دوم', played: 5, wins: 1, draws: 0, losses: 4, points: 3, buchholz: 25, score_percent: -33.3, tied: false },
  ] });
  assert.match(html, /۵۰۰٪/);
  assert.match(html, /مجموع درصد دورها/);
  assert.match(html, /هم‌امتیاز/);
  assert.match(html, /&lt;script&gt;alert/);
  assert.doesNotMatch(html, /<script>/);
  assert.equal((html.match(/tn-rank-qualified/g) || []).length, 1);
  assert.ok(html.indexOf('alert') < html.indexOf('بازیکن دوم'));
});

test('league visualization selects the active round and shows its real pairings and packet size', () => {
  const oldRound = round('league', [], 'completed');
  const currentRound = { ...round('league', [match('live-match')], 'active'), id: 'league-2', number: 2, label: 'دور دوم لیگ', question_count: 12 };
  const html = render(views.LeagueDiagram, { rounds: [oldRound, currentRound], leagueRounds: 5, capacity: 32 });
  assert.match(html, /aria-selected="true"[^>]*aria-controls="league-round-panel"[^>]*id="league-round-tab-1"/);
  assert.match(html, /بازیکن الف/);
  assert.match(html, /بازیکن ب/);
  assert.match(html, /۱۲ سؤال/);
  assert.match(html, /دور دوم لیگ/);
});

test('eight-player knockout has actual connecting paths and reserved seed slots without invented players', () => {
  const html = render(views.KnockoutBracket, { rounds: [], playoffSize: 8, awaitingTiebreak: true });
  assert.equal((html.match(/class="tn-match tn-match-compact/g) || []).length, 8);
  assert.match(html, /<svg[^>]*class="tn-bracket-lines"/);
  assert.match(html, /<path d="M240 86/);
  assert.match(html, /رتبهٔ ۱ لیگ/);
  assert.match(html, /رتبهٔ ۸ لیگ/);
  assert.match(html, /رده‌بندی · جایگاه سوم/);
  assert.match(html, /ترتیب صعود در انتظار رفع تساوی/);
  assert.doesNotMatch(html, /<img|بازیکن الف/);
});

test('knockout uses actual result names and four-player events omit quarterfinals', () => {
  const finalMatch = { ...match('final-1', 'final'), player_a: player(5, 'برندهٔ واقعی'), player_b: player(7, 'رقیب نهایی'), score_a: 80, score_b: 70, winner_id: 5, status: 'completed' };
  const html = render(views.KnockoutBracket, { rounds: [round('final', [finalMatch])], playoffSize: 4 });
  assert.equal((html.match(/class="tn-match tn-match-compact/g) || []).length, 4);
  assert.doesNotMatch(html, /یک‌چهارم نهایی|رتبهٔ ۸ لیگ/);
  assert.match(html, /برندهٔ واقعی/);
  assert.match(html, /رقیب نهایی/);
  assert.match(html, /tn-match-winner/);
  assert.match(html, /۸۰٪/);
});

test('own match desk only exposes start when server eligibility allows it and shows official start time', () => {
  const renderDesk = ready => render(views.MyTournamentMatches, { matches: [{ ...match('league-1-1'), starts_at: '2026-11-16T14:30:00Z', can_start: ready, can_resume: false, has_submitted: false, reason: ready ? null : 'هنوز زمان بازی نرسیده است', deadline_at: '2026-11-16T14:45:00Z' }], playerId: 1, authenticated: true, onStart() {}, onLogin() {}, onRetry() {} });
  assert.match(renderDesk(true), /شروع بازی<\/button>|شروع بازی<span/);
  assert.match(renderDesk(true), /شروع بازی:/);
  assert.match(renderDesk(false), /disabled=""[^>]*aria-label="شروع بازی با بازیکن ب"/);
  assert.match(renderDesk(false), /هنوز زمان بازی نرسیده است/);
  const publicDesk = render(views.MyTournamentMatches, { matches: [], playerId: null, authenticated: false, onStart() {}, onLogin() {}, onRetry() {} });
  assert.match(publicDesk, /ورود به حساب/);
  assert.doesNotMatch(publicDesk, /شروع بازی/);
});

test('autosave serializes rapid changes and a late acknowledgement cannot erase the newer selection', async () => {
  const writes = [];
  let release;
  const queue = new TournamentAnswerQueue({ revision: 0, savedRevision: 0, answers: {}, isActive: () => true, onState() {}, save: async (answers, revision) => {
    writes.push({ answers: { ...answers }, revision });
    if (revision === 1) await new Promise(resolve => { release = resolve; });
    return { revision };
  } });
  queue.stage({ q1: 0 });
  const saving = queue.flush();
  queue.stage({ q1: 3, q2: 1 });
  assert.equal(queue.flush(), saving);
  release();
  await saving;
  assert.deepEqual(writes, [{ answers: { q1: 0 }, revision: 1 }, { answers: { q1: 3, q2: 1 }, revision: 2 }]);
  assert.equal(queue.savedRevision, 2);
  assert.equal(queue.hasPending, false);
});

test('the personal desk puts a playable match before old results and future fixtures', () => {
  const base = match('base');
  const html = render(views.MyTournamentMatches, {
    playerId: 1, authenticated: true, onStart() {}, onLogin() {}, onRetry() {},
    matches: [
      { ...base, id: 'old', player_b: player(2, 'حریف گذشته'), status: 'completed', has_submitted: true, can_start: false, can_resume: false },
      { ...base, id: 'next', player_b: player(3, 'حریف آینده'), has_submitted: false, can_start: false, can_resume: false },
      { ...base, id: 'now', player_b: player(4, 'حریف فعلی'), has_submitted: false, can_start: true, can_resume: false },
    ],
  });
  assert.ok(html.indexOf('حریف فعلی') < html.indexOf('حریف آینده'));
  assert.ok(html.indexOf('حریف آینده') < html.indexOf('حریف گذشته'));
  assert.match(html, /آمادهٔ شروع/);
});

test('failed autosave retains the newest draft and retry sends that draft rather than an older snapshot', async () => {
  const writes = [];
  let reject;
  let fail = true;
  const queue = new TournamentAnswerQueue({ revision: 0, savedRevision: 0, answers: {}, isActive: () => true, onState() {}, save: async (answers, revision) => {
    writes.push({ answers, revision });
    if (fail) await new Promise((resolve, failure) => { reject = failure; });
    return { revision };
  } });
  queue.stage({ q1: 0 }); const saving = queue.flush();
  queue.stage({ q1: 2 }); reject(new Error('offline'));
  await assert.rejects(saving, /offline/);
  assert.equal(queue.savedRevision, 0);
  fail = false; await queue.flush();
  assert.equal(writes[1].revision, 2);
  assert.deepEqual(writes[1].answers, { q1: 2 });
  assert.equal(queue.savedRevision, 2);
});

test('autosave rejects work after identity changes and cancels requests without acknowledging an unsaved answer', async () => {
  let active = true;
  let finish;
  const queue = new TournamentAnswerQueue({ revision: 0, savedRevision: 0, answers: {}, isActive: () => active, onState() {}, save: async (answers, revision) => {
    await new Promise(resolve => { finish = resolve; });
    return { revision };
  } });
  queue.stage({ q1: 2 }); const saving = queue.flush();
  active = false; queue.cancel(); finish(); await saving;
  assert.equal(queue.savedRevision, 0);
  await assert.rejects(queue.flush(), /حساب یا بازی تغییر/);
});

test('resume prefers the server snapshot unless this exact account and match have a newer local draft', () => {
  const oldStorage = globalThis.localStorage;
  const values = new Map();
  globalThis.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
  try {
    const token = `header.${Buffer.from(JSON.stringify({ sub: 5 })).toString('base64url')}.signature`;
    const key = 'boom-account:5:tournament-draft:v2:1:league-1-1';
    values.set(key, JSON.stringify({ revision: 1, answers: { q1: 3 } }));
    assert.deepEqual(loadTournamentDraft(blankSession, token), { revision: 2, answers: { q1: 0 } });
    values.set(key, JSON.stringify({ revision: 3, answers: { q1: 3, q2: 0, bogus: 2 } }));
    assert.deepEqual(loadTournamentDraft(blankSession, token), { revision: 3, answers: { q1: 3, q2: 0 } });
    const otherToken = `header.${Buffer.from(JSON.stringify({ sub: 6 })).toString('base64url')}.signature`;
    assert.deepEqual(loadTournamentDraft(blankSession, otherToken), { revision: 2, answers: { q1: 0 } });
    assert.deepEqual(loadTournamentDraft({ ...blankSession, match_id: 'league-2-1' }, token), { revision: 2, answers: { q1: 0 } });
  } finally { globalThis.localStorage = oldStorage; }
});
