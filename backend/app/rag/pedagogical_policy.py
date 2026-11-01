"""Additive teaching checks; no alteration of the frozen v0.2 contract."""
import re
from app.rag.exam_corpus import payload_digest
from app.rag.pedagogical_authoring import prompt_for

VERSION='pedagogical-policy-0.3-draft'


def language_audit(candidate):
    """Script screening is a hold signal, never proof of fluent Persian."""
    p=candidate['pedagogy']
    fields={'solution':candidate['solution'],'pedagogy.key_observation':p['key_observation'],
            'pedagogy.answer_justification':p['answer_justification']}
    fields.update({f'pedagogy.steps.{i}.explanation':s['explanation'] for i,s in enumerate(p['steps'])})
    fields.update({f'pedagogy.boundary_checks.{i}':s for i,s in enumerate(p['boundary_checks'])})
    if p['alternative_route'] is not None:fields['pedagogy.alternative_route']=p['alternative_route']
    results=[]
    for path,text in fields.items():
        # Inspect explanatory prose, not equations, tag IDs, Latin point names or JSON keys.
        arabic_script=sum(c.isalpha() and '\u0600'<=c<='\u06ff' for c in text)
        latin=len(re.findall('[A-Za-z]',text))
        hold=arabic_script<8 or arabic_script/(arabic_script+latin)<0.35
        results.append({'path':path,'text_sha256':payload_digest(text),
                        'arabic_script_letters':arabic_script,'latin_letters':latin,
                        'status':'persian_prose_not_demonstrated' if hold else 'script_screen_only'})
    return {'schema_version':'0.1','policy_version':VERSION,'candidate_sha256':payload_digest(candidate),
            'fields':results,'holds':[r['path'] for r in results if r['status']=='persian_prose_not_demonstrated'],
            'persian_fluency_review':None,'mathematical_correctness':None,'eligible':False,
            'meaning':'Heuristic script check only; Arabic letters do not certify Persian language or mathematics.'}


def prompt_v03(spec):
    """New explicit revision; existing frozen prompt_for/spec hashes remain unchanged."""
    return prompt_for(spec)+'''
Additional teaching policy revision pedagogical-policy-0.3-draft:
Write ALL explanatory prose in Persian: key_observation, every step explanation,
technique evidence, boundary_checks, answer_justification, alternative_route and
verification summary. Latin point names, mathematical expressions and registry IDs
may remain unchanged. English design metadata is acceptable.
For every counterfactual or changed assumption, recalculate from those NEW givens.
Do not reuse a distance/sign formula from the original situation after changing sides
of a line. Omit optional counterfactuals when not checked; an empty claim is safer
than an unsupported teaching assertion.
An alternative solution must prove the requested conclusion, including its global
bound and attainable equality when optimizing. Computing one symmetric example
alone does not prove maximality. Null is valid when no complete alternative exists.
For feasibility/counting, prove sufficiency as well as necessary inequalities.
Keep the question figure free of auxiliary solving constructions and the optimal
point location unless those are explicitly part of the givens. Coordinates must
match all stated relations. Do not claim that schema validation proves correctness.
'''
