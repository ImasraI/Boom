"""Recovery controls tested without provider calls or disturbing the VPN."""
import importlib.util
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.rag import exam_control as control, exam_corpus as corpus, exam_network
from app.rag import exam_scanning as scanning, exam_vision


def driver():
    path=Path(__file__).resolve().parents[1]/'backend/scripts/import_exam_examples.py'
    spec=importlib.util.spec_from_file_location('recovery_driver',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_wait_reloads_changed_proxy_and_preserves_quota(tmp_path,monkeypatch):
    monkeypatch.setenv('EXAM_OCR_PROXY','direct')
    module=driver()
    quota={'untouched':{'daily_quota':True,'retry_at':9999999999}}
    corpus.atomic_json(tmp_path/'vision-quota.json',quota)
    control.set_proxy(tmp_path,'http://127.0.0.1:1111')
    control.apply_settings(tmp_path)
    monkeypatch.setattr(exam_vision,'credentials',lambda _: [SimpleNamespace(proxy=module.os.environ['EXAM_OCR_PROXY'])])
    calls=[]
    def status(specs,*_):
        calls.append(specs[0].proxy)
        return {'ready':specs[0].proxy.endswith(':2222')}
    monkeypatch.setattr(exam_network,'scan_network',status)
    monkeypatch.setattr(module.time,'sleep',lambda _:control.set_proxy(tmp_path,'http://127.0.0.1:2222'))
    assert module.wait_for_scan_network(tmp_path,limit=30,provider='gemini',watch=True)
    assert calls==['http://127.0.0.1:1111','http://127.0.0.1:2222']
    assert corpus.read_json(tmp_path/'vision-quota.json')==quota


def test_stop_interrupts_network_and_quota_waits(tmp_path,monkeypatch):
    module=driver();(tmp_path/'stop-requested').touch()
    with pytest.raises(control.ScanStopped):
        module.wait_for_scan_network(tmp_path,limit=30,provider='auto',watch=True)
    with pytest.raises(control.ScanStopped):
        module.wait_for_scan_retry(tmp_path,9999999999,limit=30,provider='auto')


@pytest.mark.parametrize('value',['http://user:secret@localhost:10809','file:///etc/passwd',
                                 'http://localhost','http://localhost:1/path','http://localhost:1?token=x'])
def test_proxy_settings_reject_credential_urls_and_invalid_routes(tmp_path,value):
    with pytest.raises(ValueError):control.set_proxy(tmp_path,value)
    assert not (tmp_path/'scanner-settings.json').exists()


def test_auto_keeps_documented_proxy_even_offline(tmp_path,monkeypatch):
    monkeypatch.setenv('EXAM_OCR_PROXY','direct')
    control.set_proxy(tmp_path,'auto');control.apply_settings(tmp_path)
    assert module_env_proxy()=='http://127.0.0.1:10809'


def module_env_proxy():
    import os
    return os.environ['EXAM_OCR_PROXY']


def test_actual_http_connection_refusal_recovers_with_fresh_client(tmp_path):
    # Real sockets, no external AI provider: first connect to a closed port,
    # then bring the local endpoint up and reconstruct the fleet from disk.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    credential=exam_vision.Credential('gemini','synthetic-key','test-model',f'http://127.0.0.1:{port}')
    image=tmp_path/'page.png';image.write_bytes(b'test fixture')
    fleet=exam_vision.VisionFleet([credential],tmp_path,minimum_interval=0)
    result=fleet.request('test',image,'gemini')
    assert result['network_error'] and result['retryable']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            body=json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"questions":[]}'}]}}]}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        # Simulate expiration of ONLY this synthetic transport cooldown.
        saved=corpus.read_json(tmp_path/'vision-quota.json');saved[credential.identity]['retry_at']=0
        corpus.atomic_json(tmp_path/'vision-quota.json',saved)
        fresh=exam_vision.VisionFleet([credential],tmp_path,minimum_interval=0)
        assert fresh.request('test',image,'gemini')['ok']
    finally:
        server.shutdown();server.server_close();thread.join()


@pytest.mark.parametrize('action',['stop','reload'])
def test_mid_batch_control_drains_and_preserves_checkpoint(tmp_path,monkeypatch,action):
    document={'document_id':'a'*64,'name':'sample.pdf','path':'mocks/sample.pdf','pages':2}
    corpus.atomic_json(tmp_path/'inventory.json',{'documents':[document],'archives':[]})
    monkeypatch.setattr(scanning,'pilot_tasks',lambda _:[(document,1)])
    credential=exam_vision.Credential('gemini','synthetic','test','https://example.invalid')
    monkeypatch.setattr(scanning,'credentials',lambda _:[credential])
    monkeypatch.setattr(scanning,'standardize',lambda *_:{})
    def save(*_):
        if action=='stop':(tmp_path/'stop-requested').touch()
        else:control.set_proxy(tmp_path,'http://127.0.0.1:2222')
        return {'ok':True,'data':{'questions':[]}}
    monkeypatch.setattr(scanning,'_scan_one',save)
    result=scanning.scan(tmp_path,workers=1,limit=2,provider='gemini')
    assert result['phase']==('stop_requested' if action=='stop' else 'configuration_changed')
    assert result['scanned_this_run']==1 and result['pending_candidates']==1
    assert corpus.read_json(tmp_path/'documents'/('a'*64)/'vision/page_00001.gemini.json')['ok']


def test_auto_next_runs_successive_batches_and_stops_at_end(tmp_path,monkeypatch):
    import sys
    module=driver()
    monkeypatch.setattr(sys,'argv',['scanner','scan','--root',str(tmp_path),'--limit','30','--auto-next'])
    monkeypatch.setattr(module,'wait_for_scan_network',lambda *a,**kw:True)
    offsets=[]
    def scan(root,**options):
        offset=options['offset'];offsets.append(offset)
        count=30 if offset==0 else 7 if offset==30 else 0
        return {'phase':'selected_scan_finished','selected_offset':offset,'selected_pages':count,
                'pending_candidates':0,'active_candidates':0}
    monkeypatch.setattr(scanning,'scan',scan)
    module.main()
    assert offsets==[0,30,37]
    assert corpus.read_json(tmp_path/'scan-status.json')['phase']=='corpus_complete'


def test_auto_next_never_advances_an_incomplete_batch(tmp_path,monkeypatch):
    import sys
    module=driver()
    monkeypatch.setattr(sys,'argv',['scanner','scan','--root',str(tmp_path),'--limit','30','--auto-next'])
    monkeypatch.setattr(module,'wait_for_scan_network',lambda *a,**kw:True)
    calls=[]
    def scan(root,**options):
        calls.append(options['offset'])
        return {'phase':'waiting_for_credentials','selected_offset':0,'selected_pages':30,
                'pending_candidates':4,'active_candidates':0,'retry_not_before':None}
    monkeypatch.setattr(scanning,'scan',scan)
    module.main()
    assert calls==[0]


def test_auto_next_honors_stop_between_batches(tmp_path,monkeypatch):
    import sys
    module=driver()
    monkeypatch.setattr(sys,'argv',['scanner','scan','--root',str(tmp_path),'--limit','30','--auto-next'])
    monkeypatch.setattr(module,'wait_for_scan_network',lambda *a,**kw:True)
    calls=[]
    def scan(root,**options):
        calls.append(options['offset']);(root/'stop-requested').touch()
        return {'phase':'selected_scan_finished','selected_offset':0,'selected_pages':30,
                'pending_candidates':0,'active_candidates':0}
    monkeypatch.setattr(scanning,'scan',scan)
    with pytest.raises(control.ScanStopped):module.main()
    assert calls==[0]
