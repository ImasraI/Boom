"""Compare a supplied prose annotation report to a frozen development manifest.

Free-text labels remain free text: this importer never guesses taxonomy IDs,
records a human review, or promotes agreement into scientific verification.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest


def parse_report(text):
    headings=list(re.finditer(r"^## Q([1-9][0-9]*)\s*[·.]\s*(.*)$",text,re.M))
    if not headings:raise ValueError("No numbered question sections")
    records={}
    for i,match in enumerate(headings):
        n=int(match[1])
        if n in records:raise ValueError("Duplicate printed question number")
        block=text[match.start():headings[i+1].start() if i+1<len(headings) else len(text)]
        key=re.search(r"\*\*Provided:\*\*\s*key\s+([1-4])\b",block)
        if not key:raise ValueError("Missing or invalid printed key")
        records[n]=dict(number=n,claimed_source_label=match[2],printed_key_index=int(key[1])-1,
                        raw_section=block,annotation_state="unmapped_external_prose")
    return records


def compare(report, manifest, publisher_keys, current_tokens):
    baseline={r["number"]:r for r in manifest["records"]}
    if len(baseline)!=len(manifest["records"]):raise ValueError("Duplicate baseline numbers")
    if manifest.get("split")!="development":raise ValueError("Only development comparison is permitted")
    if set(report)!=set(publisher_keys):raise ValueError("Incomplete or out-of-source external report")
    rows=[]
    for n,record in sorted(report.items()):
        base=baseline.get(n)
        if base and base["evidence_token"]!=current_tokens.get(n):raise ValueError("Stale frozen baseline")
        rows.append(dict(number=n,baseline_available=base is not None,
            matches_publisher_key=record["printed_key_index"]==publisher_keys[n],
            baseline_question_ref=base["question_ref"] if base else None,
            taxonomy_comparison="requires_explicit_mapping",
            mathematical_accuracy="not_established_by_key_agreement",eligible=False))
    return dict(schema_version="0.1",external_count=len(rows),shared_count=sum(r["baseline_available"] for r in rows),
                publisher_key_matches=sum(r["matches_publisher_key"] for r in rows),rows=rows,
                human_reviews_written=0,eligible_count=0,normalized_tag_agreement=None)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("report",type=Path)
    args=p.parse_args()
    data=Path(__file__).resolve().parents[1]/"data"
    root=data/"authoring_work"
    baseline=root/"reasoning-pilot-v1"
    status=json.loads((baseline/"status.json").read_text(encoding="utf-8"))
    manifest=json.loads((baseline/status["files"]["manifest"]).read_text(encoding="utf-8"))
    from app.rag.authoring_review import ReviewStore
    store=ReviewStore(root/"review-ledger-v1",root/"s1a-mapped",data/"knowledge_graph/catalog.json")
    keys,tokens={},{}
    for q in store.load()["questions"]:
        if q["section"]!="math" or q["document_id"]!=manifest["document_id"]:continue
        _,a,_,t,_,_=store.current(q["id"])
        if a is None or type(a.get("answer_index")) is not int:raise ValueError("Unresolved publisher key")
        keys[q["printed_question_number"]]=a["answer_index"];tokens[q["printed_question_number"]]=t
    raw=args.report.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    report=parse_report(raw.decode("utf-8-sig"))
    result=compare(report,manifest,keys,tokens)
    result.update(external_report_sha256=sha,baseline_manifest_sha256=manifest["manifest_sha256"],
        external_model="Claude; version not supplied",independence="not_verified_from_supplied_report",
        identity_alignment="user-assigned same exam; section numbers/keys align; external PDF byte SHA unavailable")
    out=root/"reasoning-comparison-v1";out.mkdir(exist_ok=True)
    raw_path=out/("claude-original-"+sha+".txt")
    if raw_path.exists() and raw_path.read_bytes()!=raw:raise ValueError("Original artifact conflict")
    if not raw_path.exists():raw_path.write_bytes(raw)
    atomic_json(out/("claude-sections-"+sha+".json"),list(report.values()))
    atomic_json(out/("comparison-"+payload_digest(result)+".json"),result)
    atomic_json(out/"status.json",result)
    print(json.dumps({k:result[k] for k in ("external_count","shared_count","publisher_key_matches","eligible_count")}))


if __name__=="__main__":main()
