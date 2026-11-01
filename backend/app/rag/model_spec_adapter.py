"""Local spec-only bridge. It cannot authorize a new design or a bank release."""
import json
from app.rag.authoring_sandbox import construct, validate_candidate


def build_checked_variant(raw):
    if not isinstance(raw, str) or len(raw.encode('utf8')) > 16000:
        raise ValueError('Expected bounded JSON specification')
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate specification key')
            obj[key] = value
        return obj
    spec = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(spec, dict) or set(spec) != {'family', 'params'}:
        raise ValueError('Only family and params are accepted; no prose, answer or code')
    if not isinstance(spec['family'], str) or not isinstance(spec['params'], dict):
        raise ValueError('Invalid typed specification')
    from app.rag import authoring_new_families
    from app.rag import calibrated_families
    if spec['family'] in calibrated_families.FAMILIES:
        candidate=calibrated_families.construct(spec['family'],spec['params'])
        verdict=calibrated_families.validate_candidate(candidate)
    elif spec['family'] in authoring_new_families.FAMILIES:
        candidate = authoring_new_families.construct(spec['family'], spec['params'])
        verdict = authoring_new_families.validate_candidate(candidate)
    else:
        candidate = construct(spec['family'], spec['params'])
        verdict = validate_candidate(candidate)
    if not verdict['valid']:
        raise ValueError('Constructed candidate failed its supported checks')
    return {'candidate': candidate, 'validation': verdict,
            'design_class': 'supported_practice_variant',
            'originality_approved': False, 'human_reviewed': False, 'eligible': False,
            'limitation': 'Model selects a supported spec; final wording and answer are constructor-derived.'}
