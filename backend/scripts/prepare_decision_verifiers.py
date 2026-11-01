"""Freeze answer-free evaluation packets only for saved structured drafts."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import payload_digest,atomic_json
from app.rag.authoring_benchmark import saved_json
from app.rag.decision_authoring import load_candidate
from app.rag.decision_evaluation import packets,stem_prompt,option_prompt
from scripts.prepare_decision_pilot import OUT


def main():
    ptr=saved_json(OUT/'pointer.json')
    if ptr['file']!='protocol-'+ptr['sha256']+'.json':raise ValueError('Unsafe protocol reference')
    protocol=saved_json(OUT/ptr['file'])
    if payload_digest(protocol)!=ptr['sha256']:raise ValueError('Changed protocol')
    # Freeze the evaluation instructions even before the first draft exists.
    synthetic=packets({'text':'{{written_question}}','options':['{{option_1}}','{{option_2}}','{{option_3}}','{{option_4}}']})
    policy={'schema_version':'0.1','protocol_sha256':ptr['sha256'],
        'stem_template':stem_prompt(synthetic['stem_only']),
        'option_template':option_prompt(synthetic['option_aware']),
        'provider_calls':0,'eligible':False,'independent_requests':True,
        'meaning':'Template placeholders, not real source/question data; proofs require semantic review.'}
    policy_sha=payload_digest(policy);policy_path=OUT/('evaluation-policy-'+policy_sha+'.json')
    if policy_path.exists():
        if saved_json(policy_path)!=policy:raise ValueError('Frozen evaluation policy changed')
    else:atomic_json(policy_path,policy)
    atomic_json(OUT/'evaluation-policy-pointer.json',{'file':policy_path.name,'sha256':policy_sha})
    count=0
    for draft in protocol['drafts']:
        folder=OUT/'items'/draft['spec']['id'];state=saved_json(folder/'state.json',{})
        if state.get('state')!='drafted':continue
        q,_=load_candidate(folder,state);p=packets(q)
        record={'schema_version':'0.1','protocol_sha256':ptr['sha256'],'evaluation_policy_sha256':policy_sha,'packets':p,
                'stem_only_prompt':stem_prompt(p['stem_only']),'option_aware_prompt':option_prompt(p['option_aware']),
                'judgment':'pending_independent_calls_and_semantic_review','provider_calls':0,'eligible':False}
        for key in ('stem_only_prompt','option_aware_prompt'):record[key+'_sha256']=hashlib.sha256(record[key].encode()).hexdigest()
        dest=folder/'evaluation-packets';dest.mkdir(exist_ok=True);sha=payload_digest(record);path=dest/(sha+'.json')
        if path.exists():
            if saved_json(path)!=record:raise ValueError('Changed frozen packet')
        else:atomic_json(path,record)
        atomic_json(dest/'pointer.json',{'file':path.name,'sha256':sha});count+=1
    print(json.dumps({'prepared_candidate_packets':count,'provider_calls':0,'phase':'awaiting_generation' if not count else 'packets_prepared'}))


if __name__=='__main__':main()
