from pathlib import Path
from typing import List, Dict, Optional, Generator
import json

from app.config import get_settings
from app.rag.embeddings import get_embedding_model
from app.rag.vector_store import get_vector_store, get_image_vector_store
from app.rag.llm import get_llm_client, get_vision_llm_client
from app.schemas import ChatMessage, SourceChunk
from app.utils.logger import get_logger
from app.rag.hybrid_search import get_hybrid_search, HybridSearch


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
۸. اگر کاربر خواست بخشی از برنامه هفتگی (یک روز یا چند بلوک) را لغو، کم یا جابه‌جا کند، ساعت‌های لغوشده را روی بقیه روزهای همان هفته توزیع کن تا حجم مطالعه و تعداد تست‌ها جبران شود.
۹. اگر کاربر تغییر برنامه هفتگی خواست، اول پاسخ کوتاه فارسی بده و سپس بلوک‌های روزهای مربوطه را طبق همین قالب خروجی بده و بعد از آن هیچ متن دیگری ننویس:
###UPDATE_PLAN###
{"blocks":[{"day":0,"startHour":6,"duration":2,"title":"مطالعه فیزیک","type":"study","count":null},{"day":1,"startHour":9,"duration":1,"title":"۲۰ تست فیزیک از کتاب منبع","type":"test","count":20}],"note":"توضیح کوتاه"}
type فقط یکی از: study, test, class, break. بلوک‌های تست باید با [منبع N] یا نام کتاب مشخص شوند."""


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

    blocks = schedule.get("blocks") or []
    if not blocks:
        parts.append("* هیچ بلوک زمانی در این هفته ثبت نشده است.")
    else:
        for b in blocks:
            day = b.get("day")
            start = b.get("startHour")
            dur = b.get("duration")
            label = _DAY_LABELS[day] if isinstance(day, int) and 0 <= day <= 6 else str(day)
            parts.append(
                f"- {label}: {_fmt_range(start, dur)} | {b.get('title', '')} "
                f"| نوع: {b.get('type', '')}"
                + (f" | تعداد تست: {b.get('count')}" if b.get("count") else "")
            )

    statics = schedule.get("statics") or []
    if statics:
        parts.append("بلوکهای ثابت هفتگی (هر هفته در همین روز و ساعت تکرار میشوند؛ روی این ساعتها برنامه نگذار):")
        for s in statics:
            day = s.get("day")
            try:
                day_i = int(day)
            except (TypeError, ValueError):
                day_i = -1
            label = _DAY_LABELS[day_i] if 0 <= day_i <= 6 else str(s.get("date") or day)
            parts.append(
                f"- {label}: {_fmt_range(s.get('startHour'), s.get('duration'))} "
                f"| {s.get('title', '')} | نوع: {s.get('type', '')}"
            )

    return "\n".join(parts)


# Build the message list sent to the LLM
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

    # Combine retrieved context and user's question
    student_block = "\n".join(f"- {k}: {v}" for k, v in (student or {}).items()) or "اطلاعات پروفایل موجود نیست."
    plan_block = _schedule_context(schedule)
    user_content = (
        f"اطلاعات دانش‌آموز:\n{student_block}\n\n"
        f"{plan_block}\n\n"
        f"متن‌های مرجع:\n{context_block}\n\n"
        f"سوال کاربر: {question}"
        if context_chunks
        else f"{plan_block}\n\nهیچ متن مرجعی یافت نشد.\n\nسوال کاربر: {question}"
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


def rewrite_query(question: str) -> str:
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
            messages, max_tokens=150, timeout=15).strip()

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
        # A larger candidate pool improves recall without allowing unrelated
        # pages through to the vision model.
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

    embedding_model = get_embedding_model()
    hybrid_search = get_hybrid_search()

    search_query = rewrite_query(question)
    query_embedding = embedding_model.embed_query(search_query)

    # Text retrieval: covers TXT/MD, plus any PDFs ingested in text mode
    retrieved_chunks = hybrid_search.search(
        query_text=search_query,
        query_embedding=query_embedding,
        user_id=user_id,
        top_k=k,
    )

    # Image retrieval: covers PDFs ingested in "page-as-image" mode
    image_hits = _retrieve_image_hits(search_query, user_id, settings.IMAGE_TOP_K)

    logger.info(
        f"{len(retrieved_chunks)} text chunk(s) and {len(image_hits)} page image(s) "
        f"retrieved for user {user_id}."
    )

    if image_hits:
        # At least one relevant page image was found -> use the vision LLM,
        # with any text chunks attached as supplementary context.
        vision_llm = get_vision_llm_client()
        image_paths = [hit["content"] for hit in image_hits]

        messages = _build_image_messages(question, image_hits, retrieved_chunks, history, schedule)
        answer_text = vision_llm.generate(messages, images=image_paths)

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

    # No relevant page images -> original text-only pipeline
    llm_client = get_llm_client()
    messages = _build_messages(question, retrieved_chunks, history, student, schedule)
    answer_text = llm_client.generate(messages)

    sources = [
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
    top_k: Optional[int] = None
) -> Generator[str, None, None]:
    """Stream answer chunks along with initial metadata (sources) using NDJSON protocol."""

    settings = get_settings()
    k = top_k or settings.TOP_K

    embedding_model = get_embedding_model()
    hybrid_search = get_hybrid_search()

    # STEP 1: Status - Query Rewriting
    yield json.dumps({"type": "status", "data": "در حال بازنویسی و تحلیل پرسش..."}) + "\n"
    search_query = rewrite_query(question)

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

    # Image retrieval: covers PDFs ingested in "page-as-image" mode
    image_hits = _retrieve_image_hits(search_query, user_id, settings.IMAGE_TOP_K)

    logger.info(
        f"{len(retrieved_chunks)} text chunk(s) and {len(image_hits)} page image(s) "
        f"retrieved for user {user_id} (streaming)."
    )

    if image_hits:
        vision_llm = get_vision_llm_client()
        image_paths = [hit["content"] for hit in image_hits]
        messages = _build_image_messages(question, image_hits, retrieved_chunks, history)

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

    settings = get_settings()

    dpi = dpi or settings.IMAGE_DPI
    batch_size = batch_size or settings.IMAGE_BATCH_SIZE

    output_dir = Path(settings.IMAGES_DIR) / str(user_id) / Path(document_name).stem
    image_paths = pdf_to_page_images(pdf_path, output_dir, dpi=dpi)

    if not image_paths:
        logger.warning(f"No pages were rendered from document '{document_name}'.")
        return 0

    image_embedder = get_image_embedding_model()
    image_vector_store = get_image_vector_store()

    # Make ingestion idempotent: drop any previous page embeddings for this
    # document before re-adding, so re-runs never duplicate chunks.
    image_vector_store.delete_document(document_name, user_id)

    total = 0
    for start in range(0, len(image_paths), batch_size):
        batch = image_paths[start:start + batch_size]
        embeddings = image_embedder.embed_images(batch)
        total += image_vector_store.add_chunks(
            document_name,
            [str(p) for p in batch],  # stored as "content": the file path
            embeddings,
            user_id=user_id,
            category=category,
        )
        logger.info(
            "  '%s': embedded pages %d-%d of %d.",
            document_name,
            start + 1,
            min(start + batch_size, len(image_paths)),
            len(image_paths),
        )

    logger.info(
        f"Ingested {total} page image(s) from '{document_name}' for user {user_id} "
        f"using the '{settings.IMAGE_EMBEDDING_BACKEND}' backend."
    )

    return total
