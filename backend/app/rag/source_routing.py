"""Purpose-specific local retrieval policy. No providers, DB imports or promotion."""
from pathlib import Path
import hashlib
import json
import math
import re
from collections import Counter

POLICY_PATH=Path(__file__).resolve().parents[2]/"data/authoring_work/h1/retrieval-policy-v1.json"
ROLES={"authoring_design":{"mock_exam","official_exam"},"factual_grounding":{"textbook"},"weekly_scope":{"mock_plan"},"weekly_tests":{"test_book"}}

def load_policy(path=None):
    try:
        p=json.loads(Path(path or POLICY_PATH).read_text(encoding="utf-8"))
        if not isinstance(p,dict) or p.get("schema_version")!="0.1" or not isinstance(p.get("records",[]),list):return {}
        return p
    except (OSError,ValueError,TypeError):return {}

def text_hash(text):return hashlib.sha256(text.encode("utf-8")).hexdigest()

def filter_records(records,policy,*,purpose,major,curriculum_version,scope_id=None):
    """Filter BEFORE any ranker sees data. Unknown evidence is held, never inferred."""
    accepted=[];audit=[]
    if not isinstance(policy,dict):
        return [],[{"id":None,"reasons":["missing_policy"]}]
    list_fields=('excluded_document_ids','excluded_family_ids','excluded_record_ids',
                 'development_document_ids','allowed_knowledge_ids')
    if (not isinstance(records,list) or any(not isinstance(policy.get(k,[]),list)
            or any(not isinstance(v,str) for v in policy.get(k,[])) for k in list_fields)
            or not isinstance(policy.get('scopes',{}),dict)):
        return [],[{"id":None,"reasons":["malformed_policy_or_records"]}]
    counts=Counter(r.get('id') for r in records if isinstance(r,dict) and isinstance(r.get('id'),str))
    denied=set(policy.get("excluded_document_ids",[]));denied_families=set(policy.get("excluded_family_ids",[]))
    for r in records:
        if not isinstance(r,dict):
            audit.append({"id":None,"reasons":["malformed_record"]});continue
        if (not isinstance(r.get('id'),str) or not r['id'] or counts[r['id']]!=1
            or any(not isinstance(r.get(k),str) for k in ('document_id','role','major','classification_state'))
            or not isinstance(r.get('knowledge_ids',[]),list)
            or any(not isinstance(k,str) for k in r.get('knowledge_ids',[]))
            or not isinstance(r.get('reviews',{}),dict)
            or any(not isinstance(v,dict) for v in r.get('reviews',{}).values())):
            audit.append({'id':r.get('id') if isinstance(r.get('id'),str) else None,
                          'reasons':['malformed_or_duplicate_record']});continue
        reasons=[]
        if purpose not in ROLES:reasons.append("unknown_purpose")
        if policy.get("schema_version")!="0.1":reasons.append("missing_policy")
        if r.get("role") not in ROLES.get(purpose,set()):reasons.append("wrong_source_role")
        if not r.get("document_id") or r.get("document_id") in denied:reasons.append("excluded_or_unknown_document")
        if r.get("family_id") in denied_families:reasons.append("excluded_family")
        if r.get("id") in policy.get("excluded_record_ids",[]):reasons.append("excluded_record")
        if r.get("document_id") not in policy.get("development_document_ids",[]):reasons.append("document_not_in_development_manifest")
        if purpose=="authoring_design" and r.get("contains_answer") is not False:reasons.append("answer_bearing_or_unknown_example")
        if r.get("split")!="development":reasons.append("not_development")
        if not major or r.get("major")!=major:reasons.append("major_mismatch")
        if not curriculum_version or curriculum_version!=policy.get("curriculum_version") or r.get("curriculum_version")!=curriculum_version:reasons.append("curriculum_mismatch")
        if r.get("classification_state")!="confirmed":reasons.append("unconfirmed_source_role")
        if not r.get("content_sha256") or not r.get("image_sha256"):reasons.append("missing_hash_binding")
        if r.get("issues"):reasons.append("unresolved_issues")
        if type(r.get("revision")) is not int or r["revision"]<1:reasons.append("invalid_revision")
        knowledge=r.get("knowledge_ids",[])
        if not knowledge or any(k not in policy.get("allowed_knowledge_ids",[]) for k in knowledge):reasons.append("curriculum_node_unmapped")
        if purpose=="weekly_tests":
            start,end=r.get("test_start"),r.get("test_end")
            if type(start) is not int or type(end) is not int or start<1 or end<start:reasons.append("missing_verified_test_range")
        if purpose in ("weekly_scope","weekly_tests"):
            scope=policy.get("scopes",{}).get(scope_id or "",{})
            if not isinstance(scope,dict):scope={}
            if not scope_id or scope.get("state")!="reviewed" or not scope.get("reviewer") or not scope.get("evidence_refs") or r.get("scope_id")!=scope_id:reasons.append("missing_or_unreviewed_scope")
            if (scope.get('major')!=major or scope.get('curriculum_version')!=curriculum_version
                or scope.get('source_document_id') in denied
                or scope.get('source_document_id') not in policy.get('development_document_ids',[])):
                reasons.append('scope_binding_mismatch')
        required=["extraction","curriculum"]+(["design"] if purpose=="authoring_design" else [])
        for dimension in required:
            receipt=r.get("reviews",{}).get(dimension,{})
            if (receipt.get("state")!="passed" or not receipt.get("reviewer") or not receipt.get("evidence_refs")
                or receipt.get("content_sha256")!=r.get("content_sha256")
                or receipt.get("image_sha256")!=r.get("image_sha256")
                or receipt.get("curriculum_version")!=curriculum_version
                or receipt.get("revision")!=r.get("revision")):
                reasons.append("missing_or_stale_"+dimension+"_review")
        audit.append({"id":r.get("id"),"reasons":sorted(set(reasons))})
        if not reasons:accepted.append(r)
    return accepted,audit

