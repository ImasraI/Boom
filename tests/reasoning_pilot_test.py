"""Synthetic development-pack tests; no PDF, database or model calls."""
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("reasoning_pilot", Path(__file__).resolve().parents[1] / "backend/scripts/prepare_reasoning_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class Store:
    def __init__(self, root):
        self.catalogue = root / "catalogue.json"
        self.catalogue.write_text(json.dumps({"nodes": []}))
        self.q = dict(id="synthetic:q1", document_id="a"*64, section="math", printed_question_number=1,
                      presentation=dict(candidate_sha256="d"*64, stem=[{"kind":"text","value":"Synthetic stem"}],
                                        options=[{"index":i,"text":str(i)} for i in range(4)],
                                        source_image=dict(sha256="c"*64, file="synthetic.png", pdf_page=1)))
        self.binding = dict(contentHash="b"*64, questionRevision=2)

    def load(self):
        return {"documents":[dict(document_id="a"*64, revision=1, classification="mock_exam")],"questions":[self.q]}

    def current(self, qid):
        assert qid == self.q["id"]
        a = dict(id="synthetic:a1", document_id="a"*64, content_sha256="e"*64,
                 regions=[], literal_native="DO NOT LEAK SOLUTION", answer_index=3)
        return self.q, a, self.binding, "f"*64, [], []


def draft():
    return dict(number=1, objective="obj.determine", representations=[{"id":"rep.symbolic","stage":"given"}],
        routes=[dict(id="r1",role="primary",annotations=[dict(id="tech.substitution",role="primary",evidence="Set t=x+1/x, retaining x nonzero.")])],
        family="synthetic-family", learning_objective="Synthetic relationship", essential_decision="Synthetic decision",
        variation_boundary="No parameter-only copies",knowledge_ids=[], knowledge_rationale="Unmapped")


def test_pack_is_immutable_reproducible_and_non_promoting(tmp_path):
    s=Store(tmp_path); out=tmp_path/"out"
    first=pilot.build_pilot(s,[draft()],out,document_id="a"*64,model="synthetic-model")
    snapshots={p.name:p.read_bytes() for p in out.iterdir()}
    assert pilot.build_pilot(s,[draft()],out,document_id="a"*64,model="synthetic-model")==first
    assert snapshots=={p.name:p.read_bytes() for p in out.iterdir()}
    assert first["eligible_count"]==first["human_decisions_written"]==0
    independent=json.loads((out/first["files"]["independent-input"]).read_text())
    serialized=json.dumps(independent)
    for forbidden in ("routes","DO NOT LEAK SOLUTION","answer_index","annotations","essential_decision"):
        assert forbidden not in serialized


def test_changed_source_produces_new_artifacts_not_overwrite(tmp_path):
    s=Store(tmp_path);out=tmp_path/"out"
    old=pilot.build_pilot(s,[draft()],out,document_id="a"*64,model="synthetic-model")
    saved=(out/old["files"]["annotations"]).read_bytes()
    s.binding.update(contentHash="1"*64, questionRevision=3)
    new=pilot.build_pilot(s,[draft()],out,document_id="a"*64,model="synthetic-model")
    assert new["manifest_sha256"]!=old["manifest_sha256"]
    assert (out/old["files"]["annotations"]).read_bytes()==saved


@pytest.mark.parametrize("change",["duplicate","wrong_document","unknown_node","bad_tag"])
def test_invalid_or_out_of_scope_drafts_stop_before_writing(tmp_path,change):
    s=Store(tmp_path);d=draft();ds=[d];doc="a"*64
    if change=="duplicate":ds.append(deepcopy(d))
    if change=="wrong_document":doc="9"*64
    if change=="unknown_node":d["knowledge_ids"]=["invented"]
    if change=="bad_tag":d["routes"][0]["annotations"][0]["id"]="tech.invented"
    with pytest.raises(ValueError):pilot.build_pilot(s,ds,tmp_path/"out",document_id=doc,model="synthetic-model")
    assert not (tmp_path/"out").exists()
