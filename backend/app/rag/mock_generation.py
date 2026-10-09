"""Shared AI booklet generation for Konkur-standard mocks and arena duels.

Question counts and durations come from app.rag.konkur_format — the encoded
Sazman-e Sanjesh official format (see that module's header for the year and
sources). This module owns the pipeline only:

  retrieve_book_context  -> OCR'd excerpts from the student's own books
  build_booklet_prompt   -> the structured Persian generation prompt
  generate_booklet       -> per-subject LLM calls + JSON parse + padding

`generate_booklet` drafts each subject separately, using smaller batches when
configured for a provider with a limited token budget. Focused batches reduce
format drift and isolate failures. It returns parsed rows in storage shape ({"_id",
"subject", "topic", "text", "options", "answer", "explanation"}) or [] when
nothing usable was produced — callers decide how to surface that (502 for
/api/mocks, silent placeholder for arena duels).
"""

import json
import re
from typing import Any, Callable, Dict, List, Optional

from app.rag.konkur_format import (  # noqa: F401  (re-exported for consumers)
    FORMAT_YEAR,
    GENERAL_SUBJECTS,
    KONKUR_SUBJECTS,
    MAJOR_ALIASES,
    SPECIALIZED_SUBJECTS,
    major_key,
    plan_totals,
)
from app.config import get_settings
from app.rag.llm import get_pool_llm_client, get_pool_verifier_client
from app.rag.provider_quota import is_terminal_provider_error, quota_identity
from app.rag.pool_pacing import wait_for_draft_slot
from app.rag import pool_usage
from app.utils.logger import get_logger

logger = get_logger(__name__)

OPTIONS = ["الف", "ب", "ج", "د"]

# Live progress events for whoever is watching a long generation run (the
# pool passes a reporter in; the live-mock path passes nothing). Events:
#   booklet        {"target": questions the plan asks for}
#   phase          {"name": "generating"|"verifying"}
#   generated      {"count": questions just parsed/submitted}
#   verified       {"count": questions accepted by the verifier}
#   provider_error {"message": why the LLM refused (quota, rate limit, ...)}
Reporter = Optional[Callable[[str, Dict[str, Any]], None]]

# A pool paper is served as a full mock, so it must stay materially complete.
# The generator and the verifier both legitimately drop questions, and the
# old exact-match rule then rejected EVERY booklet - the pool produced nothing
# at all for minutes on end. A paper that still holds this fraction of the
# official plan is kept, and its advertised duration is scaled down to the
# questions it really contains (see build_pool_booklet).
POOL_MIN_FILL = 0.5


def _report(report: Reporter, event: str, **data: Any) -> None:
    """Send one progress event; never let reporting break generation."""
    if report is None:
        return
    try:
        report(event, data)
    except Exception:
        logger.exception("Generation progress callback failed (%s).", event)


def _shortfall(questions: List[dict], plan: List[dict]) -> List[tuple]:
    """[(subject, planned, produced)] for every subject off its target."""
    counts: Dict[str, int] = {}
    for q in questions:
        counts[q.get("subject")] = counts.get(q.get("subject"), 0) + 1
    return [
        (row["name"], int(row.get("questions") or 0),
         counts.get(row["name"], 0))
        for row in plan
        if counts.get(row["name"], 0) != int(row.get("questions") or 0)
    ]

_DIFFICULTY_LABEL = {
    "easy": "آسان",
    "konkur": "استاندارد کنکور",
    "hard": "سخت (تست‌های بالای ۸۰٪ رتبه‌ها)",
}

