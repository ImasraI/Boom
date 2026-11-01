"""Build a private, unpublished spec-first trial with no live provider calls."""
import hashlib
import json
import re
import shutil
import subprocess
import sys
from difflib import SequenceMatcher
from fractions import Fraction
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_sandbox import FAMILIES,construct,validate_candidate,VERSION
from app.rag.exam_corpus import atomic_json,payload_digest


def normalize(text):
    text=text.translate(str.maketrans("يك۰۱۲۳۴۵۶۷۸۹","یک0123456789"))
    return re.sub(r"\s+"," ",re.sub(r"[^\w\s]"," ",text)).strip()


def geometry_svg(points):
    p={k:tuple(Fraction(x) for x in xy) for k,xy in points.items()}
    w=max(x for x,y in p.values());h=max(y for x,y in p.values())
    coords={k:(float(40+x*340/w),float(260-y*220/h)) for k,(x,y) in p.items()}
    def xy(k):return f"{coords[k][0]:.3f},{coords[k][1]:.3f}"
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 300" role="img" aria-label="مثلث و دو پاره‌خط متقاطع">',
         '<rect width="420" height="300" fill="white"/>',f'<polygon points="{xy("A")} {xy("B")} {xy("C")}" fill="none" stroke="#263b45" stroke-width="2"/>']
    for a,b in [("A","D"),("B","E")]:
        svg.append(f'<line x1="{coords[a][0]:.3f}" y1="{coords[a][1]:.3f}" x2="{coords[b][0]:.3f}" y2="{coords[b][1]:.3f}" stroke="#9d453d" stroke-width="1.7"/>')
    offsets={"A":(-15,-12),"B":(-15,18),"C":(10,18),"D":(10,18),"E":(12,-5),"P":(-14,-12)}
    for name,(x,y) in coords.items():
        dx,dy=offsets[name];svg.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="2.5" fill="#263b45"/><text x="{x+dx:.3f}" y="{y+dy:.3f}" font-size="18" fill="#15252d">{name}</text>')
    return "".join(svg)+"</svg>"


