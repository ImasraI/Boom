// Private, offline review sheets using the application's actual math/figure renderer.
import fs from 'node:fs/promises';
import path from 'node:path';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Usage: node scripts/export-model-comparison.mjs STATE_JSON OUTPUT_DIR');
const state = JSON.parse(await fs.readFile(input, 'utf8'));
await fs.mkdir(output, {recursive:true});
const vite = await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
const {default:MathText} = await vite.ssrLoadModule('/src/components/ChatMarkdown.tsx');
const {default:Figure} = await vite.ssrLoadModule('/src/components/QuestionFigure.tsx');
const text = value => renderToStaticMarkup(React.createElement(MathText,{text:String(value ?? '')}));
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const figure = value => renderToStaticMarkup(React.createElement(Figure,{figure:value}));
let mathCSS = await fs.readFile('node_modules/katex/dist/katex.min.css','utf8');
for (const match of [...mathCSS.matchAll(/url\((fonts\/[^)]+)\)/g)]) {
  const filename = match[1];
  const data = await fs.readFile(path.join('node_modules/katex/dist',filename));
  const mime = filename.endsWith('.woff2') ? 'font/woff2' : filename.endsWith('.woff') ? 'font/woff' : 'font/ttf';
  mathCSS = mathCSS.replaceAll(match[0],`url(data:${mime};base64,${data.toString('base64')})`);
}
const font = await fs.readFile('public/fonts/boom-persian-1.woff2');
const css = `${mathCSS}
@font-face{font-family:Vazir;src:url(data:font/woff2;base64,${font.toString('base64')})}
*{box-sizing:border-box}body{font-family:Vazir,sans-serif;background:#f9f6ef;color:#201b16;max-width:980px;margin:40px auto;padding:24px;line-height:1.95}
h1{font-size:26px}h2{font-size:19px}article{border-top:1px solid #cabfaa;padding:28px 0;break-inside:avoid}
small{color:#6a5d4e}ol{padding-right:28px}li{padding:5px}p{margin:7px 0}svg{max-width:100%;height:auto;max-height:320px}figure{margin:18px 0}
.katex{direction:ltr;unicode-bidi:embed}.katex-display{text-align:center;overflow-x:auto}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}
textarea{width:100%;min-height:70px;font-family:inherit;padding:10px;border:1px solid #bba;background:#fff}
select,button{font-family:inherit;padding:9px;margin:8px;background:#e8dfca;border:1px solid #aa9471}
@media print{.review,button{display:none}body{margin:0;max-width:none;background:white;padding:10px}article{break-inside:avoid}}
`;
const reviewJS = `
const id=document.body.dataset.model,storage='boom-review-'+id;
let reviews={};try{reviews=JSON.parse(localStorage.getItem(storage)||'{}')}catch{}
for(const el of document.querySelectorAll('[data-q]')){const q=el.dataset.q;const old=reviews[q]||{};
el.querySelector('select').value=old.rating||'';el.querySelector('textarea').value=old.comment||'';
el.addEventListener('input',()=>{reviews[q]={rating:el.querySelector('select').value,comment:el.querySelector('textarea').value};localStorage.setItem(storage,JSON.stringify(reviews))})}
document.querySelector('button').onclick=()=>{const blob=new Blob([JSON.stringify({model:id,reviews},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='review-'+id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
`;
try {
  for (const [provider, result] of Object.entries(state.models)) {
    if (!['groq','gemini'].includes(provider)) throw new Error('Unexpected provider identity');
    const title = `${provider} · ${result.model} · ${result.questions.length}/20`;
    const heading = escape(title);
    const articles = result.questions.map(q => `<article><h2>سوال ${Number(q._id)} · ${escape(q.subject)} · ${escape(q.topic)}</h2>
      <small>${escape(q.book)} · صفحه ${Number(q.page)}</small>${text(q.text)}${figure(q.figure)}
      <ol>${q.options.map(o => `<li>${text(o)}</li>`).join('')}</ol>
      <div class="review" data-q="${Number(q._id)}"><label>ارزیابی شما:
      <select><option value="">بررسی نشده</option><option value="3">درست و قابل استفاده</option><option value="2">نیاز به ویرایش</option><option value="1">نادرست / مبهم</option></select></label>
      <textarea placeholder="صحت پاسخ، گزینه‌ها، شکل، شباهت به کتاب و سختی"></textarea></div></article>`).join('');
    const key = result.questions.map(q => `<article><h2>سوال ${Number(q._id)} · گزینه ${Number(q.answer)+1}</h2>
      ${text(q.explanation)}<details><summary>شاهد کتاب، برای کنترل مبحث</summary>${text(q.source_quote)}</details></article>`).join('');
    const wrapper = (body, script='') => `<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>مقایسه مدل‌ها · ${provider}</title><style>${css}</style><body data-model="${provider}"><h1>${heading}</h1>${body}${script}</body></html>`;
    await fs.writeFile(path.join(output,`${provider}-questions.html`), wrapper(`<p>سطح سخت · استدلال high · نیازمند ارزیابی انسانی. این سوال‌ها وارد بانک سایت نشده‌اند.</p><button>ذخیره ارزیابی من</button>${articles}`,`<script>${reviewJS}</script>`));
    await fs.writeFile(path.join(output,`${provider}-answer-key.html`), wrapper(`<p>این کلید پیشنهادی مدل است؛ تایید صحت محسوب نمی‌شود.</p>${key}`));
  }
  await fs.writeFile(path.join(output,'progress.json'),JSON.stringify(Object.fromEntries(Object.entries(state.models).map(([k,v])=>[k,{model:v.model,saved:v.questions.length,status:v.status}])),null,2));
  console.log('Review sheets and separate answer keys exported.');
} finally {
  await vite.close();
}
