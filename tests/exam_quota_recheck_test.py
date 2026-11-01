import json
from types import SimpleNamespace
from app.rag.exam_control import request_quota_recheck, apply_quota_recheck, settings_signature
from app.rag.exam_corpus import atomic_json


def test_explicit_recheck_releases_cooldowns_once_and_keeps_evidence(tmp_path):
    root=tmp_path/'scans';root.mkdir()
    shared=tmp_path/'provider_quota.json'
    state={'one':{'retry_at':9999999999,'error':'provider_daily_quota','http_status':429},
           'denied':{'retry_at':9999999999,'access_denied':True,'http_status':401}}
    fleet=SimpleNamespace(root=root,state=state,state_path=root/'vision-quota.json',shared_path=shared,
        specs=[SimpleNamespace(identity='one'),SimpleNamespace(identity='denied')])
    atomic_json(shared,{'one':9999999999,'unrelated':9999999999,'__access':{'denied':True}})
    checkpoint=root/'completed.json';checkpoint.write_text('preserve')
    before=settings_signature(root)
    request=request_quota_recheck(root)
    assert settings_signature(root)!=before
    assert apply_quota_recheck(fleet)==1
    assert fleet.state['one']['retry_at']==0
    assert fleet.state['one']['error']=='provider_daily_quota'
    assert fleet.state['denied']['access_denied']
    saved=json.loads(shared.read_text())
    assert 'one' not in saved and saved['unrelated']==9999999999 and saved['__access']['denied']
    archive=root/'quota-rechecks'/request['request_id']/'vision-quota.json'
    assert json.loads(archive.read_text())['one']['retry_at']==9999999999
    # A new refusal must not be cleared again when the next batch starts.
    fleet.state['one']['retry_at']=8888888888
    assert apply_quota_recheck(fleet)==0
    assert fleet.state['one']['retry_at']==8888888888
    assert checkpoint.read_text()=='preserve'


def test_monitor_recheck_is_explicit_and_explains_saved_status():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/'backend/scripts/exam_scan_status.py').read_text()
    assert "def do_POST" in source
    assert "secrets.compare_digest" in source
    assert "Saved cooldowns are historical refusals" in source
    assert "method:'POST'" in source


def test_launcher_uses_os_lock_not_reused_pid(tmp_path):
    from app.rag.exam_control import scanner_running
    from app.rag.exam_corpus import job_lock
    import os
    atomic_json(tmp_path/'scan-status.json',{'pid':os.getpid()})
    assert scanner_running(tmp_path) is False
    with job_lock(tmp_path):
        assert scanner_running(tmp_path) is True
    assert scanner_running(tmp_path) is False
