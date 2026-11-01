// Offline, self-contained math preview. No browser, network, tokens or app state.
const fs=require('node:fs');
const path=require('node:path');
const katex=require('katex');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const out=path.resolve(process.argv[2]);
const allowed=path.resolve(__dirname,'../../backend/data/authoring_work');
if(!out.startsWith(allowed+path.sep))throw new Error('Private authoring output required');
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let formulas=0;const renderingErrors=[];
function math(s,displayMode=false){formulas++;try{return katex.renderToString(s,{throwOnError:true,strict:'error',trust:false,displayMode,output:'htmlAndMathml'});}catch(error){if(!input.review_only)throw error;renderingErrors.push({formula:s,error:String(error.message)});return `<code dir="ltr">${escape(s)}</code><small> [فرمول نیازمند اصلاح نمایش]</small>`;}}
function prose(s){return String(s).split(/(\$\$[\s\S]+?\$\$|\$[^$\n]+\$)/g).map(x=>x.startsWith('$$')&&x.endsWith('$$')?`<span class="math display-math" dir="ltr">${math(x.slice(2,-2),true)}</span>`:x.startsWith('$')&&x.endsWith('$')?`<span class="math" dir="ltr">${math(x.slice(1,-1))}</span>`:escape(x)).join('');}
for(const q of input.questions){
 if(q.svg && (/<(?!\/?(?:svg|rect|polygon|line|circle|text)\b)|\son\w+\s*=|href\s*=|url\s*\(|<\?|<!/i.test(q.svg)))throw new Error('Only closed declarative geometry SVG is allowed');
}
const katexDir=path.dirname(require.resolve('katex/dist/katex.min.css'));
let css=fs.readFileSync(path.join(katexDir,'katex.min.css'),'utf8').replace(/url\(fonts\/([^\)]+\.woff2)\)/g,(_,name)=>`url(data:font/woff2;base64,${fs.readFileSync(path.join(katexDir,'fonts',name)).toString('base64')})`);
const fontDir=path.resolve(__dirname,'../public/fonts');
const font=fs.readdirSync(fontDir).find(x=>/vazirmatn/i.test(x)&&/\.woff2$/.test(x));
if(font)css+=`@font-face{font-family:TrialPersian;src:url(data:font/woff2;base64,${fs.readFileSync(path.join(fontDir,font)).toString('base64')}) format('woff2');font-display:swap}`;
css+='body{max-width:1000px;margin:32px auto;padding:0 24px;background:#f7f5f1;color:#242322;font:17px/2.2 TrialPersian,Tahoma,sans-serif}header{padding:20px 0;border-bottom:2px solid #91483e}article{padding:24px 0;border-bottom:1px solid #c8c4be}h1{font-size:26px}h2{font-size:18px;color:#843e35}.math{display:inline-block;direction:ltr;unicode-bidi:isolate;max-width:100%;overflow-x:auto;overflow-y:hidden;vertical-align:middle;padding:.8em .35em}.options{display:grid;grid-template-columns:1fr 1fr;gap:12px;list-style:none;padding:0}.options li{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;border:1px solid #c6c0b9;border-radius:4px;background:white}.option-label{font-size:13px;color:#615c58}.diagram{max-width:480px;margin:20px auto}.diagram svg{width:100%;height:auto}a{color:#843e35}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:16px/1.9 system-ui}footer{margin:32px 0;color:#615c58;font-size:14px}@media(max-width:600px){.options{grid-template-columns:1fr}body{padding:0 16px}}';
css+='.math.display-math{display:block;margin:.5em 0}';
function shell(title,body){return `<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(title)}</title><style>${css}</style><body>${body}</body></html>`;}
function questionLabel(q,i){return `${i+1}${input.review_only?` <small dir="ltr">(${escape(q.id)})</small>`:''}`;}
const questionCards=input.questions.map((q,i)=>`<article><h2>سؤال ${questionLabel(q,i)}</h2><p>${prose(q.stem)}</p>${q.svg?`<div class="diagram">${q.svg}</div><p>اندازه‌گیری از تصویر مبنای حل نیست.</p>`:''}<ol class="options">${q.options.map((o,j)=>`<li><span class="option-label">گزینهٔ ${j+1}</span>${prose(o)}</li>`).join('')}</ol></article>`).join('');
const reviewInstructions=input.review_only?'در گزارش، شناسهٔ R سؤال را بنویسید؛ عدد کنار آن فقط ترتیب نمایش در این برگه است. دربارهٔ طبیعی‌بودن سؤال، کیفیت ایده یا ابهام متن و شکل نظر بدهید. نیازی به بررسی دوبارهٔ OCR نیست.':'فقط شمارهٔ سؤال و ایراد یا پیشنهادتان را در گفتگو بفرستید؛ نیازی به بررسی دوبارهٔ OCR نیست.';
const questions=shell('بررسی نمونه سؤال‌ها',`<header><h1>نمونهٔ محلیِ سؤال‌های ریاضی</h1><p>${input.questions.length} سؤال منتشرنشده؛ بدون دسته‌بندی دشواری. این مرحله برای بررسی دقت، شفافیت و شباهت به کنکور است و به معنی تأیید نهایی نیست.</p>${input.provenance?`<p>${escape(input.provenance)}</p>`:''}<p>${reviewInstructions}</p></header>${questionCards}<footer>این برگه پاسخ‌ها را در خود ندارد. <a href="solutions.html">نمایش پاسخ‌ها و بررسی‌های ریاضی</a> (پس از بررسی سؤال‌ها).</footer>`);
// No answers, solution text or hidden JSON is embedded into the questions page.
const solutionCards=input.solutions.map((s,i)=>`<article><h2>سؤال ${questionLabel(s,i)} — گزینهٔ ${s.answer_index+1}</h2>${s.answer_latex?`<p>${prose('$'+s.answer_latex+'$')}</p>`:''}<pre dir="ltr">${escape(s.proof)}</pre><details><summary>نوع بررسی‌های انجام‌شده و محدودیت</summary><pre dir="ltr">${escape(s.checks.join('\n'))}</pre><p>${input.proof_kind==='independent_assistant'?'راه‌حل با بررسی جداگانهٔ دستیار آماده شده است؛ داوری علمیِ متخصص انسانی محسوب نمی‌شود.':input.review_only?'راه‌حل پیشنهادیِ مدل نویسنده است؛ تأیید علمی یا انسانی محسوب نمی‌شود.':'بررسی همین سؤال‌های مشخص است؛ حل کور مستقل یا داوری انسانی ادعا نشده است.'}</p></details></article>`).join('');
fs.writeFileSync(path.join(out,'questions.html'),questions);
fs.writeFileSync(path.join(out,'solutions.html'),shell('پاسخ‌های نمونهٔ محلی',`<header><h1>پاسخ‌ها و بررسی‌ها</h1><p>پاسخ‌ها همراه با بررسی‌های ثبت‌شده نمایش داده می‌شوند؛ ارزیابی انسانیِ کیفیت و نوآوری هنوز انجام نشده است.</p></header>${solutionCards}`));
fs.writeFileSync(path.join(out,'render-validation.json'),JSON.stringify({questions:input.questions.length,formulas,errors:renderingErrors.length,renderingErrors,standalone:true,answersEmbeddedInQuestionPage:false}));
process.stdout.write(JSON.stringify({questions:input.questions.length,formulas,errors:renderingErrors.length}));
