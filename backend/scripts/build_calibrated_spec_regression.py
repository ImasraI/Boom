"""Freeze24 local practice-spec cases; no model calls, novelty or release claims."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.model_spec_adapter import build_checked_variant
from app.rag.calibrated_families import VERSION


def main():
    root=Path(__file__).resolve().parents[2]
    base=root/'backend/data/authoring_work'
    source=base/'grounded-authoring-trial-v1/attempt-10/validation-bundle-v1'
    pointer=json.loads((source/'status.json').read_text())
    if Path(pointer['artifact']).name!=pointer['artifact']:raise ValueError('Invalid evidence pointer')
    snapshot=json.loads((source/pointer['artifact']).read_text(encoding='utf8'))
    if payload_digest(snapshot)!=pointer['sha256'] or snapshot['summary']['local_regression_ready']!=3:
        raise ValueError('Source trial validation changed')
    specs=([dict(family='cubic_difference_feasibility',params={'k':k}) for k in (1,2,4,7,9,25,99,100)]
        +[dict(family='trapezoid_parallel_offset',params={'a':a,'b':b}) for a,b in
          ((15,10),(12,8),(20,7),(9,6),(49,48),(18,12),(25,10),(16,8))]
        +[dict(family='modular_power_square_count',params={'limit':n}) for n in (60,61,79,100,119,120,2026,5000)])
    out=base/'calibrated-spec-regression-v1';out.mkdir(exist_ok=True)
    contract=dict(schema_version='0.1',constructor_version=VERSION,specs=specs,
        source_trial_snapshot_sha256=pointer['sha256'],
        code_sha256={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in
            ('backend/app/rag/calibrated_families.py','backend/app/rag/model_spec_adapter.py')},
        role='Supported practice-variant regression, not a free-form creativity benchmark',
        inherited_human_review=False,provider_calls=0)
    name='manifest-'+payload_digest(contract)+'.json'
    if not (out/name).exists():atomic_json(out/name,contract)
    items=[build_checked_variant(json.dumps(spec)) for spec in specs]
    if any(not x['validation']['valid'] or x['eligible'] or x['human_reviewed'] for x in items):
        raise ValueError('Unexpected variant state')
    bundle=dict(manifest_sha256=payload_digest(contract),items=items,release_eligible=0,
        limitations=['Template variants do not establish new design originality',
            'Human editorial feedback on original three questions does not approve these variants',
            'No production generation/bank/retrieval activation'])
    artifact='cases-'+payload_digest(bundle)+'.json'
    if not (out/artifact).exists():atomic_json(out/artifact,bundle)
    status=dict(manifest=name,manifest_sha256=payload_digest(contract),artifact=artifact,
        sha256=payload_digest(bundle),specs=len(specs),canonical_checks_passed=len(items),
        families=3,provider_calls=0,release_eligible=0)
    atomic_json(out/'status.json',status)
    print(json.dumps({k:v for k,v in status.items() if k not in ('manifest','manifest_sha256','artifact','sha256')}))


if __name__=='__main__':main()
