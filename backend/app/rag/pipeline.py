from pathlib import Path
from typing import List, Dict, Optional, Generator
import json
import re

from app.config import get_settings
from app.rag.embeddings import get_embedding_model
from app.rag.vector_store import get_vector_store, get_image_vector_store
from app.rag.llm import get_llm_client, get_vision_llm_client, MockLLMClient
from app.auth import limits as _limits


def _record_call_tokens(user_id: int, client) -> None:
    """Charge the tokens of the last generate()/generate_stream() on `client`
    to the user's daily token budget. Success-only: MockLLMClient and failed
    calls report zero usage, so they never consume budget."""
    try:
        _limits.record_token_use(user_id, int(client.last_usage.total_tokens))
    except Exception:  # accounting must never break the AI response
        logger.exception("token accounting failed")
from app.schemas import ChatMessage, SourceChunk
from app.utils.logger import get_logger
from app.rag.hybrid_search import get_hybrid_search


# Initialize application logger
logger = get_logger(__name__)


# filename -> source-category resolver (filled lazily from the raw folder
# tree so retrieval can scope by category even for pre-category documents).
_image_category_map: Dict[str, str] = {}


# System instructions for the LLM
SYSTEM_PROMPT = """تو «بوم» هستی؛ مربی هوشمند کنکور و دستیار مطالعاتی دانش‌آموز.
قوانین پاسخ‌دهی:
۱. برای اطلاعات درسی، آموزشی، برنامه‌ریزی مبتنی بر منابع و مطالبی که نیاز به مرجع دارند، فقط از «متن‌های مرجع» استفاده کن.
۲. ادعاهای مبتنی بر منابع را با [منبع N] در همان بخش مشخص کن.
۳. اگر پاسخ در منابع موجود نیست، صادقانه بگو که در منابع فعلی اطلاعات کافی وجود ندارد؛ حدس نزن.
۴. برای برنامه‌ریزی، محدودیت‌های دانش‌آموز مثل زمان روزانه، درس‌های ضعیف، هدف و موعد آزمون را رعایت کن.
۵. پاسخ را به فارسی روان، کوتاه و ساختاریافته بنویس.
۶. اگر کاربر درخواست برنامه چندماهه کرد، برنامه را به ماه، هفته و الگوی روزانه تقسیم کن و امکان جبران عقب‌افتادگی را هم توضیح بده.
۷. «برنامه مطالعه کاربر» که در سوال آمده را مبنا بگیر؛ دانش‌آموز ممکن است آن را دستی تغییر داده باشد، پس همیشه با آخرین نسخه‌ی اعلام‌شده کار کن.
۸. اگر کاربر خواست بلوکی را لغو/حذف کند، همان بلوک را حذف کن و آن را در جای دیگری یا روز دیگری دوباره اضافه نکن، مگر اینکه کاربر صریحاً بخواهد زمانش به روز دیگری منتقل شود (مثلاً بگوید «وقتهای خالی را روی بقیه روزها بگذار»). جابه‌جایی یعنی حذف بلوک قبلی + اضافه کردن در زمان جدید.
۹. اگر کاربر تغییر برنامه هفتگی خواست (اضافه/حذف/جابه‌جایی/کاهش/افزایش بلوک)، اول یک پاسخ کوتاه فارسی بده و سپس تغییرات را به صورت «تفاوت» خروجی بده و بعد از آن هیچ متن دیگری ننویس:
###UPDATE_PLAN###
{"blocks":[{"day":1,"startHour":18,"duration":2,"title":"مطالعه فیزیک","type":"study","count":null}],"removed":[{"day":1,"startHour":6,"duration":2,"title":"مطالعه فیزیک","type":"study","count":null}],"note":"توضیح کوتاه"}
معنی فیلدها:
- removed: بلوک‌هایی که باید از برنامه کاربر حذف شوند. برای هر بلوک حذفی، day و startHour و title را دقیقاً مطابق همان چیزی که در «برنامه مطالعه کاربر» آمده است بنویس (همان ساعت شروع قبلی). اگر کاربر خواست بلوکی جابه‌جا شود یا حذف شود، حتماً بلوک قبلی را در removed بگذار؛ در غیر این صورت برنامه قدیمی حذف نمی‌شود.
- blocks: بلوک‌هایی که باید اضافه شوند یا جایگزین بلوک موجود شوند (با همان day و startHour اگر جایگزین همان ساعتی است).
- فقط بلوک‌هایی را تغییر بده که کاربر خواسته؛ بقیه بلوک‌ها را در خروجی نیاور.
نکته مهم درباره day: در «برنامه مطالعه کاربر» هر روز با [day=N] و نام فارسی آمده است؛ حتماً از همان مقدار عددی day استفاده کن (۰=شنبه، ۱=یکشنبه، ۲=دوشنبه، ۳=سه‌شنبه، ۴=چهارشنبه، ۵=پنجشنبه، ۶=جمعه).
type فقط یکی از: study, test, class, break. بلوک‌های تست باید با [منبع N] یا نام کتاب مشخص شوند.
۱۰. اگر کاربر مثلاً خواست «بعد از هر جلسه مطالعه ۳۰ دقیقه استراحت اضافه شود»، این تغییر برای همه روزهایی که آن الگو را دارند اعمال شود، نه فقط یک روز.
۱۱. «بلوکهای ثابت هفتگی» هر هفته در همان روز و ساعت تکرار میشوند (مثلاً کلاس ۱۶ تا ۱۸). آنها را حذف یا جابهجا نکن و هیچ بلوک مطالعه/تست روی آن ساعتها نگذار.
۱۲. اگر دانشآموز خواست برنامه را با کتاب/تست تنظیم کند ولی «متنهای مرجع» محتوایی نداشتند، از «منابع موجود در سامانه» مناسبترین کتاب را بر اساس رشته و پایه انتخاب کن و در پیشنهادت به همان نام اشاره کن (مثلاً «۲۰ تست فیزیک از فیزیک ۱ خیلی سبز»). از کاربر نپرس کدام کتاب؛ مگر اینکه واقعاً هیچ منبعی برای آن درس در سامانه نباشد.
۱۳. بازه صفحه (مثل صفحات ۱۵۴ تا ۲۳۴) را فقط وقتی در مرجع یا برنامه آزمون وارد شده است بنویس؛ هرگز صفحه را حدس نزن."""


