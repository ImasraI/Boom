import { useState } from "react";
import ChatMarkdown from "../components/ChatMarkdown";
import type { ApprovedSource } from "./types";
import type { Packet } from "./liveRecords";
import { examMath, examOption } from "./examNotation";

export default function SourceCheck({packet,images,answerShown,onAnswer,onDecision}:{
  packet:Packet;images:Record<string,ApprovedSource>;answerShown:boolean;
  onAnswer:()=>void;onDecision:(decision:"pass"|"fail"|"unresolved",note:string)=>Promise<void>;
}) {
  const [note,setNote]=useState(""),[saving,setSaving]=useState(false),[result,setResult]=useState(""),[zoom,setZoom]=useState(false);
  const prepared=packet.transcription;
  const previous=packet.sourceChecks?.filter(check=>check.evidenceToken===packet.evidenceToken).at(-1);
  const older=packet.sourceChecks?.filter(check=>check.evidenceToken!==packet.evidenceToken).at(-1);
  async function decide(value:"pass"|"fail"|"unresolved") {
    if(saving)return;setSaving(true);setResult("");
    const descriptions={pass:"متن، فرمول‌ها و چهار گزینه را با تصویر منبع تطبیق دادم؛ تفاوتی ندیدم.",fail:"در تطبیق متن یا گزینه‌ها با تصویر منبع، اصلاح لازم است.",unresolved:"برای تطبیق دقیق متن یا گزینه‌ها با تصویر منبع مطمئن نیستم."};
    try{await onDecision(value,descriptions[value]+(note.trim() ? " یادداشت: "+note.trim():""));setResult("نظر شما دربارهٔ تطبیق متن ثبت شد؛ این به معنی تأیید علمی یا انتشار نیست.");}catch(e){setResult((e as Error).message);}finally{setSaving(false);}
  }
  return <section className="source-check" aria-label="تطبیق پرسش با منبع">
    <header><span className="source-check-step">مرحلهٔ ۱ · تطبیق متن</span><h2>پرسش {packet.question.printed_question_number}</h2><p>فقط متن، فرمول‌ها و گزینه‌های پایین را با تصویر اصلی مقایسه کنید. لازم نیست سؤال را حل کنید.</p>{!previous && older && <p className="source-check-pending">نسخهٔ سؤال یا شواهد آن تغییر کرده است؛ گزارش قبلی شما محفوظ است. لطفاً همین نسخه را دوباره با تصویر مقایسه کنید.<br/>گزارش نسخهٔ قبلی: {older.note}</p>}</header>
    <div className="source-check-grid">
      <section><h3>تصویر اصلی پرسش</h3><p className="source-check-hint">صفحهٔ {packet.question.pages.join("، ")} از PDF</p><button aria-pressed={zoom} onClick={()=>setZoom(!zoom)}>{zoom ? "نمایش کل تصویر":"بزرگ‌نمایی تصویر"}</button><div className="source-check-image" data-zoomed={zoom} tabIndex={0} aria-label="تصویر اصلی پرسش؛ قابل پیمایش">{images.question && <img src={images.question.src} alt="پرسش و گزینه‌های اصلی در PDF"/>}</div></section>
      <section><h3>متن آماده‌شده برای تطبیق</h3>{prepared ? <>
        <p className="source-check-hint">بازنویسی پیشنهادی؛ هنوز تأیید انسانی نشده است.</p>
        <div className="source-check-stem" dir="rtl">{prepared.stem.map((s,i)=>s.kind==="math" ? <div key={i} className="source-check-equation" dir="ltr"><ChatMarkdown text={`$${examMath(s.value)}$`}/></div>:<span key={i}>{s.value}</span>)}</div>
        {prepared.table && <div className="source-check-table"><table dir="ltr" aria-label="جدول داده‌های سؤال"><tbody>{prepared.table.rows.map((row,i)=><tr key={i}><th scope="row" dir="rtl">{row.label}</th>{row.cells.map((cell,j)=><td key={j}><bdi dir="ltr">{cell}</bdi></td>)}</tr>)}</tbody></table></div>}
          <ol className="source-check-options">{prepared.options.map(o=><li key={o.index}><span>گزینهٔ {o.index+1}</span>{o.text.includes('$') ? <div className="source-check-option-math" dir="ltr"><ChatMarkdown text={examOption(o.text)}/></div>:<bdi dir={/[\u0600-\u06ff]/.test(o.text) ? "rtl":"ltr"}>{o.text}</bdi>}</li>)}</ol>
        {prepared.figureInSource && <p className="source-check-hint">شکل یا جدولِ تصویر اصلی جزء صورت سؤال است؛ هنگام تطبیق به آن هم مراجعه کنید.</p>}
      </>:<p className="source-check-pending">بازنویسی ساختاریافتهٔ این سؤال هنوز آماده نشده است. متن خام و نامرتب را برای تأیید نمایش نمی‌دهیم؛ فقط تصویر منبع در دسترس است.</p>}</section>
    </div>
    <section className="source-check-decision"><h3>آیا متن و گزینه‌ها با تصویر یکسان‌اند؟</h3>{previous && <p>آخرین نظر ثبت‌شدهٔ شما برای همین نسخه: {previous.outcome==="passed" ? "درست است":previous.outcome==="failed" ? "نیاز به اصلاح دارد":"مطمئن نیستم"} — {previous.note}</p>}<label>یادداشت اختیاری<textarea value={note} onChange={e=>setNote(e.target.value)} maxLength={7000} placeholder="مثلاً: توانِ عبارت دوم اشتباه است یا گزینه‌ای جا افتاده…"/></label><div className="source-check-actions">
      <button disabled={saving || !prepared} onClick={()=>decide("pass")}>درست است</button>
      <button disabled={saving} onClick={()=>decide("fail")}>نیاز به اصلاح دارد</button>
      <button disabled={saving} onClick={()=>decide("unresolved")}>مطمئن نیستم</button>
    </div><p role="status">{saving ? "در حال ثبت…":result}</p></section>
    <section className="source-check-answer"><h3>پاسخ ناشر — جدا از بررسی متن</h3><p>برای تطبیق متن نیازی به دیدن پاسخ نیست. دیدن آن، فرصت حل مستقلِ بدون پاسخ را برای این حساب از بین می‌برد.</p><button disabled={answerShown} onClick={onAnswer}>{answerShown ? "پاسخ نمایش داده شده است":"نمایش پاسخ ناشر"}</button>
      {answerShown && (images.answer ? <div className="source-check-image" tabIndex={0} aria-label="تصویر پاسخ ناشر"><img src={images.answer.src} alt="پاسخ تشریحی ناشر"/></div>:<p>پیوند پاسخ این سؤال هنوز قطعی نیست؛ پاسخ حدس زده نمی‌شود.</p>)}
    </section>
  </section>;
}
