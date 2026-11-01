import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { createRequire } from "node:module";

test("KaTeX renderer and imported stylesheet use the same version",()=>{
  const require=createRequire(import.meta.url);
  const rendererRequire=createRequire(require.resolve("rehype-katex"));
  assert.equal(require("katex/package.json").version,rendererRequire("katex/package.json").version);
});

const vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: "custom" });
test.after(() => vite.close());

const model = await vite.ssrLoadModule("/src/authoringReview/model.ts");
const decisions = await vite.ssrLoadModule("/src/authoringReview/decisions.ts");
const screen = await vite.ssrLoadModule("/src/authoringReview/AuthoringReviewView.tsx");
const fixtures = await vite.ssrLoadModule("/src/authoringReview/fixtures.synthetic.ts");
const live = await vite.ssrLoadModule("/src/authoringReview/liveRecords.ts");
const liveScreen = await vite.ssrLoadModule("/src/authoringReview/live.tsx");
const direction = await vite.ssrLoadModule("/src/authoringReview/textDirection.ts");
const sourceCheck = await vite.ssrLoadModule("/src/authoringReview/SourceCheck.tsx");
const notation = await vite.ssrLoadModule("/src/authoringReview/examNotation.ts");

test("exam notation displays square brackets without changing composition or canonical text",()=>{
  const original="\\sin^2(\\pi\\lfloor x\\rfloor/2)+(f\\circ g)(x)";
  assert.equal(notation.examMath(original),"\\sin^2(\\pi[ x]/2)+(f\\circ g)(x)");
  assert.equal(original.includes("\\lfloor"),true);
  assert.equal(notation.examMath("\\left\\lfloor x\\right\\rfloor"),"\\left[ x\\right]");
  assert.equal(notation.examOption("fog $\\lfloor x\\rfloor$"),"fog $[ x]$");
  assert.equal(notation.examMath("\\lceil x\\rceil"),"\\lceil x\\rceil");
});

test("plain negative options retain left-to-right signs in the Persian layout",()=>{
  const packet={question:{printed_question_number:1,pages:[2]},transcription:{stem:[{kind:"math",value:"x-1"}],options:[{index:0,text:"-2.5"},{index:1,text:"هیچ"},{index:2,text:"$-\\frac12$"},{index:3,text:"4"}]}};
  const html=renderToStaticMarkup(React.createElement(sourceCheck.default,{packet,images:{},answerShown:false,onAnswer:()=>{},onDecision:async()=>{}}));
  assert.match(html,/<bdi dir="ltr">-2.5<\/bdi>/);
  assert.match(html,/<bdi dir="rtl">هیچ<\/bdi>/);
});

test("changed evidence keeps the user's old report visible without presenting it as current approval",()=>{
  const packet={question:{printed_question_number:1,pages:[2]},evidenceToken:"new",sourceChecks:[{evidenceToken:"old",outcome:"passed",note:"Synthetic prior report"}],transcription:null};
  const html=renderToStaticMarkup(React.createElement(sourceCheck.default,{packet,images:{},answerShown:false,onAnswer:()=>{},onDecision:async()=>{}}));
  assert.match(html,/Synthetic prior report/);
  assert.match(html,/نسخهٔ سؤال یا شواهد آن تغییر کرده است/);
  assert.doesNotMatch(html,/آخرین نظر ثبت‌شدهٔ شما برای همین نسخه/);
});

test("simple source check renders equations and four options without requiring a solution",()=>{
  const packet={question:{printed_question_number:1,pages:[2]},transcription:{stem:[{kind:"text",value:"Synthetic "},{kind:"math",value:"\\frac{x^2}{2}"}],options:Array.from({length:4},(_,index)=>({index,text:String(index)}))}};
  const html=renderToStaticMarkup(React.createElement(sourceCheck.default,{packet,images:{},answerShown:false,onAnswer:()=>{},onDecision:async()=>{}}));
  assert.match(html,/katex/);
  assert.match(html,/گزینهٔ 4/);
  assert.match(html,/درست است/);
  assert.match(html,/نیاز به اصلاح دارد/);
  assert.match(html,/مطمئن نیستم/);
  assert.match(html,/لازم نیست سؤال را حل کنید/);
  assert.doesNotMatch(html,/ثبت حل کور|قرارداد داوری سمت سرور|هیچ گزینه‌ای استخراج/);
});

