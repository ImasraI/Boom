"""Freeze local H1 exclusions and aggregate exposure audit; no PDF OCR/model calls."""
import hashlib,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest

ROOT=Path(__file__).resolve().parents[1]/"data"

def freeze(root=ROOT):
    folder=root/"authoring_work/h1"
    decisions=json.loads((folder/"decisions-v1.json").read_text(encoding="utf-8"))
    additions=json.loads((folder/"new-source-reservations-v1.json").read_text(encoding="utf-8"))
    reserved={r["source_sha256"] for r in decisions["reserved_evaluation_documents"]}
    reserved.update(f["sha256"] for group in additions["folders"] for f in group["files"])
    development=decisions["development_document_sha256"]
    if development in reserved:raise ValueError("Development/evaluation document overlap")
    catalogue=root/"knowledge_graph/catalog.json"
    current=hashlib.sha256(catalogue.read_bytes()).hexdigest()
    if current!=decisions["catalogue"]["sha256"]:raise ValueError("Catalogue changed since H1; require versioned decision")
    inventory=json.loads((root/"exam_examples/inventory.json").read_text(encoding="utf-8"))
    chunks=json.loads((root/"exam_staging/batch-5000-v1/chunks.json").read_text(encoding="utf-8"))
    aliases={r["document_id"]:[r.get("path"),*r.get("aliases",[])] for r in inventory["documents"] if r["document_id"] in reserved}
    # Compare exact normalized content and number-masked templates offline only.
    # Hash equality is an overlap signal, never proof that unrelated families differ.
    groups={}
    for c in chunks:
        text=c.get("text","")
        canonical=re.sub(r"\d+","#",re.sub(r"\s+"," ",text)).strip()
        if len(canonical)<80:continue
        fp=hashlib.sha256(canonical.encode()).hexdigest()
        groups.setdefault(fp,[]).append((c["id"],c.get("metadata",{}).get("document_id")))
    excluded_ids=set();family_ids=[]
    for fp,rows in groups.items():
        if any(doc in reserved for _,doc in rows):
            excluded_ids.update(id for id,_ in rows);family_ids.append(fp)
    references=[];scanned=0
    for directory in [root/"exam_examples",root/"exam_staging",root/"authoring_work"]:
        for path in directory.rglob("*.json"):
            name=path.name.lower()
            if not any(w in name for w in ("generation-trial","sample-","retrieval-pilot")):continue
            if path.stat().st_size>10_000_000:continue
            try:raw=path.read_text(encoding="utf-8");json.loads(raw)
            except (ValueError,OSError,UnicodeError):continue
            scanned+=1
            refs=set(re.findall(r"[0-9a-f]{64}:\d+:\d+",raw))
            hits=sorted(id for id in refs if id.split(":")[0] in reserved)
            if hits:references.append({"artifact":str(path.relative_to(root)),"reference_ids":hits})
    policy={"schema_version":"0.1","major":"riazi","curriculum_version":current,
      "development_document_ids":[development],"excluded_document_ids":sorted(reserved),
      "excluded_record_ids":sorted(excluded_ids),"excluded_family_ids":sorted(family_ids),
      "records":[],"scopes":{},"active_scope_id":None,
      "allowed_knowledge_ids":[n["id"] for n in json.loads(catalogue.read_text(encoding="utf-8"))["nodes"]],
      "review_state":"routing_exclusions_frozen; eligible_source_receipts_pending",
      "holdout_unseen_verified":False,"split_approved_by":"user H1 decisions in chat"}
    report={"schema_version":"0.1","reserved_documents":len(reserved),"indexed_reserved_aliases":aliases,
      "indexed_reserved_records":sum(c.get("metadata",{}).get("document_id") in reserved for c in chunks),
      "number_masked_template_groups_excluded":len(family_ids),"excluded_record_ids":len(excluded_ids),
      "exposure_artifacts_checked":scanned,"saved_reference_matches":references,
      "exposure_limits":"Local sampled saved artifacts only; cannot prove absence from historical unsaved prompts or model pretraining.",
      "new_pdf_family_overlap":"pending controlled evaluator inspection; deny by default meanwhile",
      "eligible_reviewed_records":0,"reviewed_weekly_scopes":0,"no_pdf_contents_sent_to_models":True}
    fingerprint=payload_digest({"policy":policy,"audit":report})
    archive=folder/("split-"+fingerprint+".json")
    if not archive.exists():atomic_json(archive,{"policy":policy,"audit":report})
    atomic_json(folder/"retrieval-policy-v1.json",policy)
    atomic_json(folder/"split-audit-v1.json",report)
    print(json.dumps({k:v for k,v in report.items() if k not in ("indexed_reserved_aliases","saved_reference_matches")},indent=2))

if __name__=="__main__":freeze()