_GENERATE_PROMPT = """تو طراح آزمون آزمایشی کنکور هستی. یک دفترچه تست چهارگزینه‌ای استاندارد بساز.

درس‌ها و تعداد سوال هر کدام:
{plan}

مباحث هدف (فقط از این مباحث سوال بزن):
{topics}

سطح دشواری: {difficulty} (سوالات باید در سطح و سبک واقعی کنکور باشند).
{grade_block}

نمونه صفحات واقعی کتاب‌های دانش‌آموز:
{context}
{weak_block}قوانین:
{grounding_rule}
- برای هر سوال: متن سوال، دقیقا ۴ گزینه، شماره گزینه صحیح (۰ تا ۳) و یک توضیح کوتاه حل.
- پاسخ‌ها بین گزینه‌ها پخش باشند (همه «الف» نباشند).
- هیچ سوال تکراری یا تله‌ای با جواب واضح نساز؛ گزینه‌های انحرافی معنادار باشند.
- هر سوال باید کامل، علمی و دارای تنها یک پاسخ قطعی باشد؛ به شکل یا جدول ناموجود اشاره نکن و هویت ماده را تنها از فرمول مولکولی حدس نزن.
- شکل فقط وقتی اضافه شود که برای فهم سوال واقعاً به تصویر نیاز است؛ بیشتر سوال‌ها باید figure با type برابر none داشته باشند.
- اگر figure.type برابر none نیست، figure.data اجباری و کامل و فقط شامل داده‌های عددی/هندسی باشد؛ هرگز توضیح متنی به‌جای داده شکل ننویس.
- اعداد و اندازه‌های داخل figure.data باید دقیقاً با ادعاهای متن سوال سازگار باشند؛ زاویه، طول یا مقداری را تقریب یا نقض نکن.
- برای function_plot، expression را با نحو استاندارد Python بنویس (توان با **، نه ^ یا LaTeX)؛ فقط x و تابع‌های sin، cos، sqrt و abs مجازند.
- ساختار داده‌ها: function_plot={{"expression":"x**2 - 3*x + 2","variable":"x","domain":[-2,5],"labels":{{"x_axis":"x","y_axis":"y"}},"highlight_points":[{{"x":1,"y":0,"label":"A"}}]}}; geometry={{"shape":"triangle","points":{{"A":[0,0],"B":[4,0],"C":[0,3]}},"labels":{{"A":"A","B":"B","C":"C"}},"side_lengths":{{"AB":4,"AC":3,"BC":5}},"angles":{{"A":90}},"marks":{{"right_angle_at":"A","equal_sides":[],"parallel_pairs":[]}}}}.
- bar_chart={{"categories":["A","B","C","D"],"values":[12,19,7,15],"x_label":"دسته","y_label":"فراوانی"}}; coordinate_plane={{"points":[{{"x":1,"y":2,"label":"P"}}],"lines":[{{"from":[0,0],"to":[4,4],"label":"l"}}],"x_range":[-5,5],"y_range":[-5,5]}}.
- خروجی فقط JSON، بدون markdown و توضیح اضافه، در این قالب:
{{"questions":[{{"subject":"ریاضی","topic":"حد و پیوستگی","text":"...","options":["...","...","...","..."],"answer":2,"explanation":"...","figure":{{"type":"none","data":{{}}}}}}, ...]}}"""

_GROUNDED_RULE = ("- هر سوال باید مستقیماً بر اساس مفاهیم، اصطلاحات، اعداد و مثال‌های موجود در "
                  "«نمونه صفحات واقعی کتاب‌های دانش‌آموز» طراحی شود؛ دانش عمومی مدل فقط برای "
                  "تکمیل قالب و نگارش سوال استفاده شود، نه برای انتخاب محتوا.")
_UNGROUNDED_RULE = ("- هیچ متن کتابی در دسترس نیست؛ سوالات را از دانش استاندارد کنکور و "
                    "کتاب‌های درسی رسمی بساز.")


def grade_block(grade: str) -> str:
    """Prompt line scoping a booklet to a school grade ("" = unrestricted).

    Arena duels set this to the YOUNGER player's grade (see
    knowledge_base.grade_scope): an older opponent has already covered that
    syllabus, but the younger one must never be asked about material they
    have not reached yet."""
    label = (grade or "").strip()
    if not label:
        return ""
    return (f"- پایه تحصیلی دانش‌آموز: {label} — سوال‌ها فقط از مطالب همین پایه و "
            f"پایه‌های پایین‌تر باشند.")


def default_plan(major: str) -> List[dict]:
    """Official اختصاصی plan for a major (عمومی is NOT part of test booklets)."""
    return [dict(s) for s in KONKUR_SUBJECTS[major_key(major)]]


def build_pool_booklet(major_key_str: str, difficulty: str = "konkur",
                       user_id: int = 0, verify: bool = True,
                       plan: Optional[List[dict]] = None,
                       report: Reporter = None, on_verified=None, grade: str = "",
                       topics: Optional[List[str]] = None, seed_questions=None) -> tuple:
    """One STANDARD booklet for a (major, difficulty) combination.

    The single generation path shared by /api/mocks/generate's live
    fallback and the background pool worker (scripts/mock_pool_worker.py),
    so pool rows and live-fallback rows are built identically and can never
    drift. `user_id` only grounds retrieval in that student's own uploads;
    the pool worker passes 0 (generic grounding).

    verify=True (default) runs the independent answer-verification pass
    (verify_and_repair_booklet) on the finished booklet. This MUST happen
    here, before the booklet enters the pool: a status="pending_use" row
    can't be re-checked at claim time, so a wrong answer key would reach a
    student untouched. verify=False is the raw-pipeline escape hatch for
    tests/benchmarks only.

    `plan` overrides the major's official plan (used by the duel pool to
    pre-generate the scaled/divisor-3 shape). Defaults to the official plan.

    Returns (questions, official_plan, duration_minutes); questions is []
    when the model produced nothing usable.
    """
    plan = [dict(s) for s in (plan or KONKUR_SUBJECTS[major_key_str])]
    planned = sum(int(s.get("questions") or 0) for s in plan)
    duration = sum(s["minutes"] for s in plan)
    # Only the pool passes trusted, active bank rows here. Draft and independently
    # solve the missing slots; never spend tokens re-verifying existing bank stock.
    seeds = list(seed_questions or [])
    missing_plan = []
    for row in plan:
        missing = int(row['questions']) - sum(q.get('subject') == row['name'] for q in seeds)
        if missing > 0:
            missing_plan.append({**row, 'questions': missing,
                'minutes': max(1, round(row['minutes'] * missing / row['questions']))})
    questions = (generate_booklet(user_id, missing_plan, topics=topics or [], difficulty=difficulty,
                                 report=report, grade=grade) if missing_plan else [])
    if questions and verify:
        questions = verify_and_repair_booklet(questions, user_id,
                                              difficulty=difficulty,
                                              report=report)
        logger.info("Pool booklet verified: %d/%d question(s) survived the "
                    "answer-verification pass.", len(questions), planned)
        if on_verified and questions:
            on_verified(questions)
    seen = set()
    combined = []
    for q in seeds + questions:
        fingerprint = (q.get('subject'), _norm_qtext(q.get('text', '')))
        if fingerprint not in seen:
            combined.append({**q, '_id': len(combined) + 1})
            seen.add(fingerprint)
    questions = combined
    if verify:
        short = _shortfall(questions, plan)
        empty_subject = any(produced == 0 for _, _, produced in short)
        if not questions or len(questions) < planned * POOL_MIN_FILL or empty_subject:
            logger.error(
                "Pool booklet discarded: %d/%d questions verified "
                "(floor %d%%%s) - %s", len(questions), planned,
                round(POOL_MIN_FILL * 100),
                ", a subject came back empty" if empty_subject else "",
                ", ".join(f"{name}: {got}/{want}" for name, want, got in short)
                or "nothing usable",
            )
            questions = []
        elif short:
            # Usable, but never advertise more time than the questions it has:
            # the pool serves this row as a full-length mock.
            duration = max(1, round(duration * len(questions) / planned))
            logger.warning(
                "Pool booklet kept at %d/%d questions; duration scaled to %d "
                "min. %s", len(questions), planned, duration,
                ", ".join(f"{name}: {got}/{want}" for name, want, got in short),
            )
    return questions, plan, duration