test("unprepared questions cannot be confirmed as matching",()=>{
  const html=renderToStaticMarkup(React.createElement(sourceCheck.default,{packet:{question:{printed_question_number:2,pages:[2]}},images:{},answerShown:false,onAnswer:()=>{},onDecision:async()=>{}}));
  assert.match(html,/بازنویسی ساختاریافته/);
  assert.match(html,/<button disabled="">درست است/);
});

test("Persian prose isolates Latin equations without rewriting source characters",()=>{
  const text="اگر a(a^2 + 3b^2) = 76 باشد، مقدار (a-b)/(a+b) چیست؟\nگزینه ۳";
  const runs=direction.directionRuns(text);
  assert.equal(runs.map(r=>r.value).join(""),text);
  assert.ok(runs.some(r=>r.ltr && r.value.includes("a(a^2 + 3b^2) = 76")));
  const html=renderRecord({...fixtures.SYNTHETIC_RECORDS[0],transcription:[{kind:"text",value:text}]});
  assert.match(html,/class="ar-ltr-run" dir="ltr"/);
});

const DATASET = fixtures.SYNTHETIC_REVIEW_DATASET;
const [q1, q2, q3, q4, q5, q6] = fixtures.SYNTHETIC_RECORDS;
const render = (props) => renderToStaticMarkup(React.createElement(screen.default, props));
const renderRecord = (record) => render({ dataset: { ...DATASET, records: [record] } });

test("live entry offers local login and reconnect before questions are available", () => {
  const html=renderToStaticMarkup(React.createElement(liveScreen.default));
  assert.match(html,/ورود با حساب مدیر محلی/);
  assert.match(html,/اتصال دوباره/);
  assert.match(html,/type="password"/);
  assert.match(html,/<select disabled=""/);
  assert.match(html,/<button disabled="">بستهٔ حل کور/);
});

test("live candidate adapter preserves unknown keys and source bindings", () => {
  const binding = {...model.bindingFor(q1),pageImageHash:null,evidenceToken:"a".repeat(64)};
  const source = {id:"synthetic:q",document_id:binding.documentId,session:"synthetic",booklet_code:"A",printed_question_number:1,literal_native:"Synthetic source",pages:[2,3],continuation_state:"proposed",answer_index:null};
  const record = live.record({question:source,answer:source,binding,evidenceToken:binding.evidenceToken,receipts:[],blindSolution:null},"source");
  assert.equal(record.answer.normalizedIndex,null);
  assert.equal(record.answer.rawKey,null);
  assert.equal(record.figure.expected,null);
  assert.equal(record.continuation.total,2);
  assert.deepEqual(model.bindingFor(record),binding);
  assert.equal(record.eligibility.state,"held");
});

test("live receipts and decisions also bind answer/pairing evidence tokens", () => {
  const record = { ...q1, evidenceToken: "a".repeat(64), source: { ...q1.source, pageImageId: "src:missing:full-page", pageImageHash: null } };
  const binding = model.bindingFor(record);
  assert.ok(binding);
  const receipt = { ...q1.receipts[0], binding };
  assert.equal(model.isReceiptCurrent(record, receipt), true);
  assert.equal(model.isReceiptCurrent({ ...record, evidenceToken: "b".repeat(64) }, receipt), false);
  assert.equal(model.isReceiptCurrent(record, { ...receipt, binding: { ...binding, evidenceToken: undefined } }), false);
  const input = decisions.buildDecisionInput(record, {dimension:"extraction",decision:"hold",reviewerIdentifier:"declared",note:"Original crop inspected"});
  assert.equal(input.evidenceToken, record.evidenceToken);
  assert.equal(input.binding.evidenceToken, record.evidenceToken);
});

