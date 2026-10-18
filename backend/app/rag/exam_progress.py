"""Read-only local OCR status. Counts checkpoints, never starts provider calls."""
import re
import time
from pathlib import Path
from app.rag.exam_corpus import read_json, worker_alive


def safe_text(value):
    text = str(value or '')
    text = re.sub(r'(?:gsk_[\w-]{15,}|AQ\.[\w-]{20,}|AIza[\w-]{20,})', '[redacted]', text)
    return ''.join(c for c in text if c.isprintable())[:240]


def stored_counts(root):
    from app.rag.exam_scanning import validate_page, PIPELINE_DIGEST
    pages, retained, questions = set(), set(), set()
    for folder in (root/'documents').glob('*/vision'):
        document = folder.parent.name
        if not re.fullmatch(r'[a-f0-9]{64}', document): continue
        for file in folder.glob('page_*.json'):
            match = re.fullmatch(r'page_(\d+)\.(gemini|groq|visual)\.json', file.name)
            if not match: continue
            row = read_json(file, {})
            if not isinstance(row, dict) or row.get('ok') is not True or validate_page(row.get('data')): continue
            page = int(match[1])
            if row.get('document_id') != document or row.get('pdf_page') != page: continue
            if match[2] != 'visual' and row.get('coverage') == 'full_page': retained.add((document,page))
            if match[2] != 'visual' and row.get('prompt_digest') != PIPELINE_DIGEST: continue
            if match[2] != 'visual' and row.get('coverage') == 'full_page': pages.add((document, page))
            questions.update((document, page, q['number']) for q in row['data']['questions'])
        for file in (folder/'retained').glob('*/*.json'):
            row=read_json(file,{})
            if not isinstance(row,dict) or row.get('ok') is not True:continue
            literal=row.get('coverage')=='full_page_literal'
            if validate_page(row.get('data'),require_annotations=not literal,labelled_options=literal):continue
            if literal and row.get('expected_question_numbers')!=[q['number'] for q in row['data']['questions']]:continue
            page=row.get('pdf_page')
            if row.get('document_id')!=document or type(page) is not int or page<=0:continue
            if row.get('coverage') in ('full_page','full_page_literal'):retained.add((document,page))
            questions.update((document,page,q['number']) for q in row['data']['questions'])
        for file in folder.glob('page_*.literal.json'):
            match=re.fullmatch(r'page_(\d+)\.(gemini|groq)\.literal\.json',file.name)
            row=read_json(file,{})
            if not match or not isinstance(row,dict) or row.get('ok') is not True:continue
            data=row.get('data')
            if (validate_page(data,require_annotations=False,labelled_options=True)
                or row.get('document_id')!=document or row.get('pdf_page')!=int(match[1])
                or row.get('coverage')!='full_page_literal'):continue
            expected=row.get('expected_question_numbers')
            actual=[q['number'] for q in data['questions']]
            if (not isinstance(expected,list) or not expected or any(type(n) is not int for n in expected)
                or actual!=expected):continue
            page=int(match[1]);retained.add((document,page))
            if row.get('prompt_digest')==PIPELINE_DIGEST:pages.add((document,page))
            questions.update((document,page,n) for n in actual)
        for folder_page in folder.glob('page_*/parts'):
            match = re.fullmatch(r'page_(\d+)', folder_page.parent.name)
            if not match: continue
            for file in folder_page.glob('*.json'):
                row = read_json(file, {})
                if not isinstance(row, dict) or row.get('ok') is not True:continue
                data=row.get('data')
                if validate_page(data) and validate_page(data,require_annotations=False,labelled_options=True):continue
                questions.update((document, int(match[1]), q['number']) for q in row['data']['questions'])
    native = sum(1 for p in (root/'documents').glob('*/native/page_*.json') if not p.name.endswith('.error.json'))
    from app.rag.exam_review import reviewed_page
    checked=reviewed_page(root)
    return {'native_pages': native, 'full_ocr_pages': len(pages),
            'source_checked_full_pages':int(checked is not None),
            'retained_full_ocr_pages':len(retained),'saved_question_candidates': len(questions)}


