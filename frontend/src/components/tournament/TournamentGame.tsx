import { useCallback, useEffect, useRef, useState } from "react";
import { accountStorageFor } from "../../accountStorage";
import { saveTournamentAnswers, submitTournamentMatch, type TournamentSession, type TournamentSubmission } from "../../tournamentApi";
import { RichText } from "../../richText";
import QuestionFigure from "../QuestionFigure";
import { StudySymbol } from "../StudySymbols";
import { clockText, faNumber, faPercent, timestamp } from "./format";
import { TournamentAnswerQueue, type AnswerSaveState, type TournamentAnswers } from "./answerSync";

const readToken = () => typeof localStorage === "undefined" ? null : localStorage.getItem("boom-token");
const draftKey = (session: TournamentSession) => `tournament-draft:v2:${session.tournament_id}:${session.match_id}`;

function validAnswers(session: TournamentSession, source: unknown): TournamentAnswers {
  if (!source || typeof source !== "object" || Array.isArray(source)) return {};
  const data = source as Record<string, unknown>;
  const answers: TournamentAnswers = {};
  for (const q of session.questions) {
    const value = data[q.id];
    if (typeof value === "number" && Number.isInteger(value) && value >= 0 && value < q.options.length) answers[q.id] = value;
    else if (value === null) answers[q.id] = null;
  }
  return answers;
}

export function loadTournamentDraft(session: TournamentSession, token: string | null): { answers: TournamentAnswers; revision: number } {
  const serverRevision = session.answers_revision || 0;
  const server = { answers: validAnswers(session, session.saved_answers), revision: serverRevision };
  try {
    const data: unknown = JSON.parse(accountStorageFor(token).getItem(draftKey(session)) || "{}");
    if (!data || typeof data !== "object" || Array.isArray(data)) return server;
    const source = data as Record<string, unknown>;
    return typeof source.revision === "number" && Number.isSafeInteger(source.revision) && source.revision > serverRevision
      ? { answers: validAnswers(session, source.answers), revision: source.revision } : server;
  } catch { return server; }
}