# System instructions for the vision LLM (page-as-image pipeline)
IMAGE_SYSTEM_PROMPT = """تو دستیار هوشمند دانشگاه صنعتی خواجه نصیرالدین طوسی هستی.
به تو تصاویری از صفحات اسناد دانشگاهی داده می‌شود؛ متن، جدول‌ها، نمودارها و طرح‌بندی هر صفحه را مستقیماً از روی تصویر بخوان.

قوانین پاسخ‌دهی:
۱. فقط بر اساس چیزی که در تصاویر ارائه‌شده می‌بینی پاسخ بده.
۲. در انتهای هر جمله یا ادعا، شماره تصویر مربوطه را بنویس (مثال: «شرایط ثبت‌نام برای ترم جدید اعلام شد [تصویر ۱].»).
۳. اگر پاسخ سوال در تصاویر ارائه‌شده موجود نیست، صادقانه بگو که اطلاعات کافی در اسناد موجود نیست و از خودت حدس نزن.
۴. اگر متن مرجع تکمیلی هم داده شده، می‌توانی همراه با تصاویر از آن استفاده کنی.
۵. پاسخ را به زبان فارسی روان، روشن و ساختاریافته بنویس."""


# Build a single context string from retrieved chunks
def _build_context_block(chunks: List[dict]) -> str:
    parts = []

    for idx, c in enumerate(chunks, start=1):
        parts.append(
            f"--- [منبع {idx}] (نام سند: {c['document_name']}) ---\n{c['content']}"
        )

    return "\n\n".join(parts)


# Persian day labels matching the frontend schedule (0 = شنبه).
_DAY_LABELS = [
    "شنبه",
    "یکشنبه",
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنجشنبه",
    "جمعه",
]


def _fmt_range(start: float, duration: float) -> str:
    try:
        s = float(start)
        d = float(duration)
        fmt = lambda v: f"{int(v):02d}:{int(round((v - int(v)) * 60)):02d}"
        return f"{fmt(s)}–{fmt(s + d)}"
    except (TypeError, ValueError):
        return f"{start}–{start + duration if isinstance(start, (int, float)) and isinstance(duration, (int, float)) else ''}"


# Build a compact Persian summary of the user's weekly plan so the LLM
# always plans against the latest official version of the schedule.
def _schedule_context(schedule: Optional[dict]) -> str:
    if not schedule:
        return "برنامه مطالعه کاربر در دسترس نیست."

    parts = ["--- برنامه مطالعه کاربر (این هفته) ---"]
    week_start = schedule.get("week_start", "نامشخص")
    parts.append(f"هفته (تاریخ شروع): {week_start}")

    # Say explicitly which day is "today" so requests like "امروز" resolve
    # to the correct block instead of the model guessing the first day.
    try:
        from datetime import date, timedelta as _td
        ws = date.fromisoformat(str(week_start)[:10])
        today_idx = (date.today() - ws).days
        if 0 <= today_idx <= 6:
            parts.append(
                f"امروز: {_DAY_LABELS[today_idx]} (day={today_idx})"
            )
    except Exception:
        pass

    blocks = schedule.get("blocks") or []
    if not blocks:
        parts.append("* هیچ بلوک زمانی در این هفته ثبت نشده است.")
    else:
        for b in blocks:
            day = b.get("day")
            start = b.get("startHour")
            dur = b.get("duration")
            label = _DAY_LABELS[day] if isinstance(day, int) and 0 <= day <= 6 else str(day)
            day_num = int(day) if isinstance(day, int) and 0 <= day <= 6 else "?"
            parts.append(
                f"- [day={day_num}] {label}: {_fmt_range(start, dur)} | {b.get('title', '')} "
                f"| نوع: {b.get('type', '')}"
                + (f" | تعداد تست: {b.get('count')}" if b.get("count") else "")
            )

    statics = schedule.get("statics") or []
    if statics:
        parts.append("بلوکهای ثابت هفتگی (هر هفته در همان روز و ساعت تکرار میشوند؛ روی این ساعتها برنامه نگذار):")
        for s in statics:
            day = s.get("day")
            try:
                day_i = int(day)
            except (TypeError, ValueError):
                day_i = -1
            label = _DAY_LABELS[day_i] if 0 <= day_i <= 6 else str(s.get("date") or day)
            day_num = day_i if 0 <= day_i <= 6 else "?"
            parts.append(
                f"- [day={day_num}] {label}: {_fmt_range(s.get('startHour'), s.get('duration'))} "
                f"| {s.get('title', '')} | نوع: {s.get('type', '')}"
            )

    return "\n".join(parts)


