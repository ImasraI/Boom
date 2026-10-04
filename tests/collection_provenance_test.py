from types import SimpleNamespace
import chromadb
import pytest
from chromadb.config import Settings
from app.rag.vector_store import VectorStore
from app.rag.embedding_migration import migrate_collection, migrate_collection_parallel
from app.rag.gemini_embeddings import EmbeddingError, gemini_collection_name


def test_runtime_open_preserves_embedding_provenance_and_distance_metric(tmp_path):
    path=str(tmp_path / 'vectors')
    client=chromadb.PersistentClient(path,settings=Settings(anonymized_telemetry=False))
    metadata={'hnsw:space':'cosine','boom:embedding_fingerprint':'gemini:gemini-embedding-2:128:retrieval_v1','catalogue_version':'v1'}
    collection=client.create_collection('documents_gemini',metadata=metadata,embedding_function=None)
    collection.add(ids=['row'],documents=['تابع'],metadatas=[{'user_id':1}],embeddings=[[1.0]+[0.0]*127])
    opened=VectorStore(path,'documents_gemini')
    assert opened.collection.metadata==metadata
    assert client.get_collection('documents_gemini').metadata==metadata
    assert opened.collection.get(include=[])['ids']==['row']
    new=VectorStore(path,'new_collection')
    assert new.collection.metadata=={'hnsw:space':'cosine'}


@pytest.mark.parametrize('parallel',[False,True])
def test_migration_rejects_existing_incompatible_provenance_before_changing_it(tmp_path,parallel):
    client=chromadb.PersistentClient(str(tmp_path),settings=Settings(anonymized_telemetry=False))
    source=client.create_collection('documents',embedding_function=None)
    source.add(ids=['source'],documents=['تابع'],metadatas=[{'user_id':1}],embeddings=[[1.0,0.0]])
    model=SimpleNamespace(model='gemini-embedding-2',dimensions=128,batch_size=8,
                          fingerprint='gemini:gemini-embedding-2:128:retrieval_v1')
    name=gemini_collection_name('documents',model.model,model.dimensions)
    metadata={'hnsw:space':'cosine','boom:embedding_fingerprint':'different-model'}
    target=client.create_collection(name,metadata=metadata,embedding_function=None)
    with pytest.raises(EmbeddingError,match='provenance'):
        if parallel:migrate_collection_parallel(client,'documents',[model])
        else:migrate_collection(client,'documents',model)
    assert client.get_collection(name).metadata==metadata
    assert target.count()==0 and source.count()==1
