"""Answer-free projections and result checks for local unpublished trials.

No database/provider imports, approval writes or release eligibility.
"""
import json


def make_blind_packet(presentation):
    questions=presentation.get('questions') if isinstance(presentation,dict) else None
    if not isinstance(questions,list) or not 1<=len(questions)<=20:
        raise ValueError('A bounded presentation is required')
    result=[];mapping={};seen=set()
    for i,q in enumerate(questions,1):
        if (not isinstance(q,dict) or not isinstance(q.get('id'),str) or not q['id']
                or q['id'] in seen or not isinstance(q.get('stem'),str) or not q['stem'].strip()
                or len(q['stem'])>12000 or not isinstance(q.get('options'),list)
                or len(q['options'])!=4 or any(not isinstance(o,str) or not o.strip() or len(o)>1500 for o in q['options'])
                or len(set(q['options']))!=4):
            raise ValueError('Malformed question presentation')
        seen.add(q['id']);alias=f'blind:{i:03d}'
        # Explicit whitelist: no generic copying of model/source metadata.
        result.append(dict(id=alias,text=q['stem'],options=list(q['options'])))
        mapping[alias]=q['id']
    return dict(schema_version='0.1',mode='text_only_blind',questions=result),mapping


def solver_prompt(packet):
    return '''Independently solve these newly authored Persian mathematics questions.
You receive ONLY stems and ordered options, not proposed answers or solutions.
Use the written constraints. No diagram is supplied; if text is insufficient,
return ambiguous rather than inventing a missing relation. Do not use external
retrieval or sources. For each item give a short, checkable derivation or decisive
counterexample, not private reasoning. Use plain Unicode math in justification,
without LaTeX backslash commands. Check domains and whether exactly one option is
correct. Answer indices are zero-based in the supplied order.
Return JSON only: {"results":[{"id":"blind:001","verdict":"solved",
"answer_index":0,"justification":"Short checkable derivation"},...]}
Allowed verdicts: solved, ambiguous, inconsistent, cannot_solve. For any unsolved
verdict answer_index MUST be null. Return each supplied id exactly once.
Data:
''' + json.dumps(packet,ensure_ascii=True)


def parse_solver_results(raw,packet):
    if not isinstance(raw,str) or len(raw.encode('utf8'))>48000:
        raise ValueError('Missing or oversized solver output')
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('Duplicate JSON key')
            out[k]=v
        return out
    data=json.loads(raw,object_pairs_hook=unique)
    expected={q['id'] for q in packet['questions']}
    if not isinstance(data,dict) or set(data)!={'results'} or not isinstance(data['results'],list):
        raise ValueError('Malformed solver batch')
    seen=set()
    for r in data['results']:
        if not isinstance(r,dict) or set(r)!={'id','verdict','answer_index','justification'}:
            raise ValueError('Unexpected result fields')
        if not isinstance(r['id'],str) or r['id'] not in expected or r['id'] in seen:
            raise ValueError('Unknown or duplicate result id')
        seen.add(r['id'])
        if r['verdict'] not in ('solved','ambiguous','inconsistent','cannot_solve'):
            raise ValueError('Unknown verdict')
        if r['verdict']=='solved':
            if type(r['answer_index']) is not int or not 0<=r['answer_index']<=3:
                raise ValueError('Invalid solved answer')
        elif r['answer_index'] is not None:raise ValueError('Unsolved answers must be null')
        s=r['justification']
        if not isinstance(s,str) or not s.strip() or len(s)>6000 or any(ord(c)<32 and c!='\n' for c in s):
            raise ValueError('Missing/malformed checkable justification')
    if seen!=expected:raise ValueError('Missing result')
    return data


def compare_solver_results(results,mapping,solutions):
    expected={s['id']:s['answer_index'] for s in solutions}
    matrix=[]
    for r in results['results']:
        qid=mapping[r['id']]
        if qid not in expected:raise ValueError('Missing local answer binding')
        state=('matched' if r['answer_index']==expected[qid] else 'disagreed') if r['verdict']=='solved' else 'unresolved'
        matrix.append(dict(question_id=qid,blind_solve_state=state,solver_verdict=r['verdict'],
            solver_answer_index=r['answer_index'],expected_answer_index=expected[qid],
            justification=r['justification'],human_scientific_review=False,eligible=False))
    return matrix
