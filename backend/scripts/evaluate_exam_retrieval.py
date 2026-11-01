"""Measured local retrieval pilot, never a production activation."""
import os, sys, time, json,argparse
from pathlib import Path
BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))
from app.rag.exam_corpus import read_json,atomic_json

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',type=Path,help='Reviewed benchmark JSON with id, query, expected_ids')
    parser.add_argument('--allow-gold-overlay',action='store_true',help='Pilot only: explicitly add missing gold vectors in memory')
    args=parser.parse_args()
    import numpy as np, chromadb
    from chromadb.config import Settings
    from app.config import get_settings
    from app.rag.gemini_embeddings import GeminiEmbeddingModel,EmbeddingError
    from app.rag.exam_vision import credentials
    from app.rag.lexical_search import LexicalIndex
    from app.rag.exam_quality import retrieval_metrics
    from app.rag.reranker import get_reranker
    root=BACKEND/'data/exam_staging/batch-5000-v1'
    rows=read_json(root/'chunks.json');by_id={r['id']:r for r in rows}
    prefix='66b5551fa48873c0621e2a9ed39a6e08fa816bd9d7b0acc41a76fce992aef049:3:'
    queries={7:['ریشه های سهمی در دو طرف عدد دو و محدوده ضریب درجه دوم','بازه ضریب سهمی با دو ریشه در طرفین نقطه مشخص'],
        8:['نامساوی تابع وارون نمایی با پایه یک سوم و تعداد اعداد صحیح مثبت','دامنه حل نامساوی شامل وارون تابع نمایی نزولی'],
        11:['علامت مجموع و تفاضل دو زاویه با کسینوس و ربع های متفاوت','تعیین ربع مجموع زاویه ها با نسبت های مثلثاتی']}
    cases=[{'id':f'{n}-{i}','query':q,'expected_ids':[prefix+str(n)]} for n,qs in queries.items() for i,q in enumerate(qs)]
    if args.cases:
        cases=read_json(args.cases,[])
        if (not isinstance(cases,list) or not cases or any(not isinstance(c,dict)
            or not isinstance(c.get('id'),str) or not isinstance(c.get('query'),str) or not c['query'].strip()
            or not isinstance(c.get('expected_ids'),list) or not c['expected_ids']
            or any(x not in by_id for x in c['expected_ids']) for c in cases)
            or len({c['id'] for c in cases})!=len(cases)):
            raise ValueError('Invalid benchmark or expected sources outside the immutable snapshot')
    settings=get_settings()
    from app.rag.evaluation_cache import EvaluationCache
    cache=EvaluationCache(root/'evaluation-vector-cache.json',settings.EMBEDDING_MODEL_NAME,settings.EMBEDDING_DIMENSIONS)
    import collections
    failures=collections.Counter()
    specs=[s for s in credentials(BACKEND.parent) if s.provider=='gemini']
    def embed(texts,query=False):
        task='query' if query else 'document'
        cached=[cache.get(text,task) for text in texts]
        if all(vector is not None for vector in cached):return cached
        for spec in specs:
            client=GeminiEmbeddingModel(spec.key,settings.EMBEDDING_MODEL_NAME,settings.EMBEDDING_DIMENSIONS,
                24,100,proxy='http://127.0.0.1:10809')
            client.switch_on_rate_limit=True
            try:
                vectors=[client.probe_query(texts[0])] if query else client.embed_documents(texts)
                for text,vector in zip(texts,vectors):cache.put(text,task,vector)
                return vectors
            except EmbeddingError:
                code=client.last_error_code or 'embedding_transport_or_provider_error'
                failures[code]+=1
                atomic_json(root/'retrieval-run-status.json',{'phase':'waiting_provider','updated_at':time.time(),
                    'failure_counts':dict(failures),'published':False})
                # Changing keys cannot repair a broken connection or provider 5xx.
                if not client.last_error_code:
                    raise RuntimeError('Retrieval evaluation paused: embedding network/provider response failed') from None
                continue
            finally:client.close()
        raise RuntimeError('No eligible embedding credential for local evaluation')
    collection=chromadb.PersistentClient(path=str(root/'chroma'),settings=Settings(anonymized_telemetry=False)).get_collection('exam_ocr_candidates')
    metadata=collection.metadata or {}
    if (metadata.get('embedding_model')!=settings.EMBEDDING_MODEL_NAME
        or metadata.get('dimensions')!=settings.EMBEDDING_DIMENSIONS
        or metadata.get('snapshot_sha256')!=read_json(root/'manifest.json')['chunks_sha256']):
        raise ValueError('Evaluation model/dimensions/snapshot do not match stored vectors')
    stored=collection.get(include=['embeddings']);ids=list(stored['ids']);vectors=list(stored['embeddings'])
    stored_count=len(ids)
    gold_ids=sorted({x for c in cases for x in c['expected_ids']})
    missing=[identity for identity in gold_ids if identity not in ids]
    if missing and not args.allow_gold_overlay:
        raise RuntimeError('Gold source embeddings are missing; finish the snapshot or explicitly use --allow-gold-overlay for a pilot')
    # Gold vectors are an explicit in-memory overlay, not writes to a live index.
    if missing:vectors.extend(embed([by_id[x]['text'] for x in missing]));ids.extend(missing)
    matrix=np.asarray(vectors,dtype=np.float32)
    if (matrix.ndim!=2 or matrix.shape[1]!=settings.EMBEDDING_DIMENSIONS
        or not np.isfinite(matrix).all() or np.any(np.linalg.norm(matrix,axis=1)==0)):
        raise ValueError('Stored vectors fail dimensionality/finite/nonzero validation')
    matrix/=np.maximum(np.linalg.norm(matrix,axis=1,keepdims=True),1e-12)
    lexical=LexicalIndex([{'id':x,'content':by_id[x]['text']} for x in ids])
    rankings={name:{} for name in ['bm25','dense','hybrid','reranked']};details=[]
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    reranker=get_reranker();available=reranker.available
    for case in cases:
        q=case['query'];lexical_ids=[r['id'] for r in lexical.search(q,top_k=20)]
        qv=np.asarray(embed([q],True)[0],dtype=np.float32);qv/=max(np.linalg.norm(qv),1e-12)
        dense=[ids[i] for i in np.argsort(-(matrix@qv))[:20]];scores={}
        for ranking in [lexical_ids,dense]:
            for i,x in enumerate(ranking):scores[x]=scores.get(x,0)+1/(60+i+1)
        hybrid=sorted(scores,key=lambda x:(-scores[x],x))[:20]
        candidates=[{'id':x,'content':by_id[x]['text']} for x in hybrid]
        reranked=[r['id'] for r in reranker.rerank(q,candidates,top_k=5)] if available else hybrid[:5]
        for name,result in [('bm25',lexical_ids),('dense',dense),('hybrid',hybrid),('reranked',reranked)]:rankings[name][case['id']]=result
        details.append({**case,'results':{k:rankings[k][case['id']][:5] for k in rankings}})
        print('Evaluated',case['id'],flush=True)
    report={'created_at':time.time(),'snapshot_sha256':read_json(root/'manifest.json')['chunks_sha256'],
        'evaluated_corpus_questions':len(ids),'gold_overlay_count':len(missing),'gold_sources':len(gold_ids),
        'embedding_model':settings.EMBEDDING_MODEL_NAME,'embedding_dimensions':settings.EMBEDDING_DIMENSIONS,
        'embedding_complete':stored_count==len(rows),
        'metrics':{name:retrieval_metrics(cases,ranking) for name,ranking in rankings.items()},
        'reranker_executed':available,'release_passed':False,
        'limitations':[('Custom benchmark cases; source-review receipts still need checking.' if args.cases
            else 'Six queries from three source-checked math questions only.'),
        'Evaluated '+str(stored_count)+' stored vectors with '+str(len(missing))+' explicit in-memory gold additions.',
        'Not representative of science/figure/grade coverage; not release approval.'],'cases':details}
    atomic_json(root/'retrieval-history'/f'{time.time_ns()}.json',report)
    atomic_json(root/'retrieval-pilot.json',report)
    atomic_json(root/'retrieval-run-status.json',{'phase':'complete','updated_at':time.time(),'published':False})
    print(json.dumps({k:v for k,v in report.items() if k!='cases'},ensure_ascii=False),flush=True)

if __name__=='__main__':
    status=BACKEND/'data/exam_staging/batch-5000-v1/retrieval-run-status.json'
    atomic_json(status,{'phase':'running','pid':os.getpid(),'updated_at':time.time(),'published':False})
    try:main()
    except Exception as error:
        previous=read_json(status,{})
        atomic_json(status,{**previous,'phase':'blocked','updated_at':time.time(),
            'error_type':type(error).__name__,'published':False})
        raise
