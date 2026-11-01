"""Offline surface-copy screen against prior generated drafts, never heldouts."""
from difflib import SequenceMatcher
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_originality import screen,normalized_structure,VERSION
from app.rag.exam_corpus import payload_digest,atomic_json
from app.rag.authoring_benchmark import saved_json
from scripts.build_pedagogical_overview import source
from scripts.carry_benchmark_verification import load_review
from scripts.prepare_pedagogical_pilot import OUT
from scripts.run_pedagogical_recovery import OUT as RECOVERY


def main():
    old=OUT.parent/'development-benchmark-v1';ptr=saved_json(old/'review-pointer.json')
    _,binding,_=load_review(ptr['folder'])
    references=[]
    for row in binding['records']:
        q=row['candidate']
        if payload_digest(q)!=row['candidate_sha256']:raise ValueError('Changed original draft')
        references.append({'id':'original:'+row['alias'],'text':q['text'],'candidate_sha256':row['candidate_sha256']})
    candidates=[];parents=[]
    for folder in (OUT,RECOVERY):
        _,manifest,_,_=source(folder);parents.append(payload_digest(manifest))
        for row in manifest['records']:
            q=row['author_candidate']
            if payload_digest(q)!=row['candidate_sha256']:raise ValueError('Changed new draft')
            candidates.append({'id':row['spec_id'],'text':q['text'],'candidate_sha256':row['candidate_sha256']})
    reports=[]
    for q in candidates:
        refs=references+[r for r in candidates if r['id']!=q['id']]
        ranking=sorted([{'reference_id':r['id'],'similarity':round(SequenceMatcher(None,
            normalized_structure(q['text']),normalized_structure(r['text']),autojunk=False).ratio(),4)}
            for r in refs],key=lambda r:(-r['similarity'],r['reference_id']))[:3]
        reports.append({'spec_id':q['id'],'candidate_sha256':q['candidate_sha256'],
                        'surface_screen':screen(q['text'],refs),'nearest_surface_neighbors':ranking,
                        'semantic_originality':None,'eligible':False})
    result={'schema_version':'0.1','screen_version':VERSION,'new_review_sha256':parents,
            'old_binding_sha256':payload_digest(binding),'prior_generated_references':len(references),
            'new_candidates':len(candidates),'reports':reports,'provider_calls':0,
            'close_surface_holds':sum(r['surface_screen']['state']=='held_close_variant' for r in reports),
            'reference_set_sha256':payload_digest([{k:r[k] for k in ('id','candidate_sha256')} for r in references+candidates]),
            'eligible':False,'limitations':['Generated drafts only, not a corpus-wide comparison.',
                'Scalar-normalized text similarity misses mathematical isomorphisms and shared solution chains.',
                'A clean screen is not originality, variety, quality or human approval.']}
    folder=OUT/'originality-screen';folder.mkdir(exist_ok=True);sha=payload_digest(result);path=folder/(sha+'.json')
    if path.exists():
        if saved_json(path)!=result:raise ValueError('Frozen screen changed')
    else:atomic_json(path,result)
    atomic_json(folder/'pointer.json',{'file':path.name,'sha256':sha})
    print(json.dumps({k:result[k] for k in ('new_candidates','prior_generated_references','close_surface_holds','provider_calls','eligible')}))


if __name__=='__main__':main()