def main():
    backend=Path(__file__).resolve().parents[1];project=backend.parent;data=backend/"data";root=data/"authoring_work"
    merged_root=root/"reasoning-merged-v1";status=json.loads((merged_root/"status.json").read_text(encoding="utf-8"))
    merged=json.loads((merged_root/status["artifact"]).read_text(encoding="utf-8"))
    if payload_digest(merged)!=status["sha256"] or merged["split"]!="development":raise ValueError("Invalid development design snapshot")
    sources={r["printed_question_number"]:r for r in merged["records"]}
    catalogue=(data/"knowledge_graph/catalog.json").read_bytes()
    if hashlib.sha256(catalogue).hexdigest()!=merged["catalogue_version"]:raise ValueError("Catalogue snapshot changed")
    out=root/"local-authoring-trial-v1";out.mkdir(exist_ok=True)
    # Explicit development-only style sources; factual support stays a separate role.
    parents=[[9,19],[11,17],[1,20],[21,22],[25,30],[32,33],[35,36],[37,38]]
    facts=[[("حسابان 1 خیلی سبز",49)],[("حسابان 1 خیلی سبز",321),("حسابان 1 خیلی سبز",322)],
           [("حسابان 1 خیلی سبز",17),("ریاضی 1 خیلی سبز",7)],[("هندسه 1 خیلی سبز",72)],
           [("هندسه جامع خیلی سبز",134)],[("گسسته و آمار و احتمال جامع خیلی سبز",137)],
           [("گسسته و آمار و احتمال جامع خیلی سبز",11)],[("آمار و احتمال خیلی سبز",65),("آمار و احتمال خیلی سبز",66)]]
    changes=["Parameter-dependent line intersections replace the source's fixed-interval injectivity count.",
             "Original-domain holes interact with a parameterized level set; not a derivative or fixed trig root-count copy.",
             "Ordered outer-root product determines a horizontal level; coefficient comparison and repeated-root rejection replace centre matching.",
             "An area equality determines cevian ratios, then a new small-triangle area target; not renamed given ratios.",
             "A vector norm constraint feeds an attained optimization, rather than copying the source volume target.",
             "Cross-row agreement deliberately breaks the independent-row counting pattern.",
             "Digit reversal and square residues replace elimination of a modulus parameter.",
             "Dependent draws and a predictive third-draw target replace the source's posterior-urn question."]
    records=[];student=[];novelty=[]
    for i,family in enumerate(FAMILIES):
        item=construct(family,seed=512+i);verdict=validate_candidate(item)
        if not verdict["valid"]:raise ValueError("Failed construction: "+family)
        citations=[]
        for book,page in facts[i]:
            text=data/"ocr"/(book+".pdf")/f"page_{page:04d}.txt"
            image=data/"1"/(book+".pdf")/f"page_{page:04d}.png"
            if not text.exists():raise ValueError("Missing local book evidence")
            citations.append(dict(role="factual_grounding_candidate",book=book,pdf_page=page,
                text_ref=str(text.relative_to(data)),text_sha256=hashlib.sha256(text.read_bytes()).hexdigest(),
                image_ref=str(image.relative_to(data)) if image.exists() else None,
                image_sha256=hashlib.sha256(image.read_bytes()).hexdigest() if image.exists() else None,
                document_sha256=None,review_state="existing_OCR_candidate_not_new_human_fact_approval"))
        nearest=[]
        for number,source in sources.items():
            literal=" ".join(x["value"] for x in source["literal"]["stem"])
            nearest.append((SequenceMatcher(None,normalize(item["stem"]),normalize(literal)).ratio(),number))
        nearest.sort(reverse=True)
        if nearest[0][0]>=.85:raise ValueError("Possible source wording copy; hold for inspection")
        svg=geometry_svg(item["figure"]) if item["figure"] else None
        item.update(id=f"trial:{i+1:02d}",constructor_version=VERSION,verification=verdict,
            style_references=[dict(role="experimental_candidate_design",question_ref=sources[n]["question_ref"],
                question_revision=sources[n]["question_revision"],content_sha256=sources[n]["source"]["content_sha256"]) for n in parents[i]],
            factual_references=citations,design_change=changes[i],svg=svg,
            novelty_state="development_40_only_lexical_check_not_semantic_novelty_approval")
        records.append(item)
        student.append({k:item[k] for k in ("id","stem","options","svg")})
        novelty.append(dict(id=item["id"],nearest_source_number=nearest[0][1],similarity=round(nearest[0][0],4),change=changes[i],scope="only40_development_sources"))
    bundle=dict(schema_version="0.1",snapshot_revision=1,source_design_snapshot=status["sha256"],records=records,
        provider_calls=0,author="Codex-assisted offline constructor trial; not a production provider benchmark",
        requested_difficulty=None,eligible_count=0,human_reviews_written=0,
        limitations=["Source designs and factual references remain candidate evidence.","No independent blind-model solve or teacher review.",
                     "No full-corpus/holdout novelty claim.","Konkur likeness and originality require human evaluation.",
                     "Only the allowlisted families/templates are checked; free-form provider output is unsupported."])
    digest=payload_digest(bundle);name="trial-"+digest+".json"
    if not (out/name).exists():atomic_json(out/name,bundle)
    atomic_json(out/"questions-only.json",student);atomic_json(out/"novelty-report.json",novelty)
    atomic_json(out/"status.json",dict(artifact=name,sha256=digest,count=8,mathematical_checks_passed=8,
        requested_difficulty=None,provider_calls=0,eligible_count=0,human_reviews_written=0))
    node=shutil.which("node")
    if not node:raise RuntimeError("Existing Node runtime required to render local math; do not download one automatically")
    result=subprocess.run([node,str(project/"frontend/tools/render-authoring-trial.cjs"),str(out)],
        input=json.dumps(dict(questions=student,solutions=[{k:r[k] for k in ("id","answer_index","answer_latex","proof","checks")} for r in records])),
        capture_output=True,text=True,encoding="utf-8",cwd=project/"frontend",timeout=45)
    if result.returncode:raise RuntimeError(result.stderr[:600])
    print(json.dumps(dict(count=8,mathematical_checks_passed=8,eligible_count=0,provider_calls=0,render=result.stdout.strip())))


if __name__=="__main__":main()
