"""Local exam corpus driver. No VM access, transfer, deployment or app DB writes."""
import argparse
import json
import sys
import time
import os
from contextlib import ExitStack
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ACTIVE_ROOT = BACKEND / "data/exam_examples"
sys.path.insert(0, str(BACKEND))


def next_batch_offset(previous):
    """Never skip unfinished work when explicitly moving to another pilot batch."""
    if not isinstance(previous,dict) or previous.get('phase')!='selected_scan_finished':
        raise ValueError('The previous batch is unfinished; resume without --next-batch first')
    offset=previous.get('selected_offset',0)
    count=previous.get('selected_pages',0)
    if type(offset) is not int or offset<0 or type(count) is not int or count<=0:
        raise ValueError('No valid completed batch is saved; start without --next-batch first')
    if previous.get('pending_candidates',0) or previous.get('active_candidates',0):
        raise ValueError('The previous batch still has pending work; resume it first')
    return offset+count


def resume_batch_offset(previous, explicit=None):
    offset=explicit if explicit is not None else previous.get('selected_offset',0) if isinstance(previous,dict) else 0
    if type(offset) is not int or offset<0:raise ValueError('Invalid saved batch offset; choose an explicit --offset')
    return offset


def credential_files_signature(project):
    """Detect env-file changes without reading or publishing credential values."""
    files=[project/'backend/.env',*sorted((project/'ocr-workers').glob('worker*/worker.env'))]
    result=[]
    for file in files:
        try:
            stat=file.stat();result.append((str(file),stat.st_mtime_ns,stat.st_size))
        except FileNotFoundError:continue
    return tuple(result)


def wait_for_scan_retry(root, retry, *, limit, provider, live=False):
    from app.rag import exam_corpus
    from app.rag.exam_control import check_stop, settings_signature
    route_signature=settings_signature(root)
    signature=credential_files_signature(BACKEND.parent)
    while True:
        check_stop(root)
        now=time.time()
        if now>=retry or settings_signature(root)!=route_signature:return
        if credential_files_signature(BACKEND.parent)!=signature:
            # Reload the fleet, preserving all saved quota/access blocks.
            return
        exam_corpus.atomic_json(root/'coordinator-status.json',{
            'phase':'waiting_for_saved_provider_retry','pid':os.getpid(),'heartbeat':now,
            'retry_not_before':retry,'selected_limit':limit,'provider':provider})
        if live:
            print(f'Waiting for saved provider retry: {max(0,int(retry-now))}s. '
                  'No API request is being sent during this wait.',flush=True)
        # Printing/writing can cross the deadline; never pass a negative sleep.
        time.sleep(max(0,min(30,retry-time.time())))


