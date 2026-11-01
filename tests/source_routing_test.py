from copy import deepcopy
from types import SimpleNamespace
from app.rag.source_routing import filter_records,select,search_store,reviewed_week_scope,text_hash


def setup(role="mock_exam"):
    row=dict(id="synthetic:q",document_id="doc",role=role,classification_state="confirmed",split="development",major="riazi",curriculum_version="cat1",revision=1,knowledge_ids=["lesson:synthetic"],content_sha256="content",image_sha256="image",contains_answer=False,issues=[],reviews={})
    for dim in ("extraction","curriculum","design"):
        row["reviews"][dim]=dict(state="passed",reviewer="synthetic reviewer",evidence_refs=["synthetic"],content_sha256="content",image_sha256="image",curriculum_version="cat1",revision=1)
    policy=dict(schema_version="0.1",curriculum_version="cat1",excluded_document_ids=[],excluded_record_ids=[],excluded_family_ids=[],development_document_ids=["doc"],allowed_knowledge_ids=["lesson:synthetic"],scopes={},records=[row])
    context=dict(purpose="authoring_design",major="riazi",curriculum_version="cat1")
    return row,policy,context


def test_filters_run_before_ranker_and_strip_answer_fields():
    row,p,c=setup();bad=deepcopy(row);bad.update(id="held",split="final_evaluation",answer="hidden")
    seen=[]
    def rank(rows):seen.extend(rows);return rows
    rows,audit=select([row,bad],p,rank,**c)
    assert [r["id"] for r in seen]==[row["id"]]
    assert audit["retrieved_ids"]==[row["id"]]
    assert any("not_development" in r["reasons"] for r in audit["filtered"])


def test_cross_role_major_curriculum_and_unknown_sources():
    row,p,c=setup()
    for field,value in [("role","textbook"),("major","tajrobi"),("curriculum_version","old"),("classification_state","inferred"),("document_id",None),("contains_answer",True)]:
        bad=deepcopy(row);bad[field]=value
        assert not filter_records([bad],p,**c)[0]
    assert not filter_records([row],{},**c)[0]


def test_holdout_and_duplicate_family_exclusions():
    row,p,c=setup()
    for field,value in [("excluded_document_ids",["doc"]),("excluded_record_ids",[row["id"]]),("excluded_family_ids",["family"])]:
        row["family_id"]="family";p[field]=value
        assert not filter_records([row],p,**c)[0]
        p[field]=[]


def test_stale_review_content_image_catalogue_and_revision():
    for field in ["content_sha256","image_sha256","curriculum_version","revision"]:
        row,p,c=setup();row["reviews"]["extraction"][field]="stale"
        assert not filter_records([row],p,**c)[0]


def test_weekly_scope_missing_and_overlapping_rows_are_held():
    row,p,c=setup("mock_plan");c["purpose"]="weekly_scope"
    assert not filter_records([row],p,**c)[0]
    scope=dict(state="reviewed",major="riazi",reviewer="synthetic",source_document_id="doc",evidence_refs=["p1"],curriculum_version="cat1",valid_from="2026-10-20",valid_until="2026-10-30")
    p["scopes"]={"s":scope};c["scope_id"]="s";row["scope_id"]="s"
    assert filter_records([row],p,**c)[0]
    assert reviewed_week_scope(p,"2026-10-23",major="riazi")["scope_id"]=="s"
    p["scopes"]["s2"]=dict(scope)
    assert reviewed_week_scope(p,"2026-10-23",major="riazi") is None


