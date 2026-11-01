import pytest
from app.rag.exam_corpus import payload_digest
from app.rag.pedagogical_coverage import coverage


def inputs():
    p = {'drafts': [{'spec': {'id': i, 'primary_mechanism': i}} for i in ('circle', 'area')]}
    q = {'pedagogy': {'proposed_techniques': [{'id': 'tech.symmetry'}], 'boundary_checks': []}}
    check = {'spec_id': 'circle', 'candidate_sha256': payload_digest(q),
             'raw_geometry_audit': {'audit': {'all_passed': False}},
             'corrected_geometry_audit': {'audit': {'all_passed': True}}}
    return p, {'circle': {'state': 'drafted'}}, {'circle': q}, [check]


def test_assigned_breadth_does_not_become_verified_diversity():
    result = coverage(*inputs())
    assert result['planned'] == 2 and result['assistant_math_checked'] == 1
    assert result['adjudicated_mechanism_coverage'] is None
    assert result['outcome_counts'] == {'drafted': 1, 'not_attempted': 1}
    row = result['rows'][0]
    assert row['raw_diagram_passed'] is False and row['presented_diagram_passed'] is True
    assert row['teaching_holds'] == ['boundary_checks_unresolved']
    assert row['independently_adjudicated_mechanism'] is None and row['eligible'] is False


@pytest.mark.parametrize('mutation', ['stale', 'unknown_check', 'duplicate_check', 'not_drafted', 'unknown_state'])
def test_bad_evidence_cannot_increase_coverage(mutation):
    p, states, qs, checks = inputs()
    if mutation == 'stale': checks[0]['candidate_sha256'] = '0' * 64
    if mutation == 'unknown_check': checks[0]['spec_id'] = 'outside'
    if mutation == 'duplicate_check': checks.append(checks[0])
    if mutation == 'not_drafted': states['circle']['state'] = 'provider_error'
    if mutation == 'unknown_state': states['outside'] = {}
    with pytest.raises(ValueError): coverage(p, states, qs, checks)