def scale_plan(plan: List[dict], divisor: int = 3, minimum: int = 3) -> List[dict]:
    """Shortened plan for duel matches: question counts // divisor (min floor).

    Deliberately leaves `minutes` untouched: match duration is computed by
    the caller as sum(minutes) // divisor, mirroring the pre-refactor arena
    behaviour (questions //3, duration //3 of the FULL minutes).
    """
    return [
        {
            **s,
            "questions": max(minimum, s["questions"] // divisor),
        }
        for s in plan
    ]


def retrieve_book_context(user_id: int, subjects: List[str], topics: List[str],
                          per_subject: int = 3) -> str:
    """OCR'd page excerpts to ground generation in the student's real books.

    The context budget scales with the workload: the old flat ``blocks[:12]``
    starved multi-subject booklets (about 2 excerpts per subject on a 6-row
    plan, far too thin to actually ground generation). The cap is now
    subjects x topics x per_subject with a floor of 12 so small requests keep
    the old behavior. Retrieval is user-scoped inside HybridSearch (a student
    is only ever grounded on their own uploads + the shared corpus)."""
    try:
        from app.rag.embeddings import get_embedding_model
        from app.rag.hybrid_search import get_hybrid_search

        embedder = get_embedding_model()
        search = get_hybrid_search()
    except Exception as exc:  # stores unavailable -> generate from LLM knowledge
        logger.warning("Mock context retrieval unavailable: %s", exc)
        return ""

    topic_list = list(topics or [""]) or [""]
    cap = max(12, len(subjects) * len(topic_list) * per_subject)
    blocks: List[str] = []
    seen = set()
    for subject in subjects:
        for topic in topic_list:
            q = f"{subject} {topic} تست چهارگزینه‌ای کنکور با جواب تشریحی".strip()
            try:
                emb = embedder.embed_query(q)
                chunks = search.search(query_text=q, query_embedding=emb,
                                       user_id=user_id, top_k=per_subject)
            except Exception as exc:
                logger.warning("Mock retrieval failed for %s/%s: %s", subject, topic, exc)
                continue
            for c in chunks:
                key = (c["document_name"], c["chunk_index"])
                if key in seen:
                    continue
                seen.add(key)
                page = ""
                m = re.search(r"\[صفحه\s*([0-9۰-۹]+)\]", c.get("content", "") or "")
                if m:
                    fa = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
                    page = f" (صفحه {m.group(1).translate(fa)})"
                blocks.append(
                    f"[کتاب: {c['document_name']}{page}]\n{c['content'][:700]}"
                )
    return "\n\n".join(blocks[:cap])


def build_booklet_prompt(plan: List[dict], topics: List[str], difficulty: str,
                         context: str, weak_block: str = "",
                         grade: str = "") -> str:
    plan_text = "\n".join(f"- {s['name']}: {s['questions']} سوال" for s in plan)
    topics_text = ("\n".join(f"- {t}" for t in topics)
                   if topics else "- هر مبحث کنکوری آن درس")
    grounded = bool((context or "").strip())
    return _GENERATE_PROMPT.format(
        plan=plan_text, topics=topics_text,
        difficulty=_DIFFICULTY_LABEL.get(difficulty, _DIFFICULTY_LABEL["konkur"]),
        grade_block=grade_block(grade),
        context=context or "در دسترس نیست.",
        weak_block=weak_block,
        grounding_rule=_GROUNDED_RULE if grounded else _UNGROUNDED_RULE,
    )


def weak_areas(user_id: int, recent_n: int = 40, limit: int = 10) -> List[dict]:
    """Bias only toward actual mistakes in verified, book-matched topics."""
    from app.auth.database import SessionLocal
    from app.rag.learning_evidence import confirmed_mistakes
    with SessionLocal() as db:
        rows = confirmed_mistakes(db, user_id)[:recent_n]

    agg: dict = {}
    for idx, r in enumerate(rows):
        key = (r["subject"], r["topic"])
        entry = agg.setdefault(key, {"subject": key[0], "topic": key[1],
                                     "hits": 0, "weight": 0.0})
        entry["hits"] += 1
        entry["weight"] += 1.0 / (1.0 + idx)  # recency decay

    weak = [e for e in agg.values() if e["subject"]]
    weak.sort(key=lambda e: (-e["weight"], -e["hits"]))
    for e in weak:
        e["weight"] = round(e["weight"], 2)
    return weak[:limit]


def bias_plan(plan: List[dict], weak: List[dict],
              extra_cap: int = 5) -> List[dict]:
    """Shift question counts toward the student's weak areas (pure function).

    For every plan row whose subject has weak-topic entries, adds up to
    `extra_cap` extra questions (weighted sum of recency-decayed wrong
    answers), scales that row's minutes proportionally, and attaches the
    weak topics + entries to the row ("topics"/"weak" keys) so the prompt
    targets those concepts specifically. Rows without weak data are left
    untouched, and the official Konkur shape is never reduced — only grown.
    """
    biased: List[dict] = []
    for row in (dict(s) for s in plan):
        entries = [w for w in weak
                   if w["subject"] == row["name"] and w["hits"] > 0]
        if entries:
            extra = min(extra_cap, int(sum(w["weight"] for w in entries) + 0.5))
            if extra > 0:
                base_q = int(row.get("questions") or 0)
                row["questions"] = base_q + extra
                if base_q > 0:
                    row["minutes"] = round(
                        (int(row.get("minutes") or 0))
                        * row["questions"] / base_q)
            # targeted topics only when caller gave none (config.topics wins)
            if not row.get("topics"):
                row["topics"] = [w["topic"] for w in entries if w["topic"]]
            row["weak"] = entries
        biased.append(row)
    return biased


def parse_booklet(raw: str) -> List[dict]:
    """Parse the LLM JSON booklet; tolerate fences and trailing commas."""
    if not raw:
        return []
    candidates = [raw]
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if m:
        candidates.append(m.group(1))
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            data = json.loads(re.sub(r",\s*([}\]])", r"\1", cand.strip()))
        except (json.JSONDecodeError, TypeError):
            continue
        rows = data.get("questions") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            continue
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            options = [str(o) for o in (r.get("options") or [])][:4]
            if len(options) != 4:
                continue
            try:
                ans = int(r.get("answer"))
            except (TypeError, ValueError):
                continue
            if not (0 <= ans <= 3):
                continue
            text = str(r.get("text") or "").strip()
            if len(text) < 5:
                continue
            figure = r.get("figure") or {"type": "none", "data": {}}
            if not isinstance(figure, dict):
                continue
            figure_type = figure.get("type", "none")
            if figure_type not in {
                "function_plot", "geometry", "bar_chart",
                "coordinate_plane", "none",
            }:
                continue
            figure_data = figure.get("data", {})
            if figure_type != "none" and (
                not isinstance(figure_data, dict) or not figure_data
            ):
                continue
            out.append({
                "subject": str(r.get("subject") or "").strip(),
                "topic": str(r.get("topic") or "").strip(),
                "text": text,
                "options": options,
                "answer": ans,
                "explanation": str(r.get("explanation") or "").strip(),
                "figure": {"type": figure_type,
                           "data": figure_data if figure_type != "none" else {}},
            })
        if out:
            return out
    return []


def pad_booklet(questions: List[dict]) -> List[dict]:
    """Balance the answer key across options WITHOUT ever changing which
    option text is correct (LLMs clump on answer=0).

    Each clumped question's correct option is reassigned to the currently
    least-used slot by *swapping the option strings* - the key keeps pointing
    at the same text, so correctness is preserved, but the final distribution
    approaches a balanced 25/25/25/25 instead of a mechanical index shift
    that silently broke answer keys (the old bug)."""
    counts = [0, 0, 0, 0]
    for q in questions:
        counts[q.get("answer", 0)] += 1
    for q in questions:
        if q.get("answer") != 0:
            continue
        # Only move it when option 0 is (or would be) overloaded.
        if counts[0] <= max(counts[1:]) :
            continue
        target = counts.index(min(counts[1:]), 1)  # least-used non-zero slot
        opts = list(q["options"])
        opts[0], opts[target] = opts[target], opts[0]
        q["options"] = opts
        q["answer"] = target
        counts[0] -= 1
        counts[target] += 1
    return questions


# ---------------------------------------------------------------------------
# Independent verification pass
# ---------------------------------------------------------------------------

_VERIFY_PROMPT = """تو یک حل‌کننده مستقل تست چهارگزینه‌ای هستی. فقط این سوال را حل کن.
اگر اطلاعات کافی نیست، شکل یا جدول اشاره‌شده وجود ندارد، چند پاسخ ممکن است یا صورت سوال از نظر علمی مبهم است، answer را null بگذار. نزدیک‌ترین گزینه را حدس نزن.

سوال:
{text}

گزینه‌ها:
0) {o0}
1) {o1}
2) {o2}
3) {o3}

خروجی فقط JSON و بدون هیچ توضیح اضافه، در این قالب:
{{"answer": <شماره گزینه‌ای که محاسبه کردی، عددی بین 0 تا 3>}}
اگر با قطعیت نمی‌توانی جواب را محاسبه کنی فقط بنویس: {{"answer": null}}"""


def _parse_verify_answer(raw: str) -> Optional[int]:
    """Strictly extract a 0-3 option index from the solver's reply.

    Anything else - markdown fences around it, prose, {"answer": null}, a
    float, a bool, out of range - is a clean "could not solve" (None). No
    "closest option" fuzzy matching: only an exact clean index counts.
    """
    if not raw:
        return None
    candidates = [raw]
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        candidates.insert(0, m.group(0))
    for cand in candidates:
        try:
            data = json.loads(cand.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        v = data.get("answer")
        # bool is an int subclass in Python - reject it explicitly
        if type(v) is int and 0 <= v <= 3:
            return v
        return None
    return None


def _verify_question(client, question: dict, timeout: float) -> Optional[int]:
    """One independent solve of `question`. The solver sees ONLY the question
    text and its four options - never the stored answer or explanation.
    Returns the solver's option index, or None when it can't produce a clean
    answer (unsolvable / unparseable / call failed)."""
    if _missing_visible_reference(question):
        return None
    prompt = _VERIFY_PROMPT.format(
        text=_solver_text(question),
        o0=question["options"][0], o1=question["options"][1],
        o2=question["options"][2], o3=question["options"][3],
    )
    try:
        with pool_usage.stage('repair_verification'):
            raw = client.generate([{"role": "user", "content": prompt}],
                                  max_tokens=200, timeout=timeout)
    except Exception as exc:
        logger.warning("Verifier call failed: %s", exc)
        return None
    return _parse_verify_answer(raw)


# One solver call per BATCH of questions instead of one per question.
# A 105-question ریاضی فیزیک booklet used to cost ~108 requests (3 generation
# + 105 verification), which no free tier can serve: Gemini's free tier allows
# a small daily allowance, so the pool could not build a single row.
# At 10 questions per call verification costs far fewer requests, and the saving
# scales with every paid tier too.
_VERIFY_BATCH_SIZE = 10


def _solver_text(question: dict) -> str:
    """Include the visible diagram, never the generator's key/explanation."""
    text = question["text"]
    figure = question.get("figure") or {}
    if isinstance(figure, dict) and figure.get("type") not in (None, "none") and figure.get("data"):
        visible = {"type":figure["type"], "data":figure["data"]}
        text += "\nداده‌های شکل سوال:\n" + json.dumps(visible, ensure_ascii=False)
    return text


def _missing_visible_reference(question: dict) -> bool:
    """A referenced figure/table must actually be visible to the learner."""
    text = str(question.get('text') or '')
    normalized = _norm_qtext(text)
    if not re.search(r'(?:شکل|نمودار|جدول|تصویر)\s*(?:زیر|مقابل|روبرو|روبه\s*رو|داده\s*شده)',normalized):
        return False
    figure = question.get('figure') or {}
    if isinstance(figure,dict) and figure.get('type') not in (None,'none') and figure.get('data'):
        return False
    # Markdown tables are rendered inline by the same rich-text component.
    if re.search(r'(?m)^\s*\|[^\n]+\|\s*\n\s*\|[|:\s-]+\|',text):
        return False
    return True


def _verify_batch_prompt(batch: List[dict]) -> str:
    """Solver prompt for several questions at once (1-based numbering)."""
    items = []
    for i, q in enumerate(batch, start=1):
        options = "\n".join(f"   {j}) {opt}"
                            for j, opt in enumerate(q["options"]))
        items.append(f"[{i}]\nمتن سوال: {_solver_text(q)}\nگزینه‌ها:\n{options}")
    example = ", ".join(f'"{i}": {(i - 1) % 4}' for i in range(1, len(batch) + 1))
    return ("تو یک حل‌کننده مستقل تست چهارگزینه‌ای هستی. هر سوال را جدا و مستقل حل کن."
            " اگر اطلاعات کافی نیست، شکل یا جدول وجود ندارد، چند پاسخ ممکن است یا صورت سوال علمی و قطعی نیست، null برگردان؛ نزدیک‌ترین گزینه را حدس نزن."
            "\n\n" + "\n\n".join(items) +
            "\n\nخروجی فقط JSON و بدون هیچ توضیح اضافه، در این قالب:\n"
            '{"answers": {' + example + '}}\n'
            "برای هر شماره سوال، شماره گزینه‌ای که محاسبه کردی (عددی بین ۰ تا ۳) را بگذار. "
            "اگر یک سوال را با قطعیت نمی‌توانی حل کنی برای همان null بنویس. "
            "شماره همه سوال‌ها را برگردان.")


_FA_AR_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
                              "01234567890123456789")


def _parse_batch_answers(raw: str, count: int) -> Dict[int, Optional[int]]:
    """{1-based question number: option index or None} from a batch reply.

    Strict like _parse_verify_answer: only an exact integer 0-3 (or null)
    counts, so a question the reply omits, misframes, or answers with prose is
    None - "could not verify IT" - and never a guessed index.
    """
    out: Dict[int, Optional[int]] = {i: None for i in range(1, count + 1)}
    if not raw:
        return out
    data = None
    m = re.search(r"\{.*\}", raw, re.S)
    for cand in ([m.group(0), raw] if m else [raw]):
        try:
            parsed = json.loads(re.sub(r",\s*([}\]])", r"\1", cand.strip()))
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            inner = parsed.get("answers")
            data = inner if isinstance(inner, dict) else parsed
            break
    if not isinstance(data, dict):
        return out
    for key, value in data.items():
        try:
            idx = int(str(key).strip().translate(_FA_AR_DIGITS))
        except (TypeError, ValueError):
            continue
        if idx not in out:
            continue
        if type(value) is int and 0 <= value <= 3:
            out[idx] = value
        elif isinstance(value, str) and value.strip().translate(
                _FA_AR_DIGITS).isdigit():
            v = int(value.strip().translate(_FA_AR_DIGITS))
            out[idx] = v if 0 <= v <= 3 else None
    return out


def _verify_batch(client, batch: List[dict],
                  timeout: float) -> Optional[Dict[int, Optional[int]]]:
    """One independent solve of a batch of questions.

    The solver sees ONLY each question's text and options - never a stored
    answer or explanation. Returns {1-based position: index|None}, or None
    when the provider refused the call outright (no reply at all), which is a
    different failure from "the solver could not solve it": this codebase must
    not spend one call per question discovering that a per-day quota is gone.
    """
    try:
        with pool_usage.stage('verification'):
            raw = client.generate(
                [{"role": "user", "content": _verify_batch_prompt(batch)}],
                max_tokens=max(400, 60 * len(batch)), timeout=timeout,
            )
    except Exception as exc:
        logger.warning("Verifier batch call failed: %s", exc)
        return None
    if not (raw or "").strip():
        return None
    return _parse_batch_answers(raw, len(batch))


def _batch_verdicts(client, questions: List[dict], timeout: float, report):
    """Yield (question, solver_verdict) for every question, batched.

    A provider that refuses a batch call ENDS the stream early. The caller
    then keeps only the questions it already verified and drops the rest, so
    an unverified answer key can never reach a student - and a dead quota costs
    ONE request, not one per remaining question.
    """
    batch_size = max(1, _VERIFY_BATCH_SIZE)
    # One call now carries N questions, so it gets the per-question budget
    # twice over rather than being cut off mid-batch.
    batch_timeout = max(timeout, 30.0) * 2
    for start in range(0, len(questions), batch_size):
        batch = questions[start:start + batch_size]
        verdicts = _verify_batch(client, batch, batch_timeout)
        if verdicts is None:
            reason = (getattr(client, "last_error", "")
                      or "provider returned no response")
            logger.error(
                "Verifier refused the call (%s); stopping after %d/%d "
                "question(s) - the rest stay unverified.",
                reason, start, len(questions),
            )
            _report(report, "provider_error", message=reason)
            return
        for pos, question in enumerate(batch, start=1):
            yield question, verdicts.get(pos)


def _generate_replacement(client, user_id: int, question: dict,
                          difficulty: str, max_tokens: int,
                          timeout: float) -> Optional[dict]:
    """Regenerate ONE question for a discarded slot (same subject/topic)."""
    topic = question.get("topic") or ""
    row = {"name": question["subject"], "questions": 1, "minutes": 1}
    context = retrieve_book_context(user_id, [question["subject"]],
                                    [topic] if topic else [], per_subject=2)
    context = _draft_context(context)
    prompt = build_booklet_prompt([row], [topic] if topic else [],
                                  difficulty, context)
    with pool_usage.stage('repair'):
        raw = _draft_generate(client, prompt, max_tokens, timeout)
    rows = parse_booklet(raw)
    return rows[0] if rows else None


def _norm_qtext(text: str) -> str:
    """Cheap normalized form of a question text for duplicate detection:
    Persian digits unified, everything but letters/digits stripped."""
    t = (text or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    return re.sub(r"[\W_]+", "", t, flags=re.UNICODE).lower()


def verify_and_repair_booklet(
    questions: List[dict],
    user_id: int,
    difficulty: str = "konkur",
    max_regens: int = 2,
    timeout: float = 60.0,
    gen_max_tokens: int = 6000,
    report: Reporter = None,
) -> List[dict]:
    """Independently re-solve every question; replace the broken ones.

    The solver sees question texts, options and diagram data, without the
    generator's answer or explanation. It checks _VERIFY_BATCH_SIZE questions
    per call, then independently checks each drafted replacement.
    Verdict per question:
      - solver index == stored answer               -> keep as-is
      - solver clean but different, OR solver could
        not produce a clean 0-3 index at all        -> discard, regenerate a
        replacement for the same subject/topic, verify that too
    At most `max_regens` replacement attempts per question so an ambiguous
    topic can't loop forever; questions that never verify are discarded.
    Replacements inherit the original's "_id" and plan-enforced "subject".
    """
    if not questions:
        return questions
    client = get_pool_verifier_client()
    generator = None  # Create a drafting client only if a replacement is needed.
    _report(report, "phase", name="verifying")

    def _score(verdict: Optional[int], stated: int) -> int:
        if verdict == stated:
            return 2
        return 1 if verdict is not None else 0

    out: List[dict] = []
    seen_texts: set = set()
    repairs_blocked = False
    for q, verdict in _batch_verdicts(client, questions, timeout, report):
        if _missing_visible_reference(q):
            verdict = None  # A solver guess cannot certify a missing visual.
        if verdict == q["answer"] and _norm_qtext(q["text"]) not in seen_texts:
            q = {**q, "verification_status": "verified"}
            out.append(q)
            seen_texts.add(_norm_qtext(q["text"]))
            _report(report, "verified", count=1)
            continue

        best, best_score = q, _score(verdict, q["answer"])
        for attempt in range(1, 1 if repairs_blocked else max_regens + 1):
            if generator is None:
                generator = get_pool_llm_client()
            repl = _generate_replacement(generator, user_id, q, difficulty,
                                         gen_max_tokens, timeout)
            if getattr(generator, "last_error", ""):
                _report(report, "provider_error", message=generator.last_error)
                repairs_blocked = True
                break  # Remaining independent verdicts can still certify good questions.
            if repl is None:
                logger.warning("Verify: replacement attempt %d for a %s "
                               "question produced nothing parseable.",
                               attempt, q["subject"])
                continue
            if _norm_qtext(repl["text"]) in seen_texts:
                # Duplicate of a question already in the booklet - reject the
                # replacement (it would never be accepted) and keep trying.
                logger.info("Verify: replacement for %s duplicates an existing "
                            "question; regenerating.", q["subject"])
                continue
            repl_verdict = _verify_question(client, repl, timeout)
            if getattr(client, "last_error", ""):
                _report(report, "provider_error", message=client.last_error)
                repairs_blocked = True
                break
            s = _score(repl_verdict, repl["answer"])
            if s > best_score:
                best, best_score = repl, s
            if s == 2:
                break
        if best_score < 2:
            logger.warning(
                "Verify: %s question never verified after %d regen "
                "attempt(s); quarantining candidate (score %d).",
                q["subject"], max_regens, best_score)
            continue  # Fail closed: an unverified answer key never reaches a student.
        if _norm_qtext(best["text"]) in seen_texts:
            continue
        best = {**best, "verification_status": "verified"}
        if best is not q:
            best["_id"] = q["_id"]
            best["subject"] = q["subject"]  # plan spelling wins
        out.append(best)
        seen_texts.add(_norm_qtext(best["text"]))
        _report(report, "verified", count=1)
    return out


def _weak_block(entries: List[dict]) -> str:
    """Persian prompt section describing this subject's weak topics."""
    if not entries:
        return ""
    lines = "\n".join(
        f"- {w['topic'] or 'مباحث کلی'} ({w['hits']} پاسخ اشتباه/نزده)"
        for w in entries
    )
    return ("نقاط ضعف دانش‌آموز در این درس (سوالات بیشتری از این مباحث طرح کن و "
            f"شبیه همین مفاهیم بزن):\n{lines}\n\n")


def _draft_context(context: str) -> str:
    limit = max(0, getattr(get_settings(), "POOL_GENERATION_CONTEXT_CHARS", 0))
    return context[:limit] if limit else context


def _draft_generate(client, prompt: str, max_tokens: int, timeout: float) -> str:
    settings = get_settings()
    limit = max(0, getattr(settings, "POOL_GENERATION_MAX_TOKENS", 0))
    budget = min(max_tokens, limit) if limit else max_tokens
    # Only the drafting path is paced; ordinary chat uses the plain clients.
    provider = (settings.POOL_LLM_PROVIDER or settings.LLM_PROVIDER).strip().lower()
    model = (settings.POOL_LLM_MODEL_NAME or settings.LLM_MODEL_NAME).strip()
    identity = quota_identity(provider, model, settings.POOL_LLM_API_KEY or settings.LLM_API_KEY)
    wait_for_draft_slot(identity, max(0, getattr(settings, "POOL_GENERATION_REQUESTS_PER_MINUTE", 0)))
    with pool_usage.stage('repair' if pool_usage.current_stage() == 'repair' else 'drafting'):
        return client.generate([{"role":"user", "content":prompt}], max_tokens=budget, timeout=timeout)


def _generate_subject_questions(user_id: int, row: dict, topics: List[str],
                                difficulty: str, max_tokens: int,
                                timeout: float,
                                report: Reporter = None,
                                grade: str = "") -> List[dict]:
    """Retrieve once per subject, optionally draft in smaller paced batches.

    Subject names, grade and per-subject weak areas are enforced from the
    plan. Smaller batches fit provider token limits without repeated RAG calls.
    """
    count = int(row.get("questions") or 0)
    if count <= 0:
        return []
    subject = row["name"]
    row_topics = row.get("topics") or topics
    context = _draft_context(retrieve_book_context(user_id, [subject], row_topics))
    if not (context or "").strip():
        logger.warning("Booklet grounding MISS: subject %r generated with zero book "
                       "context (user %s) - questions will be LLM-knowledge-only.",
                       subject, user_id)
    budget = max(max_tokens, count * 90)
    client = get_pool_llm_client()
    batch_size = max(0, getattr(get_settings(), "POOL_GENERATION_BATCH_SIZE", 0)) or count
    rows: List[dict] = []
    for offset in range(0, count, batch_size):
        target = min(batch_size, count - offset)
        batch = _draft_subject_batch(client, row, target, row_topics,
                                     difficulty, context, budget, timeout, report, grade, rows)
        if batch is None:
            break  # Keep completed batches for the independent verifier and bank.
        rows.extend(batch)
    rows = pad_booklet(rows[:count])
    for r in rows:
        r["subject"] = subject
    return rows


def _draft_subject_batch(client, row, count, row_topics, difficulty, context,
                         budget, timeout, report, grade, already):
    subject = row["name"]
    rows: List[dict] = []
    for attempt, target in enumerate((count, max(1, count // 2))):
        prompt = build_booklet_prompt([{**row, "questions": target}],
                                      row_topics, difficulty, context,
                                      weak_block=_weak_block(row.get("weak") or []),
                                      grade=grade)
        if already:
            previous = "\n".join(q["text"][:120] for q in already[-8:])
            prompt += "\n\nاین سوال‌ها قبلاً ساخته شده‌اند؛ سوال تکراری نساز:\n" + previous
        raw = _draft_generate(client, prompt, budget, timeout)
        if not (raw or "").strip():
            reason = getattr(client, "last_error", "") or "provider returned no response"
            logger.error("Subject %s: provider refused the call (%s).", subject, reason)
            _report(report, "provider_error", message=reason, subject=subject)
            if rows:
                _report(report, "generated", count=len(rows), subject=subject, target=count)
            return rows or None
        parsed = parse_booklet(raw)[:count]
        if len(parsed) > len(rows):
            rows = parsed
        if len(rows) >= max(1, (count + 1) // 2):
            break
        logger.warning("Subject %s: attempt %d produced %d/%d valid questions.",
                       subject, attempt + 1, len(rows), count)
    _report(report, "generated", count=len(rows), subject=subject, target=count)
    return rows


def generate_booklet(
    user_id: int,
    plan: List[dict],
    topics: Optional[List[str]] = None,
    difficulty: str = "konkur",
    max_tokens: int = 6000,
    timeout: float = 420.0,
    report: Reporter = None,
    grade: str = "",
) -> List[dict]:
    """Full pipeline: per-subject (retrieval -> prompt -> LLM -> parse -> pad).

    One LLM call per subject row keeps large official booklets (105-160
    questions) within model quality limits; a subject that still fails after
    its retry is skipped (partial booklet) rather than failing the whole
    generation. Plan rows may carry "topics"/"weak" keys (see bias_plan) to
    target the student's weak areas; the global `topics` applies to rows
    without their own. Returns storage-shape rows with sequential "_id"s, or
    [] when the model produced nothing valid at all (caller raises/retries).
    """
    topics = list(topics or [])
    questions: List[dict] = []
    next_id = 1

    terminal_error = ""

    def track(event: str, data: dict) -> None:
        nonlocal terminal_error
        if event == "provider_error" and is_terminal_provider_error(data.get("message", "")):
            terminal_error = data["message"]
        _report(report, event, **data)

    _report(report, "booklet",
            target=sum(int(s.get("questions") or 0) for s in plan))
    _report(report, "phase", name="generating")

    for row in (dict(s) for s in plan):
        if int(row.get("questions") or 0) <= 0:
            continue
        rows = _generate_subject_questions(
            user_id, row, topics, difficulty, max_tokens, timeout, report=track,
            grade=grade)
        if not rows:
            if terminal_error:
                break
            logger.warning("Booklet: subject %s produced nothing; skipping.",
                           row["name"])
            continue
        for r in rows:
            r["_id"] = next_id
            next_id += 1
            questions.append(r)
        if terminal_error:
            # Stop drafting, but pass completed questions to the separately
            # configured solver. Only verified survivors can enter the bank.
            break

    if not questions:
        logger.warning("Booklet generation returned no valid questions "
                       "(user %s, plan=%s).", user_id, [s["name"] for s in plan])
    return questions