def test_store_receives_only_allowed_ids_and_user_intersection():
    row,p,c=setup("textbook");row["text_sha256"]=text_hash("synthetic content");c["purpose"]="factual_grounding"
    calls=[]
    def get(**kw):
        calls.append(kw);return dict(ids=[row["id"]],documents=["synthetic content"],metadatas=[dict(document_id="doc",user_id=9,document_name="Book",chunk_index=1)],embeddings=[[1.,0.]])
    store=SimpleNamespace(collection=SimpleNamespace(get=get))
    rows,audit=search_store(store,query_text="synthetic",query_embedding=[1.,0.],user_id=9,shared_user_id=1,top_k=2,policy=p,**c)
    assert len(rows)==1 and calls[0]["ids"]==[row["id"]]
    assert set(calls[0]["where"]["user_id"]["$in"])=={1,9}
    row["text_sha256"]="changed"
    assert not search_store(store,query_text="synthetic",query_embedding=[],user_id=9,shared_user_id=1,policy=p,**c)[0]


def test_missing_policy_never_calls_store():
    store=SimpleNamespace(collection=None)
    assert search_store(store,query_text="x",query_embedding=[],user_id=1,shared_user_id=1,purpose="factual_grounding",major="riazi",curriculum_version="cat1",policy={})[0]==[]


def test_weekly_test_range_must_be_explicit_and_reviewed():
    r,p,c=setup("test_book");c.update(purpose="weekly_tests",scope_id="s");r["scope_id"]="s"
    p["scopes"]={"s":{"state":"reviewed","reviewer":"human","evidence_refs":["p1"],"major":"riazi","curriculum_version":"cat1","source_document_id":"doc"}}
    assert not filter_records([r],p,**c)[0]
    r.update(test_start=30,test_end=50)
    assert filter_records([r],p,**c)[0]
    r["test_end"]=29
    assert not filter_records([r],p,**c)[0]


def test_unknown_curriculum_nodes_and_missing_revision_are_held():
    r,p,c=setup();r["knowledge_ids"]=["invented"]
    assert not filter_records([r],p,**c)[0]
    r,p,c=setup();r["revision"]=None
    assert not filter_records([r],p,**c)[0]


def test_ranker_cannot_inject_holdout_answer():
    r,p,c=setup();r.update(answer="secret",answer_index=1,explanation="secret explanation")
    def rank(rows):return [{**r,"answer":"injected"},{"id":"holdout","content":"secret"}]
    selected,audit=select([r],p,rank,**c)
    assert len(selected)==1 and "answer" not in selected[0] and "explanation" not in selected[0]


def test_reviewed_scope_cannot_bypass_document_exclusion():
    r,p,c=setup('mock_plan');c.update(purpose='weekly_scope',scope_id='s');r['scope_id']='s'
    scope=dict(state='reviewed',reviewer='human',evidence_refs=['synthetic'],major='riazi',
        curriculum_version='cat1',source_document_id='doc',valid_from='2026-10-20',valid_until='2026-10-30')
    p['scopes']={'s':scope}
    assert reviewed_week_scope(p,'2026-10-25',major='riazi')
    p['excluded_document_ids']=['doc']
    assert reviewed_week_scope(p,'2026-10-25',major='riazi') is None
    assert 'scope_binding_mismatch' in filter_records([r],p,**c)[1][0]['reasons']


def test_weekly_tests_cannot_use_scope_from_another_major_or_catalogue():
    r,p,c=setup('test_book');c.update(purpose='weekly_tests',scope_id='s')
    r.update(scope_id='s',test_start=1,test_end=10)
    p['scopes']={'s':dict(state='reviewed',reviewer='human',evidence_refs=['p'],
        source_document_id='doc',major='tajrobi',curriculum_version='old')}
    assert not filter_records([r],p,**c)[0]


def test_duplicate_sidecar_ids_never_choose_an_arbitrary_version():
    r,p,c=setup();other=deepcopy(r);other['content_sha256']='different'
    assert not filter_records([r,other],p,**c)[0]


def test_malformed_policy_and_reviews_hold_instead_of_crashing():
    for field in ('excluded_document_ids','development_document_ids','scopes'):
        r,p,c=setup();p[field]=None
        assert not filter_records([r],p,**c)[0]
    for field,value in [('reviews',None),('reviews',{'extraction':None}),('knowledge_ids',None),('document_id',[])]:
        r,p,c=setup();r[field]=value
        assert not filter_records([r],p,**c)[0]
