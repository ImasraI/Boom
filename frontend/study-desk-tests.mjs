import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

const vite=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
test.after(async()=>vite.close());
const {default:StudyDeskHero,StudyDial}=await vite.ssrLoadModule('/src/components/StudyDeskHero.tsx');
const {default:Workbench}=await vite.ssrLoadModule('/src/components/Workbench.tsx');
const {readPreferences}=await vite.ssrLoadModule('/src/components/Experience.tsx');
const render=(component,props)=>renderToStaticMarkup(React.createElement(component,props));
const task=(id,subject,done=false,skipped=false)=>({id,subject,done,skipped,title:'وظیفه '+id,
  scheduledTime:'10:00',description:'',duration:'۱ ساعت',type:'study',planBlock:{day:0,startHour:10,duration:1,title:'وظیفه '+id,type:'study'}});
const props={userData:{name:'آرسام',major:'ریاضی فیزیک',grade:'دوازدهم'},nav(){},logout(){},streak:0,daysLeft:'—',date:'2026-10-14'};

test('Sunset is the default, including corrupt preferences, while explicit palette choices persist',()=>{
  const previous=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
  let saved=null;
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:()=>saved}});
  try {
    assert.equal(readPreferences().palette,'coral');
    for(const invalid of ['{','null','{"palette":"unknown"}']) {
      saved=invalid;assert.equal(readPreferences().palette,'coral');
    }
    for(const palette of ['mint','iris','coral']) {
      saved=JSON.stringify({palette,sound:true,calm:true});
      assert.deepEqual(readPreferences(),{palette,sound:true,calm:true});
    }
  } finally {
    if(previous)Object.defineProperty(globalThis,'localStorage',previous);else delete globalThis.localStorage;
  }
});

test('today dial excludes skipped work and encodes real completion rather than mastery',()=>{
  const tasks=[task(1,'ریاضی',true),task(2,'ریاضی'),task(3,'فیزیک'),task(4,'شیمی'),task(5,'هندسه',true,true)];
  const html=render(StudyDial,{tasks});
  assert.match(html,/۱ از ۴ فعالیت امروز انجام شده/);
  assert.match(html,/۲۵/);
  assert.match(html,/stroke-dasharray="50 100"/);
  assert.equal((html.match(/stroke-dasharray="0 100"/g)||[]).length,2);
  assert.doesNotMatch(html,/هندسه|تسلط|دقت پاسخ/);
});

test('an unplanned day shows no invented percentage, progress or subject ring',()=>{
  const html=render(StudyDial,{tasks:[]});
  assert.match(html,/هنوز فعالیتی برای امروز ثبت نشده/);
  assert.match(html,/—/);
  assert.doesNotMatch(html,/٪|۱۰۰|ریاضی/);
  const hero=render(StudyDeskHero,{...props,tasks:[]});
  assert.match(hero,/ساخت برنامهٔ من/);
  assert.match(hero,/زمان‌های آزادت را مشخص کن/);
  assert.match(hero,/پیوستگی مطالعه/);
  assert.doesNotMatch(hero,/۹۰٪|۸ ساعت|رتبهٔ پیش‌بینی/);
});

test('next step is the first unfinished active task and completed days have no fabricated next task',()=>{
  const tasks=[task(1,'ریاضی',true),task(2,'فیزیک',false,true),task(3,'شیمی')];
  const html=render(StudyDeskHero,{...props,tasks});
  assert.match(html,/وظیفه 3/);
  assert.doesNotMatch(html,/وظیفه 1|وظیفه 2/);
  assert.match(html,/۱ از ۲ فعالیت امروز انجام شده/);
  assert.match(html,/10:00/);
  const complete=render(StudyDeskHero,{...props,tasks:[task(1,'ریاضی',true)]});
  assert.match(complete,/فعالیت‌های امروزت انجام شده/);
  assert.doesNotMatch(complete,/<time/);
});

test('the dial discloses additional subjects instead of silently inventing three subject coverage',()=>{
  const html=render(StudyDial,{tasks:[task(1,'ریاضی'),task(2,'فیزیک'),task(3,'شیمی'),task(4,'هندسه')]});
  assert.match(html,/\+۱ درس/);
  assert.match(html,/۰ از ۴ فعالیت امروز انجام شده/);
  assert.equal((html.match(/class="dial-progress"/g)||[]).length,3);
});

test('hero keeps unknown exam countdown unknown and escapes student supplied name',()=>{
  const html=render(StudyDeskHero,{...props,userData:{...props.userData,name:'<script>unsafe()</script>'},tasks:[],date:'not-a-date'});
  assert.match(html,/&lt;script&gt;unsafe\(\)&lt;\/script&gt;/);
  assert.doesNotMatch(html,/<script>|Invalid Date|NaN/);
  assert.match(html,/—/);
  assert.match(html,/تا آزمون ثبت‌شده/);
});
