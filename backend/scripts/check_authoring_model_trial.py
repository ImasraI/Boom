"""Reproduce bounded checks for the saved two-attempt pilot, not a general solver."""
import hashlib
import json
import sys
from pathlib import Path
import sympy as S
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json


def main():
    root = Path(__file__).resolve().parents[1] / 'data/authoring_work/model-authoring-trial-v1'
    files = [root / 'candidate-cb5c56417436d2390d7a71b6e930a44176682b251ae65f7dd48cc84b2b66ee12.json',
             root / 'attempt-2/candidate-04dd7eaccf483188c0c6980f05987b81602c9924a936c263e8e6cfacfc9feb93.json']
    a = S.symbols('a', real=True)
    low, high = 17-2*S.sqrt(66), 17+2*S.sqrt(66)
    assert S.expand((5-3*a)**2-4*a*(1+2*a)) == a*a-34*a+25
    assert low > 0 and low < 1 and high > 1
    # For any a in the open interval, (a+low)/2 is a smaller valid value.
    assert S.simplify((a+low)/2-low) == (a-low)/2
    assert S.Rational(14+9-5) == 18
    assert S.Rational(5,18) not in [S.Rational(5,n) for n in (22,14,19,9)]
    x = S.symbols('x')
    assert S.solve(x*x-1, x) == [-1,1]
    checks = [
        [{'state':'held_editorial_scope', 'computed_answer':'17/22',
          'reason':'Correct elementary union count, but no conditioning or interacting constraints.'},
         {'state':'rejected_underspecified_domain', 'computed_answer':None,
          'reason':'Real coefficient has an open feasible interval with no minimum; integer assumption is absent from stem.',
          'feasible_set':str(S.Interval.open(low,high))}],
        [{'state':'rejected_no_correct_option','computed_answer':'5/18',
          'reason':'Conditional sample space has 18 members; no option equals 5/18.'},
         {'state':'rejected_no_correct_option','computed_answer':'0',
          'reason':'a=1,b=0,c=-1 satisfies every stated constraint; |b|=0 is minimal and absent from options.'}]
    ]
    report={'scope':'manual symbolic/finite check of these frozen four drafts only',
            'model_agreement_used':False,'human_review_claimed':False,'release_eligible':False,'attempts':[]}
    expected = ['c93a9251c9c15aa6c7dcd1dbe5ab335532364a80e1957a972cb139be74473616',
                '690742c5c6b487efbdff69cd1458ae1864cc83a86ea85691f37db445f8d60dcf']
    for path, verdicts, bound_sha in zip(files,checks,expected):
        if hashlib.sha256(path.read_bytes()).hexdigest() != bound_sha:
            raise ValueError('Draft bytes changed; these checks cannot be reused')
        data=json.loads(path.read_text(encoding='utf8'))
        assert len(data['questions'])==2
        report['attempts'].append({'candidate_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                  'relative_path':str(path.relative_to(root)), 'checks':verdicts})
    atomic_json(root/'independent-checks.json',report)
    atomic_json(root/'evaluation-summary.json',{'drafts':4,'mathematically_rejected':3,
        'held_editorial_scope':1,'eligible':0,'calls':2,'model':'openai/gpt-oss-120b',
        'production_changed':False,'limitations':'Tiny synthetic-scope pilot; no retrieved eligible exam designs were sent.'})
    print('4 drafts checked: 3 mathematical rejections; 1 editorial hold; 0 eligible.')


if __name__=='__main__': main()
