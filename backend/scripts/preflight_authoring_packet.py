"""Adapt S1a sidecars to accepted F1 input; preserve originals and all holds."""
import json,sys,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json
from app.rag.exam_source_packets import pairing_key

ROOT=Path(__file__).resolve().parents[1]/"data/authoring_work/s1a-mapped"


def unique_answer(question, questions, answers):
    """Full printed identity, not printed number alone; ambiguity stays held."""
    key=pairing_key(question)
    if key is None or sum(pairing_key(q)==key for q in questions)!=1:
        return None
    matches=[a for a in answers if pairing_key(a)==key]
    return matches[0] if len(matches)==1 else None

def preflight(root=ROOT):
    packet=json.loads((root/json.loads((root/"status.json").read_text())["packet"]).read_text(encoding="utf-8"))
    docs=[]
    for source in packet["documents"]:
        docs.append({k:source.get(k) for k in ["schema_version","document_id","source_sha256","role","classification","classification_state","publisher","year","session","major","grade","booklet_code","exam_id","revision","aliases","classification_evidence"]})
    for document in docs:
        if isinstance(document.get("classification_evidence"),list):
            document["classification_evidence"]="; ".join(document["classification_evidence"])
    manifest=[]
    for q in packet["questions"]:
        a=unique_answer(q,packet["questions"],packet["answers"])
        provenance=None
        if a:
            provenance=dict(answer_document_id=a["document_id"],regions=a["regions"],printed_question_number=a["printed_question_number"],section=a["section"],booklet=a["booklet_code"],raw_key=str(a["answer_index"]+1) if a["answer_index"] is not None else "unknown",normalized_answer_index=a["answer_index"],mapping_state="unresolved",pairing_revision=packet["revision"])
        manifest.append(dict(role="question_sidecar",question_id=q["id"],question_revision=q["revision"],document_id=q["document_id"],printed_question_number=q["printed_question_number"],section=q["section"],regions=q["regions"],literal_content_sha256=q["content_sha256"],source_image_sha256=q["source_image_sha256"],figure_sha256=[],answer_provenance=provenance,issues=["native_source_candidate","source_review_pending"]))
    source=packet["documents"][0]
    manifest.append(dict(role="pairing",pairing_id="maze-h0-pairing-v1",revision=packet["revision"],question_document_id=source["document_id"],answer_document_id=source["document_id"],exam_id=source["exam_id"],session=source["session"],booklet_code=source["booklet_code"],state="unresolved",mapping=[dict(printed_question_number=q["printed_question_number"],section=q["section"],booklet_code=q["booklet_code"],question_document_id=q["document_id"],answer_document_id=q["document_id"]) for q in packet["questions"]]))
    out=root/"f1-preflight";out.mkdir(exist_ok=True)
    atomic_json(out/"inventory.json",docs);atomic_json(out/"manifest.json",manifest)
    script=Path(__file__).with_name("validate_exam_review_inputs.py")
    result=subprocess.run([sys.executable,str(script),"--inventory",str(out/"inventory.json"),"--manifest",str(out/"manifest.json"),"--base-dir",str(root),"--output",str(out/"report.json")],capture_output=True,text=True,encoding="utf-8")
    report=json.loads((out/"report.json").read_text(encoding="utf-8"))
    print(json.dumps({"exit_code":result.returncode,"structural_error_count":report.get("structural_error_count"),"hold_count":report.get("hold_count")},indent=2))
    return result.returncode

if __name__=="__main__":sys.exit(preflight())
