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
