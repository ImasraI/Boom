"""Synthetic-only reconciliation checks; no provider, PDF or review writes."""
import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
import pytest
scripts=Path(__file__).resolve().parents[1]/"backend/scripts"
sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location("merge_reports",scripts/"merge_reasoning_reports.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def inputs():
    q=dict(id="synthetic:q15",document_id="a"*64,printed_question_number=15,
        presentation=dict(stem=[dict(kind="text",value="Synthetic question")],options=[dict(index=i,text=str(i)) for i in range(4)],
                          source_image=dict(file="synthetic.png",sha256="c"*64),table={"rows":[{"label":"Synthetic","cells":["1","2"]}]}))
    a=dict(id="synthetic:a15",document_id="a"*64,content_sha256="d"*64,answer_index=1,regions=[])
    binding=dict(contentHash="b"*64,questionRevision=2,documentRevision="1")
    current=(q,a,binding,"t",[],[])
    external=dict(number=15,printed_key_index=1,raw_section="**Concepts:** Synthetic concept\n**Route A:** Check the two original cases.\n**Route B:** none materially different.\n**Techniques**\n**Distractors (inferred):** Unknown explanation.")
    curated=dict(number=15,decision="Synthetic decision",tags=[dict(id="tech.case_analysis",role="primary",evidence="Two exhaustive synthetic cases are checked.")],
                 conventions=["Closed-interval convention is explicit; no source key is overwritten."])
    return current,external,curated


def merge(current,baseline,ext,c):return m.merge_one(current,baseline,ext,c,catalogue=[],catalogue_version="synthetic-catalogue",external_sha="e"*64)


def test_merge_preserves_originals_and_does_not_promote_or_invent_distractors():
    current,ext,c=inputs();original=deepcopy((current,ext,c))
    r=merge(current,None,ext,c)
    assert (current,ext,c)==original
    assert r["literal"]["table"]==current[0]["presentation"]["table"]
    assert r["reasoning_annotation"]["review"]["human_reviewed"] is False
    assert r["review"]["eligible"] is False and r["validation"]["valid"] is True
    assert r["design"]["conventions"]==c["conventions"]
    assert r["inferred_distractor_proposals"]["state"]=="unverified_hypotheses_not_generator_targets"
    assert len(r["design"]["routes"])==1


def test_reconciliation_has_new_annotation_revision_and_frozen_provenance():
    current,ext,c=inputs();base=merge(current,None,ext,c)["reasoning_annotation"];saved=deepcopy(base)
    r=merge(current,base,ext,c)
    assert base==saved
    assert r["reasoning_annotation"]["annotation_revision"]==base["annotation_revision"]+1
    assert r["provenance"]["baseline_annotation_sha256"]==m.payload_digest(base)
    assert r["provenance"]["independent_validation"] is False
    current[2]["contentHash"]="f"*64
    with pytest.raises(ValueError):merge(current,base,ext,c)


@pytest.mark.parametrize("fault",["number","key","node","preferred_route"])
def test_conflicts_or_unknown_references_hold_instead_of_silent_merge(fault):
    current,ext,c=inputs()
    if fault=="number":ext["number"]=16
    if fault=="key":ext["printed_key_index"]=2
    if fault=="node":c["knowledge_ids"]=["invented"]
    if fault=="preferred_route":c["preferred_route"]="missing"
    with pytest.raises(ValueError):merge(current,None,ext,c)
