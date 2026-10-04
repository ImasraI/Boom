"""Portable, verified shared text vectors; never replaces the live user database."""
import hashlib
import json
import math
from pathlib import Path

from app.rag.embedding_migration import source_digest, validate_migration
from app.rag.gemini_embeddings import gemini_collection_name


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def export_shared_corpus(client, path, base_names, model, dimensions, owner):
    fingerprint = f"gemini:{model}:{dimensions}:retrieval_v1"
    collections = []
    for base in base_names:
        name = gemini_collection_name(base, model, dimensions)
        source = client.get_collection(base, embedding_function=None)
        target = client.get_collection(name, embedding_function=None)
        validate_migration(source, target)
        if (target.metadata or {}).get("boom:embedding_fingerprint") != fingerprint:
            raise ValueError("Collection embedding provenance does not match the export.")
        values = target.get(where={"user_id": owner}, include=["documents", "metadatas", "embeddings"])
        rows = [{"id": key, "document": text, "metadata": meta, "vector": [float(v) for v in vector]}
                for key, text, meta, vector in zip(values["ids"], values["documents"],
                                                 values["metadatas"], values["embeddings"])]
        collections.append({"base": base, "name": name, "rows": sorted(rows, key=lambda row: row["id"])})
    payload = {"format": "boom-shared-text-v1", "model": model, "dimensions": dimensions,
               "fingerprint": fingerprint, "owner": owner, "collections": collections}
    validate_bundle(payload, base_names, owner)
    content = _encoded(payload)
    envelope = {"sha256": hashlib.sha256(content).hexdigest(), "payload": payload}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_encoded(envelope))
    temporary.replace(path)
    return {collection["name"]: len(collection["rows"]) for collection in collections}


def validate_bundle(payload, base_names, owner):
    if payload.get("format") != "boom-shared-text-v1" or payload.get("owner") != owner:
        raise ValueError("Corpus format or shared owner differs from this deployment.")
    model, dimensions = payload.get("model"), payload.get("dimensions")
    if model not in {"gemini-embedding-2", "gemini-embedding-001"} or type(dimensions) is not int or not 128 <= dimensions <= 3072:
        raise ValueError("Unsupported embedding model or dimensions.")
    fingerprint = f"gemini:{model}:{dimensions}:retrieval_v1"
    if payload.get("fingerprint") != fingerprint:
        raise ValueError("Corpus embedding provenance is inconsistent.")
    collections = payload.get("collections", [])
    if len(collections) != len(base_names) or {item["base"] for item in collections} != set(base_names):
        raise ValueError("Corpus collection set differs from the configured base collections.")
    for collection in collections:
        if collection["name"] != gemini_collection_name(collection["base"], model, dimensions):
            raise ValueError("Corpus collection name differs from its embedding provenance.")
        ids = set()
        rows = collection["rows"]
        if not rows:
            raise ValueError("An exported shared collection is empty.")
        for row in rows:
            key, text, meta, vector = row["id"], row["document"], row["metadata"], row["vector"]
            if not isinstance(key, str) or not key or key in ids or not isinstance(text, str) or not text.strip():
                raise ValueError("Corpus contains duplicate IDs or invalid documents.")
            ids.add(key)
            if not isinstance(meta, dict) or type(meta.get("user_id")) is not int or meta["user_id"] != owner:
                raise ValueError("Corpus contains private or mismatched account ownership.")
            if any(not isinstance(k, str) or type(v) not in {str, int, float, bool} or
                   isinstance(v, float) and not math.isfinite(v) for k, v in meta.items()):
                raise ValueError("Invalid corpus metadata.")
            original_meta = {k: v for k, v in meta.items() if k != "boom:migration_digest"}
            if meta.get("boom:migration_digest") != source_digest(text, original_meta):
                raise ValueError("Corpus document or citation digest does not match.")
            if len(vector) != dimensions or any(type(v) not in {int, float} or not math.isfinite(v) for v in vector):
                raise ValueError("Corpus contains invalid vector dimensions or values.")
            if not math.isclose(sum(v * v for v in vector), 1, rel_tol=1e-5):
                raise ValueError("Corpus vectors are not normalized.")
    return payload


def read_bundle(path, base_names, owner):
    envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    payload = envelope["payload"]
    if hashlib.sha256(_encoded(payload)).hexdigest() != envelope.get("sha256"):
        raise ValueError("Corpus checksum failed; transfer the file again.")
    return validate_bundle(payload, base_names, owner)


def import_shared_corpus(client, path, base_names, owner):
    # Validate every row and every destination before performing any writes.
    payload = read_bundle(path, base_names, owner)
    names = {collection.name for collection in client.list_collections()}
    for item in payload["collections"]:
        if item["name"] not in names:
            continue
        target = client.get_collection(item["name"], embedding_function=None)
        if (target.metadata or {}).get("boom:embedding_fingerprint") != payload["fingerprint"]:
            raise ValueError("Destination embedding provenance differs; existing vectors are untouched.")
        sample = target.get(limit=1, include=["embeddings"])
        if sample["ids"] and len(sample["embeddings"][0]) != payload["dimensions"]:
            raise ValueError("Destination vector dimensions differ; existing vectors are untouched.")
        existing = target.get(ids=[row["id"] for row in item["rows"]], include=["metadatas"])
        if any(type((meta or {}).get("user_id")) is not int or meta["user_id"] != owner
               for meta in existing["metadatas"]):
            raise ValueError("An imported ID conflicts with a private user document; import refused.")
    result = {}
    for item in payload["collections"]:
        target = client.get_or_create_collection(item["name"], embedding_function=None,
            metadata={"hnsw:space": "cosine", "boom:embedding_fingerprint": payload["fingerprint"]})
        for start in range(0, len(item["rows"]), 64):
            batch = item["rows"][start:start + 64]
            target.upsert(ids=[row["id"] for row in batch], documents=[row["document"] for row in batch],
                          metadatas=[row["metadata"] for row in batch], embeddings=[row["vector"] for row in batch])
            stored = target.get(ids=[row["id"] for row in batch], include=["documents", "metadatas", "embeddings"])
            actual = {key: (text, meta, vector) for key, text, meta, vector in
                      zip(stored["ids"], stored["documents"], stored["metadatas"], stored["embeddings"])}
            for row in batch:
                text, meta, vector = actual[row["id"]]
                if text != row["document"] or meta != row["metadata"] or len(vector) != payload["dimensions"] or not all(
                    math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-7) for a, b in zip(vector, row["vector"])):
                    raise ValueError("Imported corpus verification failed; keep the prior runtime configuration.")
        result[item["name"]] = len(item["rows"])
    return result
