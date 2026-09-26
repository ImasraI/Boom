"""Shared AI booklet generation for Konkur-standard mocks and arena duels.

Question counts and durations come from app.rag.konkur_format — the encoded
Sazman-e Sanjesh official format (see that module's header for the year and
sources). This module owns the pipeline only:

  retrieve_book_context  -> OCR'd excerpts from the student's own books
  build_booklet_prompt   -> the structured Persian generation prompt
  generate_booklet       -> per-subject LLM calls + JSON parse + padding

`generate_booklet` makes ONE LLM call per subject row of the plan (not one
giant call): 105-160 question booklets degrade badly in a single generation
(format drift, repetition), while focused per-subject calls hold quality and
isolate failures. It returns validated rows in storage shape ({"_id",
"subject", "topic", "text", "options", "answer", "explanation"}) or [] when
nothing usable was produced — callers decide how to surface that (502 for
/api/mocks, silent placeholder for arena duels).
"""

import json
import re
from typing import List, Optional

from app.rag.konkur_format import (  # noqa: F401  (re-exported for consumers)
    FORMAT_YEAR,
    GENERAL_SUBJECTS,
    KONKUR_SUBJECTS,
    MAJOR_ALIASES,
    SPECIALIZED_SUBJECTS,
    major_key,
    plan_totals,
)
from app.rag.llm import get_pool_llm_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

OPTIONS = ["الف", "ب", "ج", "د"]

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

