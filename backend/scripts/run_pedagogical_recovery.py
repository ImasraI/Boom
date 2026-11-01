"""One separately frozen recovery attempt after the reported VPN server change.

Original six outcomes are never changed. This is not an automatic retry loop.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.authoring_benchmark import saved_json,execution_lock
from scripts import run_pedagogical_pilot as runner
from scripts.prepare_pedagogical_pilot import OUT as ORIGINAL,ROOT

OUT=ORIGINAL.parent/'pedagogical-geometry-v2-provider-recovery-v1'
TARGETS=('cyclic_constraints','reflection_isometry')


def prepare():
    pointer=saved_json(ORIGINAL/'pointer.json')
    if pointer['file']!='protocol-'+pointer['sha256']+'.json':raise ValueError('Unsafe parent protocol')
    parent=saved_json(ORIGINAL/pointer['file'])
    if payload_digest(parent)!=pointer['sha256']:raise ValueError('Changed parent protocol')
    states={name:saved_json(ORIGINAL/'items'/name/'state.json') for name in TARGETS}
    if any(s['state']!='provider_error' for s in states.values()):raise ValueError('Only recorded provider failures may enter recovery')
    manifest=copy.deepcopy(parent)
    manifest.update(planned_items=2,parent_protocol_sha256=pointer['sha256'],
                    parent_outcome_sha256={k:payload_digest(v) for k,v in states.items()},
                    recovery_reason='User reported switching VPN servers; one new attempt per prior provider failure.',
                    original_outcomes_preserved=True)
    manifest['drafts']=[row for row in parent['drafts'] if row['spec']['id'] in TARGETS]
    manifest['evidence']=[row for row in parent['evidence'] if row['spec_id'] in TARGETS]
    digest=payload_digest(manifest);OUT.mkdir(exist_ok=True);path=OUT/('protocol-'+digest+'.json')
    if (OUT/'pointer.json').exists() and saved_json(OUT/'pointer.json')['sha256']!=digest:
        raise ValueError('Changed frozen recovery')
    if path.exists():
        if saved_json(path)!=manifest:raise ValueError('Changed recovery manifest')
    else:atomic_json(path,manifest)
    atomic_json(OUT/'pointer.json',{'file':path.name,'sha256':digest})
    return manifest,digest


if __name__=='__main__':
    if Path.cwd().resolve()!=ROOT/'backend':raise ValueError('Run from backend')
    OUT.mkdir(exist_ok=True)
    runner.OUT=OUT;runner.prepare=prepare
    with execution_lock(OUT):runner.run(2)
