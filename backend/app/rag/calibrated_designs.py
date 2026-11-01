"""Local, summary-only calibrated designs. Not source/science/bank approval."""
from copy import deepcopy
from app.rag.exam_corpus import payload_digest
from app.rag.source_routing import filter_records


def retrieval_major(value):
    """Explicit S1a-to-retrieval schema alias; unknown majors remain unknown."""
    return {'math_physics':'riazi','riazi':'riazi'}.get(value)


def reviewed_material(item, record, binding, catalogue_nodes):
    """Validate exactly what was shown, against current source and catalogue."""
    annotation=record['reasoning_annotation']
    if (item['question_ref']!=binding['questionId'] or item['question_ref']!=record['question_ref']
        or record['question_revision']!=binding['questionRevision']
        or record['source']['content_sha256']!=binding['contentHash']
        or record.get('evidence_token')!=binding['evidenceToken']
        or annotation['question_ref']!=binding['questionId']
        or annotation['question_revision']!=binding['questionRevision']
        or annotation['source']['document_id']!=binding['documentId']
        or annotation['source']['content_sha256']!=binding['contentHash']
        or str(record['source']['document_revision'])!=binding['documentRevision']
        or str(annotation['source']['document_revision'])!=binding['documentRevision']
        or item['question_revision']!=binding['questionRevision']
        or item['content_sha256']!=binding['contentHash']
        or record['source']['document_id']!=binding['documentId']
        or item['catalogue_version']!=binding['catalogueVersion']
        or annotation['catalogue_version']!=binding['catalogueVersion']
        or item['annotation_revision']!=annotation['annotation_revision']
        or item['main_decision']!=record['design']['main_decision_fa']
        or item['preferred_route']!=record['design']['preferred_route']):
        raise ValueError('Calibration view is stale')
    ids=annotation['knowledge_ids']
    if not ids or any(k not in catalogue_nodes for k in ids):
        raise ValueError('Unknown book-backed node')
    titles=[catalogue_nodes[k]['title'] for k in ids]
    if titles!=item['proposed_book_topics']:raise ValueError('Displayed topic mapping changed')
    return {'question_ref':item['question_ref'],'binding':deepcopy(binding),
        'annotation_revision':item['annotation_revision'],'knowledge_ids':list(ids),
        'family_id':record.get('family_id'),
        'book_topics':titles,'main_decision':item['main_decision'],
        'preferred_route_identifier':item['preferred_route'],
        'review_scope':'displayed_topics_and_main_decision_only',
        'full_route_reviewed':False,'scientific_reviewed':False}


def select_summaries(materials, receipt, policy, *, knowledge_ids, current_bindings, major):
    """Prefilter exact reviewed summary material; return no solutions or answers.

    The local caller must validate the receipt file and attribution. There is no
    endpoint accepting client-supplied receipts or policy objects.
    """
    if (not knowledge_ids or not isinstance(knowledge_ids,list)
        or receipt.get('schema_version')!='summary-calibration-0.1'
        or receipt.get('reviewer_kind')!='human' or receipt.get('outcome')!='confirmed'
        or not receipt.get('evidence_ref') or not receipt.get('reviewer')
        or receipt.get('materials_sha256')!=payload_digest(materials)):
        return [],{'reasons':['missing_scope_or_bound_human_confirmation'],'retrieved_ids':[]}
    output=[];audit=[]
    for material in materials:
        binding=material['binding'];qid=material['question_ref']
        if current_bindings.get(qid)!=binding:
            audit.append({'id':qid,'reasons':['stale_current_binding']});continue
        if not set(material['knowledge_ids']).issubset(set(knowledge_ids)):
            audit.append({'id':qid,'reasons':['outside_requested_curriculum_scope']});continue
        if retrieval_major(material.get('major'))!=major or material.get('classification_state')!='confirmed':
            audit.append({'id':qid,'reasons':['unconfirmed_source_identity']});continue
        # Scoped reviews approve only material returned below, not the source's
        # complete taxonomy, alternative solutions or answer-bearing analysis.
        reviewed={'state':'passed','reviewer':receipt['reviewer'],'evidence_refs':[receipt['evidence_ref']],
            'content_sha256':binding['contentHash'],'image_sha256':binding['cropImageHash'],
            'revision':binding['questionRevision'],'curriculum_version':binding['catalogueVersion']}
        sidecar={'id':qid,'document_id':binding['documentId'],'role':material.get('source_role'),
            'family_id':material.get('family_id'),
            'classification_state':material.get('classification_state'),'split':material.get('split'),'major':retrieval_major(material.get('major')),
            'curriculum_version':binding['catalogueVersion'],'knowledge_ids':material['knowledge_ids'],
            'revision':binding['questionRevision'],'content_sha256':binding['contentHash'],
            'image_sha256':binding['cropImageHash'],'contains_answer':False,'issues':[],
            'reviews':{d:reviewed for d in ('extraction','curriculum','design')}}
        # Extraction is supplied separately from actual current ledger evidence.
        sidecar['reviews']['extraction']=material.get('extraction_review',{})
        good,decisions=filter_records([sidecar],policy,purpose='authoring_design',major=major,
                                    curriculum_version=binding['catalogueVersion'])
        audit.extend(decisions)
        if good:
            output.append({k:deepcopy(material[k]) for k in ('question_ref','knowledge_ids','book_topics','main_decision','review_scope')})
    return output,{'filtered':audit,'retrieved_ids':[m['question_ref'] for m in output],
                   'purpose':'reviewed_design_summary_only','scientific_reviewed':False}
