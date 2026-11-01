"""Freeze three local briefs and checks. No provider, scan or database calls."""
import copy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import payload_digest,atomic_json
from app.rag.authoring_benchmark import saved_json
from app.rag.decision_authoring import prompt_for,VERSION
from scripts.prepare_pedagogical_pilot import ROOT,OUT as PARENT

OUT=PARENT.parent/'decision-authoring-pilot-v1'
BRIEFS=[
 ('cyclic_constraints','cyclic_decision',
  'Construct a convex cyclic configuration requiring a consequential angle/feasibility decision together with an independent given constraint. Do not reuse the isosceles trapezoid plus diagonal-intersection angle and internal bisector chain from the previous pilot. No mere opposite-angle complement question.',
  ['Confusing an exterior angle with an interior angle.','Accepting an algebraic angle branch incompatible with convex point order.'],
  ['Try diagram measurement and visually symmetric special cases.','Check whether bounds or one option format reveal the key without the intended decision.']),
 ('cosine_feasibility','cosine_branch_decision',
  'Construct a cosine-law problem in which algebra permits more than one apparent length/angle branch and an explicit meaningful geometric condition selects the admissible result. Prove existence and uniqueness. Do not repeat the 60-degree fixed-opposite-side perimeter-range problem or make the only positive option correct by inspection.',
  ['Keeping a squared-equation branch that violates a stated condition.','Confusing a side with a projection or losing the sign of the cosine term.'],
  ['Try positivity, scale and triangle-bound elimination on all options.','Try admissible symmetric/equality cases; keep a legitimate complete shortcut.']),
 ('altitude_admissibility','altitude_shape_decision',
  'Use common area and reciprocal-altitude relationships plus one explicit nonredundant geometric constraint to recover a feasible triangle property or ratio. Prove sufficiency. Do not merely count the integer third altitudes when two fixed altitudes are given, or relabel that earlier question.',
  ['Applying triangle inequalities directly to altitudes instead of reciprocal altitudes.','Treating a necessary ratio constraint as sufficient without checking realizability.'],
  ['Try equal-altitude or equal-side guesses against EVERY given.','Test units, scaling, bounds and back-substitution; distinguish valid elimination from lucky guesses.'])]


def prepare():
    p=saved_json(PARENT/'pointer.json')
    if p['file']!='protocol-'+p['sha256']+'.json':raise ValueError('Unsafe parent reference')
    parent=saved_json(PARENT/p['file'])
    if payload_digest(parent)!=p['sha256']:raise ValueError('Changed factual protocol')
    fp=saved_json(PARENT/'editorial-feedback/pointer.json')
    if fp['file']!=fp['sha256']+'.json':raise ValueError('Unsafe feedback reference')
    feedback=saved_json(PARENT/'editorial-feedback'/fp['file'])
    if payload_digest(feedback)!=fp['sha256'] or len(feedback['records'])!=6:raise ValueError('Missing bound owner review')
    evidence={r['spec_id']:r for r in parent['evidence']};old={r['spec']['id']:r['spec'] for r in parent['drafts']}
    drafts=[];sources=[]
    for previous,identifier,target,error_hypotheses,attacks in BRIEFS:
        fact=evidence[previous]
        for field in ('image','ocr'):
            path=(ROOT/'backend/data'/fact[field+'_ref']).resolve()
            if not path.is_relative_to((ROOT/'backend/data').resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=fact[field+'_sha256']:
                raise ValueError('Factual source changed; requires renewed check')
        spec=copy.deepcopy(old[previous]);spec.update(id=identifier,task=target,
             proposed_error_hypotheses=error_hypotheses,required_shortcut_attacks=attacks,
             sample_target='Meaningful decision and plausible distractors; not a difficulty rating',
             source_mechanism=previous)
        prompt=prompt_for(spec)
        drafts.append({'spec':spec,'prompt':prompt,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
        sources.append(copy.deepcopy(fact))
    manifest={'schema_version':'0.1','prompt_version':VERSION,'provider':'gemini','model':parent['model'],
        'temperature':0.2,'reasoning_effort':'high','completion_tokens':16384,'timeout_seconds':180,
        'planned_items':3,'drafts':drafts,'evidence':sources,'parent_factual_protocol_sha256':p['sha256'],
        'owner_editorial_receipt_sha256':fp['sha256'],'released':False,'eligible':False,
        'predeclared_checks':['Exact candidate/sidecar validation, independent mathematical derivation and distinct options.',
            'Derive each wrong option from its claimed first invalid step; model proposal alone does not pass.',
            'Answer-withheld solver and separate option-aware audit; preserve provider failures.',
            'Persian teaching audit and complete domain/existence/equality arguments.',
            'Coordinate fidelity, desktop/mobile short-segment screen and visual review when a figure exists.',
            'Compare against previous generated drafts; no held-out source access or originality guarantee.'],
        'independent_review':{'state':'self_reviewed_plan_only','external_architecture_review':None,
            'findings':['Rejecting every shortcut would contradict the learning goal: preserve valid routes.',
              'A derivation string matching an option is only a binding, not proof the wrong route produces it.',
              'No forced trap count or combined-topic count establishes Konkur quality.',
              'Prompts contain generic factual/design briefs, not private source literals or expert approval.']},
        'limitations':['Convenience three-item trial, not a randomized model comparison.',
            'Existing free-tier resources only; no bulk approval or production integration.',
            'Formal technique and population-error statistics remain unresolved.']}
    OUT.mkdir(exist_ok=True);sha=payload_digest(manifest);path=OUT/('protocol-'+sha+'.json')
    if (OUT/'pointer.json').exists() and saved_json(OUT/'pointer.json')['sha256']!=sha:raise ValueError('Frozen trial differs; make a new revision')
    if path.exists():
        if saved_json(path)!=manifest:raise ValueError('Changed protocol')
    else:atomic_json(path,manifest)
    atomic_json(OUT/'pointer.json',{'file':path.name,'sha256':sha})
    print(json.dumps({'planned':3,'protocol_sha256':sha,'provider_calls_in_preparation':0,'heldouts_read':0}))
    return manifest,sha


if __name__=='__main__':prepare()
