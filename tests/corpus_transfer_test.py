import hashlib
import json
import math

import chromadb
import pytest
from chromadb.config import Settings

from app.rag.corpus_transfer import export_shared_corpus, import_shared_corpus, _encoded
from app.rag.embedding_migration import migrate_collection
from app.rag.gemini_embeddings import EmbeddingError, gemini_collection_name


class Model:
    model = "gemini-embedding-2"
    dimensions = 128
    batch_size = 8
    fingerprint = "gemini:gemini-embedding-2:128:retrieval_v1"

    def embed_documents(self, texts):
        return [[1 / math.sqrt(128)] * 128 for _ in texts]


def client_at(path):
    return chromadb.PersistentClient(str(path), settings=Settings(anonymized_telemetry=False))


@pytest.fixture
def corpus(tmp_path):
    client = client_at(tmp_path / "laptop")
    for name in ["documents", "question_bank"]:
        source = client.create_collection(name, embedding_function=None)
        source.add(ids=["shared", "private"], documents=["تابع و حد", "Private study notes"],
                   metadatas=[{"user_id": 1, "book": "ریاضی", "page": 12, "question_number": 30},
                              {"user_id": 7}], embeddings=[[1, 0], [0, 1]])
        migrate_collection(client, name, Model())
    path = tmp_path / "corpus.json"
    counts = export_shared_corpus(client, path, ["documents", "question_bank"], "gemini-embedding-2", 128, 1)
    assert sorted(counts.values()) == [1, 1]
    return client, path


def test_roundtrip_keeps_vm_private_vectors_legacy_collections_and_citations(corpus, tmp_path):
    _, path = corpus
    vm = client_at(tmp_path / "vm")
    legacy = vm.create_collection("documents", embedding_function=None)
    legacy.add(ids=["old-private"], documents=["VM private"], embeddings=[[1, 0]], metadatas=[{"user_id": 77}])
    name = gemini_collection_name("documents", Model.model, Model.dimensions)
    target = vm.create_collection(name, embedding_function=None,
                                  metadata={"hnsw:space": "cosine", "boom:embedding_fingerprint": Model.fingerprint})
    target.add(ids=["other-private"], documents=["VM new private"],
               embeddings=Model().embed_documents(["x"]), metadatas=[{"user_id": 77}])
    for _ in range(2):
        counts = import_shared_corpus(vm, path, ["documents", "question_bank"], 1)
        assert sorted(counts.values()) == [1, 1]
    assert legacy.count() == 1 and target.count() == 2
    assert target.get(ids=["other-private"], include=["metadatas"])["metadatas"] == [{"user_id": 77}]
    metadata = target.get(ids=["shared"], include=["metadatas"])["metadatas"][0]
    assert (metadata["user_id"], metadata["book"], metadata["page"], metadata["question_number"]) == (1, "ریاضی", 12, 30)


@pytest.mark.parametrize("change", ["checksum", "owner", "dimension", "document", "duplicate", "nan"])
def test_bad_bundle_rejected_before_creating_any_collections(corpus, tmp_path, change):
    _, path = corpus
    envelope = json.loads(path.read_text(encoding="utf-8"))
    payload = envelope["payload"]
    row = payload["collections"][0]["rows"][0]
    if change == "owner": row["metadata"]["user_id"] = 7
    if change == "dimension": row["vector"].pop()
    if change in {"checksum", "document"}: row["document"] = "Tampered"
    if change == "duplicate": payload["collections"][0]["rows"].append(row.copy())
    if change == "nan": row["vector"][0] = float("nan")
    if change != "checksum": envelope["sha256"] = hashlib.sha256(_encoded(payload)).hexdigest()
    path.write_bytes(_encoded(envelope))
    vm = client_at(tmp_path / "vm")
    with pytest.raises(ValueError):
        import_shared_corpus(vm, path, ["documents", "question_bank"], 1)
    assert vm.list_collections() == []


def test_private_id_collision_refuses_entire_import_before_writes(corpus, tmp_path):
    _, path = corpus
    vm = client_at(tmp_path / "vm")
    name = gemini_collection_name("question_bank", Model.model, Model.dimensions)
    target = vm.create_collection(name, embedding_function=None,
                                  metadata={"boom:embedding_fingerprint": Model.fingerprint})
    target.add(ids=["shared"], documents=["Private VM text"], embeddings=Model().embed_documents(["x"]),
               metadatas=[{"user_id": 77}])
    with pytest.raises(ValueError, match="private"):
        import_shared_corpus(vm, path, ["documents", "question_bank"], 1)
    assert len(vm.list_collections()) == 1
    assert target.get(include=["documents"])["documents"] == ["Private VM text"]


def test_export_refuses_incomplete_migration(corpus, tmp_path):
    client, _ = corpus
    source = client.get_collection("documents", embedding_function=None)
    source.add(ids=["new"], documents=["New unembedded text"], metadatas=[{"user_id": 1}], embeddings=[[1, 0]])
    with pytest.raises(EmbeddingError):
        export_shared_corpus(client, tmp_path / "bad.json", ["documents", "question_bank"], Model.model, 128, 1)
    assert not (tmp_path / "bad.json").exists()
