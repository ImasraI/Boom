"""Versioned exam OCR staging. Never writes live RAG, question bank or review flags."""
import json
from pathlib import Path
from app.rag.exam_corpus import read_json, payload_digest, atomic_json
from app.rag.exam_scanning import validate_page

SCHEMA = 1

def page_chunks(page):
    data=page.get('data',{})
    if (page.get('ok') is not True or page.get('coverage')!='full_page_literal'
            or validate_page(data,require_annotations=False,labelled_options=True)):
        return []
    questions=data.get('questions',[])
    if page.get('expected_question_numbers') != [q.get('number') for q in questions]:return []
    document=page.get('document_id');number=page.get('pdf_page')
    if not isinstance(document,str) or len(document)!=64 or type(number) is not int or number<1:return []
    result=[]
    for q in questions:
        literal={'text':q['text'],'options':q['options'],'figure_description':q.get('figure_description',''),
                 'figure_labels':q.get('figure_labels',[]),'bbox':q.get('bbox')}
        lines=[q['text']]
        lines += [str(o['label'])+') '+o['text'] for o in q['options']]
        if q.get('figure_description'):lines.append('توصیف شکل در OCR تأییدنشده: '+q['figure_description'])
        text='\n'.join(lines)
        identity=f"{document}:{number}:{q['number']}"
        result.append({'id':identity,'text':text,'content_sha256':payload_digest(literal),
            'literal':literal,'metadata':{'document_id':document,'document_name':page.get('document_name',''),
            'pdf_page':number,'question_number':q['number'],'major':data.get('source_major') or 'unknown',
            'printed_page':str(data.get('printed_page') or ''),'has_figure':bool(q.get('has_figure')),
            'image':page.get('image',''),'extraction_state':'ocr_candidate',
            'human_reviewed':False,'scientific_state':'not_checked','kind':'exam_style_candidate'}})
    return result


def snapshot(root,destination,max_pages=5000):
    """Freeze immutable source records; later runs resume rather than change selection."""
    root=Path(root);destination=Path(destination);manifest=destination/'manifest.json'
    if manifest.exists():
        saved=read_json(manifest)
        rows=read_json(destination/'chunks.json')
        if not saved or payload_digest(rows)!=saved.get('chunks_sha256'):
            raise ValueError('Snapshot checksum mismatch; preserve and repair it')
        return saved
    destination.mkdir(parents=True,exist_ok=True)
    rows={};pages=[];rejected=0
    for path in sorted(root.glob('documents/*/vision/page_*.literal.json')):
        page=read_json(path,{})
        if page.get('document_id')!=path.parent.parent.name:rejected+=1;continue
        chunks=page_chunks(page)
        if not chunks:rejected+=1;continue
        page_id=(page['document_id'],page['pdf_page'])
        if page_id in pages:continue
        pages.append(page_id)
        for chunk in chunks:rows[chunk['id']]=chunk
        if len(pages)>=max_pages:break
    records=sorted(rows.values(),key=lambda r:r['id'])
    saved={'schema_version':SCHEMA,'pages':len(pages),'chunks':len(records),'rejected_or_nonquestion_pages':rejected,
        'chunks_sha256':payload_digest(records),'evidence_status':'unreviewed OCR candidates',
        'live_activation':False,'purpose':'local retrieval and authoring evaluation only',
        'page_ids':[list(value) for value in pages]}
    atomic_json(destination/'chunks.json',records);atomic_json(manifest,saved)
    return saved
