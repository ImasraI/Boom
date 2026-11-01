"""Audit current review evidence without activating or replacing retrieval policy."""
import hashlib,json,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_review import ReviewStore,ReviewError
from app.rag.review_policy_projection import project_reviews
from app.rag.exam_corpus import atomic_json,payload_digest


def main():
    data=Path(__file__).resolve().parents[1]/'data'
    base=data/'authoring_work'
    store=ReviewStore(base/'review-ledger-v1',base/'s1a-mapped',data/'knowledge_graph/catalog.json')
    packet=store.load();items=[];dimensions=Counter();gaps=Counter()
    for q in packet['questions']:
        if q['section']!='math':continue
        try:
            _,_,binding,_,_,_=store.current(q['id'])
            projection=project_reviews(binding,store.events(q['id']))
            for dimension in projection['reviews']:dimensions[dimension]+=1
            missing=[d for d in ('extraction','curriculum','design') if d not in projection['reviews']]
            for d in missing:gaps[d]+=1
            items.append({'record_id':q['id'],'binding':binding,'projection':projection,
                          'missing_authoring_dimensions':missing,'eligible':False})
        except (ReviewError,OSError,ValueError) as error:
            items.append({'record_id':q['id'],'error_type':type(error).__name__,'eligible':False})
    body={'schema_version':'0.1','packet_sha256':packet['packet_sha256'],'items':items,
          'automatic_activation':False,'eligible':False}
    digest=payload_digest(body);out=base/'review-policy-projection-v1';out.mkdir(exist_ok=True)
    name='projection-'+digest+'.json'
    if not (out/name).exists():atomic_json(out/name,body)
    summary={'artifact':name,'sha256':digest,'math_records':len(items),
        'current_passed_dimensions':dict(dimensions),'missing_authoring_dimensions':dict(gaps),
        'record_errors':sum('error_type' in r for r in items),'eligible':0,
        'automatic_activation':False,'policy_replaced':False,
        'limitation':'Projection is evidence-only; no knowledge mapping or design approval is inferred.'}
    atomic_json(out/'status.json',summary)
    print(json.dumps(summary))


if __name__=='__main__':main()
