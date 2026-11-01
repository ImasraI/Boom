"""Freeze a paired development evaluation plan, without generating or approving items."""
import hashlib
import json
import random
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from scripts.run_grounded_authoring_trial import current_inputs


def main():
    root=Path(__file__).resolve().parents[2]
    out=root/'backend/data/authoring_work/development-benchmark-v1';out.mkdir(exist_ok=True)
    packet=current_inputs(2)
    tasks={
        'cubic_identity':[
            'Real existence from identities with explicit parameter domains',
            'Count distinct real ordered pairs, including degeneracies',
            'Reachability of an expression under cubic and symmetric constraints',
            'Integer-parameter admissibility with an attained boundary',
            'Consistency of two algebraic constraints, beyond direct evaluation',
            'Branch counting with an equal-variable boundary case',
            'Evaluate an equivalence claim after a potentially invalid division'],
        'parallel_similarity':[
            'A diagonal intersection linked to a parallel-section distance',
            'A ratio invariant under an arbitrary shear of the geometry',
            'Locate an intersection and enforce segment membership',
            'Infer an unknown base from two parallel-section relationships',
            'Determine when an intersection is internal rather than on an extension',
            'Compare two lengths using linked but correctly matched similarities',
            'Feasibility of a specified point arrangement and distances'],
        'residue_cycles':[
            'Power and polynomial residues combined with a second counting constraint',
            'A modular cycle with a nonempty partial terminal block',
            'Classify feasible residues before counting solutions',
            'Combine distinct short cycles without unjustified division',
            'Find a least positive admissible value under cyclic constraints',
            'Count a parity-restricted set with an exponential congruence']}
    order=['baseline_first']*10+['conditioned_first']*10
    random.Random(20261027).shuffle(order)
    rows=[]
    for brief,targets in tasks.items():
        for target in targets:
            i=len(rows)
            rows.append(dict(spec_id=f'dev-pair:{i+1:02d}',brief_id=brief,target=target,
                arms=['baseline','design_conditioned'],arm_order=order[i],
                paired_controls=['same factual scope','same provider/model/reasoning/output budget',
                    'same novelty/domain/option requirements','same retry and quota rules'],
                baseline='Generic task and factual mathematics only',
                design_conditioned='Same inputs plus approved-summary-derived generic design guidance',
                difficulty=None,review_state='not_started'))
    manifest=dict(schema_version='0.1',protocol_revision=1,planned_pairs=20,planned_attempted_items=40,
        source_packet_sha256=payload_digest(packet),generation_profile=packet['protocol']['generation_profile'],
        tasks=rows,purpose='Paired development test of generic design guidance, not final holdout or full RAG benefit',
        sealed_holdouts_accessed=False,practice_template_variants_excluded=True,
        original_three_calibration_questions_excluded=True,
        provider_assignment='Freeze one available configured free-tier model for both arms before execution; do not silently mix providers',
        substitutions='No silent replacement of failed items; provider/protocol/math/editorial outcomes counted separately',
        metrics=['attempted items','usable drafts','critical mathematical defects','exactly one correct option',
            'curriculum alignment','figure fidelity','clarity','Konkur likeness','structural novelty',
            'latency','reported tokens and missing-usage count'],
        human_rubric=dict(state='draft_pending_expert_calibration',ordinal_anchors={
            '1':'Unusable or misleading','3':'Usable but routine or requiring edits','5':'Clear, insightful and naturally exam-like'},
            correctness='Separate pass/fail/unresolved with checkable evidence, not this ordinal score',
            student_difficulty='Not inferred or assigned by this benchmark'),
        evaluation=dict(review_order='Fixed randomization; reviewers see neutral aliases, not arm/provider',
            answers='Separate blind-solve and answer-bearing review packets',
            treatment='Do not expose one arm output to the other authoring prompt',
            scientific_approval='Never inferred from model agreement',
            release_eligibility=False),
        limits=['Three-topic convenience slice; no global quality or production-readiness estimate',
            'Actual ranking/rater agreement cannot be measured before reviews',
            'This prepares a plan only; no provider calls, questions or reviews are produced'])
    assert len(rows)==20 and sum(r['brief_id']=='cubic_identity' for r in rows)==7
    name='protocol-'+payload_digest(manifest)+'.json'
    if (out/'status.json').exists():
        saved=json.loads((out/'status.json').read_text())
        if saved.get('sha256')!=payload_digest(manifest):
            raise ValueError('Frozen protocol differs; create a new protocol revision instead of replacing it')
        print('Existing development protocol preserved; generation progress was not reset.')
        return
    if not (out/name).exists():atomic_json(out/name,manifest)
    atomic_json(out/'status.json',dict(artifact=name,sha256=payload_digest(manifest),
        planned_pairs=20,planned_items=40,generated_items=0,provider_calls=0,release_eligible=0,
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print('Development protocol frozen:20 paired specifications/40 planned items;0 generated;0 provider calls.')


if __name__=='__main__':main()