test("evidence states come from bound receipts, never from model agreement", () => {
  assert.equal(model.evidenceStateFor(q1, "extraction"), "verified_human");
  assert.equal(model.evidenceStateFor(q1, "science"), "model_only");
  assert.equal(model.evidenceStateFor(q1, "curriculum"), "model_only");
  assert.equal(model.evidenceStateFor(q1, "figure_fidelity"), "missing");
  assert.equal(model.evidenceStateFor(q1, "intended_difficulty"), "unresolved");

  assert.equal(model.evidenceStateFor(q4, "extraction"), "stale");
  assert.equal(model.evidenceStateFor(q4, "answer_association"), "model_only");

  assert.equal(model.evidenceStateFor(q5, "answer_association"), "disagreement");
  assert.equal(model.evidenceStateFor(q5, "science"), "disagreement");
  assert.equal(model.evidenceStateFor(q5, "figure_fidelity"), "verified_human");

  assert.equal(model.evidenceStateFor(q6, "science"), "missing");
  assert.equal(model.evidenceStateFor(q3, "figure_fidelity"), "verified_human");

  assert.equal(model.isReceiptCurrent(q4, q4.receipts[0]), false);
  assert.equal(model.isReceiptCurrent(q4, q4.receipts.at(-1)), true);
  assert.equal(model.summarize(fixtures.SYNTHETIC_RECORDS).eligible, 0);
});

test("record navigation clamps at the ends and zoom stays inside its range", () => {
  assert.equal(model.nextRecordIndex(0, 6, "ArrowDown"), 1);
  assert.equal(model.nextRecordIndex(5, 6, "ArrowDown"), 5);
  assert.equal(model.nextRecordIndex(0, 6, "ArrowUp"), 0);
  assert.equal(model.nextRecordIndex(3, 6, "Home"), 0);
  assert.equal(model.nextRecordIndex(3, 6, "End"), 5);
  assert.equal(model.nextRecordIndex(3, 6, "x"), 3);
  assert.equal(model.zoomBy(1, -1), 1);
  assert.equal(model.zoomBy(2.4, 1), 2.5);
  assert.equal(model.zoomBy(1.6, 0), 1);
  assert.equal(model.formatZoom(1.5), "۱۵۰٪");
});

test("the screen renders transcription, ordered options, answer source, tags and every evidence dimension", () => {
  const html = render({ dataset: DATASET });

  assert.match(html, /ریشه/);
  assert.match(html, /x² − 5x \+ 6 = 0/);
  assert.ok(html.indexOf("دو و سه") < html.indexOf("منفی دو و منفی سه"));
  assert.ok(html.indexOf("منفی دو و منفی سه") < html.indexOf("یک و شش"));

  assert.match(html, /منبع پاسخ/);
  assert.match(html, /برگهٔ کلید ساختگی A/);
  assert.match(html, /گزینهٔ ادعاشده/);
  assert.match(html, /پیشنهاد مدل/);

  for (const dimension of ["استخراج", "پیوند پاسخ", "ویرایش", "وفاداری شکل", "دشواری هدفمند"]) {
    assert.ok(html.includes(dimension), `missing evidence dimension: ${dimension}`);
  }
  assert.match(html, /وضعیت شواهد/);
  assert.match(html, /تأیید انسانی/);

  assert.match(html, /سهمی|برنامه/);
  assert.match(html, /برچسب استنباطی/);
  assert.match(html, /دشواری تجربی/);

  assert.match(html, /۰ رکورد واجد شرایط/);
  assert.match(html, /دادهٔ ساختگی/);
  assert.match(html, /برش پرسش \(ساختگی\)/);
  assert.match(html, /data:image\/svg\+xml/);
  assert.match(html, /این پرسش شکل ندارد/);
  assert.match(html, /aria-current="true"/);
  assert.equal((html.match(/aria-current="true"/g) || []).length, 1);
  assert.match(html, /tabindex="-1"/);
});

test("missing images, continuations and unreadable options are shown explicitly", () => {
  const html = render({ dataset: DATASET, initialQuestionId: "syn-0002-q2" });
  assert.match(html, /تصویر تأییدشده در دسترس نیست/);
  assert.match(html, /ادعا شده اما تصویر تأییدشده‌ای ثبت نشده است/);
  assert.match(html, /بخش ۱ از ۲/);
  assert.match(html, /ناخوانا/);
  assert.match(html, /نمادهای نامطمئن/);
  assert.match(html, /بدون پاسخ قطعی/);
  assert.match(html, /کلیدی برای این پرسش در بسته نیست/);
  assert.equal((html.match(/<img /g) || []).length, 0);
});