def select(records,policy,ranker,**context):
    eligible,audit=filter_records(records,policy,**context)
    ranked=ranker(eligible) if eligible else []
    allowed={r["id"]:r for r in eligible}
    result=[]
    for row in ranked:
        if row.get("id") not in allowed:continue
        # Rebuild from approved originals; ranker cannot inject another item's content/key.
        original=allowed[row["id"]]
        result.append({k:v for k,v in original.items() if k not in ("answer","answer_index","explanation","literal","reviews")})
    return result,{"filtered":audit,"retrieved_ids":[r["id"] for r in result],"purpose":context["purpose"]}

def search_store(store,*,query_text,query_embedding,user_id,shared_user_id,purpose,major,curriculum_version,scope_id=None,top_k=4,policy=None):
    policy=load_policy() if policy is None else policy
    eligible,audit=filter_records(policy.get("records",[]),policy,purpose=purpose,major=major,curriculum_version=curriculum_version,scope_id=scope_id)
    trace={"purpose":purpose,"filtered":audit,"retrieved_ids":[]}
    if not eligible:return [],trace
    # Explicit ids and ownership are intersected before nearest-neighbour/lexical ranking.
    data=store.collection.get(ids=[r["id"] for r in eligible],where={"user_id":{"$in":list(set([user_id,shared_user_id]))}},include=["documents","metadatas","embeddings"])
    manifest={r["id"]:r for r in eligible};ranked=[]
    words=set(re.findall(r"\w+",query_text.casefold()))
    for index,id in enumerate(data.get("ids",[])):
        r=manifest.get(id);text=data["documents"][index];meta=data["metadatas"][index]
        if not r or meta.get("document_id")!=r["document_id"] or text_hash(text)!=r.get("text_sha256"):
            trace["filtered"].append({"id":id,"reasons":["store_binding_mismatch"]});continue
        if meta.get("user_id") not in (user_id,shared_user_id):continue
        vector=data.get("embeddings");vector=vector[index] if vector is not None else []
        dense=0
        if len(vector)==len(query_embedding) and len(vector) and all(math.isfinite(float(v)) for v in [*vector,*query_embedding]):
            norm=math.sqrt(sum(v*v for v in vector)*sum(v*v for v in query_embedding))
            if norm:dense=sum(a*b for a,b in zip(vector,query_embedding))/norm
        lexical=len(words & set(re.findall(r"\w+",text.casefold())))/max(1,len(words))
        ranked.append({"id":id,"content":text,"document_name":meta.get("document_name",""),"chunk_index":meta.get("chunk_index",0),"score":dense+lexical,"image_sha256":r.get("image_sha256")})
    ranked.sort(key=lambda r:(-r["score"],r["id"]));ranked=ranked[:max(0,top_k)]
    trace["retrieved_ids"]=[r["id"] for r in ranked]
    return ranked,trace


def reviewed_week_scope(policy,day,*,major):
    """Only a reviewed, currently applicable Maze row may supply planner scope."""
    from datetime import date
    day=date.fromisoformat(str(day)[:10])
    eligible=[]
    for id,scope in policy.get("scopes",{}).items():
        try:
            if scope.get("state")!="reviewed" or scope.get("major")!=major:continue
            if not scope.get("reviewer") or not scope.get("source_document_id") or not scope.get("evidence_refs"):continue
            if scope['source_document_id'] in policy.get('excluded_document_ids',[]):continue
            if scope['source_document_id'] not in policy.get('development_document_ids',[]):continue
            start=date.fromisoformat(scope["valid_from"]);end=date.fromisoformat(scope["valid_until"])
            if start<=day<=end and scope.get("curriculum_version")==policy.get("curriculum_version"):
                eligible.append({**scope,"scope_id":id})
        except (KeyError,TypeError,ValueError):continue
    # Ambiguous overlapping schedule revisions are held rather than guessed.
    return eligible[0] if len(eligible)==1 else None
