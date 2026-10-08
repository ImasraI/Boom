import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

const vite = await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
test.after(async () => {await vite.close();});

test('Mock page and its shared math/report modules load with an empty profile', async () => {
  const {default:Mock} = await vite.ssrLoadModule('/src/pages/Mock.tsx');
  const html = renderToStaticMarkup(React.createElement(Mock, {nav(){},userData:null}));
  assert.match(html, /تمرین از سوال‌های قبلی/);
  assert.match(html, /ساخت دفترچه آزمون/);
  assert.match(html, /آزمون با استاندارد کنکور/);
  assert.match(html, /تعداد کل سوال‌ها/);
  assert.doesNotMatch(html, /آزمون کامل کنکور/);
  assert.doesNotMatch(html, /صفحه آماده نشد/);
});

test('Ranked page loads its controls before account and filter requests finish', async () => {
  const {default:Arena} = await vite.ssrLoadModule('/src/pages/Arena.tsx');
  const html = renderToStaticMarkup(React.createElement(Arena, {nav(){},userData:null}));
  assert.match(html, /فیلتر دروس/);
  assert.match(html, /در حال دریافت اطلاعات آرنا/);
  assert.match(html, /تلاش دوباره برای دریافت آرنا|در حال بارگذاری دروس/);
  assert.doesNotMatch(html, /صفحه آماده نشد/);
});

test('Admin pool renders unlimited and targeted production controls', async () => {
  const {default:Admin} = await vite.ssrLoadModule('/src/pages/Admin.tsx');
  const html = renderToStaticMarkup(React.createElement(Admin, {nav(){}}));
  assert.match(html, /ذخیره بدون سقف/);
  assert.match(html, /رنکینگ \+ آزمون آزمایشی و تمرین/);
  assert.match(html, /تعداد کل سوال‌های آزمون آزمایشی/);
  assert.match(html, /مباحث هدف/);
  assert.match(html, /راه‌اندازی مجدد سرور ادامه می‌دهد/);
  assert.match(html, /موجودی سوال‌های قابل استفاده/);
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