test("stale receipts are named as stale and not counted as evidence", () => {
  const html = render({ dataset: DATASET, initialQuestionId: "syn-0004-q4" });
  assert.match(html, /منقضی/);
  assert.match(html, /این رسید به نسخه\/هش فعلی بسته نیست/);
  assert.match(html, /رسیدها \(/);
  assert.match(html, /هیچ رسید فعلی برای استخراج وجود ندارد|منقضی شده‌اند/);
  assert.equal(model.evidenceStateFor(q4, "editorial"), "stale");
});

test("conflicting answer keys stay a disagreement until a human resolves them", () => {
  const html = render({ dataset: DATASET, initialQuestionId: "syn-0005-q5" });
  assert.match(html, /دو کلید ناسازگار/);
  assert.match(html, /اختلاف/);
  assert.match(html, /دوم درست است/);
  assert.match(html, /اول درست است/);
  assert.match(html, /اختلاف تا داوری انسانی حل‌شده محسوب نمی‌شود/);
  assert.match(html, /نمودار ساختگی سهمی/);
});

test("an empty transcription and zero options render explicit empty states", () => {
  const html = render({ dataset: DATASET, initialQuestionId: "syn-0006-q6" });
  assert.match(html, /هیچ متنی برای این رکورد استخراج نشده است/);
  assert.match(html, /هیچ گزینه‌ای استخراج نشده است/);
  assert.match(html, /این پرسش شکل ندارد/);
  assert.match(html, /بدون کلید در بسته/);
  assert.match(html, /۰ رکورد واجد شرایط/);
  assert.match(html, /نگه‌داشته‌شده/);
});

test("an empty dataset never implies an eligible record", () => {
  const html = render({ dataset: { ...DATASET, records: [] } });
  assert.match(html, /هیچ رکوردی برای نمایش نیست/);
  assert.equal(html.includes("aria-current"), false);
});

test("record text is escaped and model content never becomes markup", () => {
  const hostile = '<img src=x onerror="alert(1)"><script>alert(1)</script>';
  const record = {
    ...q1,
    options: [{ index: 0, text: hostile }],
    issues: [hostile],
    transcription: [{ kind: "text", value: hostile }],
  };
  const html = renderRecord(record);
  assert.match(html, /&lt;img src=x onerror=/);
  assert.match(html, /&lt;script&gt;/);
  assert.equal(html.includes("<script>"), false);
  assert.equal(/<img[^>]+onerror/.test(html), false);
});

test("image requests only follow approved source ids", () => {
  const record = {
    ...q1,
    source: {
      ...q1.source,
      pageImageId: "https://tracker.example/pixel.png",
      cropImageId: "../../private/scan.png",
    },
    answer: { ...q1.answer, imageId: "javascript:alert(1)" },
    figure: { expected: true, imageId: "/etc/passwd", label: "شکل نامعتبر" },
  };
  const html = renderRecord(record);
  assert.equal(html.includes("tracker.example"), false);
  assert.equal(html.includes("scan.png"), false);
  assert.equal(html.includes("/etc/passwd"), false);
  assert.match(html, /تصویر تأییدشده در دسترس نیست/);
  assert.match(html, /شناسهٔ منبع تأیید نشده است/);
});

test("without a decision API the screen is read-only and names the dependency", () => {
  const html = render({ dataset: DATASET });
  assert.match(html, /وابستگی: قرارداد داوری سمت سرور در دسترس نیست/);
  assert.match(html, /فقط‌خواندنی/);
  assert.equal(/<button[^>]*>[^<]*(قبول همه|تأیید همه)/.test(html), false);
  assert.equal(html.includes("<form"), false);
  assert.match(html, /content_hash/);
});

test("with a decision API the form submits one dimension bound to revision and hash", async () => {
  const api = {
    calls: [],
    async submitDecision(input) {
      this.calls.push(input);
      return { ok: true, receiptId: "receipt-1", recordedAt: "2026-10-23T10:00:00Z" };
    },
  };
  const html = render({ dataset: DATASET, decisionApi: api });
  assert.match(html, /<form/);
  assert.match(html, /ثبت تصمیم برای این بُعد/);
  assert.match(html, /name="decision"/);
  assert.equal(/قبول همه|تأیید همه|approve all/i.test(html), false);

  const form = {
    dimension: "science",
    decision: "pass",
    reviewerIdentifier: "reviewer-synthetic",
    note: "شاهد تصویری و متن برای این بُعد کافی است.",
  };
  const input = decisions.buildDecisionInput(q1, form);
  assert.equal(input.questionId, q1.questionId);
  assert.deepEqual(input.binding, model.bindingFor(q1));
  assert.equal(input.binding.questionRevision, q1.questionRevision);
  assert.equal(input.binding.contentHash, q1.contentHash);
  assert.equal(input.binding.documentId, q1.source.documentId);
  assert.equal(input.binding.documentRevision, q1.source.documentRevision);
  assert.equal(input.binding.pageImageHash, q1.source.pageImageHash);
  assert.equal(input.binding.cropImageHash, q1.source.cropImageHash);
  assert.equal(input.binding.figureImageHash, q1.figure.imageHash);
  assert.equal(input.binding.catalogueVersion, q1.curriculum.catalogueVersion);
  assert.equal(input.dimension, "science");
  assert.equal(input.reviewerKind, "human");
  assert.equal(input.synthetic, true);

  assert.equal(decisions.validateDecisionForm({ ...form, reviewerIdentifier: "  " }).ok, false);
  assert.equal(decisions.validateDecisionForm({ ...form, note: "کوتاه" }).ok, false);

  const result = await decisions.submitDecision(api, q1, form);
  assert.equal(result.ok, true);
  assert.equal(api.calls.length, 1);
  assert.deepEqual(api.calls[0], input);

  const failure = await decisions.submitDecision(
    {
      async submitDecision() {
        throw new Error("offline");
      },
    },
    q1,
    form,
  );
  assert.equal(failure.ok, false);
  assert.match(failure.message, /offline/);
});

/* -------- adversarial receipt probes: F2 correction (see F2_REVIEW.md) ---- */

function humanReceipt(over) {
  return {
    receiptId: over.receiptId,
    dimension: over.dimension ?? "extraction",
    outcome: over.outcome ?? "passed",
    reviewerKind: over.reviewerKind ?? "human",
    reviewerIdentifier: over.reviewerKind === "model" ? "model:fixture-local" : "بازبین-ساختگی",
    model: over.reviewerKind === "model" ? "fixture-model-a" : null,
    promptVersion: null,
    timestamp: over.timestamp ?? "2026-10-23T08:00:00Z",
    binding: over.binding ?? model.bindingFor(q1),
    supersedes: over.supersedes ?? [],
    synthetic: true,
  };
}

test("conflicting or failing current human receipts never become human verification", () => {
  const base = model.bindingFor(q1);
  assert.ok(base, "q1 must expose a complete evidence binding");

  const pass = humanReceipt({ receiptId: "rcp-x-pass", outcome: "passed", binding: base });
  const failOlder = humanReceipt({
    receiptId: "rcp-x-fail",
    outcome: "failed",
    timestamp: "2026-10-19T08:00:00Z",
    binding: base,
  });

  // Probe 1: current pass + current fail, disagreements empty → never verified.
  const conflict = { ...q1, receipts: [pass, failOlder] };
  assert.equal(model.evidenceStateFor(conflict, "extraction"), "disagreement");
  assert.notEqual(model.evidenceStateFor(conflict, "extraction"), "verified_human");
  assert.match(renderRecord(conflict), /اختلاف/);

  // Failure recorded AFTER a pass must not be swallowed by the earlier pass.
  const failNewer = humanReceipt({
    receiptId: "rcp-x-fail-newer",
    outcome: "failed",
    timestamp: "2026-10-24T09:00:00Z",
    binding: base,
  });
  const failAfterPass = { ...q1, receipts: [pass, failNewer] };
  assert.equal(model.evidenceStateFor(failAfterPass, "extraction"), "disagreement");

  // A lone current human failure is "rejected", never "verified_human".
  const loneFail = { ...q1, receipts: [failOlder] };
  assert.equal(model.evidenceStateFor(loneFail, "extraction"), "rejected");
  assert.equal(model.EVIDENCE_STATE_LABELS.rejected, "رد انسانی");
  assert.match(renderRecord(loneFail), /رد انسانی/);

  // Conflicting MODEL judgments are never displayed as model verification either.
  const modelPass = humanReceipt({
    receiptId: "rcp-x-mpass",
    reviewerKind: "model",
    binding: base,
  });
  const modelFail = humanReceipt({
    receiptId: "rcp-x-mfail",
    reviewerKind: "model",
    outcome: "failed",
    binding: base,
  });
  assert.equal(
    model.evidenceStateFor({ ...q1, receipts: [modelPass, modelFail] }, "extraction"),
    "disagreement",
  );
});

test("superseded or stale failures stay visible yet cannot block a current pass", () => {
  const base = model.bindingFor(q1);
  const fail = humanReceipt({
    receiptId: "rcp-fix-fail",
    outcome: "failed",
    timestamp: "2026-10-18T09:00:00Z",
    binding: base,
  });
  const pass = humanReceipt({ receiptId: "rcp-fix-pass", outcome: "passed", binding: base });

  // Explicit supersession (S0 `supersedes`): a later same-kind receipt replaces the failure.
  const superseding = humanReceipt({
    receiptId: "rcp-fix-pass-2",
    outcome: "passed",
    binding: base,
    supersedes: ["rcp-fix-fail"],
  });
  const resolved = { ...q1, receipts: [fail, superseding] };
  assert.equal(model.evidenceStateFor(resolved, "extraction"), "verified_human");
  const resolvedHtml = renderRecord(resolved);
  assert.match(resolvedHtml, /جایگزین‌شده/);
  assert.equal(resolved.receipts.length, 2, "superseded history is preserved, not deleted");

  // Supersession only within the same reviewer kind: a model pass can never
  // erase a human rejection.
  const modelSupersedes = humanReceipt({
    receiptId: "rcp-fix-mpass",
    reviewerKind: "model",
    binding: base,
    supersedes: ["rcp-fix-fail"],
  });
  assert.equal(
    model.evidenceStateFor({ ...q1, receipts: [fail, modelSupersedes] }, "extraction"),
    "rejected",
  );

  // A failure bound to an older revision/hash is stale: it does not block the
  // current pass, but the stale receipt itself stays marked منقضی.
  const staleBinding = {
    ...base,
    questionRevision: base.questionRevision - 1,
    contentHash: "sha256:000000000000dead",
  };
  const staleFail = humanReceipt({
    receiptId: "rcp-fix-stale-fail",
    outcome: "failed",
    binding: staleBinding,
  });
  const afterRevision = { ...q1, receipts: [staleFail, pass] };
  assert.equal(model.isReceiptCurrent(afterRevision, staleFail), false);
  assert.equal(model.evidenceStateFor(afterRevision, "extraction"), "verified_human");

  const onlyStale = { ...q1, receipts: [staleFail] };
  assert.equal(model.evidenceStateFor(onlyStale, "extraction"), "stale");
  assert.match(renderRecord(onlyStale), /منقضی/);
});

test("receipts bind the exact question id, document, image hashes and catalogue", () => {
  const base = model.bindingFor(q1);
  const bound = humanReceipt({ receiptId: "rcp-bind", binding: base });
  assert.equal(model.isReceiptCurrent(q1, bound), true);
  assert.deepEqual(model.receiptBindingGaps(q1, bound), []);

  // Probe 2: record question id changes while revision/hash stay identical.
  const renamed = { ...q1, questionId: "syn-0001-q1-renamed" };
  assert.equal(model.isReceiptCurrent(renamed, bound), false);
  assert.ok(model.receiptBindingGaps(renamed, bound).includes("questionId"));
  assert.equal(model.evidenceStateFor(renamed, "extraction"), "stale");

  // Source image hash (recrop) invalidates the receipt.
  const recrop = { ...q1, source: { ...q1.source, cropImageHash: "sha256:ff99ce00000000ff" } };
  assert.equal(model.isReceiptCurrent(recrop, bound), false);
  assert.ok(model.receiptBindingGaps(recrop, bound).includes("cropImageHash"));

  // Document revision invalidates the receipt.
  const redoc = { ...q1, source: { ...q1.source, documentRevision: "doc-rev:2" } };
  assert.equal(model.isReceiptCurrent(redoc, bound), false);
  assert.ok(model.receiptBindingGaps(redoc, bound).includes("documentRevision"));

  // Catalogue version invalidates the receipt.
  const recat = {
    ...q1,
    curriculum: { ...q1.curriculum, catalogueVersion: "curriculum-synthetic-0.4" },
  };
  assert.equal(model.isReceiptCurrent(recat, bound), false);
  assert.ok(model.receiptBindingGaps(recat, bound).includes("catalogueVersion"));

  // Figure image hash invalidates a receipt bound to figure evidence.
  const q3Bound = humanReceipt({ receiptId: "rcp-bind-fig", binding: model.bindingFor(q3) });
  assert.equal(model.isReceiptCurrent(q3, q3Bound), true);
  const refig = { ...q3, figure: { ...q3.figure, imageHash: "sha256:ff99ce000000000f" } };
  assert.equal(model.isReceiptCurrent(refig, q3Bound), false);
  assert.ok(model.receiptBindingGaps(refig, q3Bound).includes("figureImageHash"));

  // Missing binding fields are rejected, never assumed current.
  const missingField = { ...bound, binding: { ...base, questionId: undefined } };
  assert.equal(model.isReceiptCurrent(q1, missingField), false);
  assert.ok(model.receiptBindingGaps(q1, missingField).includes("questionId"));
  assert.equal(model.isReceiptCurrent(q1, { ...bound, binding: undefined }), false);

  // A record whose referenced image carries no hash has an incomplete binding:
  // no receipt may count as current for it.
  const hashless = { ...q1, source: { ...q1.source, cropImageHash: null } };
  assert.equal(model.bindingFor(hashless), null);
  assert.equal(model.isReceiptCurrent(hashless, bound), false);
  assert.equal(model.evidenceStateFor(hashless, "extraction"), "stale");
});

test("a stale receipt names the exact bindings that no longer match", () => {
  const base = model.bindingFor(q1);
  const stale = humanReceipt({
    receiptId: "rcp-gaps",
    binding: { ...base, catalogueVersion: "curriculum-synthetic-0.2" },
  });
  const html = renderRecord({ ...q1, receipts: [stale] });
  assert.match(html, /این رسید به نسخه\/هش فعلی بسته نیست/);
  assert.match(html, /نسخهٔ فهرست درسی/);
  assert.match(html, /به‌عنوان شاهد پذیرفته نمی‌شود/);
  assert.match(html, /curriculum-synthetic-0.2/);
});

test("a decision payload carries the full binding and refuses incomplete records", async () => {
  const form = {
    dimension: "science",
    decision: "pass",
    reviewerIdentifier: "reviewer-synthetic",
    note: "شاهد تصویری و متن برای این بُعد کافی است.",
  };
  const input = decisions.buildDecisionInput(q1, form);
  assert.deepEqual(input.binding, model.bindingFor(q1));
  for (const key of [
    "questionId",
    "questionRevision",
    "contentHash",
    "documentId",
    "documentRevision",
    "pageImageHash",
    "cropImageHash",
    "figureImageHash",
    "catalogueVersion",
  ]) {
    assert.ok(Object.hasOwn(input.binding, key), `decision binding must carry ${key}`);
  }

  // Probe 3: an incomplete record never produces a submit-able decision.
  const hashless = { ...q1, source: { ...q1.source, pageImageHash: null } };
  assert.throws(() => decisions.buildDecisionInput(hashless, form), /ناقص/);

  const api = {
    calls: [],
    async submitDecision(payload) {
      this.calls.push(payload);
      return { ok: true, receiptId: "r-1", recordedAt: "2026-10-23T10:00:00Z" };
    },
  };
  const refused = await decisions.submitDecision(api, hashless, form);
  assert.equal(refused.ok, false);
  assert.match(refused.message, /ناقص/);
  assert.equal(api.calls.length, 0, "no unbound decision may reach the API");
});

test("source tables retain row labels and ordered cells",()=>{
 const packet={question:{printed_question_number:1,pages:[2]},transcription:{stem:[{kind:"text",value:"Synthetic table"}],options:[],table:{rows:[{label:"حدود دسته",cells:["0–2","2–4"]},{label:"فراوانی",cells:["3","a"]}]}}};
 const html=renderToStaticMarkup(React.createElement(sourceCheck.default,{packet,images:{},answerShown:false,onAnswer:()=>{},onDecision:async()=>{}}));
 assert.match(html,/<th scope="row" dir="rtl">حدود دسته<\/th>/);
 assert.match(html,/<th scope="row" dir="rtl">فراوانی<\/th>/);
 assert.ok(html.indexOf('0–2')<html.indexOf('2–4'));
});
