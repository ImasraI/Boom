import copy,json
from app.rag.exam_candidate_index import page_chunks,snapshot
from app.rag.exam_corpus import atomic_json


def page():
 return {'ok':True,'coverage':'full_page_literal','document_id':'a'*64,'pdf_page':1,
 'document_name':'exam.pdf','image':'documents/a/images/page_00001.png','expected_question_numbers':[1],
 'data':{'page_kind':'questions','source_major':None,'major_evidence':'','printed_page':None,
 'page_text':'','complete':True,'uncertainties':[],'answers':[],
 'questions':[{'number':1,'text':'کدام گزینه درست است؟','options':[
 {'label':i,'text':str(i),'ordered_tokens':[],'visual_tokens_left_to_right':[]} for i in range(1,5)],
 'bbox':[0.1,0.1,0.9,0.3],'has_figure':False,'figure_labels':[],'figure_description':'',
 'answer_index':None,'answer_evidence':'','uncertainties':[]}]}}


def test_complete_question_and_options_stay_together_without_approval():
 result=page_chunks(page())
 assert len(result)==1
 assert all(str(i)+') '+str(i) in result[0]['text'] for i in range(1,5))
 assert result[0]['metadata']['extraction_state']=='ocr_candidate'
 assert result[0]['metadata']['scientific_state']=='not_checked'
 assert result[0]['metadata']['human_reviewed'] is False


def test_uncertain_or_partial_pages_never_enter_snapshot():
 bad=page();bad['data']['uncertainties']=['missing formula']
 assert page_chunks(bad)==[]
 bad=page();bad['expected_question_numbers']=[1,2]
 assert page_chunks(bad)==[]


def test_snapshot_is_fixed_and_detects_modified_chunks(tmp_path):
 root=tmp_path/'source';dest=tmp_path/'stage'
 atomic_json(root/('documents/'+('a'*64)+'/vision/page_00001.gemini.literal.json'),page())
 first=snapshot(root,dest,1)
 assert first['pages']==1 and first['chunks']==1
 assert snapshot(root,dest,9)==first
 (dest/'chunks.json').write_text('[]')
 import pytest
 with pytest.raises(ValueError,match='checksum'):snapshot(root,dest)
