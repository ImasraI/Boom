"""Explicit format-only projections; original provider outcomes remain held."""
import hashlib
import json
from app.rag.exam_corpus import payload_digest
from app.rag.pedagogical_authoring import parse_pedagogical_candidate


def repair_text(raw, operation):
    if operation == 'remove_trailing_markdown_fence':
        text = raw.rstrip()
        if not text.endswith('}```'): raise ValueError('Expected exact trailing fence')
        return text[:-3]
    if operation == 'escape_literal_circ':
        # Only the observed invalid JSON escape is authorized. Never repair
        # valid escapes such as \n or interpret model-provided executable text.
        if raw.count('\\circ') != 1 or '\\\\circ' in raw:
            raise ValueError('Expected one literal invalid circ escape')
        return raw.replace('\\circ', '\\\\circ')
    raise ValueError('Unknown format repair')


def load_candidate(folder, state):
    response_sha = state['response_sha256']
    if not isinstance(response_sha,str) or len(response_sha)!=64 or any(c not in '0123456789abcdef' for c in response_sha):
        raise ValueError('Invalid response reference')
    raw = (folder / (response_sha + '.txt')).read_bytes()
    if hashlib.sha256(raw).hexdigest() != state['response_sha256']:
        raise ValueError('Changed author response')
    if state['state'] == 'drafted':
        candidate = parse_pedagogical_candidate((folder / 'candidate.json').read_text(encoding='utf8'))
        if json.loads(raw) != candidate: raise ValueError('Candidate differs from author response')
        return candidate, None
    if state['state'] != 'protocol_held': raise ValueError('No reviewable candidate')
    pointer = json.loads((folder / 'format-repair-pointer.json').read_text(encoding='utf8'))
    digest = pointer['sha256']
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid repair reference')
    record = json.loads((folder / ('format-repair-' + digest + '.json')).read_text(encoding='utf8'))
    if payload_digest(record) != digest or record['source_response_sha256'] != state['response_sha256']:
        raise ValueError('Stale format repair')
    repaired = repair_text(raw.decode('utf8'), record['operation'])
    candidate = parse_pedagogical_candidate(repaired)
    if candidate != record['candidate'] or payload_digest(candidate) != record['candidate_sha256']:
        raise ValueError('Changed format projection')
    if record['original_outcome'] != 'protocol_held' or record['eligible'] is not False:
        raise ValueError('Format repair cannot promote the original outcome')
    return candidate, digest
