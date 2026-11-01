"""Build versioned review candidates from visually prepared local transcriptions.

No OCR/provider calls, source rewrites, approvals or vector/database changes.
Input is private JSON: [{number,text (inline $math$),options[4],figure_in_source?}].
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.authoring_review import ReviewStore

def segments(text):
    if not isinstance(text,str) or not text.strip() or text.count('$')%2:
        raise ValueError('Invalid prepared transcription')
    return [{'kind':'math' if s.startswith('$') and s.endswith('$') else 'text',
             'value':s[1:-1] if s.startswith('$') and s.endswith('$') else s}
            for s in re.split(r'(\$[^$]+\$)',text) if s]

def prepare(source,packet_root,drafts,candidate_root,catalogue):
    import fitz
    packet_root=Path(packet_root);candidate_root=Path(candidate_root)
    if candidate_root.resolve()!= (packet_root.parent/'review-candidates-v1').resolve():
        raise ValueError('Use the approved sibling candidate directory')
    store=ReviewStore(packet_root.parent/'review-ledger-v1',packet_root,catalogue)
    packet=store.load();rows=json.loads(Path(drafts).read_text(encoding='utf-8'))
    if not isinstance(rows,list):raise ValueError('Expected a list')
    numbers=[row.get('number') for row in rows if isinstance(row,dict)]
    if len(numbers)!=len(rows) or len(set(numbers))!=len(rows) or any(type(n) is not int for n in numbers):raise ValueError('Duplicate or invalid question numbers')
    digest=hashlib.sha256(Path(source).read_bytes()).hexdigest()
    questions={q['printed_question_number']:q for q in packet['questions'] if q['section']=='math'}
    if any(n not in questions or questions[n]['document_id']!=digest for n in numbers):
        raise ValueError('Original PDF SHA mismatch')
    made=[];preserved=[]
    candidate_root.mkdir(parents=True,exist_ok=True)
    with fitz.open(source) as pdf:
        for row in rows:
            q=questions[row['number']]
            if q['document_id']!=digest:raise ValueError('Original PDF SHA mismatch')
            pointer=candidate_root/(hashlib.sha256(q['id'].encode()).hexdigest()+'.json')
            if pointer.exists():
                store.current(q['id']);preserved.append(row['number']);continue
            opts=row.get('options')
            if not isinstance(opts,list) or len(opts)!=4 or any(not isinstance(v,str) or not v.strip() for v in opts):raise ValueError('Four literal options required')
            stem=segments(row['text'])
            if type(row.get('figure_in_source',False)) is not bool:raise ValueError('Invalid figure state')
            # This development paper was visually checked: all 40 math questions
            # end on their first source page. Original spillover regions remain
            # preserved in the parent; do not include next-paper covers/physics.
            first=q['regions'][0];page=pdf[first['pdf_page']-1];b=first['bbox']
            rect=fitz.Rect(b[0]*page.rect.width,max(0,b[1]*page.rect.height-14),b[2]*page.rect.width,min(620,b[3]*page.rect.height-5))
            if rect.height<=0:raise ValueError('Invalid crop boundary')
            data=page.get_pixmap(matrix=fitz.Matrix(2.5,2.5),clip=rect).tobytes('png')
            sha=hashlib.sha256(data).hexdigest();image=candidate_root/(sha+'.png')
            if not image.exists():image.write_bytes(data)
            c={'schema_version':'0.1','candidate_revision':1,'question_revision':q['revision']+1,'state':'candidate',
               'annotator':{'kind':'model','identifier':'assistant:visual-transcription','human_reviewed':False},
               'question_id':q['id'],'parent_content_sha256':q['content_sha256'],'parent_image_sha256':q['source_image_sha256'],
               'source_document_sha256':digest,'stem':stem,'options':[{'index':i,'text':v} for i,v in enumerate(opts)],
               'figure_in_source':row.get('figure_in_source',False),
               'source_selection_note':'Visually inspected first-page question boundary; original regions retained in parent packet.',
               'source_image':{'file':image.name,'sha256':sha,'pdf_page':first['pdf_page'],
                   'bbox':[rect.x0/page.rect.width,rect.y0/page.rect.height,rect.x1/page.rect.width,rect.y1/page.rect.height],'render_scale':2.5}}
            c['candidate_sha256']=payload_digest(c)
            name='candidate-'+c['candidate_sha256']+'.json'
            atomic_json(candidate_root/name,c);atomic_json(pointer,{'candidate':name})
            store.current(q['id']);made.append(row['number'])
    result={'created':made,'preserved':preserved,'human_reviews_written':0,'eligible':False}
    atomic_json(candidate_root/'preparation-status.json',result)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','packet_root','drafts','candidate_root','catalogue'):parser.add_argument(name,type=Path)
    args=parser.parse_args();print(json.dumps(prepare(**vars(args))))