# Build the message list sent to the LLM
# --- Simple-message gate -------------------------------------------------
# Greetings and short chit-chat ("سلام", "ممنون", "خوبی؟") and simple
# self-contained questions ("مشتق 2x چی میشه؟", "آب چند درجه میجوشه؟")
# need no book retrieval. Running the full RAG path for them wasted an
# LLM query-rewrite call + embeddings + searches per message, which is
# exactly how free-tier rate limits (429) got hit. Heuristic only - it
# errs toward retrieval, so real study/book/plan questions still go
# through the grounded path.
_SIMPLE_GREETINGS = (
    "سلام", "درود", "هی", "های", "hi", "hello", "hey",
    "ممنون", "مرسی", "دستت درد نکنه", "خواهش", "مچکریم",
    "خوبی", "چطوری", "چه خبر", "خسته نباشی", "عصر بخیر", "صبح بخیر",
    "بدرود", "خداحافظ", "bye", "اوکی", "اوکیه", "باشه", "چشم",
)
_SIMPLE_QUESTION_RE = re.compile(
    r"^[\s\w\d؟?.,!+\-*/^()=<>%ضصثقفغعهخحجچشسیبلاتنمکگظطزرذدپوءأئؤإآ]*$"
)
# Words that mark a message as needing grounded retrieval even when it is
# short: planning/schedule/books/tests - things only this system's data can
# answer. Plain concept questions ("مشتق 2x چی میشه؟") stay direct: the LLM
# knows them without any book.
_GROUNDED_HINTS = re.compile(
    r"کنکور|کتاب|تست|برنامه|آزمون|ماز|قلم‌چی|سنجش|مبحث|فصل|صفحه|درس|"
    r"سرفصل|مرور|جمع‌بندی|خلاصه|تدریس|روزانه|هفتگی|تقویم|زمان‌بندی"
)


def _is_simple_message(question: str) -> bool:
    """True when the question needs no book retrieval (short chit-chat or a
    simple self-contained question). Conservative by design."""
    q = (question or "").strip()
    if not q:
        return True
    if len(q) > 60:
        return False
    lowered = q.lower()
    # Greetings/thanks - exact token match on any whitespace-separated word
    tokens = re.split(r"[\s،,!?.؟]+", lowered)
    if any(t in _SIMPLE_GREETINGS for t in tokens if t):
        return True
    # Anything mentioning study topics/plans/books always goes to RAG.
    if _GROUNDED_HINTS.search(q):
        return False
    # Short plain questions without book-ish keywords: simple.
    if len(q) <= 30 and _SIMPLE_QUESTION_RE.match(q):
        return True
    return False


def _build_messages(
    question: str,
    context_chunks: List[dict],
    history: Optional[List[ChatMessage]],
    student: Optional[dict] = None,
    schedule: Optional[dict] = None,
) -> List[Dict[str, str]]:

    # Start with the system prompt
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # Add the last few conversation messages to preserve context
    if history:
        for h in history[-12:]:
            messages.append({
                "role": h.role,
                "content": h.content
            })

    # Build context from retrieved chunks
    context_block = _build_context_block(context_chunks)

    # The available reference sources (book catalog from the raw folder tree)
    # ground plan/test suggestions in real books, even before per-page OCR
    # content is indexed.
    try:
        from app.routers.boom_ai import book_catalog
        catalog = "، ".join(book_catalog())
    except Exception:
        catalog = ""
    catalog_block = (
        f"منابع موجود در سامانه (کتاب‌های فایل‌شده):\n{catalog}\n\n"
        if catalog else ""
    )

    # Combine retrieved context and user's question
    student_block = "\n".join(f"- {k}: {v}" for k, v in (student or {}).items()) or "اطلاعات پروفایل موجود نیست."
    plan_block = _schedule_context(schedule)
    user_content = (
        f"اطلاعات دانش‌آموز:\n{student_block}\n\n"
        f"{plan_block}\n\n"
        f"متن‌های مرجع:\n{context_block}\n\n"
        f"سوال کاربر: {question}"
        if context_chunks
        else f"{plan_block}\n\n{catalog_block}سوال کاربر: {question}"
    )

    messages.append({
        "role": "user",
        "content": user_content
    })

    return messages


