import pytest
from app.rag.exam_quality import delta,parent_children,release_eligibility,join_continuation,retrieval_metrics,curriculum_suggestions

def record(text='text',sha='a',page=1):
 return {'id':'doc:'+str(page),'text':text,'content_sha256':sha,'literal':{'text':text,'options':['a','b','c','d']},
 'metadata':{'document_id':'doc','pdf_page':page,'major':'riazi'}}

def test_corrections_supersede_old_vectors_and_children_keep_parent():
 assert delta([record()],[record(sha='b')])['superseded'][0]['old_sha256']=='a'
 parts=parent_children(record('sentence. '*100),80)
 assert len(parts)>1 and all(p['parent_id']=='doc:1' and len(p['text'])<=80 for p in parts)
 short=record('Question?\n1) A\n2) B\n3) C\n4) D')
 assert parent_children(short)[0]['text']==short['text']

def test_export_never_confuses_format_checks_with_review():
 reasons=release_eligibility(record(),{'source_checked':True},{'vector':[1]}, {'release_passed':False})
 assert 'stale_or_missing_review' in reasons and 'scientific_not_verified' in reasons
 assert 'curriculum_not_verified' in reasons and 'evaluation_not_passed' in reasons

def test_continuations_require_source_hash_review_and_adjacent_pages():
 parts=[record(page=1),record(page=2)]
 with pytest.raises(ValueError):join_continuation(parts,{})
 review={'source_checked':True,'part_sha256':['a','a'],'reviewer':'visual review','source_image_sha256':['x','y']}
 assert join_continuation(parts,review)['pdf_pages']==[1,2]
 parts[1]['content_sha256']='changed'
 with pytest.raises(ValueError):join_continuation(parts,review)

def test_retrieval_metrics_use_expected_sources_not_model_confidence():
 cases=[{'id':'q','expected_ids':['a']}]
 assert retrieval_metrics(cases,{'q':['x','a']})=={'queries':1,'recall_at_5':1.0,'mrr':0.5}
 assert retrieval_metrics(cases,{'q':['x']})['recall_at_5']==0

def test_only_book_backed_curriculum_candidates_and_no_false_verification():
 node={'id':'lesson:one','title':'محاسبه چگالی','subject':'فیزیک','majors':['riazi'],'year':10,
 'sources':[{'book':'physics','page':2,'quote':'محاسبه چگالی'}]}
 result=curriculum_suggestions(record('محاسبه چگالی'),[node])
 assert result[0]['mapping_state']=='suggested_not_verified'
 assert curriculum_suggestions(record('محاسبه چگالی'),[{**node,'sources':[]}])==[]


def test_nonfinite_vectors_and_unsupported_science_cannot_ship():
 r=record()
 review={'record_id':r['id'],'content_sha256':'a','source_checked':True,'source_image_sha256':'x',
 'curriculum_state':'verified','curriculum_ids':['lesson:a'],'scientific_state':'verified','answer_index':0}
 embedding={'content_sha256':'a','vector':[float('nan')],'model':'test'}
 evaluation={'release_passed':True,'embedding_dimensions':1,'embedding_model':'test'}
 reasons=release_eligibility(r,review,embedding,evaluation)
 assert 'scientific_not_verified' in reasons and 'embedding_contract_mismatch' in reasons


def test_quality_source_endpoint_does_not_accept_paths():
 from app.rag.exam_quality_view import item
 assert item('../../backend/.env') is None
 assert item('a'*64+':1:2/../../.env') is None


def test_good_small_pilot_does_not_pass_full_release_policy():
 from app.rag.exam_quality import release_evaluation_reasons
 report={'gold_sources':3,'gold_overlay_count':3,'release_passed':True,
 'selected_policy_metrics':{'queries':6,'recall_at_5':1.0,'mrr':1.0}}
 reasons=release_evaluation_reasons(report)
 assert 'insufficient_independent_sources' in reasons and 'evaluation_used_gold_overlay' in reasons
 assert 'retrieval_acceptance_not_met' in reasons and 'generation_acceptance_not_met' in reasons


def test_number_comparison_does_not_confuse_arabic_and_persian_digits():
 from app.rag.exam_quality import norm
 assert norm('٥٠')==norm('۵۰')==norm('50')
