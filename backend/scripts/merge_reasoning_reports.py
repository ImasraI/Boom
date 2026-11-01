"""Offline candidate reconciliation, preserving sources and both model passes.

Private curation supplies explicit tag mappings; prose is never auto-promoted.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.reasoning_tags import validate_annotation
from compare_annotation_reports import parse_report


def extract_routes(section):
    matches=list(re.finditer(r"^\*\*Route ([A-Z])(?: \(([^*\n]+)\))?:\*\*",section,re.M))
    routes=[]
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(section)
        body=re.split(r"^\*\*(?:Techniques|Key insight|Distractors)",section[m.end():end],maxsplit=1,flags=re.M)[0].strip()
        if body.lower().startswith("none materially different"):continue
        routes.append(dict(id="claude:"+m[1],qualifier=m[2],summary=body,origin="external_report",curriculum_state="not_established"))
    return routes


def merge_one(current, baseline, external, curated, *, catalogue, catalogue_version, external_sha):
    q,a,binding,token,_,_=current
    c=q.get("presentation")
    if not c or a is None:raise ValueError("Structured source and unique answer required")
    n=q["printed_question_number"]
    if external["number"]!=n or curated["number"]!=n:raise ValueError("Printed question number mismatch")
    if external["printed_key_index"]!=a["answer_index"]:raise ValueError("Publisher key conflict requires resolution")
    source=dict(document_id=q["document_id"],document_revision=int(binding["documentRevision"]),content_sha256=binding["contentHash"],figure_sha256=[c["source_image"]["sha256"]])
    ref=dict(question_ref=q["id"],question_revision=binding["questionRevision"],source=source)
    if baseline:
        if any(baseline.get(k)!=ref[k] for k in ref):raise ValueError("Frozen baseline is stale")
        annotation=json.loads(json.dumps(baseline))
        annotation["annotation_revision"]+=1
        annotation["unresolved_labels"]=[]
    else:
        annotation=dict(annotation_schema_version="0.1",taxonomy_version="0.1",annotation_revision=1,**ref,
            catalogue_version=catalogue_version,knowledge_ids=[],knowledge_evidence=[],objective=None,
            representations=[dict(id="rep.symbolic",stage="given")],routes=[],checks_shortcuts=[],
            misconceptions=[],unresolved_labels=[],intended_difficulty=dict(level=None,rationale=None),empirical_difficulty=None)
    if annotation["catalogue_version"]!=catalogue_version:raise ValueError("Catalogue changed since baseline")
    if curated.get("knowledge_ids") is not None:
        nodes={node["id"]:node for node in catalogue}
        annotation["knowledge_ids"]=curated["knowledge_ids"]
        annotation["knowledge_evidence"]=[]
        for node_id in curated["knowledge_ids"]:
            node=nodes.get(node_id)
            if not node or not node.get("sources"):raise ValueError("Unknown or non-book-backed knowledge mapping")
            annotation["knowledge_evidence"].append(dict(knowledge_id=node_id,source=node["sources"][0],
                evidence=curated["decision"]+" — proposed topic mapping to this existing catalogue node; not a claim of full prerequisite coverage."))
    annotation["annotator"]=dict(kind="model",identifier="codex:reconciliation-after-external-report",model="GPT-6 (Codex; exact snapshot unavailable)",prompt_version="merged-reasoning-0.1")
    annotation["review"]=dict(annotation_state="candidate",source_state="candidate",scientific_state="not_checked",human_reviewed=False,
        eligibility="held",issues=["model_reconciliation_not_independent","human_tag_review_pending","curriculum_mapping_proposed_not_approved"])
    annotation["objective"]="obj."+curated.get("objective","determine")
    if curated.get("representations") is not None:annotation["representations"]=curated["representations"]
    annotation["routes"]=[dict(id="r1",role="primary",annotations=curated["tags"])]
    annotation["checks_shortcuts"]=[]
    if curated.get("taxonomy_gap"):
        annotation["unresolved_labels"].append(dict(axis="technique",reason=curated["taxonomy_gap"]))
    if not annotation["knowledge_ids"]:
        annotation["unresolved_labels"].append(dict(axis="knowledge",reason="No reviewed current book-backed mapping established for this merged record."))
    validation=validate_annotation(annotation,catalogue=catalogue,catalogue_version=catalogue_version,question=ref)
    if not validation["valid"]:raise ValueError(f"Invalid merged annotation: {validation['errors']}")
    routes=extract_routes(external["raw_section"])
    if baseline:
        routes.extend(dict(id="codex:"+r["id"],summary="; ".join(t["evidence"] for t in r["annotations"]),origin="frozen_codex_pass_a",curriculum_state="not_established") for r in baseline["routes"])
    routes.extend(curated.get("added_routes",[]))
    preferred=curated.get("preferred_route","claude:A")
    if preferred not in [r["id"] for r in routes]:raise ValueError("Missing preferred route")
    for route in routes:
        route["role"]="primary" if route["id"]==preferred else "alternative"
        if n==1 and route["id"]=="claude:B":route.update(role="checking",limitation="Find-and-verify witness; not a uniqueness proof by itself.")
        if n==21 and route["id"] in ("claude:A","claude:C"):route["limitation"]="Mathematically valid alternative; Menelaus/mass-points curriculum evidence not established."
        if n==25 and route["id"]=="claude:B":route["limitation"]="Symmetry alone does not prove a minimum; convexity or an equivalent proof is required."
        if n==35 and route["id"]=="claude:A":route["limitation"]="Fermat route retained as optional; theorem-specific curriculum support remains unestablished."
        if n==24 and route["id"]=="claude:B":route["summary"]+=" Scale clarification: the side ratios define a similarity class; the specified inradius fixes its scale, so p=18 is not an arbitrary general choice."
    concepts=re.search(r"^\*\*Concepts:\*\*\s*(.+)$",external["raw_section"],re.M)
    distractors=re.search(r"^\*\*Distractors \(inferred\):\*\*\s*(.+)$",external["raw_section"],re.M)
    publisher_line=re.search(r"^\*\*Provided:\*\*\s*(.+)$",external["raw_section"],re.M)
    return dict(merge_schema_version="0.1",merge_revision=1,**ref,printed_question_number=n,split="development",evidence_token=token,
        literal=dict(stem=c["stem"],options=c["options"],table=c.get("table"),crop=c["source_image"]),
        answer_provenance=dict(answer_id=a["id"],document_id=a["document_id"],content_sha256=a["content_sha256"],
            key_index=a["answer_index"],regions=a["regions"],state="publisher_key_not_new_scientific_approval"),
        reasoning_annotation=annotation,validation=validation,
        publisher_labels=dict(source_native=a.get("publisher_labels_raw"),external_reported_line=publisher_line[1] if publisher_line else None,
            state="raw_provenance_not_reviewed_difficulty",automatic_difficulty_conversion=False),
        design=dict(main_decision_fa=curated["decision"],specific_skills=concepts[1] if concepts else None,
            preferred_route=preferred,routes=routes,conventions=curated.get("conventions",[]),
            inferred=True,difficulty=None,empirical_difficulty=None),
        inferred_distractor_proposals=dict(raw_external=distractors[1] if distractors else None,state="unverified_hypotheses_not_generator_targets"),
        corrections=curated.get("corrections",[]),
        provenance=dict(external_report_sha256=external_sha,external_model="Claude; exact version not supplied",
            baseline_annotation_sha256=payload_digest(baseline) if baseline else None,
            independent_validation=False,originals_preserved=True),
        review=dict(state="candidate",human_reviewed=False,eligible=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("curation",type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/"data/authoring_work"
    if not args.curation.resolve().is_relative_to(root.resolve()):raise ValueError("Private curation required")
    from app.rag.authoring_review import ReviewStore
    store=ReviewStore(root/"review-ledger-v1",root/"s1a-mapped",root.parent/"knowledge_graph/catalog.json")
    bs=json.loads((root/"reasoning-pilot-v1/status.json").read_text(encoding="utf-8"));baseline=json.loads((root/"reasoning-pilot-v1"/bs["files"]["annotations"]).read_text(encoding="utf-8"));base={r["question_ref"]:r for r in baseline}
    comparison=json.loads((root/"reasoning-comparison-v1/status.json").read_text(encoding="utf-8"));sha=comparison["external_report_sha256"]
    raw=(root/"reasoning-comparison-v1"/("claude-original-"+sha+".txt")).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError("External report changed")
    external=parse_report(raw.decode("utf-8-sig"));drafts=json.loads(args.curation.read_text(encoding="utf-8"));curation={r["number"]:r for r in drafts}
    if len(curation)!=len(drafts) or set(curation)!=set(range(1,41)):raise ValueError("Exactly40 unique curated question numbers required")
    catalogue_bytes=store.catalogue.read_bytes();cv=hashlib.sha256(catalogue_bytes).hexdigest();catalogue=json.loads(catalogue_bytes)["nodes"]
    manifest=json.loads((root/"reasoning-pilot-v1"/bs["files"]["manifest"]).read_text(encoding="utf-8"))
    questions=[q for q in store.load()["questions"] if q["section"]=="math" and q["document_id"]==manifest["document_id"]]
    if {q["printed_question_number"] for q in questions}!=set(curation):raise ValueError("Source scope mismatch")
    records=[merge_one(store.current(q["id"]),base.get(q["id"]),external[q["printed_question_number"]],curation[q["printed_question_number"]],catalogue=catalogue,catalogue_version=cv,external_sha=sha) for q in sorted(questions,key=lambda q:q["printed_question_number"])]
    artifact=dict(schema_version="0.1",revision=1,split="development",source_document_id=manifest["document_id"],
        taxonomy_version="0.1",registry_changed=False,catalogue_version=cv,records=records,human_reviews_written=0,eligible_count=0)
    digest=payload_digest(artifact);out=root/"reasoning-merged-v1";out.mkdir(exist_ok=True);name="merged-"+digest+".json"
    if (out/name).exists() and json.loads((out/name).read_text(encoding="utf-8"))!=artifact:raise ValueError("Immutable artifact conflict")
    if not (out/name).exists():atomic_json(out/name,artifact)
    atomic_json(out/"status.json",dict(artifact=name,sha256=digest,count=len(records),eligible_count=0,human_reviews_written=0,structural_errors=0))
    lines=["# تحلیل ترکیبیِ بهبود‌یافتهٔ ۴۰ سؤال ماز", "", "نسخهٔ نامزد؛ تحلیل اصلی دو مدل و تأییدهای متن دست‌نخورده مانده‌اند. این نسخه حل کور یا تأیید انسانیِ برچسب‌ها نیست.", "", "سؤال۱۵: پاسخ منتشرشده۴ نگه داشته شده است؛ تعبیر پیوستگی روی بازهٔ بسته صریح ثبت می‌شود. خطای قطعی در کلید اعلام نشده است."]
    for r in records:
        lines.extend(["",f"## سؤال {r['printed_question_number']}","",r["design"]["main_decision_fa"],"",f"گزینهٔ پاسخ ناشر: {r['answer_provenance']['key_index']+1}","",f"مهارت‌های موضوعی: {r['design']['specific_skills']}","", "برچسب‌ها: "+", ".join(t["id"]+" ("+t["role"]+")" for route in r["reasoning_annotation"]["routes"] for t in route["annotations"])])
        for route in sorted(r["design"]["routes"],key=lambda v:v["role"]!="primary"):
            lines.extend(["",f"### {route['id']} — {route['role']}","",route["summary"]])
            if route.get("limitation"):lines.extend(["", "محدودیت: "+route["limitation"]])
        for note in r["design"]["conventions"]+r["corrections"]:lines.extend(["", "یادداشت: "+note])
        lines.extend(["", "فرضیه‌های گزینه‌های غلط، تأیید نشده‌اند و هدف ساخت گزینهٔ جدید نیستند."])
    (out/"MERGED_ANALYSIS.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps(dict(count=len(records),structural_errors=0,eligible_count=0,human_reviews_written=0)))


if __name__=="__main__":main()
