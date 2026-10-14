"""Local exam corpus driver. No VM access, transfer, deployment or app DB writes."""
import argparse
import json
import sys
import time
import os
from contextlib import ExitStack
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["inventory", "extract", "status", "benchmark", "scan", "standardize"])
    parser.add_argument("--root", type=Path, default=BACKEND / "data/exam_examples")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--provider", choices=["gemini", "groq", "auto"], default="auto")
    parser.add_argument('--local-only',action='store_true',help='Benchmark local engines without API requests')
    parser.add_argument('--watch',action='store_true',help='Resume a scan after its saved provider retry time')
    parser.add_argument('--live',action='store_true',help='Print worker stages and counters while scanning')
    parser.add_argument('--extract-first',action='store_true',help='Refresh local text/layout checkpoints before scanning')
    parser.add_argument('--wait-for-lock',action='store_true',help='Queue behind an existing local corpus worker')
    args = parser.parse_args()
    if args.workers<1 or args.workers>8 or args.limit<0:parser.error('Workers must be 1..8 and limit nonnegative')
    if args.watch and args.mode!='scan':parser.error('--watch is supported only for scan')
    from app.rag import exam_corpus
    def live_progress(state):
        stamp=time.strftime('%H:%M:%S')
        print(f"[{stamp}] {state['phase']} | saved this run {state.get('scanned_this_run',0)} | "
              f"active {state.get('active_candidates',0)} | pending {state.get('pending_candidates',0)} | "
              f"requests {state.get('requests_this_run',0)}",flush=True)
        for row in state.get('workers',[]):
            print(f"  {row['worker']}: {row.get('phase','')} / {row.get('stage','')} | "
                  f"page {row.get('pdf_page','')} | {row.get('credential_label','')} | "
                  f"HTTP {row.get('http_status','-')} | {row.get('document_name','')}",flush=True)
    if args.mode == "status": print(json.dumps(exam_corpus.status(args.root), ensure_ascii=False)); return
    with ExitStack() as held:
        while True:
            try:held.enter_context(exam_corpus.job_lock(args.root));break
            except RuntimeError:
                if not args.wait_for_lock:raise
                exam_corpus.atomic_json(args.root/'coordinator-status.json',{
                    'phase':'waiting_for_existing_local_worker','pid':os.getpid(),'heartbeat':time.time()})
                time.sleep(30)
        if args.mode == 'inventory':
            from app.rag.exam_inventory import inventory
            result=inventory(BACKEND.parent,args.root)
        elif args.mode == "extract":
            result = exam_corpus.extract_native(BACKEND.parent, args.root,
                progress=lambda s: print(json.dumps({k:s[k] for k in ["document","completed","failed","total_pages"]}, ensure_ascii=False), flush=True))
        else:
            from app.rag import exam_scanning
            if args.extract_first:
                exam_corpus.extract_native(BACKEND.parent,args.root)
            options={'workers':args.workers,'limit':args.limit,'provider':args.provider}
            if args.mode=='scan' and args.live:options['progress']=live_progress
            if args.mode=='benchmark':options['local_only']=args.local_only
            while True:
                exam_corpus.atomic_json(args.root/'coordinator-status.json',{
                    'phase':'executing','pid':os.getpid(),'heartbeat':time.time(),
                    'selected_limit':args.limit,'provider':args.provider})
                result = getattr(exam_scanning, args.mode)(args.root, **options)
                retry=result.get('retry_not_before')
                if not (args.mode=='scan' and args.watch and result.get('phase')=='waiting_for_credentials'
                        and isinstance(retry,(int,float)) and retry>time.time()):break
                while time.time()<retry:
                    exam_corpus.atomic_json(args.root/'coordinator-status.json',{
                        'phase':'waiting_for_saved_provider_retry','pid':os.getpid(),'heartbeat':time.time(),
                        'retry_not_before':retry,'selected_limit':args.limit,'provider':args.provider})
                    if args.live:
                        print(f"Waiting for saved provider retry: {max(0,int(retry-time.time()))}s. "
                              "No API request is being sent during this wait.",flush=True)
                    time.sleep(min(30,retry-time.time()))
            exam_corpus.atomic_json(args.root/'coordinator-status.json',{
                'phase':'stopped','pid':os.getpid(),'heartbeat':time.time(),'last_scan_phase':result.get('phase')})
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:main()
    except RuntimeError as error:
        if str(error)=='Another corpus worker is running':
            print(json.dumps({'phase':'busy','error':'Another corpus worker is running; use status or --wait-for-lock.'}))
            raise SystemExit(75) from None
        if str(error).startswith('Invalid saved quota state'):
            print(json.dumps({'phase':'blocked','error':'Saved quota state needs repair; no provider request was sent.'}))
            raise SystemExit(2) from None
        raise
