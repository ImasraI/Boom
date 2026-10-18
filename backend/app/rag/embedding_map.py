"""Two-dimensional map of the query embedding among its retrieved neighbours.

A trace records each retrieved chunk's cosine similarity to the query, but not
the vectors themselves. Chroma still holds them, so this module fetches the
retrieved candidates by id and projects them down to two dimensions.

Two properties keep the picture honest instead of decorative:

* The candidates are unit-normalised and projected with PCA, so the axes are
  real principal directions of those vectors and the share of variance they
  carry is recorded rather than implied.
* The query's position is derived, not invented. In cosine space each recorded
  score IS the query's inner product with that chunk, and the principal plane
  lies inside the span of the candidates, so the query's coordinates in that
  plane follow exactly from the scores: no second embedding call, and no
  approximation beyond the projection itself.

Only what the trace actually recorded is drawn: the candidates listed in the
semantic-search stage (capped rows), not the whole collection. Nothing here
runs on the chat path - it is a lazy read of one finished trace.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Stage names are built as f"{label} · semantic_search"; only these carry the
# cosine similarities that make the query's position recoverable.
SEMANTIC_SUFFIX = "semantic_search"
# A plane through fewer points would be a line pretending to be a map.
MIN_POINTS = 3
# The retrieval stages record at most this many rows each.
MAX_POINTS = 25
DIGITS = 4

SHELF_LABELS: Dict[str, str] = {
    "books": "کتاب‌ها",
    "qbank": "بانک سؤال",
    "image": "تصویر صفحه",
}

LIMITATIONS: List[str] = [
    "این نقشه فقط کاندیدهای بازیابی‌شدهٔ همین اجرا را نشان می‌دهد، نه کل مجموعهٔ برداری.",
    "دو محور، دو جهت اصلی نخست همین کاندیدهاست؛ فاصلهٔ شکل‌ها تصویر تقریبی بردارهای پرابعاد است، نه فاصلهٔ دقیق.",
    "جای نشانگر پرسش از شباهت‌های کسینوسی ثبت‌شده بهدست آمده و در صفحهٔ همین کاندیدها دقیق است؛ مؤلفه‌های بیرون این صفحه در نقشه دیده نمی‌شوند.",
]

TRACE_ONLY = ("مختصات بردارها در خود رد ذخیره نمی‌شود؛ این نقشه از بردارهای همین کاندیدها "
              "در مجموعهٔ برداری ساخته می‌شود و به شبکه نیازی ندارد.")


def project_vectors(
    vectors: Sequence[Sequence[float]],
    similarities: Sequence[float],
) -> Optional[Dict[str, Any]]:
    """Project unit vectors to 2-D and place the query exactly among them.

    ``vectors[i]`` is the stored embedding of candidate ``i`` and
    ``similarities[i]`` the cosine similarity the trace recorded for it.
    Returns ``None`` when there is not enough signal for a plane.
    """
    matrix = np.asarray(vectors, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < MIN_POINTS:
        return None
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if not np.all(norms > 0):
        return None
    matrix = matrix / norms

    mean = matrix.mean(axis=0)
    centred = matrix - mean
    # PCA by SVD. The right singular vectors are the principal directions in
    # embedding space (the left ones span the candidates instead), and all of
    # them lie in the span of the candidates, which is what makes the query
    # position recoverable from its inner products below.
    _, singular, right = np.linalg.svd(centred, full_matrices=False)
    components = min(2, singular.size)
    direction = right.T[:, :components]
    coordinates = centred @ direction

    variance = singular ** 2
    total = float(variance.sum())
    if total <= 1e-12:
        # Every candidate is the same vector: there is nothing to spread out.
        return None
    ratio = [float(value) for value in (variance[:components] / total)]

    # query coordinates = Vᵀ(ĥq − mean). Gram of the unit candidates times the
    # unknown ĥq gives the recorded similarities, so ĥq's projection onto their
    # span follows from a least-squares solve of an n×n system.
    gram = matrix @ matrix.T
    similarity = np.asarray(similarities, dtype=float)
    if similarity.shape[0] != matrix.shape[0] or not np.all(np.isfinite(similarity)):
        return None
    basis = matrix @ direction                     # ĈᵀV, the candidates in V
    try:
        weights = np.linalg.lstsq(gram, similarity, rcond=None)[0]
    except np.linalg.LinAlgError:                  # pragma: no cover - LAPACK
        return None
    query = basis.T @ weights - direction.T @ mean

    return {
        "coordinates": [[round(float(a), DIGITS), round(float(b), DIGITS)]
                        for a, b in coordinates],
        "query": [round(float(query[0]), DIGITS),
                  round(float(query[1] if query.size > 1 else 0.0), DIGITS)],
        "explained_variance_ratio": [round(value, DIGITS) for value in ratio],
        "components": components,
        "dimensions": int(matrix.shape[1]),
    }


def build_map(stage: str, collection: str, rows: List[Dict[str, Any]],
              vectors: Dict[str, Sequence[float]]) -> Optional[Dict[str, Any]]:
    """One collection's map from its recorded rows and the stored vectors."""
    shelf = shelf_of(stage)
    usable: List[Dict[str, Any]] = []
    unstored = 0
    unscored = 0
    for row in rows:
        chunk_id = str(row.get("id") or "")
        if not chunk_id:
            # Nothing to look up: a row without an id is not a missing vector.
            continue
        if not vectors.get(chunk_id):
            unstored += 1
            continue
        try:
            similarity = float(row.get("score"))
        except (TypeError, ValueError):
            unscored += 1
            continue
        if not np.isfinite(similarity):
            unscored += 1
            continue
        usable.append({"id": chunk_id, "row": row, "vector": vectors[chunk_id],
                       "similarity": similarity})
        if len(usable) >= MAX_POINTS:
            break

    geometry = project_vectors([item["vector"] for item in usable],
                               [item["similarity"] for item in usable])
    if geometry is None:
        return None

    points = []
    for item, (x, y) in zip(usable, geometry["coordinates"]):
        row = item["row"]
        points.append({
            "id": item["id"], "x": x, "y": y,
            "doc": str(row.get("doc") or ""),
            "chunk": row.get("chunk", ""),
            "rank": row.get("rank", ""),
            "score": round(item["similarity"], DIGITS),
            "preview": str(row.get("preview") or ""),
            "shelf": shelf,
        })
    points.sort(key=lambda point: float(point["score"]), reverse=True)

    return {
        "stage": stage,
        "collection": collection,
        "shelf": shelf,
        "shelf_label": SHELF_LABELS.get(shelf, shelf),
        "point_count": len(points),
        "recorded_rows": len(rows),
        # Rows the map could not use, kept apart: a chunk whose vector is no
        # longer stored is a different fact from one the trace never scored.
        "missing_vectors": unstored,
        "unscored_rows": unscored,
        "dimensions": geometry["dimensions"],
        "metric": "cosine",
        "explained_variance_ratio": geometry["explained_variance_ratio"],
        "components": geometry["components"],
        # Derived from the recorded similarities, not read from the trace.
        "query": {"x": geometry["query"][0], "y": geometry["query"][1]},
        "points": points,
    }


