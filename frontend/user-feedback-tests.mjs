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
