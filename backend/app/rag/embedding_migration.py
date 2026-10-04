"""Resume a text-vector migration while preserving the original collections.

Uses the text already stored in Chroma, so raw PDFs and another OCR pass are
unnecessary. IDs, account ownership, citations and printed question metadata
survive unchanged. Page-image vectors are handled by their existing backend.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.rag.gemini_embeddings import EmbeddingError, gemini_collection_name
from app.rag.collection_ops import get_or_create_collection


def source_digest(text, metadata):
    payload = json.dumps([text, metadata], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def migrate_collection(client, source_name, model, progress=lambda value: None):
    source = client.get_collection(source_name, embedding_function=None)
    target_name = gemini_collection_name(source_name, model.model, model.dimensions)
    if source_name == target_name:
        raise ValueError("Source and destination collections must be different.")
    target = get_or_create_collection(
        client, target_name,
        metadata={"hnsw:space": "cosine", "boom:embedding_fingerprint": model.fingerprint},
    )
    metadata = target.metadata or {}
    if metadata.get("boom:embedding_fingerprint") != model.fingerprint:
        raise EmbeddingError("Destination collection has incompatible embedding provenance.")
    # Capture IDs once: concurrent uploads cannot shift pagination offsets.
    ids = sorted(source.get(include=[])["ids"])
    completed = 0
    for start in range(0, len(ids), model.batch_size):
        batch_ids = ids[start:start + model.batch_size]
        rows = source.get(ids=batch_ids, include=["documents", "metadatas"])
        existing = target.get(ids=batch_ids, include=["metadatas"])
        digests = {key: (meta or {}).get("boom:migration_digest") for key, meta in
                   zip(existing["ids"], existing["metadatas"] or [])}
        pending = []
        for key, text, meta in zip(rows["ids"], rows["documents"], rows["metadatas"]):
            if not isinstance(text, str) or not text.strip():
                raise EmbeddingError("Source has an empty text chunk; repair it before migration.")
            digest = source_digest(text, meta)
            if digests.get(key) != digest:
                pending.append((key, text, {**(meta or {}), "boom:migration_digest": digest}))
        if pending:
            vectors = model.embed_documents([row[1] for row in pending])
            if len(vectors) != len(pending) or any(len(v) != model.dimensions for v in vectors):
                raise EmbeddingError("Embedding batch incomplete; source and completed batches are safe.")
            target.upsert(ids=[row[0] for row in pending], documents=[row[1] for row in pending],
                          metadatas=[row[2] for row in pending], embeddings=vectors)
        completed += len(rows["ids"])
        progress({"source": source_name, "target": target_name, "completed": completed,
                  "total": len(ids), "updated_this_batch": len(pending)})
    validate_migration(source, target)
    return {"source": source_name, "target": target_name, "chunks": source.count()}


def validate_migration(source, target):
    # Do not activate a snapshot if source data changed while it was embedded.
    current = source.get(include=["documents", "metadatas"])
    migrated = target.get(ids=current["ids"], include=["metadatas"]) if current["ids"] else {"ids": [], "metadatas": []}
    hashes = {key: (meta or {}).get("boom:migration_digest") for key, meta in
              zip(migrated["ids"], migrated["metadatas"] or [])}
    if any(hashes.get(key) != source_digest(text, meta) for key, text, meta in
           zip(current["ids"], current["documents"], current["metadatas"])):
        raise EmbeddingError("Source changed during migration; run again to finish the updated chunks.")
    if set(target.get(include=[])["ids"]) != set(current["ids"]):
        raise EmbeddingError("Destination contains stale/extra chunks; inspect it before activation.")


def migrate_collection_parallel(client, source_name, models, progress=lambda value: None):
    """Parallel API workers with one coordinator owning every Chroma operation."""
    import queue
    import threading

    if not models or len({model.fingerprint for model in models}) != 1:
        raise ValueError("All workers must use the same embedding model and format.")
    model = models[0]
    source = client.get_collection(source_name, embedding_function=None)
    target_name = gemini_collection_name(source_name, model.model, model.dimensions)
    target = get_or_create_collection(client, target_name,
        metadata={"hnsw:space": "cosine", "boom:embedding_fingerprint": model.fingerprint})
    if (target.metadata or {}).get("boom:embedding_fingerprint") != model.fingerprint:
        raise EmbeddingError("Destination collection has incompatible embedding provenance.")
    ids = sorted(source.get(include=[])["ids"])
    tasks, completed = [], 0
    for start in range(0, len(ids), model.batch_size):
        batch_ids = ids[start:start + model.batch_size]
        rows = source.get(ids=batch_ids, include=["documents", "metadatas"])
        existing = target.get(ids=batch_ids, include=["metadatas"])
        hashes = {key: (meta or {}).get("boom:migration_digest") for key, meta in
                  zip(existing["ids"], existing["metadatas"] or [])}
        pending = []
        for key, text, meta in zip(rows["ids"], rows["documents"], rows["metadatas"]):
            if not isinstance(text, str) or not text.strip():
                raise EmbeddingError("Source has an empty text chunk; repair it before migration.")
            digest = source_digest(text, meta)
            if hashes.get(key) == digest:
                completed += 1
            else:
                pending.append((key, text, {**(meta or {}), "boom:migration_digest": digest}))
        if pending:
            tasks.append(pending)

    def report(updated=0, worker=None):
        progress({"source": source_name, "target": target_name, "completed": completed,
                  "total": len(ids), "updated_this_batch": updated, "last_worker": worker})

    report()
    results = queue.Queue(maxsize=max(2, 2 * len(models)))
    stop = threading.Event()

    def run_worker(index, worker_model):
        try:
            for pending in tasks[index::len(models)]:
                if stop.is_set():
                    break
                vectors = worker_model.embed_documents([row[1] for row in pending])
                if len(vectors) != len(pending) or any(len(v) != model.dimensions for v in vectors):
                    raise EmbeddingError("Embedding worker returned an incomplete batch.")
                results.put(("batch", index + 1, pending, vectors))
        except Exception as error:
            stop.set()
            safe_error = str(error) if isinstance(error, EmbeddingError) else type(error).__name__
            results.put(("error", index + 1, safe_error, None))
        finally:
            results.put(("done", index + 1, None, None))

    threads = [threading.Thread(target=run_worker, args=(i, worker), name=f"embedding-worker-{i+1}")
               for i, worker in enumerate(models)]
    for thread in threads:
        thread.start()
    ended, first_error = 0, None
    while ended < len(threads):
        kind, worker, pending, vectors = results.get()
        if kind == "done":
            ended += 1
        elif kind == "error":
            first_error = first_error or EmbeddingError(f"Worker {worker}: {pending}")
        else:
            try:
                target.upsert(ids=[row[0] for row in pending], documents=[row[1] for row in pending],
                              metadatas=[row[2] for row in pending], embeddings=vectors)
            except Exception as error:
                stop.set()
                first_error = first_error or EmbeddingError(f"Index write failed ({type(error).__name__}); rerun to resume.")
            else:
                completed += len(pending)
                try:
                    report(len(pending), worker)
                except Exception as error:
                    stop.set()
                    first_error = first_error or EmbeddingError(f"Progress status write failed ({type(error).__name__}); stored vectors are safe.")
    for thread in threads:
        thread.join()
    if first_error:
        raise first_error
    validate_migration(source, target)
    return {"source": source_name, "target": target_name, "chunks": source.count()}


def activate_gemini(env_path, model, backup_dir):
    """Only called after both text collections pass migration validation."""
    from dotenv import set_key
    import shutil
    env_path, backup_dir = Path(env_path), Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if env_path.exists():
        shutil.copy2(env_path, backup_dir / f"runtime-env-before-{stamp}.env")
    staged_env = backup_dir / f"runtime-env-staged-{stamp}.env"
    if env_path.exists():
        shutil.copy2(env_path, staged_env)
    else:
        staged_env.touch()
    updates = {"EMBEDDING_PROVIDER": "gemini", "EMBEDDING_MODEL_NAME": model.model,
               "EMBEDDING_DIMENSIONS": str(model.dimensions),
               "EMBEDDING_API_KEY": model.api_key, "EMBEDDING_PROXY": model.proxy}
    for key, value in updates.items():
        set_key(str(staged_env), key, value)
    staged_env.replace(env_path)
