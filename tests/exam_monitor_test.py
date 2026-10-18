import importlib.util
import json
from pathlib import Path

import pytest


def monitor():
    path = Path(__file__).resolve().parents[1]/'backend/scripts/exam_scan_status.py'
    spec = importlib.util.spec_from_file_location('exam_monitor_recovery', path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_reader_recovers_and_does_not_log_exception_secrets(tmp_path, monkeypatch):
    module=monitor();calls=[]
    monkeypatch.setattr(module,'stored_counts',lambda root:{})
    def snapshot(*args,**kwargs):
        calls.append(1)
        if len(calls)==1:raise PermissionError('private-key-and-proxy-secret')
        return {'phase':'scanning'}
    monkeypatch.setattr(module,'snapshot',snapshot)
    reader=module.Reader(tmp_path)
    with pytest.raises(PermissionError):reader.get()
    assert reader.get()=={'phase':'scanning'}
    content=(tmp_path/'monitor-errors.jsonl').read_text()
    assert 'private-key-and-proxy-secret' not in content
    error=json.loads(content)
    assert error['error_type']=='PermissionError' and error['frames']


def test_continuous_monitor_survives_one_failed_read(tmp_path, monkeypatch, capsys):
    import sys
    module=monitor();reads=[];waits=[]
    class Reader:
        def __init__(self,root):pass
        def get(self):
            reads.append(1)
            if len(reads)==1:raise OSError('simulated read failure')
            return dict(phase='scanning',worker_alive=True,full_ocr_pages=5,total_pages=30,
                        saved_question_candidates=20,active_candidates=1,requests_this_run=2,
                        qualified_references=0,retry_not_before=None)
    def sleep(seconds):
        waits.append(seconds)
        if len(waits)==2:raise KeyboardInterrupt()
    monkeypatch.setattr(module,'Reader',Reader)
    monkeypatch.setattr(module.time,'sleep',sleep)
    monkeypatch.setattr(sys,'argv',['monitor','--watch','--root',str(tmp_path)])
    module.main()
    output=capsys.readouterr().out
    assert len(reads)==2 and waits==[5,5]
    assert 'retrying' in output and 'OCR pages 5/30' in output
