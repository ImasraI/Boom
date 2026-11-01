"""Project two inspected formatting defects; no rewrite, provider or promotion."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import payload_digest, atomic_json
from app.rag.pedagogical_authoring import parse_pedagogical_candidate
from app.rag.pedagogical_repairs import repair_text, load_candidate
from scripts.prepare_pedagogical_pilot import OUT

REPAIRS = {
    'cosine_feasibility': ('f8c42136d4b0f09f36089e5eaef34db3d81735db412e68285affca2091098433', 'escape_literal_circ'),
    'altitude_admissibility': ('e475061ffa6e06c2e56f2566aea30faa48c2a558f8d9b146b55e3200ac32f1da', 'remove_trailing_markdown_fence'),
}


def main():
    for identifier, (expected, operation) in REPAIRS.items():
        folder = OUT / 'items' / identifier
        state = json.loads((folder / 'state.json').read_text(encoding='utf8'))
        if state['state'] != 'protocol_held' or state['response_sha256'] != expected:
            raise ValueError('Repair requires the inspected held response')
        raw = (folder / (expected + '.txt')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected: raise ValueError('Changed held response')
        q = parse_pedagogical_candidate(repair_text(raw.decode('utf8'), operation))
        record = {'schema_version': '0.1', 'source_response_sha256': expected,
                  'operation': operation, 'candidate': q, 'candidate_sha256': payload_digest(q),
                  'original_outcome': 'protocol_held', 'eligible': False,
                  'scope': 'Format-only assistant projection; no scientific or human approval'}
        sha = payload_digest(record); path = folder / ('format-repair-' + sha + '.json')
        if path.exists():
            if json.loads(path.read_text(encoding='utf8')) != record: raise ValueError('Frozen repair changed')
        else: atomic_json(path, record)
        atomic_json(folder / 'format-repair-pointer.json', {'sha256': sha})
        load_candidate(folder, state)
        print(json.dumps({'spec_id': identifier, 'candidate_sha256': payload_digest(q), 'original_outcome': 'protocol_held'}))


if __name__ == '__main__': main()
