"""Offline regression for real multiline math and separate question/answer sheets."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import pytest


def test_display_math_cases_render_without_delimiters_or_hidden_answers():
    root=Path(__file__).resolve().parents[1]
    node=shutil.which('node')
    if not node:pytest.skip('Existing Node runtime unavailable')
    base=root/'backend/data/authoring_work'
    base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.renderer-check-',dir=base) as name:
        out=Path(name).resolve()
        assert out.is_relative_to(base.resolve())
        data={'questions':[{'id':'synthetic:display','stem':r'متن پیش از دستگاه $$\begin{cases} x=1 \\ y=2 \end{cases}$$ و متن پس از آن.',
                           'options':['$1$','$2$','$3$','$4$'],'svg':None}],
              'solutions':[{'id':'synthetic:display','answer_index':2,'answer_latex':'3',
                            'proof':'SOLUTION_ONLY_TOKEN','checks':['Synthetic renderer test']}],
              'provenance':'<script>UNTRUSTED_HTML</script>'}
        result=subprocess.run([node,str(root/'frontend/tools/render-authoring-trial.cjs'),str(out)],
            input=json.dumps(data),encoding='utf8',text=True,capture_output=True,timeout=30)
        assert result.returncode==0,result.stderr
        question=(out/'questions.html').read_text(encoding='utf8')
        answer=(out/'solutions.html').read_text(encoding='utf8')
        assert 'katex-display' in question and 'class="math display-math"' in question
        assert '$$' not in question and question.count('class="option-label"')==4
        assert 'SOLUTION_ONLY_TOKEN' not in question and 'SOLUTION_ONLY_TOKEN' in answer
        assert '<script>UNTRUSTED_HTML</script>' not in question
        report=json.loads((out/'render-validation.json').read_text())
        assert report['errors']==0 and report['answersEmbeddedInQuestionPage'] is False
