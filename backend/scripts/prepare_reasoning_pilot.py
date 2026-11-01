"""Offline, immutable development annotation packs; no providers or promotion.

Drafts and output contain private exam material and belong under authoring_work.
The second annotator input intentionally excludes the first annotator's labels.
"""
import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_review import ReviewStore
from app.rag.exam_corpus import atomic_json, payload_digest
from app.rag.reasoning_tags import validate_annotation


def build_pilot(store, drafts, output, *, document_id, model):
    if not isinstance(drafts, list) or not 1 <= len(drafts) <= 50:
        raise ValueError("A bounded development sample of 1..50 drafts is required")
    numbers = [d.get("number") for d in drafts if isinstance(d, dict)]
    if len(numbers) != len(drafts) or any(type(n) is not int for n in numbers) or len(set(numbers)) != len(numbers):
        raise ValueError("Invalid or duplicate printed question numbers")
    packet = store.load()
    documents = [d for d in packet["documents"] if d["document_id"] == document_id]
    if len(documents) != 1 or documents[0].get("classification") not in ("mock_exam", "official_exam"):
        raise ValueError("Explicit development exam identity required")
    rows = {q["printed_question_number"]: q for q in packet["questions"]
            if q["document_id"] == document_id and q["section"] == "math"}
    catalogue_bytes = store.catalogue.read_bytes()
    catalogue = json.loads(catalogue_bytes)["nodes"]
    catalogue_version = hashlib.sha256(catalogue_bytes).hexdigest()
    nodes = {n["id"]: n for n in catalogue}
    manifest_rows, annotations, independent, designs, validations = [], [], [], [], []
    for draft in drafts:
        if draft["number"] not in rows:
            raise ValueError("Draft outside declared development source")
        q, answer, binding, token, _, _ = store.current(rows[draft["number"]]["id"])
        c = q.get("presentation")
        if not c:
            raise ValueError("Structured source presentation required")
        source = dict(document_id=q["document_id"], document_revision=documents[0]["revision"],
                      content_sha256=binding["contentHash"], figure_sha256=[c["source_image"]["sha256"]])
        ref = dict(question_ref=q["id"], question_revision=binding["questionRevision"], source=source)
        knowledge, refs = draft.get("knowledge_ids", []), []
        for node_id in knowledge:
            node = nodes.get(node_id)
            if not node or not node.get("sources"):
                raise ValueError("Unknown or non-book-backed knowledge node")
            refs.append(dict(knowledge_id=node_id, source=node["sources"][0], evidence=draft["knowledge_rationale"]))
        annotation = dict(annotation_schema_version="0.1", taxonomy_version="0.1", annotation_revision=1,
            **ref, catalogue_version=catalogue_version, knowledge_ids=knowledge, knowledge_evidence=refs,
            objective=draft["objective"], representations=draft["representations"], routes=draft["routes"],
            checks_shortcuts=draft.get("checks_shortcuts", []), misconceptions=[],
            unresolved_labels=draft.get("unresolved_labels", []),
            annotator=dict(kind="model", identifier="codex:development-annotation-pass-a", model=model,
                           prompt_version="maze-reasoning-calibration-0.1"),
            review=dict(annotation_state="candidate", source_state="candidate", scientific_state="not_checked",
                        human_reviewed=False, eligibility="held", issues=["independent_annotation_pending",
                        "human_tag_calibration_pending", "curriculum_mapping_proposed_not_approved"]),
            intended_difficulty=dict(level=None, rationale=None), empirical_difficulty=None)
        result = validate_annotation(annotation, catalogue=catalogue, catalogue_version=catalogue_version, question=ref)
        if not result["valid"]:
            raise ValueError(f"Invalid draft {draft['number']}: {result['errors']}")
        manifest_rows.append(dict(**ref, number=draft["number"], evidence_token=token,
            candidate_sha256=c["candidate_sha256"], question_crop=c["source_image"],
            answer_provenance=dict(answer_id=answer["id"], document_id=answer["document_id"],
                content_sha256=answer["content_sha256"], regions=answer["regions"]) if answer else None))
        independent.append(dict(**ref, number=draft["number"], stem=c["stem"], options=c["options"],
                                table=c.get("table"), question_crop=c["source_image"]))
        designs.append(dict(design_schema_version="0.1", design_revision=1, **ref,
            taxonomy_version="0.1", catalogue_version=catalogue_version, inferred=True,
            family=draft["family"], learning_objective=draft["learning_objective"],
            essential_decision=draft["essential_decision"],
            variation_boundary=draft["variation_boundary"], constructor_status="not_implemented",
            distractor_mechanisms=[], difficulty_level=None, eligibility="held"))
        annotations.append(annotation)
        validations.append(dict(number=draft["number"], **result))
    manifest = dict(schema_version="0.1", split="development", document_id=document_id,
        taxonomy_version="0.1", catalogue_version=catalogue_version,
        sampling="Purposive cross-topic calibration; not representative evaluation or a sealed holdout.",
        records=manifest_rows)
    manifest["manifest_sha256"] = payload_digest(manifest)
    artifacts = {"manifest": manifest, "annotations": annotations, "designs": designs,
                 "independent-input": independent, "validation": validations}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    names = {}
    for kind, artifact in artifacts.items():
        name = f"{kind}-{payload_digest(artifact)}.json"
        path = output / name
        if path.exists() and json.loads(path.read_text(encoding="utf-8")) != artifact:
            raise ValueError("Immutable artifact conflict")
        if not path.exists():
            atomic_json(path, artifact)
        names[kind] = name
    summary = dict(schema_version="0.1", count=len(annotations), structural_errors=0,
        eligible_count=0, human_decisions_written=0, independent_annotations_received=0,
        files=names, manifest_sha256=manifest["manifest_sha256"])
    atomic_json(output / "status.json", summary)
    labels = {"substitution":"تغییر متغیر یا تبدیل معادل", "equation_setup":"تشکیل معادله",
              "direct_substitution":"جایگذاری مستقیم", "symmetry":"تقارن", "case_analysis":"بررسی حالت‌ها",
              "domain_checks":"بررسی دامنه و قیود", "limiting_cases":"رفتار حدی",
              "representation_change":"تغییر بازنمایی", "complement_counting":"شمارش متمم",
              "repeated_unit_counting":"شمارش واحدهای مستقل تکرارشونده"}
    cards = []
    for draft, annotation, item in zip(drafts, annotations, manifest_rows):
        tags = annotation["routes"][0]["annotations"]
        primary = [t for t in tags if t["role"] == "primary"]
        names_fa = "، ".join(labels.get(t["id"].split(".")[-1], t["id"]) for t in primary)
        cards.append(f'<article><h2>سؤال {draft["number"]} · {html.escape(draft["learning_objective"])}</h2>'
            f'<p><b>برچسب اصلی پیشنهادی:</b> {html.escape(names_fa)}</p>'
            f'<p><b>تصمیم کلیدی:</b> {html.escape(draft["essential_decision"])}</p>'
            '<p>آیا این روش، تصمیم مهم حل را توصیف می‌کند؟ برچسبی لازم است که جا افتاده باشد؟</p>'
            '<details><summary>شواهد کوتاه و مرز طراحی</summary>' +
            ''.join(f'<p dir="ltr"><b>{html.escape(t["id"])} ({t["role"]})</b>: {html.escape(t["evidence"])}</p>' for t in tags) +
            f'<p dir="ltr">{html.escape(draft["variation_boundary"])}</p></details>'
            f'<details><summary>تصویر اصل سؤال</summary><img alt="تصویر اصل سؤال {draft["number"]}" src="../review-candidates-v1/{html.escape(item["question_crop"]["file"], quote=True)}"></details></article>')
    page = '<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><title>مرور برچسب‌های استدلال</title><style>' \
        'body{max-width:1000px;margin:40px auto;padding:0 24px;background:#f7f5f1;color:#242322;font:16px/2 Tahoma,sans-serif}' \
        'article{border-top:1px solid #bbb;padding:24px 0}h2{font-size:21px}summary{cursor:pointer;color:#843d34;padding:10px 0}' \
        'img{width:100%;height:auto;background:white}p[dir=ltr]{overflow-wrap:anywhere;font:15px/1.8 system-ui}header{background:#fff;padding:24px}' \
        '</style><header><h1>۱۴ نمونه برای بررسی برچسب‌های استدلال</h1><p>این‌ها پیشنهاد مدل‌اند؛ تأیید شما دربارهٔ متن سؤال به معنای تأیید این برچسب‌ها نیست.</p>' \
        '<p>نیازی به حل دوبارهٔ سؤال‌ها یا ویرایش JSON نیست. مثلاً پاسخ بدهید: «۱ درست؛ ۲ برچسب … بهتر است؛ ۱۵ مطمئن نیستم». نمونهٔ ۱۴تایی برای کالیبراسیون است، نه ارزیابی آماری کل کنکور.</p>' \
        '<p>برای هر مورد فقط تناسب تصمیم کلیدی و برچسب را بررسی کنید. نگاشت کتاب‌ها و درجهٔ سختی هنوز تأیید نشده‌اند. این صفحه گزارش را خودکار ذخیره نمی‌کند؛ پاسخ را در گفتگو بفرستید.</p></header>' + ''.join(cards) + '</html>'
    review_name = f"review-{manifest['manifest_sha256']}.html"
    (output / review_name).write_text(page, encoding="utf-8")
    prompt = f'''Independently annotate only the {len(annotations)} DEVELOPMENT items in {names['manifest']}.
Read docs/QUESTION_REASONING_TAXONOMY.md and backend/app/rag/reasoning_tags.py.
Read only {names['manifest']} and {names['independent-input']} from this pack, then the referenced question crops and current book catalogue.
Do not read draft-input-v1.json, annotations-*.json, designs-*.json, review-*.html or another annotator's results before saving yours.
Never open reserved evaluation exams. Do not alter source files, receipts, catalogue, taxonomy or app code.
Publisher solution regions referenced by the manifest may support annotation; this is NOT a blind-solver experiment.
Use schema/taxonomy0.1 and the exact frozen source/content/catalogue revisions. Knowledge must reference current book-backed catalogue nodes.
Record the actual model identifier and prompt version. Leave empirical difficulty null and human_reviewed false; all records remain held.
Prefer a small useful set of primary/supporting/alternative techniques with short checkable evidence. Do not infer private author thoughts, difficulty from tag counts or student weaknesses.
Keep doubtful techniques, catalogue mappings and endpoint conventions unresolved. Do not copy an answer as a reasoning label.
Write your own immutable annotation file and a handoff under a NEW ignored independent-pass-b subfolder here; never overwrite passA.
Validate with validate_annotation against each frozen question ref. Report structural errors and holds separately.
No paid calls, key probes, workers, deployment, Git push or bulk relabeling. No secrets or private exam text in tracked files.
This prompt does not authorize code changes. Human adjudication is still required after independent outputs are saved.
'''
    (output / "INDEPENDENT_ANNOTATOR_PROMPT.md").write_text(prompt, encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drafts", type=Path)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    data = Path(__file__).resolve().parents[1] / "data"
    root = data / "authoring_work"
    if not args.drafts.resolve().is_relative_to(root.resolve()):
        raise SystemExit("Drafts must remain in the private authoring work directory")
    store = ReviewStore(root / "review-ledger-v1", root / "s1a-mapped", data / "knowledge_graph/catalog.json")
    result = build_pilot(store, json.loads(args.drafts.read_text(encoding="utf-8")),
                         root / "reasoning-pilot-v1", document_id=args.document_id, model=args.model)
    print(json.dumps({k: result[k] for k in ("count", "structural_errors", "eligible_count", "human_decisions_written")}))
