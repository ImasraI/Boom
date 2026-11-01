from copy import deepcopy
from app.rag.calibrated_designs import select_summaries, reviewed_material
import pytest
from app.rag.exam_corpus import payload_digest


def fixture():
    b=dict(questionId='synthetic:q',questionRevision=1,documentId='doc',contentHash='c',cropImageHash='i',catalogueVersion='cat',evidenceToken='t')
    review=dict(state='passed',reviewer='synthetic-human',evidence_refs=['extraction'],content_sha256='c',image_sha256='i',revision=1,curriculum_version='cat')
    material=dict(question_ref='synthetic:q',binding=b,knowledge_ids=['lesson:synthetic'],book_topics=['Synthetic'],main_decision='Synthetic insight',review_scope='displayed_topics_and_main_decision_only',extraction_review=review)
    material.update(major='riazi',classification_state='confirmed',source_role='mock_exam',split='development')
    materials=[material]
    receipt=dict(schema_version='summary-calibration-0.1',reviewer_kind='human',outcome='confirmed',reviewer='synthetic-human',evidence_ref='chat:synthetic',materials_sha256=payload_digest(materials))
    policy=dict(schema_version='0.1',curriculum_version='cat',development_document_ids=['doc'],allowed_knowledge_ids=['lesson:synthetic'])
    return materials,receipt,policy,dict(knowledge_ids=['lesson:synthetic'],current_bindings={'synthetic:q':b},major='riazi')


def test_only_reviewed_summary_is_returned():
    m,r,p,c=fixture();out,audit=select_summaries(m,r,p,**c)
    assert len(out)==1 and audit['retrieved_ids']==['synthetic:q']
    assert 'binding' not in out[0] and 'answer' not in out[0]
    assert audit['scientific_reviewed'] is False


def test_changed_material_receipt_or_source_binding_is_held():
    m,r,p,c=fixture();m[0]['main_decision']='changed'
    assert not select_summaries(m,r,p,**c)[0]
    m,r,p,c=fixture();c['current_bindings']=deepcopy(c['current_bindings']);c['current_bindings']['synthetic:q']['evidenceToken']='changed'
    assert not select_summaries(m,r,p,**c)[0]


def test_reserved_or_out_of_scope_source_cannot_enter_summary_retrieval():
    m,r,p,c=fixture();p['excluded_document_ids']=['doc']
    assert not select_summaries(m,r,p,**c)[0]
    m,r,p,c=fixture();c['knowledge_ids']=['lesson:other']
    assert not select_summaries(m,r,p,**c)[0]


def test_missing_actual_extraction_review_and_model_attribution_hold():
    m,r,p,c=fixture();m[0]['extraction_review']={};r['materials_sha256']=payload_digest(m)
    assert not select_summaries(m,r,p,**c)[0]


def test_s1a_major_alias_is_supported_without_guessing_unknown_majors():
    m,r,p,c=fixture();m[0]['major']='math_physics';r['materials_sha256']=payload_digest(m)
    assert len(select_summaries(m,r,p,**c)[0])==1
    m[0]['major']='unknown';r['materials_sha256']=payload_digest(m)
    assert not select_summaries(m,r,p,**c)[0]


def test_family_exclusion_applies_even_after_confirmation():
    m,r,p,c=fixture();m[0]['family_id']='reserved-family';r['materials_sha256']=payload_digest(m)
    assert len(select_summaries(m,r,p,**c)[0])==1
    p['excluded_family_ids']=['reserved-family']
    assert not select_summaries(m,r,p,**c)[0]


def material_fixture():
    item=dict(question_ref='synthetic:q',question_revision=2,content_sha256='new',catalogue_version='cat',
              annotation_revision=1,main_decision='summary',preferred_route='route:A',proposed_book_topics=['Synthetic'])
    binding=dict(questionId='synthetic:q',questionRevision=2,documentId='doc',documentRevision='1',
                 contentHash='new',cropImageHash='i',catalogueVersion='cat',evidenceToken='token')
    source=dict(document_id='doc',document_revision=1,content_sha256='new')
    annotation=dict(question_ref='synthetic:q',question_revision=2,source=deepcopy(source),catalogue_version='cat',
                    annotation_revision=1,knowledge_ids=['lesson:synthetic'])
    record=dict(question_ref='synthetic:q',question_revision=2,source=source,evidence_token='token',
                reasoning_annotation=annotation,design=dict(main_decision_fa='summary',preferred_route='route:A'))
    return item,record,binding,{'lesson:synthetic':{'title':'Synthetic'}}


def test_current_material_binds_source_annotation_and_view():
    args=material_fixture()
    assert reviewed_material(*args)['full_route_reviewed'] is False


@pytest.mark.parametrize('path,value',[
    (('question_revision',),1),(('source','content_sha256'),'old'),(('evidence_token',),'old'),
    (('reasoning_annotation','question_ref'),'other'),(('reasoning_annotation','question_revision'),1),
    (('reasoning_annotation','source','document_id'),'other'),
    (('reasoning_annotation','source','content_sha256'),'old'),
    (('source','document_revision'),2),
])
def test_unchanged_summary_cannot_hide_stale_underlying_evidence(path,value):
    item,record,binding,nodes=material_fixture();target=record
    for key in path[:-1]:target=target[key]
    target[path[-1]]=value
    with pytest.raises(ValueError,match='stale'):
        reviewed_material(item,record,binding,nodes)
    m,r,p,c=fixture();r['reviewer_kind']='model'
    assert not select_summaries(m,r,p,**c)[0]
