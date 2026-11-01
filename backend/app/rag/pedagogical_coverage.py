"""Describe assigned versus checked coverage without promoting model labels."""
from collections import Counter
from app.rag.exam_corpus import payload_digest
from app.rag.pedagogical_authoring import teaching_holds


def coverage(protocol, states, candidates, checks):
    specs = [row['spec'] for row in protocol['drafts']]
    ids = [s['id'] for s in specs]
    if len(ids) != len(set(ids)) or set(states) - set(ids) or set(candidates) - set(ids):
        raise ValueError('Unknown or duplicate pilot item')
    if len({r['spec_id'] for r in checks}) != len(checks) or {r['spec_id'] for r in checks} - set(ids):
        raise ValueError('Unknown or duplicate check')
    by_id = {r['spec_id']: r for r in checks}
    rows = []
    for spec in specs:
        identifier = spec['id']; state = states.get(identifier, {})
        q = candidates.get(identifier); check = by_id.get(identifier)
        if q is not None and state.get('state') not in ('drafted','protocol_held'):
            raise ValueError('Candidate lacks drafted outcome')
        if q is not None and state.get('state')=='protocol_held' and not (check and check.get('format_repair_sha256')):
            raise ValueError('Held candidate lacks checked format repair')
        if check and (q is None or check['candidate_sha256'] != payload_digest(q)):
            raise ValueError('Stale mathematical check')
        rows.append({
            'spec_id': identifier, 'assigned_mechanism': spec['primary_mechanism'],
            'outcome': state.get('state', 'not_attempted'),
            'candidate_sha256': payload_digest(q) if q is not None else None,
            'format_repair_sha256': check.get('format_repair_sha256') if check else None,
            'assistant_math_checked': check is not None,
            'raw_diagram_passed': check['raw_geometry_audit']['audit']['all_passed'] if check else None,
            'presented_diagram_passed': check['corrected_geometry_audit']['audit']['all_passed'] if check else None,
            'teaching_holds': teaching_holds(q) if q is not None else None,
            'proposed_techniques': [t['id'] for t in q['pedagogy']['proposed_techniques']] if q is not None else [],
            # No theorem-family diversity is inferred from the task or technique names.
            'independently_adjudicated_mechanism': None,
            'human_review': False, 'eligible': False,
        })
    return {'schema_version': '0.1', 'protocol_sha256': payload_digest(protocol),
            'planned': len(rows), 'assigned_mechanism_counts': dict(Counter(r['assigned_mechanism'] for r in rows)),
            'outcome_counts': dict(Counter(r['outcome'] for r in rows)),
            'assistant_math_checked': sum(r['assistant_math_checked'] for r in rows),
            'adjudicated_mechanism_coverage': None, 'rows': rows, 'eligible': False,
            'limitations': ['Assigned breadth is not demonstrated solution diversity.',
                            'Technique presence does not establish difficulty, originality or student weakness.',
                            'Assistant checks and model agreement do not establish human scientific approval.']}