export default function TournamentGame({ session, onBack, onRecorded }: {
  session: TournamentSession; onBack: () => void; onRecorded: () => void;
}) {
  const [token] = useState(readToken);
  const [initialDraft] = useState(() => loadTournamentDraft(session, token));
  const [answers, setAnswers] = useState<TournamentAnswers>(initialDraft.answers);
  const [current, setCurrent] = useState(0);
  const [now, setNow] = useState(Date.now);
  const [clockOffset] = useState(() => timestamp(session.server_now) - Date.now());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<TournamentSubmission | null>(() => session.submitted ? { match_id: session.match_id, status: "completed", score: session.score, submitted: true } : null);
  const [saveState, setSaveState] = useState<AnswerSaveState>(initialDraft.revision > (session.answers_revision || 0) ? "pending" : "saved");
  const request = useRef<AbortController | null>(null);
  const sentOnExpiry = useRef(false);
  const alive = useRef(true);
  const confirmDialog = useRef<HTMLDialogElement | null>(null);
  const [queue] = useState(() => new TournamentAnswerQueue({
    revision: initialDraft.revision, savedRevision: session.answers_revision || 0, answers: initialDraft.answers,
    save: (values, revision, signal) => saveTournamentAnswers(session.tournament_id, session.match_id, values, revision, signal),
    onState: state => { if (alive.current) setSaveState(state); },
    isActive: () => alive.current && readToken() === token,
  }));
  const remaining = Math.max(0, timestamp(session.deadline_at) - (now + (Number.isFinite(clockOffset) ? clockOffset : 0)));
  const answered = session.questions.filter(q => typeof answers[q.id] === "number").length;
  const question = session.questions[current];

  useEffect(() => { alive.current = true; queue.activate(); return () => { alive.current = false; request.current?.abort(); queue.cancel(); }; }, [queue]);
  useEffect(() => {
    if (result || !queue.hasPending) return;
    const timer = window.setTimeout(() => void queue.flush().catch(() => {}), 350);
    return () => window.clearTimeout(timer);
  }, [answers, queue, result]);
  useEffect(() => {
    if (result) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [result]);

  const submit = useCallback(async () => {
    if (request.current || result) return;
    if (readToken() !== token) { setError("حساب ورود تغییر کرده است؛ به تورنومنت برگرد و دوباره وارد بازی شو."); return; }
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError(""); setConfirm(false);
    try {
      // Before the deadline, submit only after the latest write is acknowledged.
      // After expiry the server grades its last saved snapshot; the UI must not
      // claim that an offline or late selection was received.
      const beforeDeadline = timestamp(session.deadline_at) > Date.now() + (Number.isFinite(clockOffset) ? clockOffset : 0);
      if (beforeDeadline) await queue.flush();
      const completeAnswers = Object.fromEntries(session.questions.map(q => [q.id, queue.answers[q.id] ?? null]));
      const response = await submitTournamentMatch(session.tournament_id, session.match_id, completeAnswers, controller.signal);
      if (!alive.current || controller.signal.aborted || readToken() !== token) return;
      setResult(response);
      try { accountStorageFor(token).removeItem(draftKey(session)); } catch { /* Cache is optional. */ }
      onRecorded();
    } catch (failure) {
      if (alive.current && !controller.signal.aborted && readToken() === token) setError(failure instanceof Error ? failure.message : "ثبت پاسخ‌ها انجام نشد؛ دوباره تلاش کن.");
    } finally {
      if (request.current === controller) request.current = null;
      if (alive.current && !controller.signal.aborted) setBusy(false);
    }
  }, [clockOffset, onRecorded, queue, result, session, token]);

  useEffect(() => {
    if (!remaining && !result && !sentOnExpiry.current) { sentOnExpiry.current = true; void submit(); }
  }, [remaining, result, submit]);
  useEffect(() => { if (confirm && confirmDialog.current && !confirmDialog.current.open) confirmDialog.current.showModal(); }, [confirm]);

  const choose = (id: string, value: number | null) => {
    const next = { ...queue.answers, [id]: value };
    queue.stage(next); setAnswers(next);
    try { accountStorageFor(token).setItem(draftKey(session), JSON.stringify({ revision: queue.revision, answers: next })); } catch { /* Optional recovery cache. */ }
  };

  if (result) return <section className="tn-game tn-game-result" aria-labelledby="game-result-title">
    <StudySymbol kind="award" size={48} /><span className="tn-eyebrow">MATCH RECORDED</span><h1 id="game-result-title">پاسخ‌هایت ثبت شد</h1>
    <p>نتیجه توسط سرور ثبت شده است. جدول و مسیر صعود پس از تعیین تکلیف بازی به‌روز می‌شوند.</p>
    <div className="tn-recorded-score"><span>درصد ثبت‌شدهٔ تو</span><strong>{faPercent(result.score)}</strong></div>
    <p className="tn-footnote">پاسخ صحیح و توضیح سؤال‌ها هنگام برگزاری دور نمایش داده نمی‌شوند.</p>
    <button type="button" className="tn-button tn-button-primary" onClick={onBack}>بازگشت به تورنومنت</button>
  </section>;

  return <section className="tn-game" aria-labelledby="game-title">
    <header className="tn-game-header"><div><span className="tn-eyebrow">TOURNAMENT MATCH</span><h1 id="game-title">{session.title}</h1></div><div className={`tn-game-clock ${remaining < 60000 ? "tn-clock-low" : ""}`} aria-label="زمان باقی‌مانده"><span>زمان باقی‌مانده</span><strong dir="ltr">{clockText(remaining)}</strong></div></header>
    <div className="tn-game-toolbar"><p>{faNumber(answered)} پاسخ از {faNumber(session.questions.length)} سؤال پاسخ داده شده است.</p><button type="button" onClick={onBack}>بازگشت به تورنومنت</button></div>
    <p className="tn-footnote">با خروج از این صفحه زمان بازی متوقف نمی‌شود. در پایان مهلت، فقط آخرین پاسخ‌های ذخیره‌شده روی سرور تصحیح می‌شوند.</p>
    <div className={`tn-save-state tn-save-${saveState}`} role="status"><span>{saveState === "saved" ? "آخرین انتخاب‌ها روی سرور ذخیره شده‌اند" : saveState === "saving" ? "در حال ذخیرهٔ پاسخ‌ها…" : saveState === "pending" ? "انتخاب‌های تازه هنوز روی سرور ذخیره نشده‌اند" : "ذخیرهٔ پاسخ‌ها انجام نشد؛ اتصال را بررسی کن"}</span>{saveState === "error" && <button type="button" onClick={() => void queue.flush().catch(() => {})}>تلاش دوباره برای ذخیره</button>}</div>
    {error && <div className="tn-inline-error" role="alert"><p>{error}</p><button type="button" disabled={busy} onClick={() => void submit()}>تلاش دوباره برای ثبت</button></div>}
    {!remaining && <p className="tn-notice" role="status">مهلت بازی پایان یافته است؛ در حال تعیین وضعیت ثبت پاسخ‌ها.</p>}
    <nav className="tn-question-nav" aria-label="فهرست سؤال‌های مسابقه">{session.questions.map((q, i) => <button key={q.id} type="button" aria-label={`سؤال ${faNumber(i + 1)}${typeof answers[q.id] === "number" ? "، پاسخ انتخاب شده" : ""}`} aria-current={current === i ? "step" : undefined} className={`${current === i ? "tn-question-current" : ""} ${typeof answers[q.id] === "number" ? "tn-question-answered" : ""}`} onClick={() => setCurrent(i)}>{faNumber(i + 1)}</button>)}</nav>
    {question ? <article className="tn-question" key={question.id}>
      <div className="tn-question-meta"><span>سؤال {faNumber(current + 1)}</span><span>{question.subject}{question.topic ? ` · ${question.topic}` : ""}</span></div>
      <div className="tn-question-text"><RichText text={question.text} /></div>
      <QuestionFigure figure={question.figure} />
      <fieldset disabled={busy || !remaining} className="tn-answers"><legend className="tn-sr-only">گزینهٔ پاسخ سؤال {faNumber(current + 1)}</legend>{question.options.map((option, i) => <label key={i} className={`tn-option ${answers[question.id] === i ? "tn-option-selected" : ""}`}><input type="radio" name={`tournament-question-${question.id}`} value={i} checked={answers[question.id] === i} onChange={() => choose(question.id, i)} /><span className="tn-option-number">{faNumber(i + 1)}</span><span><RichText text={option} /></span></label>)}</fieldset>
      <button type="button" className="tn-clear-answer" disabled={busy || !remaining || answers[question.id] == null} onClick={() => choose(question.id, null)}>پاک کردن انتخاب این سؤال</button>
    </article> : <p role="alert" className="tn-notice">سؤال‌های بازی دریافت نشده‌اند؛ به تورنومنت برگرد و وضعیت بازی را بررسی کن.</p>}
    <footer className="tn-game-footer"><button type="button" className="tn-button tn-button-secondary" disabled={current <= 0} onClick={() => setCurrent(index => Math.max(0, index - 1))}>سؤال قبلی</button>{current < session.questions.length - 1 ? <button type="button" className="tn-button tn-button-primary" onClick={() => setCurrent(index => index + 1)}>سؤال بعدی</button> : <button type="button" className="tn-button tn-button-primary" disabled={busy || !question} onClick={() => setConfirm(true)}>{busy ? "در حال ثبت…" : "پایان و ثبت پاسخ‌ها"}</button>}</footer>
    {confirm && <dialog ref={confirmDialog} className="tn-dialog" aria-labelledby="submit-tournament-title" onCancel={event => { event.preventDefault(); setConfirm(false); }}><h2 id="submit-tournament-title">پاسخ‌ها نهایی شوند؟</h2><p>{faNumber(session.questions.length - answered)} سؤال بدون پاسخ مانده است. بعد از ثبت نهایی، پاسخ‌ها قابل تغییر نیستند.</p><div><button type="button" className="tn-button tn-button-primary" onClick={() => void submit()}>ثبت نهایی پاسخ‌ها</button><button type="button" className="tn-button tn-button-secondary" autoFocus onClick={() => setConfirm(false)}>ادامهٔ بررسی</button></div></dialog>}
  </section>;
}