def shelf_of(stage: str) -> str:
    """The retrieval shelf a stage belongs to: books, qbank, image or ''."""
    label = stage.split("·", 1)[0].strip().lower()
    return label if label in SHELF_LABELS else ""


def semantic_groups(stages: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group the recorded semantic-search rows by the collection they hit.

    Vectors of two collections are not comparable, so each one gets its own
    map. Rows repeated across stages of the same collection are kept once, at
    their best (lowest) rank.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for stage in stages:
        name = str(stage.get("name") or "")
        if not name.endswith(SEMANTIC_SUFFIX):
            continue
        meta = stage.get("meta") or {}
        collection = str(meta.get("collection") or "") or name
        rows = [row for row in (stage.get("rows") or []) if isinstance(row, dict)]
        if not rows:
            continue
        group = groups.get(collection)
        if group is None:
            group = {"stage": name, "collection": collection, "rows": {}}
            groups[collection] = group
            order.append(collection)
        for row in rows:
            chunk_id = str(row.get("id") or "")
            if not chunk_id:
                continue
            existing = group["rows"].get(chunk_id)
            if existing is None or _rank_of(row) < _rank_of(existing):
                group["rows"][chunk_id] = row
    return [{"stage": groups[name]["stage"], "collection": name,
             "rows": list(groups[name]["rows"].values())} for name in order]


def _rank_of(row: Dict[str, Any]) -> float:
    try:
        return float(row.get("rank"))
    except (TypeError, ValueError):
        return float("inf")


def fetch_collection_vectors(collection: str,
                             ids: Sequence[str]) -> Dict[str, Sequence[float]]:
    """Read stored vectors for these ids, without creating a collection."""
    if not ids:
        return {}
    from chromadb.api.types import Include
    from typing import cast

    from app.rag.vector_store import get_vector_store

    try:
        client = get_vector_store().client
        handle = client.get_collection(collection, embedding_function=None)
    except Exception as exc:
        logger.info("Embedding map: collection %r is not available (%s)", collection, exc)
        return {}
    try:
        found = handle.get(ids=list(ids), include=cast(Include, ["embeddings"]))
    except Exception as exc:
        logger.warning("Embedding map: reading vectors from %r failed (%s)", collection, exc)
        return {}
    stored_ids = found.get("ids") or []
    embeddings = found.get("embeddings")
    if embeddings is None:
        return {}
    return {str(chunk_id): list(vector)
            for chunk_id, vector in zip(stored_ids, embeddings) if len(vector)}


def build_embedding_maps(
    trace: Dict[str, Any],
    *,
    fetch: Optional[Callable[[str, Sequence[str]], Dict[str, Sequence[float]]]] = None,
) -> Dict[str, Any]:
    """Every map this trace supports, plus why any of them is missing."""
    stages = trace.get("stages") or []
    groups = semantic_groups(stages)
    reader = fetch or fetch_collection_vectors
    maps: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for group in groups:
        ids = [str(row.get("id") or "") for row in group["rows"]]
        try:
            vectors = reader(group["collection"], ids) or {}
        except Exception as exc:  # a broken store must not fail the panel
            logger.warning("Embedding map: vector lookup failed (%s)", exc)
            vectors = {}
        built = build_map(group["stage"], group["collection"], group["rows"], vectors)
        if built is None:
            skipped.append({
                "collection": group["collection"],
                "stage": group["stage"],
                "reason": ("کمتر از سه بردار ذخیره‌شدهٔ قابل‌استفاده برای این مجموعه پیدا شد؛ "
                           "برای رسم نقشه حداقل سه تکهٔ برداری لازم است."),
                "found_vectors": len(vectors),
                "recorded_rows": len(group["rows"]),
            })
            continue
        maps.append(built)

    payload: Dict[str, Any] = {"trace_id": trace.get("id", ""), "maps": maps,
                               "skipped": skipped, "limitations": LIMITATIONS,
                               "notice": TRACE_ONLY}
    if not maps and not skipped:
        payload["reason"] = ("این اجرا جست‌وجوی برداری با شباهت کسینوسی ثبت نکرده است؛ "
                             "نقشهٔ معنایی فقط برای مرحلهٔ جست‌وجوی برداری ساخته می‌شود.")
    return payload
