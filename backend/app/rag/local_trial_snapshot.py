"""Bind trusted local trial evidence; never authorizes production eligibility.

Caller verifies file hashes and the origin of the chat feedback. This pure
projection does not authenticate arbitrary imported reviewer identities.
"""
from app.rag.exam_corpus import payload_digest


def validation_snapshot(presentation,math_report,blind_report,feedback):
    digest=payload_digest(presentation)
    if math_report.get('presentation_sha256')!=digest:
        raise ValueError('Mathematical checks target another presentation')
    if feedback.get('presentation_payload_sha256')!=digest:
        raise ValueError('Editorial feedback targets another presentation')
    questions=presentation['questions'];solutions=presentation['solutions']
    ids={q['id'] for q in questions}
    if len(ids)!=len(questions) or len(ids)!=len(solutions):raise ValueError('Duplicate/missing questions')
    solution_map={s['id']:s for s in solutions}
    math_map={r['id']:r for r in math_report['records']}
    blind_map={r['question_id']:r for r in blind_report['matrix']}
    for rows,keys in [(solutions,solution_map),(math_report['records'],math_map),(blind_report['matrix'],blind_map)]:
        if len(rows)!=len(keys) or set(keys)!=ids:raise ValueError('Evidence coverage mismatch')
    if set(feedback.get('question_ids',[]))!=ids:raise ValueError('Feedback question set changed')
    records=[]
    for q in questions:
        qid=q['id'];answer=solution_map[qid]['answer_index'];math=math_map[qid]['mathematics'];blind=blind_map[qid]
        if type(answer) is not int or not 0<=answer<4 or math['answer_index']!=answer:
            raise ValueError('Math/key binding mismatch')
        if blind['expected_answer_index']!=answer:raise ValueError('Blind comparison used a different key')
        verdict=blind.get('solver_verdict');solver_answer=blind.get('solver_answer_index')
        derived=('matched' if solver_answer==answer else 'disagreed') if verdict=='solved' else 'unresolved'
        if derived!=blind['blind_solve_state']:raise ValueError('Inconsistent blind comparison state')
        if q['options'][answer]!='$'+math['answer']+'$':raise ValueError('Option content changed')
        records.append(dict(id=qid,question_revision=1,
            literal_sha256=payload_digest({k:q.get(k) for k in ('stem','options','svg')}),
            solution_sha256=payload_digest(solution_map[qid]),
            mathematics='bounded_checks_recorded',blind_solve=blind['blind_solve_state'],
            editorial='positive_feedback_recorded',
            local_regression_ready=blind['blind_solve_state']=='matched',
            human_scientific_review=False,semantic_originality_approved=False,release_eligible=False,
            release_holds=['local_experiment_only','qualified_scientific_review_pending',
                'curriculum_release_receipts_pending','semantic_novelty_review_pending',
                'expanded_release_evaluation_pending']))
    return dict(schema_version='0.1',purpose='local_development_regression',
        presentation_sha256=digest,records=records,
        summary=dict(questions=len(records),blind_answer_matches=sum(r['blind_solve']=='matched' for r in records),
            editorial_feedback_count=len(records),local_regression_ready=sum(r['local_regression_ready'] for r in records),
            release_eligible=0),
        limitations=['Evidence projection only; input hashes/provenance must be verified by trusted local caller',
            'No general model-quality claim from three examples','No production adapter, bank or eligibility activation'])