def wait_for_scan_network(root,*,limit,provider,watch,live=False,specs=None):
    from app.rag.exam_corpus import atomic_json
    from app.rag.exam_vision import credentials
    from app.rag.exam_network import scan_network
    from app.rag.exam_control import check_stop, apply_settings, settings_signature
    route_signature=settings_signature(root)
    last_notice=0
    while True:
        check_stop(root)
        if settings_signature(root)!=route_signature:
            apply_settings(root)
            specs=credentials(BACKEND.parent)
            route_signature=settings_signature(root)
        # During a proxy reset keep the previously selected route. Resolving
        # auto again while its listener is down would silently fall back direct.
        status=scan_network(specs if specs is not None else credentials(BACKEND.parent),provider)
        if status['ready']:return True
        now=time.time()
        atomic_json(root/'coordinator-status.json',{
            'phase':'waiting_for_network','pid':os.getpid(),'heartbeat':now,
            'selected_limit':limit,'provider':provider,**status})
        if live and now-last_notice>=30:
            print('Configured scanning proxy is unreachable. Waiting for network; no AI request is sent and saved quota state is unchanged.',flush=True)
            last_notice=now
        if not watch:return False
        time.sleep(5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["inventory", "extract", "status", "benchmark", "scan", "standardize"])
    parser.add_argument("--root", type=Path, default=BACKEND / "data/exam_examples")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=None, help="Explicit batch offset; default resumes the last selected batch")
    parser.add_argument("--auto-next", action="store_true", help="Continue completed bounded batches until the selected corpus ends")
    parser.add_argument("--next-batch", action="store_true", help="Select the next bounded batch only after the previous batch completed")
    parser.add_argument("--provider", choices=["gemini", "groq", "auto"], default="auto")
    parser.add_argument('--local-only',action='store_true',help='Benchmark local engines without API requests')
    parser.add_argument('--method',choices=['structured','whole-page'],default='structured',
                        help='Whole-page uses one image request per page; all outputs remain unreviewed candidates')
    parser.add_argument('--watch',action='store_true',help='Resume a scan after its saved provider retry time')
    parser.add_argument('--live',action='store_true',help='Print worker stages and counters while scanning')
    parser.add_argument('--extract-first',action='store_true',help='Refresh local text/layout checkpoints before scanning')
    parser.add_argument('--wait-for-lock',action='store_true',help='Queue behind an existing local corpus worker')
    args = parser.parse_args()
    global ACTIVE_ROOT
    ACTIVE_ROOT = args.root
    if args.workers<1 or args.workers>30 or args.limit<0 or (args.offset is not None and args.offset<0):parser.error('Workers must be 1..30; limit and offset must be nonnegative')
    if (args.offset is not None or args.next_batch) and args.mode!='scan':parser.error('Batch selection is supported only for scan')
    if args.next_batch and (args.offset is not None or not args.limit):parser.error('--next-batch requires a bounded --limit and no --offset')
    if args.auto_next and (args.mode!='scan' or not args.limit):parser.error('--auto-next requires scan and a positive --limit')
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
        if args.mode=='scan':
            from app.rag.exam_control import apply_settings, keep_awake
            held.enter_context(keep_awake())
            (args.root/'stop-requested').unlink(missing_ok=True)
            apply_settings(args.root)
        if args.next_batch:
            previous=exam_corpus.read_json(args.root/'scan-status.json',{})
            try:args.offset=next_batch_offset(previous)
            except ValueError as error:parser.error(str(error))
        elif args.mode=='scan':
            try:args.offset=resume_batch_offset(exam_corpus.read_json(args.root/'scan-status.json',{}),args.offset)
            except ValueError as error:parser.error(str(error))
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
            if args.mode=='scan':options.update(method=args.method,offset=args.offset)
            if args.mode=='scan' and args.live:options['progress']=live_progress
            if args.mode=='benchmark':options['local_only']=args.local_only
            while True:
                if args.mode=='scan' and not wait_for_scan_network(args.root,limit=args.limit,
                        provider=args.provider,watch=args.watch,live=args.live):
                    result={'phase':'blocked_network','error':'Configured OCR proxy is unreachable'}
                    break
                exam_corpus.atomic_json(args.root/'coordinator-status.json',{
                    'phase':'executing','pid':os.getpid(),'heartbeat':time.time(),
                    'selected_limit':args.limit,'provider':args.provider})
                from app.rag.exam_control import apply_settings, check_stop
                check_stop(args.root)
                apply_settings(args.root)
                result = getattr(exam_scanning, args.mode)(args.root, **options)
                if result.get('phase')=='stop_requested':
                    break
                if args.auto_next and result.get('phase')=='selected_scan_finished':
                    check_stop(args.root)
                    if result.get('selected_pages',0)==0:
                        result['phase']='corpus_complete'
                        exam_corpus.atomic_json(args.root/'scan-status.json',result)
                        break
                    options['offset']=next_batch_offset(result)
                    if args.live:
                        print(f"Batch complete; automatically continuing at offset {options['offset']}. "
                              "Saved candidates remain unreviewed.",flush=True)
                    continue
                if result.get('phase')=='configuration_changed' and args.watch:
                    continue
                if args.mode=='scan' and args.watch and result.get('phase')=='waiting_for_network':
                    from app.rag.exam_vision import credentials
                    pinned_specs=credentials(BACKEND.parent)
                    # The route originally used by auto was a local proxy.
                    # Reconstruct only that non-secret endpoint if auto has
                    # already switched to system routing during this outage.
                    if result.get('waiting_for_local_proxy'):
                        from dataclasses import replace
                        pinned_specs=[replace(s,proxy='http://127.0.0.1:10809') if not s.proxy else s for s in pinned_specs]
                    wait_for_scan_network(args.root,limit=args.limit,provider=args.provider,
                        watch=True,live=args.live,specs=pinned_specs)
                    continue
                retry=result.get('retry_not_before')
                if not (args.mode=='scan' and args.watch and result.get('phase')=='waiting_for_credentials'
                        and isinstance(retry,(int,float))):break
                wait_for_scan_retry(args.root,retry,limit=args.limit,provider=args.provider,live=args.live)
            exam_corpus.atomic_json(args.root/'coordinator-status.json',{
                'phase':'stopped','pid':os.getpid(),'heartbeat':time.time(),'last_scan_phase':result.get('phase')})
    if args.mode=='scan' and args.live:
        print(f"Selected batch finished: {result.get('selected_pages',0)} pages starting at offset {result.get('selected_offset',0)}; "
              f"{result.get('stored_candidates',0)+result.get('scanned_this_run',0)} saved (including reused), {result.get('quarantined_candidates',0)} held; "
              f"{result.get('pending_candidates',0)} pending. Saved work was preserved.",flush=True)
        if result.get('phase')=='selected_scan_finished':
            print('This bounded benchmark is complete. Restarting it reuses saved pages and sends no new requests. '
                  f'To explicitly test the next batch, run "{BACKEND.parent / "START-EXAM-WORKERS.cmd"}" next in Command Prompt. '
                  'Candidates still require source review; full-corpus scanning is not enabled.',flush=True)
    else:print(json.dumps(result, ensure_ascii=False))