# Build the message list sent to the vision LLM (page-as-image pipeline)
def _build_image_messages(
    question: str,
    image_hits: List[dict],
    text_chunks: Optional[List[dict]],
    history: Optional[List[ChatMessage]],
    schedule: Optional[dict] = None,
) -> List[Dict[str, str]]:

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": IMAGE_SYSTEM_PROMPT}
    ]

    if history:
        for h in history[-12:]:
            messages.append({"role": h.role, "content": h.content})

    # Label each attached image so the model's citations ("[تصویر ۱]")
    # line up with the order images are actually sent in.
    image_labels = "\n".join(
        f"--- [تصویر {idx}] (سند: {hit['document_name']}، صفحه {hit['chunk_index'] + 1}) ---"
        for idx, hit in enumerate(image_hits, start=1)
    )

    parts = [f"تصاویر پیوست‌شده:\n{image_labels}" if image_hits else "هیچ تصویری یافت نشد."]

    # Any hits from the regular text pipeline (TXT/MD, or PDFs ingested in
    # text mode) are appended as extra reference text alongside the images,
    # so a mixed corpus (some docs image-mode, some text-mode) still works
    # in a single answer.
    if text_chunks:
        text_context = _build_context_block(text_chunks)
        parts.append(f"متن‌های مرجع تکمیلی:\n{text_context}")

    parts.append(f"برنامه مطالعه کاربر:\n{_schedule_context(schedule)}")
    parts.append(f"سوال کاربر: {question}")

    messages.append({
        "role": "user",
        "content": "\n\n".join(parts)
    })

    return messages


QUERY_REWRITE_PROMPT = """تو یک دستیار بازنویسی سوال برای سیستم RAG آموزشی «بوم» هستی.
سوال محاوره‌ای کاربر را به یک پرسش دقیق و حاوی کلیدواژه‌های اصلی تبدیل کن تا جستجو در منابع کنکور و آموزشی بهتر انجام شود.
فقط عبارت بازنویسی‌شده را خروجی بده و هیچ توضیح اضافه ننویس.
اگر سوال واضح است، همان را بدون تغییر برگردان.

سوال کاربر: {question}
پاسخ بازنویسی‌شده:"""


def rewrite_query(question: str, user_id: Optional[int] = None) -> str:
    """Rewrite a user query into a formal, keyword-rich search query."""
    llm_client = get_llm_client()

    messages = [
        {
            "role": "user",
            "content": QUERY_REWRITE_PROMPT.format(question=question)
        }
    ]

    try:
        # این مرحله فقط باید یک جمله‌ی کوتاه برگرداند، پس max_tokens کوچک
        # و یک سقف زمانی سخت‌گیرانه (۱۵ ثانیه) دارد تا در صورت کند بودن
        # مدل (مثلا روی CPU-only)، به‌جای معطل ماندن طولانی، سریع به سوال
        # اصلی کاربر برگردیم.
        rewritten = llm_client.generate(
            messages, max_tokens=150, timeout=60).strip()
        if user_id is not None:
            _record_call_tokens(user_id, llm_client)

        looks_invalid = (
            not rewritten
            or len(rewritten) > len(question) * 5 + 100
            or "متاسفانه مدل نتوانست" in rewritten
        )
        if looks_invalid:
            logger.warning(
                "Query rewriting produced an invalid/empty result; falling back to original question."
            )
            return question

        logger.info(
            f"Original Query: '{question}' -> Rewritten Query: '{rewritten}'")
        return rewritten
    except Exception as e:
        logger.warning(
            f"Query rewriting failed: {e}. Falling back to original question.")
        return question


def _load_page_images(
    image_hits: List[dict],
) -> tuple[List[dict], List[bytes]]:
    """Load page-image bytes for image hits, skipping missing files.

    Retrieval matches vector-store entries, but the underlying PNG can be
    missing (fresh checkout / server without the synced data/page_images
    tree). One missing file must never 500 the whole chat: hits without a
    readable image are dropped with a warning. Returns (usable_hits, bytes).
    If nothing loads at all, both lists come back empty and the caller
    should fall back to text-only answering.
    """
    from app.utils.storage import get_object

    loaded: List[bytes] = []
    usable_hits: List[dict] = []
    for hit in image_hits:
        try:
            loaded.append(get_object(hit["content"]))
            usable_hits.append(hit)
        except FileNotFoundError:
            logger.warning(
                "Page image missing on disk, skipping: %s", hit["content"]
            )
        except Exception as exc:  # unreadable/corrupt file: same treatment
            logger.warning(
                "Page image unreadable (%s), skipping: %s", exc, hit["content"]
            )
    return usable_hits, loaded


