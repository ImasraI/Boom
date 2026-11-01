from app.rag.pedagogical_policy import language_audit,prompt_v03
from app.rag.pedagogical_authoring import prompt_for


def question(prose):
    return {'solution':prose,'pedagogy':{'key_observation':prose,'answer_justification':prose,
            'steps':[{'id':'s1','explanation':prose,'math':'x+1=2'}],
            'boundary_checks':[prose],'alternative_route':None}}


def test_english_teaching_is_held_even_with_persian_full_solution():
    q=question('Use the triangle inequality to find the interval.')
    q['solution']='ابتدا نامساوی مثلث را برای تعیین دامنهٔ مجاز اعمال می‌کنیم.'
    r=language_audit(q)
    assert 'solution' not in r['holds'] and 'pedagogy.key_observation' in r['holds']
    assert r['eligible'] is False and r['mathematical_correctness'] is None


def test_persian_script_does_not_become_fluency_or_science_approval():
    r=language_audit(question('ابتدا نامساوی مثلث را برای تعیین دامنهٔ مجاز اعمال می‌کنیم.'))
    assert r['holds']==[] and r['persian_fluency_review'] is None
    assert all(f['status']=='script_screen_only' for f in r['fields'])


def test_latin_point_labels_and_math_do_not_require_translation():
    r=language_audit(question('با استفاده از نامساوی مثلث، ابتدا طول AB و سپس طول BC را به دست می‌آوریم.'))
    assert r['holds']==[]


def test_new_prompt_is_explicit_and_preserves_original_prompt_bytes():
    spec={'id':'synthetic','facts':['Synthetic fact']}
    before=prompt_for(spec);new=prompt_v03(spec)
    assert new.startswith(before) and prompt_for(spec)==before
    assert 'recalculate from those NEW givens' in new
    assert 'prove sufficiency' in new and 'ALL explanatory prose in Persian' in new
