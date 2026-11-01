import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('preflight_pairing',Path(__file__).parents[1]/'backend/scripts/preflight_authoring_packet.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def row(**kw):
    return dict(exam_id='synthetic',session='morning',booklet_code='A',section='math',printed_question_number=1,**kw)


def test_other_session_same_number_cannot_join():
    q=row();a=row();a['session']='afternoon'
    assert m.unique_answer(q,[q],[a]) is None


def test_ambiguous_answers_and_questions_cannot_join():
    q=row();a=row()
    assert m.unique_answer(q,[q],[a,a]) is None
    assert m.unique_answer(q,[q,q],[a]) is None


def test_missing_identity_cannot_join_but_complete_identity_can():
    q=row();a=row()
    assert m.unique_answer(q,[q],[a])==a
    q['booklet_code']=None
    assert m.unique_answer(q,[q],[a]) is None
