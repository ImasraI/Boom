"""Hash-bound blind projections for the local paired experiment, never approval."""
import hashlib
import json
import re
import unicodedata
from app.rag.authoring_benchmark import FINAL, parse_candidate, figure_svg, saved_json
from app.rag.exam_corpus import payload_digest
from app.rag.authoring_originality import normalized_structure,screen


def checked_candidate(store,item):
    folder=store.folder(item['item_id']);state=store.state(item['item_id'])
    if not state or state.get('state')!='drafted':return None
    sha=state.get('response_sha256','')
    if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('Malformed response binding')
    path=folder/(('fragment-' if state.get('recovered') else '')+sha+'.txt')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Response changed')
    q=parse_candidate(raw.decode('utf8'))
    if saved_json(folder/'candidate.json')!=q:raise ValueError('Candidate changed after generation')
    return q


def normalized(text,mask_numbers=False):
    text=unicodedata.normalize('NFKC',text).casefold()
    text=text.translate(str.maketrans('يكى','یکی'))
    if mask_numbers:return normalized_structure(text)
    return re.sub(r'\s+','',text)


def similarity_flags(records):
    """Screen NFKC/whitespace-normalized similarity; no semantic originality claim."""
    flags=[]
    for i,a in enumerate(records):
        for b in records[i+1:]:
            left,right=a['candidate']['text'],b['candidate']['text']
            exact=normalized(left)==normalized(right)
            masked=normalized(left,True)==normalized(right,True)
            surface=screen(left,[{'id':b['alias'],'text':right}])
            if exact or masked or surface['matches']:flags.append(dict(a=a['alias'],b=b['alias'],
                kind='normalized_stem_duplicate' if exact else 'number_masked_stem_duplicate' if masked else 'high_surface_similarity',
                screening=surface,requires_review=True))
    return flags


def carry_verified_results(old_binding,new_binding,old_presentation,new_presentation,verified):
    """Reuse only exact raw candidates; this carries no figure or human approval."""
    if old_binding['protocol_sha256']!=new_binding['protocol_sha256']:raise ValueError('Different benchmark protocol')
    if (payload_digest(old_presentation)!=old_binding['presentation_sha256']
            or payload_digest(new_presentation)!=new_binding['presentation_sha256']):raise ValueError('Presentation binding changed')
    old_records={r['alias']:r for r in old_binding['records']}
    new_records={r['alias']:r for r in new_binding['records']}
    old_q={q['id']:q for q in old_presentation['questions']};new_q={q['id']:q for q in new_presentation['questions']}
    old_keys={q['id']:q['answer_index'] for q in old_presentation['solutions']}
    new_keys={q['id']:q['answer_index'] for q in new_presentation['solutions']}
    result=[]
    for alias,row in verified.items():
        if set(row)!={'question_id','blind_solve_state','solver_verdict','solver_answer_index',
                'expected_answer_index','justification','human_scientific_review','eligible'}:
            raise ValueError('Unexpected solver evidence fields')
        if alias not in old_records:raise ValueError('Unknown prior verified question')
        if alias not in new_records:continue
        a,b=old_records[alias],new_records[alias]
        if a['item_id']!=b['item_id'] or a['candidate_sha256']!=b['candidate_sha256']:raise ValueError('Changed candidate cannot inherit a solve')
        if any(old_q[alias][key]!=new_q[alias][key] for key in ('stem','options')) or old_keys[alias]!=new_keys[alias]:
            raise ValueError('Changed literal/key cannot inherit a solve')
        if row.get('eligible') is not False or row.get('human_scientific_review') is not False:
            raise ValueError('Imported approval is not solver evidence')
        if row['expected_answer_index']!=old_keys[alias] or row['question_id']!=alias:raise ValueError('Wrong solver comparison binding')
        if row['solver_verdict'] not in ('solved','ambiguous','inconsistent','cannot_solve'):raise ValueError('Unknown solver verdict')
        if row['solver_verdict']=='solved':
            if type(row['solver_answer_index']) is not int or not 0<=row['solver_answer_index']<4:raise ValueError('Invalid solved answer')
        elif row['solver_answer_index'] is not None:raise ValueError('Unsolved answer must be null')
        state=('matched' if row['solver_answer_index']==old_keys[alias] else 'disagreed') if row['solver_verdict']=='solved' else 'unresolved'
        if row['blind_solve_state']!=state:raise ValueError('False solver comparison state')
        result.append(dict(**row,candidate_sha256=b['candidate_sha256'],carried_from_review_sha256=payload_digest(old_binding),
            carried_to_review_sha256=payload_digest(new_binding),text_only=True,figure_approval=False))
    return result


def review_projection(store,items,protocol_sha,require_complete=True):
    assignment=saved_json(store.root/'assignment.json')
    if assignment['protocol_sha256']!=protocol_sha:raise ValueError('Assignment protocol changed')
    records=[];states=[]
    ordered=sorted(items,key=lambda i:hashlib.sha256((protocol_sha+i['item_id']).encode()).hexdigest())
    for position,item in enumerate(ordered,1):
        alias=f'R{position:02d}'
        state=store.state(item['item_id'])
        if not state or state.get('state') not in FINAL:
            if require_complete or state is not None:raise ValueError('Generation is not complete')
        if state and state['binding']['assignment_sha256']!=payload_digest(assignment):raise ValueError('Stale assignment binding')
        states.append(dict(alias=alias,item_id=item['item_id'],state_sha256=payload_digest(state) if state else None,
            state=state['state'] if state else 'unattempted'))
        q=checked_candidate(store,item)
        if q is not None:records.append(dict(alias=alias,item_id=item['item_id'],arm=item['arm'],
            candidate=q,candidate_sha256=payload_digest(q),response_sha256=state['response_sha256']))
    presentation=dict(questions=[dict(id=r['alias'],stem=r['candidate']['text'],
        options=r['candidate']['options'],svg=figure_svg(r['candidate']['figure'])) for r in records],
        solutions=[dict(id=r['alias'],answer_index=r['candidate']['answer_index'],answer_latex='',
        proof=r['candidate']['solution'],checks=['Author-model answer claim only; independent verification is pending',
        'Diagram coordinates are author claims, not verified geometry']) for r in records],
        provenance=('مقایسهٔ توسعه‌ای با ترتیب کور؛ پاسخ و راه‌حلِ نویسنده هنوز تأیید علمی نشده‌اند.'
            if require_complete else 'این برگه فقط پیش‌نویس‌های ذخیره‌شده را دارد؛ اجرای مقایسه هنوز کامل نشده است. پاسخ‌ها تأیید علمی نشده‌اند.'),
        review_only=True)
    binding=dict(schema_version='0.1',protocol_sha256=protocol_sha,assignment_sha256=payload_digest(assignment),
        states=states,records=records,presentation_sha256=payload_digest(presentation),
        generation_complete=all(r['state'] in FINAL for r in states),planned_items=len(items),
        surface_similarity_flags=similarity_flags(records),eligible=False,human_review=False,
        limitations=['Literal duplicate screening does not establish structural originality',
            'No reserved exam content was read','No automatic scientific or curriculum approval'])
    return presentation,binding