def _retrieve_image_hits(
    search_query: str,
    user_id: int,
    k: int,
    category: Optional[str] = None,
) -> List[dict]:
    """Retrieve only *relevant* page images for a query.

    Chroma always returns the nearest neighbours when a collection contains
    anything, even when every neighbour is a poor match.  Passing those
    neighbours to the vision model makes unrelated PDFs/images hijack normal
    chat questions.  We therefore retrieve a few extra candidates and apply
    an explicit cosine-similarity cutoff before enabling the vision path.

    When ``category`` is given, the search is scoped to that source category
    (e.g. only the plan/mock documents) and the similarity cutoff is skipped:
    within an already-topical category every candidate is useful, even at
    the flat 0.20-0.30 CLIP band shared by small table-heavy PDFs.
    """
    from app.config import get_settings
    from app.rag.image_embeddings import get_image_embedding_model

    try:
        settings = get_settings()
        image_vector_store = get_image_vector_store()
        if image_vector_store.collection.count() == 0:
            return []

        image_embedder = get_image_embedding_model()
        query_embedding = image_embedder.embed_query(search_query)

        # filename -> category map for documents embedded before categories
        # existed (their metadata lacks the field, but their raw folder says it).
        try:
            from app.rag.ingest_raw import document_category_map
            _image_category_map.update(document_category_map())
        except Exception:
            pass

    # Retrieve extra candidates, then filter by actual similarity.

        candidate_k = max(k * 4, 20) if category else max(k * 3, 10)
        candidates = image_vector_store.similarity_search(
            query_embedding=query_embedding,
            top_k=candidate_k,
            user_id=user_id,
            category=category,
        )

        for hit in candidates:
            hit["category"] = str(
                hit.get("category") or _image_category_map.get(hit.get("document_name", ""), "")
            )

        if category:
            relevant = [h for h in candidates if h.get("category") == category]
            threshold = 0.0  # scoped category already guarantees topical fit
        else:
            threshold = settings.IMAGE_RELEVANCE_THRESHOLD
            relevant = [
                hit for hit in candidates
                if float(hit.get("score", 0.0)) >= threshold
            ]

        # Keep the requested number of best relevant pages only.
        relevant = relevant[:k]

        logger.info(
            "Image retrieval: %d candidate(s), %d relevant page(s), "
            "threshold=%.3f for user %s.",
            len(candidates), len(relevant), threshold, user_id,
        )
        return relevant
    except Exception as e:
        logger.warning(f"Image retrieval failed, continuing with text-only: {e}")
        return []


def _render_qbank_page_image(book: str, page: int) -> Optional[str]:
    """Render one raw-PDF page to PNG (cached in storage); returns the key.

    Question-bank chunks point at real book pages that were never ingested
    through the app, so their page images don't exist in storage yet. Render
    on demand from the raw PDF and cache under page_images/qbank/ so later
    reads (and the vision model) get the real figure-bearing page.
    """
    from app.utils.storage import get_object, put_object

    key = f"page_images/qbank/{book}/page_{page:04d}.png"
    try:
        get_object(key)  # already rendered
        return key
    except Exception:
        pass

    try:
        from app.rag.ingest_raw import list_raw_pdfs

        pdf = next((p for p in list_raw_pdfs() if p.stem == book), None)
        if pdf is None:
            return None
        import pymupdf

        with pymupdf.open(pdf) as doc:
            if not (1 <= page <= doc.page_count):
                return None
            pix = doc[page - 1].get_pixmap(dpi=150)
            put_object(key, pix.tobytes("png"))
        return key
    except Exception as exc:
        logger.warning("Could not render page image for %s p%d: %s", book, page, exc)
        return None


def _retrieve_question_bank_chunks(
    search_query: str,
    user_id: int,
    top_k: int = 5,
) -> List[dict]:
    """Retrieve structured question-bank chunks (vision transcriptions).

    Each hit is one printed question / lesson-prose / figure chunk carrying
    the question number, options and a text description of any figure - the
    retrieval layer that actually "understands" shapes, symbols and question
    numbering. Fails soft (returns []) when the bank is empty/unavailable.
    """
    try:
        from app.rag.hybrid_search import get_question_hybrid_search

        embedding = get_embedding_model().embed_query(search_query)
        return get_question_hybrid_search().search(
            query_text=search_query,
            query_embedding=embedding,
            user_id=user_id,
            top_k=top_k,
        )
    except Exception as exc:
        logger.warning("Question-bank retrieval unavailable: %s", exc)
        return []


