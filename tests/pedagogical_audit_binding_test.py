import json
import pytest
from app.rag.exam_corpus import payload_digest
from scripts import build_pedagogical_overview as overview


def test_optional_quality_audit_is_bound_to_exact_bytes_and_safe_reference(tmp_path,monkeypatch):
    monkeypatch.setattr(overview,'OUT',tmp_path)
    assert overview.optional_audit('language-policy') is None
    folder=tmp_path/'language-policy';folder.mkdir()
    record={'reports':[],'eligible':False};sha=payload_digest(record)
    (folder/(sha+'.json')).write_text(json.dumps(record))
    (folder/'pointer.json').write_text(json.dumps({'file':sha+'.json','sha256':sha}))
    assert overview.optional_audit('language-policy')==record
    (folder/(sha+'.json')).write_text('{"reports":[],"eligible":true}')
    with pytest.raises(ValueError):overview.optional_audit('language-policy')


def test_quality_audit_reference_cannot_escape_private_folder(tmp_path,monkeypatch):
    monkeypatch.setattr(overview,'OUT',tmp_path)
    folder=tmp_path/'language-policy';folder.mkdir()
    (folder/'pointer.json').write_text(json.dumps({'file':'../../outside.json','sha256':'a'*64}))
    with pytest.raises(ValueError):overview.optional_audit('language-policy')