def record_failure(error):
    from app.rag.exam_corpus import atomic_json
    atomic_json(ACTIVE_ROOT/'coordinator-status.json', {
        'phase':'failed','pid':os.getpid(),'heartbeat':time.time(),
        'error_type':type(error).__name__})
    print('Scanner stopped after '+type(error).__name__+
          '. Saved checkpoints are preserved. Inspect the local failure before resuming.',flush=True)


if __name__ == "__main__":
    from app.rag.exam_control import ScanStopped
    try:main()
    except KeyboardInterrupt:
        from app.rag.exam_corpus import atomic_json, DEFAULT_ROOT
        atomic_json(ACTIVE_ROOT/'coordinator-status.json', {'phase':'stopped','pid':os.getpid(),
                    'heartbeat':time.time(),'reason':'keyboard_interrupt'})
        print('Stopped by keyboard. Saved checkpoints are preserved.')
    except ScanStopped as error:
        from app.rag.exam_corpus import atomic_json
        atomic_json(error.root/'coordinator-status.json', {'phase':'stopped','pid':os.getpid(),
                    'heartbeat':time.time(),'reason':'user_stop'})
        print('Stopped on request. Saved checkpoints are preserved.')
    except RuntimeError as error:
        if str(error)=='Another corpus worker is running':
            print(json.dumps({'phase':'busy','error':'Another corpus worker is running; use status or --wait-for-lock.'}))
            raise SystemExit(75) from None
        if str(error).startswith('Invalid saved quota state'):
            print(json.dumps({'phase':'blocked','error':'Saved quota state needs repair; no provider request was sent.'}))
            raise SystemExit(2) from None
        record_failure(error)
        raise SystemExit(1) from None
    except Exception as error:
        record_failure(error)
        raise SystemExit(1) from None
