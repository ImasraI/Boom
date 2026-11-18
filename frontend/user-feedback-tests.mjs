import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

const values=new Map();
const previousStorage=globalThis.localStorage;
globalThis.localStorage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value)),removeItem:key=>values.delete(key)};
const vite=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
test.after(async()=>{await vite.close();if(previousStorage===undefined)delete globalThis.localStorage;else globalThis.localStorage=previousStorage;});

test('login exposes a named password recovery entry',async()=>{
  const {default:Login}=await vite.ssrLoadModule('/src/pages/Login.tsx');
  const html=renderToStaticMarkup(React.createElement(Login,{nav(){},onLogin(){}}));
  assert.match(html,/رمز عبورم را فراموش کرده‌ام/);
});

test('expired Arena requests clear the active session and preserve a later sign-in', async () => {
  const {apiJson, SESSION_EXPIRED, SESSION_EXPIRED_MESSAGE} = await vite.ssrLoadModule('/src/api.ts');
  const previousFetch = globalThis.fetch;
  const previousWindow = globalThis.window;
  const target = new EventTarget();
  let resets = 0;
  target.addEventListener(SESSION_EXPIRED, () => resets++);
  globalThis.window = target;
  const rejected = () => new Response(JSON.stringify({detail:'Invalid token'}), {status:401});
  try {
    values.set('boom-token', 'old-session');
    let respond;
    globalThis.fetch = () => new Promise(resolve => { respond = resolve; });
    const request = apiJson('/api/arena/me');
    values.set('boom-token', 'new-session');
    respond(rejected());
    await assert.rejects(request, {message:SESSION_EXPIRED_MESSAGE, status:401});
    assert.equal(values.get('boom-token'), 'new-session');
    assert.equal(resets, 0);

    globalThis.fetch = async () => rejected();
    await assert.rejects(apiJson('/api/arena/filters'), {message:SESSION_EXPIRED_MESSAGE, status:401});
    assert.equal(values.has('boom-token'), false);
    assert.equal(resets, 1);
  } finally {
    values.delete('boom-token');
    globalThis.fetch = previousFetch;
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});

test('explicit password recovery starts with phone, not a new onboarding profile',async()=>{
  values.set('boom-reset-phone','9121112233');
  try{
    const {default:Signup}=await vite.ssrLoadModule('/src/pages/Signup.tsx');
    const html=renderToStaticMarkup(React.createElement(Signup,{nav(){},onComplete(){}}));
    assert.match(html,/بازیابی رمز عبور/);
    assert.match(html,/value="912 111 2233"/);
    assert.match(html,/شماره موبایلت چیه/);
    assert.doesNotMatch(html,/اسمت چیه/);
  }finally{values.delete('boom-reset-phone');}
});

test('mock entry exposes saved-answer history and an honest empty state',async()=>{
  const {default:Mock}=await vite.ssrLoadModule('/src/pages/Mock.tsx');
  const html=renderToStaticMarkup(React.createElement(Mock,{nav(){},userData:null}));
  assert.match(html,/آزمون‌های قبلی و پاسخنامه‌ها/);
  assert.match(html,/هنوز آزمونی ثبت نکرده‌ای/);
});


test('friend challenges expose entry and sharing without using the pilot code',async()=>{
  const {FriendChallengeEntry,FriendChallengeResult}=await vite.ssrLoadModule('/src/components/FriendChallenge.tsx');
  const entry=renderToStaticMarkup(React.createElement(FriendChallengeEntry,{onOpen(){}}));
  assert.match(entry,/چالش دوستانه · ورود با کد/);
  assert.match(entry,/کد شش‌کاراکتری/);
  const result=renderToStaticMarkup(React.createElement(FriendChallengeResult,{mockId:42,code:''}));
  assert.match(result,/دوستم همین دفترچه را حل کند/);
});

test('profile offers every post-verification study field and a read-only phone', async () => {
  const {default:Profile} = await vite.ssrLoadModule('/src/pages/Profile.tsx');
  const {MAJORS,GRADES,STUDY_HOURS_OPTIONS,TEST_EXAM_OPTIONS} = await vite.ssrLoadModule('/src/data.ts');
  const {normalizeSignupData} = await vite.ssrLoadModule('/src/types.ts');
  const html = renderToStaticMarkup(React.createElement(Profile, {
    nav(){},onSave(){},logout(){},toggleDark(){},dark:false,
    userData:normalizeSignupData({name:'Example',phone:'9120000011',major:MAJORS[0],grade:GRADES[0],studyHours:STUDY_HOURS_OPTIONS[0]}),
  }));
  for (const label of [...MAJORS,...GRADES,...STUDY_HOURS_OPTIONS,...TEST_EXAM_OPTIONS]) assert.ok(html.includes(label), label);
  assert.match(html, /readonly="" value="9120000011"/i);
  assert.match(html, /ارزیابی دروس/);
  assert.match(html, /تغییر ذخیره‌نشده‌ای نداری/);
});

test('profile sync roundtrips study edits, rejects failed writes and preserves login phone', async () => {
  const sync = await vite.ssrLoadModule('/src/profileSync.ts');
  const {normalizeSignupData} = await vite.ssrLoadModule('/src/types.ts');
  const previousFetch = globalThis.fetch;
  const data = normalizeSignupData({name:'Example',phone:'9120000011',major:'علوم تجربی',grade:'یازدهم',studyHours:'۴ تا ۶ ساعت',testExams:['ماز'],city:'example',school:'school'});
  values.set('boom-token', 'header.'+Buffer.from(JSON.stringify({sub:'profile-test'})).toString('base64url')+'.signature');
  try {
    let payload;
    globalThis.fetch = async (_url, init) => {
      payload = JSON.parse(init.body);
      return Response.json({profile:{...payload,version:2}});
    };
    const saved = await sync.pushProfile(data);
    assert.equal(saved.ok,true);
    assert.equal(payload.major,data.major);
    assert.equal(payload.grade,data.grade);
    assert.equal(payload.availability.preferences.city,'example');
    assert.equal('phone' in payload,false);
    assert.equal(sync.toSignupData(saved.profile,data).school,'school');
    assert.equal(sync.toSignupData({version:3,availability:{preferences:{phone:'other'}}},data).phone,data.phone);
    globalThis.fetch = async () => Response.json({detail:'offline'},{status:503});
    assert.equal((await sync.pushProfile(data)).ok,false);
    globalThis.fetch = async () => Response.json({detail:{profile:{version:4,grade:'دهم'}}},{status:409});
    const conflict = await sync.pushProfile(data);
    assert.equal(conflict.ok,false);
    assert.equal(conflict.conflict,true);
    assert.equal(conflict.profile.grade,'دهم');
  } finally {globalThis.fetch=previousFetch;values.clear();}
});
