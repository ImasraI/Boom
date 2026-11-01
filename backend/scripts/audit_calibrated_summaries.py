"""Read-only local summary retrieval audit; preserves confirmation and active policy."""
import hashlib,json,sys
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_review import ReviewStore
from app.rag.calibrated_designs import reviewed_material,select_summaries
from app.rag.review_policy_projection import project_reviews
from app.rag.source_routing import load_policy
from app.rag.exam_corpus import payload_digest,atomic_json


def main():
    data=Path(__file__).resolve().parents[1]/'data';base=data/'authoring_work'
    out=base/'calibrated-design-summaries-v1'
    status=json.loads((out/'status.json').read_text(encoding='utf8'))
    name=status['artifact']
    if Path(name).name!=name or not name.startswith('confirmation-'):raise ValueError('Invalid confirmation pointer')
    confirmation=json.loads((out/name).read_text(encoding='utf8'))
    if payload_digest(confirmation)!=status['sha256']:raise ValueError('Confirmation changed')
    receipt=confirmation['receipt'];materials=confirmation['materials']
    views=[]
    for path in (base/'review-policy-projection-v1').glob('calibration-*.json'):
        if hashlib.sha256(path.read_bytes()).hexdigest()==receipt['displayed_calibration_sha256']:
            views.append(json.loads(path.read_text(encoding='utf8')))
    if len(views)!=1:raise ValueError('Missing or ambiguous reviewed view')
    view=views[0];view_items={r['question_ref']:r for r in view['items']}
    merged=base/'reasoning-merged-v1';ms=json.loads((merged/'status.json').read_text())
    if ms['sha256']!=view['source_artifact_sha256']:raise ValueError('Merged annotations changed')
    if Path(ms['artifact']).name!=ms['artifact']:raise ValueError('Invalid merged pointer')
    bundle=json.loads((merged/ms['artifact']).read_text(encoding='utf8'))
    if payload_digest(bundle)!=ms['sha256']:raise ValueError('Merged artifact integrity failed')
    records={r['question_ref']:r for r in bundle['records']}
    cat=data/'knowledge_graph/catalog.json';nodes={n['id']:n for n in json.loads(cat.read_text(encoding='utf8'))['nodes']}
    store=ReviewStore(base/'review-ledger-v1',base/'s1a-mapped',cat)
    documents={d['document_id']:d for d in store.load()['documents']}
    bindings={};held=[]
    for material in materials:
        qid=material['question_ref']
        try:
            _,_,binding,_,_,_=store.current(qid)
            expected=reviewed_material(view_items[qid],records[qid],binding,nodes)
            if any(material.get(k)!=v for k,v in expected.items()):
                raise ValueError('Reviewed summary material changed')
            doc=documents[binding['documentId']]
            if any(material.get(k)!=doc[v] for k,v in [('major','major'),('source_role','classification'),('classification_state','classification_state')]):
                raise ValueError('Source classification changed')
            current_extraction=project_reviews(binding,store.events(qid))['reviews'].get('extraction',{})
            if not current_extraction or current_extraction!=material.get('extraction_review'):
                raise ValueError('Extraction decision changed')
            bindings[qid]=binding
        except Exception as error:
            # Saved artifacts remain inspectable; no raw question text in reports.
            held.append({'id':qid,'reason':'current_evidence_failed','error_type':type(error).__name__})
    scope=list({k for m in materials for k in m['knowledge_ids']})
    policy=load_policy()
    def retrieve(ms=materials,rc=receipt,pl=policy,ks=scope,bs=bindings):
        return select_summaries(ms,rc,pl,knowledge_ids=ks,current_bindings=bs,major='riazi')
    selected,audit=retrieve()
    checks={}
    if len(selected)==len(materials) and materials:
        checks['missing_scope_returns_zero']=len(retrieve(ks=[])[0])==0
        altered=deepcopy(bindings);altered[materials[0]['question_ref']]['evidenceToken']='stale-test'
        checks['changed_binding_removes_one']=len(retrieve(bs=altered)[0])==len(materials)-1
        excluded=deepcopy(policy)
        excluded['excluded_document_ids']=list(set(policy.get('excluded_document_ids',[]))|{m['binding']['documentId'] for m in materials})
        checks['excluded_sources_return_zero']=len(retrieve(pl=excluded)[0])==0
        wrong=deepcopy(receipt);wrong['reviewer_kind']='model'
        checks['model_attribution_returns_zero']=len(retrieve(rc=wrong)[0])==0
        changed=deepcopy(materials);changed[0]['main_decision']='changed-test'
        checks['changed_summary_invalidates_confirmation']=len(retrieve(ms=changed)[0])==0
        checks['each_scope_retrieves_only_its_node']=all(
            all(set(r['knowledge_ids']).issubset(set(m['knowledge_ids'])) for r in retrieve(ks=m['knowledge_ids'])[0])
            and any(r['question_ref']==m['question_ref'] for r in retrieve(ks=m['knowledge_ids'])[0]) for m in materials)
        if not all(checks.values()):raise ValueError('Local retrieval regression failed')
    result={'schema_version':'0.1','confirmation_sha256':status['sha256'],
        'selected_summaries':selected,'audit':audit,'held':held,'regression_checks':checks,'scope':'local_summary_retrieval_only',
        'scientific_approval':False,'production_activation':False}
    digest=payload_digest(result);audit_name='retrieval-'+digest+'.json'
    if not (out/audit_name).exists():atomic_json(out/audit_name,result)
    atomic_json(out/'selected-summaries.json',selected)
    atomic_json(out/'local-retrieval-audit.json',audit)
    status.update(retrievable_local_summaries=len(selected),latest_audit=audit_name,
                  audit_sha256=digest,current_evidence_holds=len(held),local_regression_checks=checks)
    atomic_json(out/'status.json',status)
    print(json.dumps({k:v for k,v in status.items() if k not in ('artifact','latest_audit')}))


if __name__=='__main__':main()
