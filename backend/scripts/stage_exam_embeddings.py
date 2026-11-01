"""Build/resume isolated Gemini vectors for a frozen local exam OCR snapshot."""
import argparse,concurrent.futures,json,os,sys,threading,time
from pathlib import Path
BACKEND=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND))
from app.rag.exam_corpus import DEFAULT_ROOT,read_json,atomic_json
from app.rag.exam_candidate_index import snapshot


def _run():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,default=BACKEND/'data/exam_staging/batch-5000-v1')
    p.add_argument('--pages',type=int,default=5000)
    p.add_argument('--workers',type=int,choices=range(1,17),default=4)
    p.add_argument('--snapshot-only',action='store_true')
    args=p.parse_args()
    manifest=snapshot(DEFAULT_ROOT,args.snapshot,args.pages)
    print(json.dumps({k:v for k,v in manifest.items() if k!='page_ids'}),flush=True)
    if args.snapshot_only:return
    import chromadb
    from chromadb.config import Settings
    from app.rag.gemini_embeddings import GeminiEmbeddingModel,EmbeddingError
    from app.rag.exam_vision import credentials
    from app.config import get_settings
    settings=get_settings();model=settings.EMBEDDING_MODEL_NAME;dimensions=settings.EMBEDDING_DIMENSIONS
    client=chromadb.PersistentClient(path=str(args.snapshot/'chroma'),settings=Settings(anonymized_telemetry=False))
    collection=client.get_or_create_collection('exam_ocr_candidates',metadata={'hnsw:space':'cosine',
        'embedding_model':model,'dimensions':dimensions,'snapshot_sha256':manifest['chunks_sha256'],
        'evidence_status':'ocr_candidate','live_activation':False})
    if collection.metadata.get('embedding_model')!=model or collection.metadata.get('dimensions')!=dimensions:
        raise ValueError('Embedding model/dimensions changed; use a new snapshot destination')
    if collection.metadata.get('snapshot_sha256')!=manifest['chunks_sha256']:
        raise ValueError('Collection belongs to another immutable snapshot')
    from app.rag.exam_quality import parent_children
    parents=read_json(args.snapshot/'chunks.json');rows=[]
    for parent in parents:
        for child in parent_children(parent):
            rows.append({**parent,'id':child['id'],'text':child['text'],
                'content_sha256':parent['content_sha256'] if child['parts']==1 else child['content_sha256'],
                'metadata':{**parent['metadata'],'parent_id':parent['id'],
                    'parent_content_sha256':parent['content_sha256'],'part':child['part'],'parts':child['parts']}})
    stored=collection.get(include=['metadatas'])
    expected={r['id']:r['content_sha256'] for r in rows}
    if any(meta.get('content_sha256')!=expected.get(identity) for identity,meta in zip(stored['ids'],stored['metadatas'])):
        raise ValueError('Existing vectors do not match snapshot content; refuse silent reuse')
    existing=set(stored['ids'])
    todo=[r for r in rows if r['id'] not in existing]
    specs=[s for s in credentials(BACKEND.parent) if s.provider=='gemini']
    lock=threading.RLock();batches=[todo[i:i+24] for i in range(0,len(todo),24)];cursor=[0]
    status={'phase':'embedding','pid':os.getpid(),'model':model,'dimensions':dimensions,
        'pages':manifest['pages'],'total_chunks':len(rows),'stored_chunks':len(existing),'failed_credentials':0,
        'live_activation':False,'started_at':time.time()}
    def save():
        status['updated_at']=time.time();atomic_json(args.snapshot/'embedding-status.json',status)
    save()
    def work(worker):
        for spec in specs[worker::max(1,min(args.workers,len(specs)))]:
            embed=GeminiEmbeddingModel(spec.key,model,dimensions,24,2,proxy=os.getenv('EXAM_OCR_PROXY') or 'http://127.0.0.1:10809')
            embed.switch_on_rate_limit=True
            try:
                while True:
                    with lock:
                        if cursor[0]>=len(batches):return
                        batch=batches[cursor[0]];cursor[0]+=1
                    try:vectors=embed.embed_documents([r['text'] for r in batch])
                    except EmbeddingError:
                        with lock:
                            batches.append(batch);status['failed_credentials']+=1;status['last_error']=embed.last_error_code or 'embedding_transport_error';save()
                        if embed.last_error_code=='provider_rate_limit':
                            time.sleep(60)
                            continue
                        break
                    with lock:
                        collection.upsert(ids=[r['id'] for r in batch],documents=[r['text'] for r in batch],
                            metadatas=[{**r['metadata'],'content_sha256':r['content_sha256']} for r in batch],embeddings=vectors)
                        status['stored_chunks']+=len(batch);save()
                        print('Embedded',status['stored_chunks'],'/',len(rows),flush=True)
            finally:embed.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(args.workers,len(specs)))) as pool:
        list(pool.map(work,range(max(1,min(args.workers,len(specs))))))
    status['stored_chunks']=collection.count()
    status['phase']='complete' if collection.count()==len(rows) else 'paused_provider_limits'
    save();print(json.dumps(status),flush=True)

def main():
    from app.rag.exam_corpus import job_lock,worker_alive
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--snapshot',type=Path,default=BACKEND/'data/exam_staging/batch-5000-v1')
    known,_=parser.parse_known_args()
    # Also recognize an already-running pre-lock worker during this upgrade.
    previous=read_json(known.snapshot/'embedding-status.json',{})
    pid=previous.get('pid')
    if type(pid) is int and pid!=os.getpid() and previous.get('phase')=='embedding' and worker_alive(pid):
        import subprocess
        if os.name=='nt':
            probe=subprocess.run(['powershell.exe','-NoProfile','-Command',
                f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").CommandLine'],
                capture_output=True,text=True,timeout=15)
            command=probe.stdout
        else:
            try:command=Path(f'/proc/{pid}/cmdline').read_text()
            except OSError:command=''
        if 'stage_exam_embeddings.py' in command:
            print('Existing embedding worker is still active; no duplicate started.',flush=True)
            return 2
    try:
        with job_lock(known.snapshot):return _run()
    except RuntimeError as error:
        if str(error)=='Another corpus worker is running':
            print('Another embedding writer owns this snapshot; no duplicate started.',flush=True)
            return 2
        raise

if __name__=='__main__':raise SystemExit(main())