def snapshot(root, *, counts=None, now=None):
    from app.rag.exam_vision import credentials, VisionFleet
    now = time.time() if now is None else now
    root = Path(root)
    inventory = read_json(root/'inventory.json', {})
    scan = read_json(root/'scan-status.json', {})
    coordinator = read_json(root/'coordinator-status.json', {})
    catalog = read_json(root/'style-index.json', {})
    process_alive = worker_alive(scan.get('pid')) or worker_alive(coordinator.get('pid'))
    heartbeat=max(scan.get('heartbeat',0),coordinator.get('heartbeat',0))
    scan_alive = worker_alive(scan.get('pid')) and now-scan.get('heartbeat', 0)<90
    coordinator_alive = worker_alive(coordinator.get('pid')) and now-coordinator.get('heartbeat', 0)<90
    phase = scan.get('phase', 'starting') if scan_alive else coordinator.get('phase') if coordinator_alive else 'stopped'
    completed=(scan.get('phase')=='selected_scan_finished' and scan.get('pending_candidates')==0
               and scan.get('active_candidates')==0 and scan.get('selected_pages',0)>0)
    if completed and not (scan_alive or coordinator_alive):phase='benchmark_complete'
    if scan.get('phase')=='corpus_complete' and not process_alive:phase='corpus_complete'
    if not process_alive and coordinator.get('phase')=='failed':phase='failed'
    if process_alive and not (scan_alive or coordinator_alive):phase='unresponsive'
    if (root/'stop-requested').exists():phase='stopping' if process_alive else 'stopped'
    if coordinator_alive and coordinator.get('phase') in ('waiting_for_saved_provider_retry','waiting_for_network'): phase = coordinator['phase']
    specs = credentials(Path(__file__).resolve().parents[3])
    # Monitor is a separate process; use the live job's model, not its own env.
    from dataclasses import replace
    current_model = scan.get('gemini_model')
    if isinstance(current_model,str) and current_model:
        specs = [replace(s, model=current_model) if s.provider=='gemini' else s for s in specs]
    fleet = VisionFleet(specs, root, groq_output_tokens=scan.get('groq_output_tokens'))
    old = {row.get('credential_id'): row for row in scan.get('credentials', []) if isinstance(row, dict)}
    groups, providers = {}, []
    for spec, health in zip(fleet.specs, fleet.health()):
        groups[spec.provider] = groups.get(spec.provider, 0)+1
        refusal = fleet.state.get(spec.identity, {})
        pending=scan.get('pending_by_provider',{}).get(spec.provider)
        held=scan.get('quarantined_by_provider',{}).get(spec.provider,0)
        active=scan.get('active_by_provider',{}).get(spec.provider,0) if scan_alive else 0
        selected=scan.get('provider','auto') in ('auto',spec.provider)
        work_state=('not selected for this run' if not selected else
                    'benchmark complete' if phase=='benchmark_complete' else
                    'scanner stopped' if not (scan_alive or coordinator_alive) else
                    'no eligible pilot pages · held for review' if pending==0 and not active and held else
                    'selected work complete' if pending==0 and not active else 'work pending')
        providers.append({'label': f'{spec.provider} {groups[spec.provider]}', 'model': safe_text(spec.model),
            'busy': bool(scan_alive and old.get(health['credential_id'], {}).get('busy')),
            'blocked': health['blocked'], 'retry_at': health['retry_at'],
            'http_status': refusal.get('http_status'),
            'error':'provider_overloaded · model cooldown' if health.get('service_overloaded') else safe_text(refusal.get('error')),
            'capacity_blocked': health['request_capacity_blocked'], 'access_denied': health['access_denied'],
            'selected':selected,
            'work_state':work_state,'pending_pages':pending,'held_pages':held})
    rows = []
    for row in scan.get('workers', []):
        if not isinstance(row, dict): continue
        fields = {k: safe_text(row.get(k)) for k in ('worker','document_name','phase','stage','provider','model','credential_label','error')}
        fields.update(pdf_page=row.get('pdf_page'), http_status=row.get('http_status'),
                      updated_at=row.get('updated_at'), request_started_at=row.get('request_started_at'),
                      finished_at=row.get('finished_at'))
        if not scan_alive: fields['phase'] = 'stopped'
        rows.append(fields)
    records = catalog.get('records', [])
    local = read_json(root/'model-probe/paddleocr-vl-pilot/status.json', {})
    if not isinstance(local,dict):local={}
    local_pilot={k:safe_text(local.get(k)) for k in ('phase','repo','file','source')}
    local_pilot.update(alive=worker_alive(local.get('pid')) and now-local.get('heartbeat',0)<90,
        downloaded_bytes=local.get('downloaded_bytes',0),file_bytes=local.get('file_bytes',local.get('total_weight_bytes',0)),
        completed=local.get('completed',0),total=local.get('total',0))
    return {'timestamp': now, 'phase': phase, 'last_scan_phase': scan.get('phase'),
        'worker_alive': bool(scan_alive or coordinator_alive), 'process_alive':bool(process_alive),
        'last_heartbeat':heartbeat, 'heartbeat_age_seconds':max(0,now-heartbeat) if heartbeat else None,
        'last_progress_at':max(scan.get('last_progress_at',0),max((r.get('finished_at',0) or 0 for r in scan.get('workers',[]) if isinstance(r,dict) and r.get('phase')=='saved'),default=0)), 'pid': scan.get('pid') if scan_alive else coordinator.get('pid') if coordinator_alive else None,
        'selected_pages': scan.get('selected_pages',0), 'worker_capacity': scan.get('worker_capacity',0),
        'selected_offset':scan.get('selected_offset',0),
        'batch_saved_candidates':scan.get('stored_candidates',0)+scan.get('scanned_this_run',0),
        'total_pages': sum(d.get('pages',0) for d in inventory.get('documents',[]) if isinstance(d,dict)),
        **(stored_counts(root) if counts is None else counts),
        'saved_this_run': scan.get('scanned_this_run',0), 'failed_this_run':scan.get('failed_this_run',0),
        'requests_this_run':scan.get('requests_this_run',0),
        'credential_count':len(providers),
        'selected_credential_count':sum(p['selected'] for p in providers),
        'held_candidates':scan.get('quarantined_candidates',0),
        'in_flight_requests':sum(bool(p['busy']) for p in providers),
        'quota_eligible_credentials':sum(not p['blocked'] for p in providers),
        'access_denied_credentials':sum(bool(p['access_denied']) for p in providers),
        'active_candidates': scan.get('active_candidates',0) if scan_alive and phase=='scanning' else 0,
        'pending_candidates':scan.get('pending_candidates',0),
        'retry_not_before':coordinator.get('retry_not_before') if phase=='waiting_for_saved_provider_retry' else scan.get('retry_not_before'),
        'qualified_references':len(records), 'human_reviewed_references':sum(bool(r.get('human_reviewed')) for r in records if isinstance(r,dict)),
        'workers':rows, 'providers':providers,'local_pilot':local_pilot,
        'network_blocked':phase=='waiting_for_network'}
