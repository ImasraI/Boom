"""Offline language-adherence audit of the six exact pilot records."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import payload_digest,atomic_json
from app.rag.pedagogical_policy import language_audit,prompt_v03,VERSION
from scripts.build_pedagogical_overview import source
from scripts.prepare_pedagogical_pilot import OUT
from scripts.run_pedagogical_recovery import OUT as RECOVERY


def main():
    reports=[];bindings=[]
    for folder in (OUT,RECOVERY):
        _,manifest,receipt,_=source(folder)
        bindings.append(payload_digest(manifest))
        for record in manifest['records']:
            q=record['author_candidate']
            if payload_digest(q)!=record['candidate_sha256']:raise ValueError('Changed review candidate')
            reports.append({'spec_id':record['spec_id'],'audit':language_audit(q)})
    p=json.loads((OUT/'pointer.json').read_text());protocol=json.loads((OUT/p['file']).read_text())
    if payload_digest(protocol)!=p['sha256']:raise ValueError('Changed source protocol')
    prompts=[{'spec_id':r['spec']['id'],'prompt':prompt_v03(r['spec'])} for r in protocol['drafts']]
    for r in prompts:r['prompt_sha256']=hashlib.sha256(r['prompt'].encode()).hexdigest()
    result={'schema_version':'0.1','policy_version':VERSION,'source_review_sha256':bindings,
            'reports':reports,'held_candidates':sum(bool(r['audit']['holds']) for r in reports),
            'next_prompt_candidates':prompts,'provider_calls':0,'eligible':False,
            'next_prompts_frozen_for_execution':False,'human_approved':False}
    folder=OUT/'language-policy';folder.mkdir(exist_ok=True);sha=payload_digest(result);path=folder/(sha+'.json')
    if path.exists():
        if json.loads(path.read_text())!=result:raise ValueError('Changed audit snapshot')
    else:atomic_json(path,result)
    atomic_json(folder/'pointer.json',{'file':path.name,'sha256':sha})
    print(json.dumps({'audited_candidates':len(reports),'language_holds':result['held_candidates'],
                      'new_prompt_drafts':len(prompts),'provider_calls':0,'eligible':False}))


if __name__=='__main__':main()
