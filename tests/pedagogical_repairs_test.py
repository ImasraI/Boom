import hashlib
import json
import pytest
from app.rag.exam_corpus import payload_digest
from app.rag import pedagogical_repairs as R


def test_observed_repairs_are_minimal_and_not_general_json_rewriting():
    raw = '{"text":"$60^\\circ$"}'
    fixed = R.repair_text(raw, 'escape_literal_circ')
    assert json.loads(fixed) == {'text': '$60^\\circ$'}
    assert R.repair_text('{"x":1}```\n', 'remove_trailing_markdown_fence') == '{"x":1}'


@pytest.mark.parametrize('raw,operation', [
    ('{}', 'unknown'), ('{}', 'escape_literal_circ'),
    ('{"x":"\\\\circ"}', 'escape_literal_circ'),
    ('{}', 'remove_trailing_markdown_fence'),
    ('```json\n{}', 'remove_trailing_markdown_fence'),
])
def test_unobserved_formats_are_not_silently_repaired(raw,operation):
    with pytest.raises(ValueError): R.repair_text(raw,operation)


def setup_record(tmp_path,monkeypatch):
    # Shape validation has its own tests; here test the immutable raw/projection binding.
    monkeypatch.setattr(R, 'parse_pedagogical_candidate', json.loads)
    raw = b'{"synthetic":true}```'; original_sha = hashlib.sha256(raw).hexdigest()
    (tmp_path/(original_sha+'.txt')).write_bytes(raw)
    candidate = {'synthetic':True}
    record = {'source_response_sha256':original_sha,'operation':'remove_trailing_markdown_fence',
              'candidate':candidate,'candidate_sha256':payload_digest(candidate),
              'original_outcome':'protocol_held','eligible':False}
    sha = payload_digest(record)
    (tmp_path/('format-repair-'+sha+'.json')).write_text(json.dumps(record))
    (tmp_path/'format-repair-pointer.json').write_text(json.dumps({'sha256':sha}))
    return {'state':'protocol_held','response_sha256':original_sha},sha,record


def test_repair_is_replayed_from_original_bytes_without_promoting_outcome(tmp_path,monkeypatch):
    state,sha,record=setup_record(tmp_path,monkeypatch)
    assert R.load_candidate(tmp_path,state)==(record['candidate'],sha)
    assert state['state']=='protocol_held' and not (tmp_path/'candidate.json').exists()


@pytest.mark.parametrize('mutation',['raw','projection','pointer'])
def test_stale_or_unsafe_projection_fails_closed(tmp_path,monkeypatch,mutation):
    state,sha,record=setup_record(tmp_path,monkeypatch)
    if mutation=='raw': (tmp_path/(state['response_sha256']+'.txt')).write_text('changed')
    if mutation=='projection':
        record['candidate']={'synthetic':False}
        (tmp_path/('format-repair-'+sha+'.json')).write_text(json.dumps(record))
    if mutation=='pointer': (tmp_path/'format-repair-pointer.json').write_text('{"sha256":"../outside"}')
    with pytest.raises(ValueError): R.load_candidate(tmp_path,state)


def test_response_reference_cannot_escape_item_folder(tmp_path):
    with pytest.raises(ValueError):R.load_candidate(tmp_path,{'state':'drafted','response_sha256':'../outside'})
