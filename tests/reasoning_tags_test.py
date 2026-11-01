import json
from pathlib import Path
from copy import deepcopy
import pytest
from app.rag.reasoning_tags import validate_annotation, REGISTRY

FIXTURE=Path(__file__).parent/"fixtures/reasoning_tags/candidate.json"

def sample(): return json.loads(FIXTURE.read_text(encoding="utf-8"))
def validate(r, **kw): return validate_annotation(r,catalogue=kw.pop("catalogue",[]),catalogue_version="synthetic-catalogue-v1",**kw)

def test_candidate_is_valid_but_always_held():
    result=validate(sample())
    assert result["valid"] and not result["eligible"]
    assert "curriculum_unmapped" in result["holds"]

@pytest.mark.parametrize("field,value",[("taxonomy_version","2"),("question_revision",True),("routes",None),("objective","obj.invented"),("empirical_difficulty",{"accuracy":1})])
def test_bad_contracts(field,value):
    r=sample();r[field]=value
    assert not validate(r)["valid"]

def test_unknown_knowledge_and_unbacked_nodes():
    r=sample();r["knowledge_ids"]=["lesson:invented"]
    assert not validate(r)["valid"]
    assert not validate(r,catalogue=[{"id":"lesson:invented","sources":[]}])["valid"]

def test_current_catalogue_source_and_revision_binding():
    r=sample(); source={"book":"synthetic-book","page":2,"quote":"synthetic heading"}
    r["knowledge_ids"]=["lesson:synthetic"]
    r["knowledge_evidence"]=[{"knowledge_id":"lesson:synthetic","source":source,"evidence":"Synthetic item uses this relationship."}]
    cat=[{"id":"lesson:synthetic","sources":[source]}]
    bound={k:deepcopy(r[k]) for k in ("question_ref","question_revision","source")}
    assert validate(r,catalogue=cat,question=bound)["valid"]
    bound["question_revision"]=2
    assert not validate(r,catalogue=cat,question=bound)["valid"]
    r["knowledge_evidence"][0]["source"]["page"]=3
    assert not validate(r,catalogue=[{"id":"lesson:synthetic","sources":[{"book":"synthetic-book","page":2,"quote":"synthetic heading"}]}])["valid"]

def test_roles_evidence_and_routes():
    r=sample();r["routes"][0]["annotations"][0]["evidence"]=""
    assert not validate(r)["valid"]
    r=sample();r["checks_shortcuts"][0]["route_id"]="missing"
    assert not validate(r)["valid"]
    r=sample();r["routes"][1]["role"]="supporting"
    assert not validate(r)["valid"]

@pytest.mark.parametrize("value",[None,[],"text",{}, {"source":[],"routes":[None],"annotator":1}])
def test_malformed_input_reports_errors(value):
    assert not validate(value)["valid"]

def test_no_approval_or_mutation():
    r=sample();original=deepcopy(r);validate(r);assert r==original
    for field,value in [("human_reviewed",True),("eligibility","eligible"),("scientific_state","verified")]:
        r=sample();r["review"][field]=value
        assert not validate(r)["valid"]

def test_registry_matches_document():
    import re
    doc=(Path(__file__).parents[1]/"docs/QUESTION_REASONING_TAXONOMY.md").read_text(encoding="utf-8")
    assert set(REGISTRY)==set(re.findall(r"`((?:tech|rep|obj|check|shortcut|mis)\.[a-z_]+)`",doc))
