"""Offline, hash-bound pilot status; no providers, database or source promotion."""
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_benchmark import saved_json
from app.rag.exam_corpus import atomic_json, payload_digest
from app.rag.pedagogical_authoring import parse_pedagogical_candidate
from app.rag.pedagogical_repairs import load_candidate
from app.rag.pedagogical_coverage import coverage
from scripts.prepare_pedagogical_pilot import OUT


def bound_file(folder, pointer):
    if not re.fullmatch(r'(?:protocol-)?[a-f0-9]{64}\.json', pointer['file']):
        raise ValueError('Unsafe artifact reference')
    record = saved_json(folder / pointer['file'])
    if payload_digest(record) != pointer['sha256']:
        raise ValueError('Changed artifact')
    return record


def main():
    protocol = bound_file(OUT, saved_json(OUT / 'pointer.json'))
    states = {}; candidates = {}
    for row in protocol['drafts']:
        identifier = row['spec']['id']; folder = OUT / 'items' / identifier
        states[identifier] = saved_json(folder / 'state.json', {})
        if (states[identifier].get('state') == 'drafted' or
            states[identifier].get('state') == 'protocol_held' and (folder/'format-repair-pointer.json').exists()):
            candidates[identifier],_ = load_candidate(folder,states[identifier])
    check_folder = OUT / 'independent-checks'
    checks = bound_file(check_folder, saved_json(check_folder / 'pointer.json'))['records']
    result = coverage(protocol, states, candidates, checks)
    folder = OUT / 'coverage'; folder.mkdir(exist_ok=True)
    sha = payload_digest(result); path = folder / (sha + '.json')
    if not path.exists(): atomic_json(path, result)
    elif saved_json(path) != result: raise ValueError('Changed frozen coverage')
    atomic_json(folder / 'pointer.json', {'file': path.name, 'sha256': sha})
    print(json.dumps({k: result[k] for k in ('planned', 'outcome_counts', 'assistant_math_checked', 'adjudicated_mechanism_coverage')}))


if __name__ == '__main__': main()
