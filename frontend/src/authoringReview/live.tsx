/** Admin-authenticated adapter. Data never chooses URLs or filesystem paths. */
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import AuthoringReviewScreen from "./AuthoringReviewView";
import { SourceResolverContext } from "./approvedSources";
import type { ApprovedSource, ReviewDataset } from "./types";
import { record, type Packet } from "./liveRecords";
import SourceCheck from "./SourceCheck";
import "../index.css";
import "../desk.css";
import "./live.css";

const base="/api/authoring-review";
async function request(path:string, body?:unknown) {
  const token=localStorage.getItem("boom-token");
  if (!token) throw new Error("ابتدا در سایت محلی با حساب مدیر وارد شوید.");
  const response=await fetch(base+path,{headers:{Authorization:`Bearer ${token}`, ...(body ? {"Content-Type":"application/json"} : {})},method:body ? "POST":"GET",body:body ? JSON.stringify(body):undefined,cache:"no-store"});
  if (!response.ok) {
    if(response.status===401)throw new Error("نشست معتبر نیست؛ دوباره وارد حساب مدیر محلی شوید.");
    if(response.status===403)throw new Error("این حساب مدیر نیست؛ بازبینی فقط برای مدیر محلی مجاز است.");
    if(response.status>=500)throw new Error("API محلی بازبینی در دسترس نیست. سرور پورت ۸۰۰۰ را اجرا کنید و دوباره تلاش کنید.");
    const error=await response.json().catch(()=>({detail:"خطای شبکه"}));throw new Error(String(error.detail));
  }
  return response;
}
export default function LiveReview() {
  const [items,setItems]=useState<{id:string;number:number}[]>([]),[qid,setQid]=useState(""),[mode,setMode]=useState("blind"),[packet,setPacket]=useState<Packet|null>(null),[images,setImages]=useState<Record<string,ApprovedSource>>({}),[message,setMessage]=useState(""),[solution,setSolution]=useState(""),[refresh,setRefresh]=useState(0);
  const [reload,setReload]=useState(0),[loading,setLoading]=useState(false),[username,setUsername]=useState(""),[password,setPassword]=useState(""),[signingIn,setSigningIn]=useState(false);
  useEffect(()=>{
    let disposed=false;setLoading(true);setMessage("");
    request("/questions").then(r=>r.json()).then(rows=>{if(!disposed){setItems(rows);setQid(rows[0]?.id ?? "");setRefresh(n=>n+1);if(!rows.length)setMessage("پرسشی برای این پایلوت ثبت نشده است.");}}).catch(e=>{if(!disposed){setItems([]);setQid("");setMessage(e.message);}}).finally(()=>{if(!disposed)setLoading(false);});
    return()=>{disposed=true;};
  },[reload]);
  useEffect(()=>{
    let disposed=false; const urls:string[]=[];setPacket(null);setImages({});setSolution("");
    if(!qid)return;
    setMessage("");
    (async()=>{const p:Packet=await (await request(`/questions/${encodeURIComponent(qid)}/packet?mode=${mode}`)).json();const sources:Record<string,ApprovedSource>={};
      for(const kind of p.answer ? ["question","answer"]:["question"]){const blob=await (await request(`/questions/${encodeURIComponent(qid)}/images/${kind}?mode=${mode}&evidenceToken=${encodeURIComponent(p.evidenceToken)}`)).blob();if(disposed)return;const url=URL.createObjectURL(blob);urls.push(url);sources[kind]={id:kind,kind:kind==="answer" ? "answer":"crop",src:url,alt:kind==="answer" ? "برش پاسخ ناشر":"برش‌های اصلی پرسش",width:1000,height:1000};}
      if(!disposed){setImages(sources);setPacket(p);}
    })().catch(e=>{if(!disposed)setMessage(e.message);});
    return ()=>{disposed=true;urls.forEach(url=>URL.revokeObjectURL(url));};
  },[qid,mode,refresh]);
  const dataset:ReviewDataset|null=packet ? {datasetId:"h2-math-pilot",title:"بازبینی منابع ریاضی",snapshotVersion:packet.evidenceToken,policyVersion:"SR-0.1",generatedAt:new Date().toISOString(),synthetic:false,eligibleCount:0,eligibilityNotes:["تصمیم هر بُعد مستقل است؛ صلاحیت علمی بازبین توسط سامانه گواهی نمی‌شود."],records:[record(packet,mode)]}:null;
  return <main dir="rtl" className="authoring-review-live">
    <h1>تطبیق پرسش با منبع</h1><p>در این مرحله فقط بررسی کنید متن و چهار گزینه با تصویر اصلی یکسان باشند. حل سؤال و داوری علمی، مرحله‌ای جداست.</p>
    {items.length>0 && <p className="review-live-account">وارد حساب مدیر محلی شده‌اید · {items.length} پرسش در دسترس</p>}
    <details><summary>ورود با حساب مدیر محلی</summary><form onSubmit={async e=>{
      e.preventDefault();setSigningIn(true);setMessage("");
      try{
        const response=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:new URLSearchParams({username,password})});
        if(response.status>=500)throw new Error("API محلی در دسترس نیست؛ سرور بازبینی پورت ۸۰۰۰ را اجرا کنید.");
        const data=await response.json();if(!response.ok || typeof data.access_token!=="string")throw new Error("ورود ناموفق بود؛ اطلاعات حساب محلی را بررسی کنید.");
        localStorage.setItem("boom-token",data.access_token);setMode("blind");setReload(n=>n+1);
      }catch(error){setMessage((error as Error).message);}finally{setPassword("");setSigningIn(false);}
    }}><label>نام کاربری / شمارهٔ حساب محلی <input required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label><label>رمز عبور <input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label><button disabled={signingIn}>{signingIn ? "در حال ورود…":"ورود"}</button></form></details>
    <button disabled={loading} onClick={()=>setReload(n=>n+1)}>{loading ? "در حال اتصال…":"اتصال دوباره / بارگذاری پرسش‌ها"}</button>{" "}
    <label>پرسش <select disabled={!items.length || loading} value={qid} onChange={e=>{setQid(e.target.value);setMode("blind");}}>{items.map(i=><option key={i.id} value={i.id}>{i.number}</option>)}</select></label>{" "}
    <p className="review-live-status" role="status">{message}</p>
    {packet && <SourceCheck key={qid+packet.evidenceToken} packet={packet} images={images} answerShown={mode==="source"} onAnswer={()=>setMode("source")} onDecision={async(decision,note)=>{
      await request(`/questions/${encodeURIComponent(qid)}/decisions`,{questionId:qid,dimension:"extraction",decision,reviewerKind:"human",synthetic:false,note,binding:packet.binding,evidenceToken:packet.evidenceToken});
    }}/>}
    <details className="review-expert"><summary>بازبینی تخصصی و جزئیات شواهد — اختیاری</summary>
    <p>این بخش برای بازبین علمی است؛ برای تطبیق متن نیازی به تکمیل آن ندارید.</p>
    <button disabled={!qid || loading} onClick={()=>{setMode("blind");setRefresh(n=>n+1);}}>بستهٔ حل کور</button>{" "}<button disabled={!qid || loading} onClick={()=>{setMode("source");setRefresh(n=>n+1);}}>نمایش پاسخ ناشر و داوری</button>
    {mode==="source" && packet?.blindSolution && <section><h2>حل کور ثبت‌شدهٔ همین حساب</h2><p style={{whiteSpace:"pre-wrap"}}>{packet.blindSolution}</p></section>}
    {packet && mode==="blind" && <form onSubmit={async e=>{e.preventDefault();try{await request(`/questions/${encodeURIComponent(qid)}/blind-solve`,{binding:packet.binding,evidenceToken:packet.evidenceToken,solution});setMessage("حل کور با هویت حساب شما ثبت شد. اکنون پاسخ ناشر را بررسی کنید.");}catch(err){setMessage((err as Error).message);}}}><label>حل مستقل و قابل‌بررسی<textarea required minLength={10} maxLength={8000} value={solution} onChange={e=>setSolution(e.target.value)} /></label><button type="submit">ثبت حل کور</button></form>}
    {dataset && <SourceResolverContext.Provider value={id=>id ? images[id] ?? null:null}><AuthoringReviewScreen key={`${qid}:${mode}:${refresh}`} dataset={dataset} decisionApi={mode==="source" ? {submitDecision:async input=>{try{const result=await (await request(`/questions/${encodeURIComponent(qid)}/decisions`,input)).json();setRefresh(n=>n+1);return result;}catch(e){return {ok:false,message:(e as Error).message};}}}:undefined}/></SourceResolverContext.Provider>}
    </details>
  </main>;
}
if(typeof document!=="undefined")createRoot(document.getElementById("root")!).render(<LiveReview/>);
