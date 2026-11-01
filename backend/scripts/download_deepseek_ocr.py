"""Resume this pinned free OCR model in small durable ranges, then benchmark it.

Stop other `ollama pull deepseek-ocr` clients first. Does not start/stop Ollama,
read API keys, use cloud inference, or modify source books/scan checkpoints.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import httpx

BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))
from app.rag.exam_corpus import atomic_json,digest,job_lock
from app.rag.exam_network import default_proxy

MODEL='deepseek-ocr:3b-bf16'
SHA='3a18673ff291a1d8de94d490877127899356d33a18028d5f3945bf245c11b02c'
TOTAL=6687238848
PART_SIZE=417952428
RANGE_SIZE=8*1024*1024
REGISTRY=f'https://registry.ollama.ai/v2/library/deepseek-ocr/blobs/sha256:{SHA}'


def validate_parts(parts,file_size):
    if len(parts)!=16 or sorted(p.get('N',-1) for p in parts)!=list(range(16)):
        raise ValueError('Incomplete native model-download metadata; repair before resuming')
    for p in parts:
        if (any(type(p.get(k)) is not int for k in ('N','Offset','Size','Completed'))
            or p['Offset']!=p['N']*PART_SIZE or p['Size']!=PART_SIZE
            or not 0<=p['Completed']<=p['Size'] or p['Offset']+p['Completed']>file_size):
            raise ValueError('Invalid or truncated model-download checkpoint; do not trust its progress')
    return sorted(parts,key=lambda p:p['N'])


def resolve_download(client):
    # No signed redirect URL is written to disk or printed.
    with client.stream('GET',REGISTRY,headers={'Range':'bytes=0-0'},follow_redirects=False) as response:
        if response.status_code in (307,302):
            url=response.headers.get('location','')
            parsed=urlsplit(url)
            host=parsed.hostname or ''
            if (parsed.scheme!='https' or parsed.username or parsed.password
                or not (host.endswith('.cloudflarestorage.com') or host.endswith('.ollama.ai'))):
                raise ValueError('Unexpected registry redirect; refusing to follow it')
            return url
        if response.status_code in (200,206):return REGISTRY
        raise ValueError(f'Model registry refused the download: HTTP {response.status_code}')


def fetch_range(client,url,start,end,total=TOTAL):
    with client.stream('GET',url,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'},follow_redirects=False) as response:
        if response.status_code>=500:
            raise httpx.ReadError('Model storage temporarily unavailable')
        if response.status_code!=206:
            raise ValueError(f'Model storage did not honor the range: HTTP {response.status_code}')
        expected=f'bytes {start}-{end}/{total}'
        if response.headers.get('content-range')!=expected:
            raise ValueError('Incorrect Content-Range; refusing to commit model bytes')
        data=bytearray()
        for block in response.iter_bytes():
            data.extend(block)
            if len(data)>end-start+1:raise ValueError('Oversized model range response')
        if len(data)!=end-start+1:raise httpx.ReadError('Incomplete model range response')
        return data


def commit_range(file,part,data,checkpoint,*,save=atomic_json):
    start=part['Offset']+part['Completed']
    with file.open('r+b') as handle:
        handle.seek(start);handle.write(data);handle.flush();os.fsync(handle.fileno())
    updated={**part,'Completed':part['Completed']+len(data)}
    # A failed atomic checkpoint leaves the previous offset intact. Re-fetching
    # these same bytes is safe; never advertise bytes before durable storage.
    save(checkpoint,updated)
    part.update(updated)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,choices=(1,2,3),default=2)
    parser.add_argument('--benchmark',action='store_true')
    args=parser.parse_args()
    cache=Path(os.environ.get('OLLAMA_MODELS') or Path.home()/'.ollama/models').resolve()/'blobs'
    final=(cache/f'sha256-{SHA}').resolve()
    partial=(cache/f'sha256-{SHA}-partial').resolve()
    if final.parent!=cache.resolve() or partial.parent!=cache.resolve():
        parser.error('Model cache paths escape the intended blob directory')
    root=BACKEND/'data/exam_examples/model-probe/local-ocr'
    status=root/'small-range-download/result.json'
    source=BACKEND/'data/exam_examples/documents/66b5551fa48873c0621e2a9ed39a6e08fa816bd9d7b0acc41a76fce992aef049/images/page_00016.png'
    row={'engine':'DeepSeek model download','model':MODEL,'source_sha256':digest(source),
         'source_faithfulness_approved':False,'human_reviewed':False,'scientific_state':'not_checked',
         'state':'downloading','download_total_bytes':TOTAL,'text':'Only durable completed bytes count. Two network transfers at most; no AI API keys used. OCR has not been tested yet.'}
    lock=threading.Lock();started=time.monotonic();last_print=[0]
    with job_lock(root/'download-lock'):
        if final.exists():
            if final.stat().st_size!=TOTAL or digest(final)!=SHA:raise ValueError('Existing model blob failed integrity verification')
            parts=[]
        else:
            paths=[cache/f'sha256-{SHA}-partial-{n}' for n in range(16)]
            parts=validate_parts([json.loads(p.read_text()) for p in paths],partial.stat().st_size)
            # Keep original native checkpoint metadata as recovery evidence.
            atomic_json(root/'small-range-download/native-checkpoint-before.json',parts)
            proxy=default_proxy() or None
            with httpx.Client(trust_env=False,proxy=proxy,timeout=httpx.Timeout(60,connect=10,read=45),
                              limits=httpx.Limits(max_connections=args.workers+1,max_keepalive_connections=args.workers+1)) as client:
                url=resolve_download(client)
                def publish():
                    with lock:
                        row.update(download_bytes=sum(p['Completed'] for p in parts),updated_at=time.time(),
                                   elapsed_seconds=round(time.monotonic()-started,1))
                        atomic_json(status,row)
                        if time.monotonic()-last_print[0]>10:
                            print(f"Durable model download: {row['download_bytes']/1e9:.3f} / {TOTAL/1e9:.3f} GB",flush=True)
                            last_print[0]=time.monotonic()
                def work(part):
                    delay=2
                    while part['Completed']<part['Size']:
                        start=part['Offset']+part['Completed']
                        end=min(start+RANGE_SIZE,part['Offset']+part['Size'])-1
                        try:data=fetch_range(client,url,start,end)
                        except httpx.TransportError as error:
                            # Actual source/refusal/format errors are not network
                            # retries. URLs/headers/response bodies stay private.
                            with lock:
                                row.update(last_network_error=type(error).__name__,retry_not_before=time.time()+delay)
                                atomic_json(status,row)
                            time.sleep(delay);delay=min(30,delay*2);continue
                        commit_range(partial,part,data,cache/f"sha256-{SHA}-partial-{part['N']}")
                        delay=2;publish()
                publish()
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    for _ in pool.map(work,parts):pass
            row.update(state='verifying_model_sha256');atomic_json(status,row)
            actual=digest(partial)
            if actual!=SHA:
                row.update(state='checksum_failed',actual_sha256=actual);atomic_json(status,row)
                raise ValueError('Full model SHA256 mismatch: do not install or use it')
            if final.exists():raise ValueError('Model cache changed concurrently; refusing to overwrite it')
            os.replace(partial,final)
            # Only this verified model's obsolete metadata is removed. Both
            # absolute paths were checked inside the named cache above.
            for n in range(16):
                checkpoint=(cache/f'sha256-{SHA}-partial-{n}').resolve()
                if checkpoint.parent!=cache.resolve():raise ValueError('Invalid checkpoint path')
                checkpoint.unlink(missing_ok=True)
        row.update(state='model_blob_verified',download_bytes=TOTAL,model_sha256=SHA,
                   text='Full model blob verified. Native Ollama installation and actual OCR still need to complete.')
        atomic_json(status,row)
    if args.benchmark:
        destination=root/time.strftime('deepseek-small-range-%Y%m%dT%H%M%S')
        process=subprocess.run([sys.executable,'-X','utf8',str(BACKEND/'scripts/benchmark_local_ocr.py'),
            '--engine','deepseek','--pull','--output',str(destination),'--timeout','600'])
        row.update(state='ocr_test_finished' if process.returncode==0 else 'ocr_test_failed',
                   text=f'Actual OCR result: {destination.name}. A finished request is not quality approval.')
        atomic_json(status,row)
        return process.returncode
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit(130) from None
    except (OSError,ValueError,httpx.HTTPError) as error:
        # No exception repr: httpx errors can contain signed model download URLs.
        print(f'Model setup stopped safely: {type(error).__name__}. Saved ranges were retained.',flush=True)
        raise SystemExit(2) from None