نمونه صفحات واقعی کتاب‌های دانش‌آموز:
{context}
{weak_block}قوانین:
{grounding_rule}
- برای هر سوال: متن سوال، دقیقا ۴ گزینه، شماره گزینه صحیح (۰ تا ۳) و یک توضیح کوتاه حل.
- پاسخ‌ها بین گزینه‌ها پخش باشند (همه «الف» نباشند).
- هیچ سوال تکراری یا تله‌ای با جواب واضح نساز؛ گزینه‌های انحرافی معنادار باشند.
- خروجی فقط JSON، بدون markdown و توضیح اضافه، در این قالب:
{{"questions":[{{"subject":"ریاضی","topic":"حد و پیوستگی","text":"...","options":["...","...","...","..."],"answer":2,"explanation":"..."}}, ...]}}"""

_GROUNDED_RULE = ("- هر سوال باید مستقیماً بر اساس مفاهیم، اصطلاحات، اعداد و مثال‌های موجود در "
                  "«نمونه صفحات واقعی کتاب‌های دانش‌آموز» طراحی شود؛ دانش عمومی مدل فقط برای "
                  "تکمیل قالب و نگارش سوال استفاده شود، نه برای انتخاب محتوا.")
_UNGROUNDED_RULE = ("- هیچ متن کتابی در دسترس نیست؛ سوالات را از دانش استاندارد کنکور و "
                    "کتاب‌های درسی رسمی بساز.")


def default_plan(major: str) -> List[dict]:
    """Official اختصاصی plan for a major (عمومی is NOT part of test booklets)."""
    return [dict(s) for s in KONKUR_SUBJECTS[major_key(major)]]


def build_pool_booklet(major_key_str: str, difficulty: str = "konkur",
                       user_id: int = 0, verify: bool = True,
                       plan: Optional[List[dict]] = None) -> tuple:
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
    duration = sum(s["minutes"] for s in plan)
    questions = generate_booklet(user_id, plan, topics=[], difficulty=difficulty)
    if questions and verify:
        questions = verify_and_repair_booklet(questions, user_id,
                                              difficulty=difficulty)
        logger.info("Pool booklet verified: %d question(s) survived the "
                    "answer-verification pass.", len(questions))
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
                         context: str, weak_block: str = "") -> str:
    plan_text = "\n".join(f"- {s['name']}: {s['questions']} سوال" for s in plan)
    topics_text = ("\n".join(f"- {t}" for t in topics)
                   if topics else "- هر مبحث کنکوری آن درس")
    grounded = bool((context or "").strip())
    return _GENERATE_PROMPT.format(
        plan=plan_text, topics=topics_text,
        difficulty=_DIFFICULTY_LABEL.get(difficulty, _DIFFICULTY_LABEL["konkur"]),
        context=context or "در دسترس نیست.",
        weak_block=weak_block,
        grounding_rule=_GROUNDED_RULE if grounded else _UNGROUNDED_RULE,
    )


def weak_areas(user_id: int, recent_n: int = 40, limit: int = 10) -> List[dict]:
    """The student's weakest (subject, topic) pairs from WrongAnswer rows.

    Reads the most recent `recent_n` wrong/blank answers, groups them by
    (subject, topic) and weights each hit with recency decay (newest hit =
    1.0, each older hit multiplied by ~1/position), so what the student
    missed THIS WEEK outweighs what they missed last month. Returns at most
    `limit` entries sorted by weight desc:
        [{"subject", "topic" (may be ""), "hits", "weight"}, ...]
    """
    from app.auth.database import SessionLocal, WrongAnswer  # local: avoids import cycle at load
    from sqlalchemy import select

    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(WrongAnswer)
                .where(WrongAnswer.student_id == user_id)
                .order_by(WrongAnswer.created_at.desc())
                .limit(recent_n)
            )
            .scalars()
            .all()
        )
    finally:
        db.close()

    agg: dict = {}
    for idx, r in enumerate(rows):
        key = ((r.subject or "").strip(), (r.topic or "").strip())
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
            out.append({
                "subject": str(r.get("subject") or "").strip(),
                "topic": str(r.get("topic") or "").strip(),
                "text": text,
                "options": options,
                "answer": ans,
                "explanation": str(r.get("explanation") or "").strip(),
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
    prompt = _VERIFY_PROMPT.format(
        text=question["text"],
        o0=question["options"][0], o1=question["options"][1],
        o2=question["options"][2], o3=question["options"][3],
    )
    try:
        raw = client.generate([{"role": "user", "content": prompt}],
                              max_tokens=200, timeout=timeout)
    except Exception as exc:
        logger.warning("Verifier call failed: %s", exc)
        return None
    return _parse_verify_answer(raw)


def _generate_replacement(client, user_id: int, question: dict,
                          difficulty: str, max_tokens: int,
                          timeout: float) -> Optional[dict]:
    """Regenerate ONE question for a discarded slot (same subject/topic)."""
    topic = question.get("topic") or ""
    row = {"name": question["subject"], "questions": 1, "minutes": 1}
    context = retrieve_book_context(user_id, [question["subject"]],
                                    [topic] if topic else [], per_subject=2)
    prompt = build_booklet_prompt([row], [topic] if topic else [],
                                  difficulty, context)
    raw = client.generate([{"role": "user", "content": prompt}],
                          max_tokens=max_tokens, timeout=timeout)
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
) -> List[dict]:
    """Independently re-solve every question; replace the broken ones.

    For each question a separate solver call (small max_tokens, cheap) sees
    only the question text and options and returns the option it computed.
    Verdict per question:
      - solver index == stored answer               -> keep as-is
      - solver clean but different, OR solver could
        not produce a clean 0-3 index at all        -> discard, regenerate a
        replacement for the same subject/topic, verify that too
    At most `max_regens` replacement attempts per question so an ambiguous
    topic can't loop forever; if nothing verifies by then, the best-scoring
    attempt is kept with a warning (verified > solvable-but-different >
    unsolvable) - booklet size never shrinks. Replacements inherit the
    original's "_id" and plan-enforced "subject".
    """
    if not questions:
        return questions
    client = get_pool_llm_client()

    def _score(verdict: Optional[int], stated: int) -> int:
        if verdict == stated:
            return 2
        return 1 if verdict is not None else 0

    out: List[dict] = []
    seen_texts: set = set()
    for q in questions:
        verdict = _verify_question(client, q, timeout)
        if verdict == q["answer"]:
            out.append(q)
            seen_texts.add(_norm_qtext(q["text"]))
            continue

        best, best_score = q, _score(verdict, q["answer"])
        for attempt in range(1, max_regens + 1):
            repl = _generate_replacement(client, user_id, q, difficulty,
                                         gen_max_tokens, timeout)
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
            s = _score(repl_verdict, repl["answer"])
            if s > best_score:
                best, best_score = repl, s
            if s == 2:
                break
        if best_score < 2:
            logger.warning(
                "Verify: %s question never verified after %d regen "
                "attempt(s); keeping best attempt (score %d).",
                q["subject"], max_regens, best_score)
        if best is not q:
            best["_id"] = q["_id"]
            best["subject"] = q["subject"]  # plan spelling wins
        out.append(best)
        seen_texts.add(_norm_qtext(best["text"]))
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


def _generate_subject_questions(user_id: int, row: dict, topics: List[str],
                                difficulty: str, max_tokens: int,
                                timeout: float) -> List[dict]:
    """One subject -> one (retried) LLM call. Subject name is enforced from
    the plan row so scoring/grouping never depends on the model's spelling.
    A row may carry "topics" (per-subject topic targets) and "weak" (weak-area
    entries) from bias_plan; row-level values win over the global topics."""
    count = int(row.get("questions") or 0)
    subject = row["name"]
    row_topics = row.get("topics") or topics
    context = retrieve_book_context(user_id, [subject], row_topics)
    if not (context or "").strip():
        # Make the ungrounded path VISIBLE: this subject's questions come from
        # general model knowledge, not the student's books. Logged per subject
        # (not per booklet) so a partial grounding failure is still diagnosable
        # from the logs afterwards.
        logger.warning(
            "Booklet grounding MISS: subject %r generated with zero book "
            "context (user %s) - questions will be LLM-knowledge-only.",
            subject, user_id,
        )
    # ~90 output tokens per question (Persian text + 4 options + explanation)
    budget = max(max_tokens, count * 90)

    rows: List[dict] = []
    for attempt, target in enumerate((count, max(3, count // 2))):
        prompt = build_booklet_prompt([{**row, "questions": target}],
                                      row_topics, difficulty, context,
                                      weak_block=_weak_block(row.get("weak") or []))
        raw = get_pool_llm_client().generate(
            [{"role": "user", "content": prompt}],
            max_tokens=budget, timeout=timeout,
        )
        rows = parse_booklet(raw)
        if len(rows) >= count // 2:
            break
        logger.warning("Subject %s: attempt %d produced %d/%d valid questions.",
                       subject, attempt + 1, len(rows), count)

    rows = pad_booklet(rows[:count])
    for r in rows:
        r["subject"] = subject  # plan row wins over LLM spelling
    return rows


def generate_booklet(
    user_id: int,
    plan: List[dict],
    topics: Optional[List[str]] = None,
    difficulty: str = "konkur",
    max_tokens: int = 6000,
    timeout: float = 420.0,
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

    for row in (dict(s) for s in plan):
        if int(row.get("questions") or 0) <= 0:
            continue
        rows = _generate_subject_questions(
            user_id, row, topics, difficulty, max_tokens, timeout)
        if not rows:
            logger.warning("Booklet: subject %s produced nothing; skipping.",
                           row["name"])
            continue
        for r in rows:
            r["_id"] = next_id
            next_id += 1
            questions.append(r)

    if not questions:
        logger.warning("Booklet generation returned no valid questions "
                       "(user %s, plan=%s).", user_id, [s["name"] for s in plan])
    return questions