def _resolve_ocr_page_images(
    text_chunks: List[dict],
    user_id: int,
) -> List[dict]:
    """Turn OCR text hits into exact page-image hits.

    The OCR corpus stores each book page as ``[صفحه N] ...`` in the text
    store.  When a retrieved chunk carries that marker, the underlying page
    PNG has already been rendered by the OCR job -- so we serve the actual
    *image* to the vision model, preserving figures, shapes and formulas that
    OCR text alone cannot represent.  Returns image-hit dicts compatible with
    ``_retrieve_image_hits`` output.
    """
    import re as _re

    from app.utils.storage import get_object

    marker = _re.compile(r"\[صفحه\s*([0-9۰-۹]+)\]\s*")
    hits: List[dict] = []
    seen = set()
    for c in text_chunks:
        # Question-bank chunks carry book/page metadata directly; their page
        # images are rendered on demand from the raw PDF (see helper above).
        if c.get("category") == "question_bank" and c.get("book") and c.get("page") is not None:
            name = str(c["book"])
            try:
                page = int(c["page"])
            except (TypeError, ValueError):
                continue
            key = _render_qbank_page_image(name, page)
            if not key:
                continue
        else:
            name = c.get("document_name", "")
            m = marker.search(c.get("content", "") or "")
            if not m:
                continue
            try:
                page = int(m.group(1).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
            except ValueError:
                continue
            key = f"{user_id}/{name}/page_{page:04d}.png"
            try:
                get_object(key)
            except Exception:
                continue  # page image not rendered for this book -> text chunk only
        dedupe = (name, page)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        hits.append({
            "document_name": name,
            "chunk_index": page - 1,
            "content": key,
            "score": float(c.get("score") or 0.0),
        })
    if hits:
        logger.info("OCR text hits resolved %d page image(s) for the vision read.", len(hits))
    return hits


# Answer a user question using the RAG pipeline (Non-streaming)
def answer_question(
    question: str,
    user_id: int,
    history: Optional[List[ChatMessage]] = None,
    top_k: Optional[int] = None,
    student: Optional[dict] = None,
    schedule: Optional[dict] = None,
) -> Dict:

    settings = get_settings()
    k = top_k or settings.TOP_K

    if schedule is not None and question:
        # "Which tests should I do today?" -> dedicated recommender that ties
        # today's schedule, the week's mock exam topics and the OCR'd test
        # books together, instead of the generic RAG.
        try:
            from app.routers.boom_ai import maybe_daily_tests
            rec = maybe_daily_tests(question, user_id, student or {}, schedule)
            if rec:
                return {
                    "answer": rec["answer"],
                    "sources": [
                        SourceChunk(
                            document_name=s["document_name"],
                            chunk_index=s["chunk_index"],
                            content=s["content"],
                            score=float(s.get("score", 0.0)),
                        )
                        for s in rec.get("sources", [])
                    ],
                }
        except Exception:
            pass

    # Simple messages (greetings, short self-contained questions) skip the
    # whole retrieval machinery: no query-rewrite LLM call, no embeddings,
    # no book/image search. They burn quota without helping the answer.
    if _is_simple_message(question):
        logger.info("Simple message detected; skipping retrieval for user %s.", user_id)
        messages = _build_messages(question, [], history, student, schedule)
        llm_client = get_llm_client()
        answer_text = llm_client.generate(messages)
        _record_call_tokens(user_id, llm_client)
        return {"answer": answer_text, "sources": []}

    embedding_model = get_embedding_model()
    hybrid_search = get_hybrid_search()

    search_query = rewrite_query(question, user_id=user_id)
    query_embedding = embedding_model.embed_query(search_query)

    # Text retrieval: covers TXT/MD, plus any PDFs ingested in text mode
    retrieved_chunks = hybrid_search.search(
        query_text=search_query,
        query_embedding=query_embedding,
        user_id=user_id,
        top_k=k,
    )

    # Question bank: structured per-question chunks (text, options, figure
    # descriptions) from the vision transcriptions. Ranked ahead of generic
    # text chunks - they answer "which printed question is this?" precisely.
    qa_hits = _retrieve_question_bank_chunks(search_query, user_id, top_k=max(4, k // 2))
    if qa_hits:
        qa_ids = {c.get("id") for c in qa_hits}
        retrieved_chunks = qa_hits + [
            c for c in retrieved_chunks if c.get("id") not in qa_ids
        ]

    # Image retrieval: covers PDFs ingested in "page-as-image" mode
    image_hits = _retrieve_image_hits(search_query, user_id, settings.IMAGE_TOP_K)
    if not image_hits and retrieved_chunks:
        image_hits = _resolve_ocr_page_images(retrieved_chunks, user_id) or []

    logger.info(
        f"{len(retrieved_chunks)} text chunk(s) and {len(image_hits)} page image(s) "
        f"retrieved for user {user_id}."
    )

    vision_llm = get_vision_llm_client()
    # Only use vision if we have image hits and we actually have a real vision LLM (not the MockLLMClient)
    use_vision = bool(image_hits) and not isinstance(vision_llm, MockLLMClient)

    if use_vision:
        # Load the images defensively: one missing file must not 500 the
        # whole chat (regression: FileNotFoundError crashed boom_chat).
        image_hits, image_paths = _load_page_images(image_hits)
        if not image_hits:
            logger.warning(
                "Vision path had image hit(s) but no image files exist on "
                "disk; falling back to text-only answering."
            )
            # Hits already dropped by the helper, so the text-only path
            # below cannot cite pages the model never actually saw.
            use_vision = False
    if use_vision:
        messages = _build_image_messages(question, image_hits, retrieved_chunks, history, schedule)
        answer_text = vision_llm.generate(messages, images=image_paths)
        _record_call_tokens(user_id, vision_llm)

        sources = [
            SourceChunk(
                document_name=hit["document_name"],
                chunk_index=hit["chunk_index"],
                content=f"صفحه {hit['chunk_index'] + 1}",
                score=hit["score"],
            )
            for hit in image_hits
        ] + [
            SourceChunk(
                document_name=c["document_name"],
                chunk_index=c["chunk_index"],
                content=c["content"],
                score=c["hybrid_score"],
            )
            for c in retrieved_chunks
        ]
        return {"answer": answer_text, "sources": sources}


    llm_client = get_llm_client()
    messages = _build_messages(question, retrieved_chunks, history, student, schedule)
    answer_text = llm_client.generate(messages)
    _record_call_tokens(user_id, llm_client)
    sources = [
        SourceChunk(
            document_name=hit["document_name"],
            chunk_index=hit["chunk_index"],
            content=f"صفحه {hit['chunk_index'] + 1}",
            score=hit["score"],
        )
        for hit in image_hits
    ] + [
        SourceChunk(
            document_name=c["document_name"],
            chunk_index=c["chunk_index"],
            content=c["content"],
            score=c["hybrid_score"],
        )
        for c in retrieved_chunks
    ]

    return {
        "answer": answer_text,
        "sources": sources
    }


# Streaming variant for live chunk-by-chunk response
def answer_question_stream(
    question: str,
    user_id: int,
    history: Optional[List[ChatMessage]] = None,
    top_k: Optional[int] = None,
    schedule: Optional[dict] = None,
) -> Generator[str, None, None]:
    """Stream answer chunks along with initial metadata (sources) using NDJSON protocol."""

    settings = get_settings()
    k = top_k or settings.TOP_K

    # Daily-tests recommender hook (streaming form).
    if schedule is not None and question:
        try:
            from app.routers.boom_ai import maybe_daily_tests
            rec = maybe_daily_tests(question, user_id, {}, schedule)
            if rec:
                yield json.dumps(
                    {"type": "sources", "data": [
                        {
                            "document_name": s["document_name"],
                            "chunk_index": s["chunk_index"],
                            "content": s["content"],
                            "score": float(s.get("score", 0.0)),
                        } for s in rec.get("sources", [])
                    ]}
                ) + "\n"
                yield json.dumps(
                    {"type": "status", "data": "بر اساس برنامه امروز و آزمون هفته، تست‌های پیشنهادی:"}
                ) + "\n"
                for line in (rec["answer"] or "").split("\n"):
                    while len(line) > 150:
                        yield json.dumps({"type": "text", "data": line[:150]}) + "\n"
                        line = line[150:]
                    if line:
                        yield json.dumps({"type": "text", "data": line}) + "\n"
                return
        except Exception:
            pass

    # Simple messages (greetings, short self-contained questions) skip the
    # whole retrieval machinery - same rationale as the non-streaming path.
    if _is_simple_message(question):
        logger.info("Simple message detected; skipping retrieval (streaming) for user %s.", user_id)
        yield json.dumps({"type": "sources", "data": []}) + "\n"
        yield json.dumps({"type": "status", "data": "در حال نگارش پاسخ..."}) + "\n"
        llm_client = get_llm_client()
        messages = _build_messages(question, [], history, None, None)
        for text_chunk in llm_client.generate_stream(messages):
            yield json.dumps({"type": "text", "data": text_chunk}) + "\n"
        _record_call_tokens(user_id, llm_client)
        return

    embedding_model = get_embedding_model()
    hybrid_search = get_hybrid_search()

    # STEP 1: Status - Query Rewriting
    yield json.dumps({"type": "status", "data": "در حال بازنویسی و تحلیل پرسش..."}) + "\n"
    search_query = rewrite_query(question, user_id=user_id)

    # STEP 2: Status - Search
    yield json.dumps({"type": "status", "data": "در حال جستجو در اسناد و قوانین دانشگاه..."}) + "\n"
    query_embedding = embedding_model.embed_query(search_query)

    # Retrieve chunks from vector store, scoped to this user only
    retrieved_chunks = hybrid_search.search(
        query_text=search_query,
        query_embedding=query_embedding,
        user_id=user_id,
        top_k=k,
    )

    # Question bank merge (same as the non-streaming path)
    qa_hits = _retrieve_question_bank_chunks(search_query, user_id, top_k=max(4, k // 2))
    if qa_hits:
        qa_ids = {c.get("id") for c in qa_hits}
        retrieved_chunks = qa_hits + [
            c for c in retrieved_chunks if c.get("id") not in qa_ids
        ]

    # Image retrieval: covers PDFs ingested in "page-as-image" mode
    image_hits = _retrieve_image_hits(search_query, user_id, settings.IMAGE_TOP_K)

    # OCR text hits resolve to exact page images for the vision read.
    if not image_hits and retrieved_chunks:
        image_hits = _resolve_ocr_page_images(retrieved_chunks, user_id) or []

    vision_llm = get_vision_llm_client()
    use_vision = bool(image_hits) and not isinstance(vision_llm, MockLLMClient)

    logger.info(
        f"{len(retrieved_chunks)} text chunk(s) and {len(image_hits)} page image(s) "
        f"retrieved for user {user_id} (streaming). use_vision={use_vision}"
    )

    if use_vision:
        # Load the images defensively: one missing file must not break the
        # stream, and keys are storage keys - load bytes via storage, not
        # open() (regression: previously paths were passed through unread,
        # so the vision model silently received no images at all).
        image_hits, image_paths = _load_page_images(image_hits)
        if not image_hits:
            logger.warning(
                "Vision path had image hit(s) but no image files exist on "
                "disk; falling back to text-only answering (streaming)."
            )
            use_vision = False

    if use_vision:
        messages = _build_image_messages(question, image_hits, retrieved_chunks, history, schedule)

        sources_data = [
            {
                "document_name": hit["document_name"],
                "chunk_index": hit["chunk_index"],
                "content": f"صفحه {hit['chunk_index'] + 1}",
                "score": hit["score"],
            }
            for hit in image_hits
        ] + [
            {
                "document_name": c["document_name"],
                "chunk_index": c["chunk_index"],
                "content": c["content"],
                "score": c["hybrid_score"],
            }
            for c in retrieved_chunks
        ]

        yield json.dumps({"type": "sources", "data": sources_data}) + "\n"
        yield json.dumps({"type": "status", "data": "در حال بررسی تصاویر صفحات و نگارش پاسخ..."}) + "\n"

        for text_chunk in vision_llm.generate_stream(messages, images=image_paths):
            yield json.dumps({"type": "text", "data": text_chunk}) + "\n"
        _record_call_tokens(user_id, vision_llm)
        return

    # No relevant page images -> original text-only pipeline
    llm_client = get_llm_client()

    # Build message chain
    messages = _build_messages(
        question,
        retrieved_chunks,
        history
    )

    # Prepare sources list
    sources_data = [
        {
            "document_name": c["document_name"],
            "chunk_index": c["chunk_index"],
            "content": c["content"],
            "score": c["hybrid_score"],
        }
        for c in retrieved_chunks
    ]

    # Frame: Send sources payload line
    yield json.dumps({"type": "sources", "data": sources_data}) + "\n"

    # STEP 3: Status - Generating Answer
    yield json.dumps({"type": "status", "data": "در حال نگارش پاسخ نهایی..."}) + "\n"

    # Stream response text chunks from LLM line by line
    for text_chunk in llm_client.generate_stream(messages):
        yield json.dumps({"type": "text", "data": text_chunk}) + "\n"
    _record_call_tokens(user_id, llm_client)


# Process a document and store its chunks in the vector database
def ingest_document(document_name: str, raw_text: str, user_id: int) -> int:
    from app.rag.chunking import chunk_text

    settings = get_settings()

    chunks = chunk_text(
        raw_text,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP
    )

    if not chunks:
        logger.warning(
            f"No chunks were generated from document '{document_name}'."
        )
        return 0

    embedding_model = get_embedding_model()
    vector_store = get_vector_store()

    embeddings = embedding_model.embed_documents(chunks)

    result = vector_store.add_chunks(
        document_name,
        chunks,
        embeddings,
        user_id=user_id,
    )

    # Only rebuild this user's lexical index, not everyone's
    get_hybrid_search().refresh(user_id)

    return result


# Process a PDF as page images and store their embeddings ("page-as-image" pipeline)
def ingest_pdf_as_images(
    document_name: str,
    pdf_path: Path,
    user_id: int,
    dpi: Optional[int] = None,
    batch_size: Optional[int] = None,
    category: str = "",
) -> int:
    from app.rag.image_loader import pdf_to_page_images
    from app.rag.image_embeddings import get_image_embedding_model
    from app.utils.storage import get_object

    settings = get_settings()

    dpi = dpi or settings.IMAGE_DPI
    batch_size = batch_size or settings.IMAGE_BATCH_SIZE

    output_dir = Path(settings.IMAGES_DIR) / str(user_id) / Path(document_name).stem
    image_keys = pdf_to_page_images(pdf_path, user_id, document_name, dpi=dpi)

    if not image_keys:
        logger.warning(f"No pages were rendered from document '{document_name}'.")
        return 0

    image_embedder = get_image_embedding_model()
    image_vector_store = get_image_vector_store()

    # Make ingestion idempotent: drop any previous page embeddings for this
    # document before re-adding, so re-runs never duplicate chunks.
    image_vector_store.delete_document(document_name, user_id)

    total = 0
    for start in range(0, len(image_keys), batch_size):
        batch = image_keys[start:start + batch_size]
        # batch contains keys like "user_id/document_name/page_NNNN.png"
        # get_object returns the bytes for each key
        image_bytes = [get_object(key) for key in batch]
        embeddings = image_embedder.embed_images(image_bytes)
        total += image_vector_store.add_chunks(
            document_name,
            [key for key in batch],  # stored as "content": the key (R2 or local path)
            embeddings,
            user_id=user_id,
            category=category,
        )
        logger.info(
            "  '%s': embedded pages %d-%d of %d.",
            document_name,
            start + 1,
            min(start + batch_size, len(image_keys)),
            len(image_keys),
        )

    logger.info(
        f"Ingested {total} page image(s) from '{document_name}' for user {user_id} "
        f"using the '{settings.IMAGE_EMBEDDING_BACKEND}' backend."
    )

    return total
