"""Draft annotation sidecars. Pure validation: no DB/config/provider imports or promotion."""
import re
SCHEMA_VERSION = "0.1"
TAXONOMY_VERSION = "0.1"
REGISTRY = ['tech.equation_setup', 'tech.substitution', 'tech.direct_substitution', 'tech.graph_visual', 'tech.relevance_selection', 'tech.case_analysis', 'tech.domain_checks', 'tech.limiting_cases', 'tech.dimensional_analysis', 'tech.approximation', 'tech.optimization', 'tech.symmetry', 'tech.worst_case', 'tech.counterexample', 'tech.small_cases', 'tech.repeated_unit_counting', 'tech.option_elimination', 'tech.invariants_conservation', 'tech.work_backward', 'tech.bounds', 'tech.complement_counting', 'tech.representation_change', 'rep.verbal', 'rep.symbolic', 'rep.graph', 'rep.geometry', 'rep.table', 'rep.schematic', 'rep.chemical', 'obj.determine', 'obj.compare', 'obj.count', 'obj.probability', 'obj.evaluate_claim', 'obj.interpret', 'obj.extremum', 'obj.guarantee', 'check.units', 'check.admissibility', 'check.residual', 'check.independent_route', 'shortcut.options', 'shortcut.estimate', 'mis.sign', 'mis.domain', 'mis.units', 'mis.angle_unit', 'mis.graph_quantity', 'mis.overcount', 'mis.illegal_operation']


def validate_annotation(record, *, catalogue, catalogue_version, question=None):
    """Return structural errors separately from evidence holds; never approve an item.

    catalogue is an explicit list of current book_curriculum node dictionaries.
    catalogue_version must identify the caller's frozen catalogue (prefer SHA256).
    question, when supplied, binds current source revisions and hashes.
    """
    errors, holds = [], []
    def error(path, code): errors.append({"path": path, "code": code})
    def string(value): return isinstance(value,str) and bool(value.strip())
    def obj(value, path, fields):
        if not isinstance(value,dict):
            error(path,"expected_object"); return {}
        for key in fields:
            if key not in value: error(path+"."+key,"required")
        return value
    def array(value,path):
        if not isinstance(value,list): error(path,"expected_array"); return []
        return value
    def enum(value, choices, path):
        if value not in choices: error(path,"unknown_value")
    def evidence(value,path):
        if not string(value) or len(value)>1500: error(path,"short_checkable_evidence_required")
    r=obj(record,"$",["annotation_schema_version","taxonomy_version","annotation_revision","question_ref","question_revision","source","catalogue_version","knowledge_ids","knowledge_evidence","objective","representations","routes","checks_shortcuts","misconceptions","unresolved_labels","annotator","review","intended_difficulty","empirical_difficulty"])
    if r.get("annotation_schema_version")!=SCHEMA_VERSION: error("annotation_schema_version","unsupported_version")
    if r.get("taxonomy_version")!=TAXONOMY_VERSION: error("taxonomy_version","unsupported_version")
    for name in ("annotation_revision","question_revision"):
        if type(r.get(name)) is not int or r[name]<1: error(name,"positive_integer_required")
    if not string(r.get("question_ref")): error("question_ref","required_string")
    source=obj(r.get("source"),"source",["document_id","document_revision","content_sha256","figure_sha256"])
    if type(source.get("document_revision")) is not int or source["document_revision"]<1: error("source.document_revision","positive_integer_required")
    for name in ("document_id","content_sha256"):
        if source.get(name) is None: holds.append("missing_"+name)
        elif not re.fullmatch("[0-9a-f]{64}",str(source[name])): error("source."+name,"invalid_sha256")
    for h in array(source.get("figure_sha256"),"source.figure_sha256"):
        if not isinstance(h,str) or not re.fullmatch("[0-9a-f]{64}",h): error("source.figure_sha256","invalid_sha256")
    if not catalogue_version or r.get("catalogue_version")!=catalogue_version:
        error("catalogue_version","catalogue_version_mismatch")
    nodes={n.get("id"):n for n in catalogue if isinstance(n,dict)}
    knowledge=array(r.get("knowledge_ids"),"knowledge_ids")
    if not knowledge: holds.append("curriculum_unmapped")
    known=[]
    for k in knowledge:
        if not isinstance(k,str) or k not in nodes: error("knowledge_ids","unknown_catalogue_node"); continue
        known.append(k)
        if not nodes[k].get("sources"): error("knowledge_ids","node_not_book_backed")
    refs=array(r.get("knowledge_evidence"),"knowledge_evidence")
    for k in known:
        matching=[e for e in refs if isinstance(e,dict) and e.get("knowledge_id")==k]
        if not matching: error("knowledge_evidence","missing_node_evidence")
        for e in matching:
            evidence(e.get("evidence"),"knowledge_evidence.evidence")
            if e.get("source") not in nodes[k].get("sources",[]): error("knowledge_evidence.source","not_catalogue_source")
    if r.get("objective") is None: holds.append("objective_unresolved")
    else: enum(r.get("objective"),[x for x in REGISTRY if x.startswith("obj.")],"objective")
    for rep in array(r.get("representations"),"representations"):
        rep=obj(rep,"representation",["id","stage"])
        enum(rep.get("id"),[x for x in REGISTRY if x.startswith("rep.")],"representation.id")
        enum(rep.get("stage"),["given","constructed","requested"],"representation.stage")
    route_ids=[]
    routes=array(r.get("routes"),"routes")
    if not routes: holds.append("routes_unresolved")
    for route in routes:
        route=obj(route,"route",["id","role","annotations"])
        rid=route.get("id")
        if not string(rid) or rid in route_ids: error("route.id","missing_or_duplicate_id")
        route_ids.append(rid)
        enum(route.get("role"),["primary","alternative"],"route.role")
        annotations=array(route.get("annotations"),"route.annotations")
        if not annotations: holds.append("empty_route")
        for tag in annotations:
            tag=obj(tag,"tag",["id","role","evidence"])
            enum(tag.get("id"),[x for x in REGISTRY if x.startswith("tech.")],"tag.id")
            enum(tag.get("role"),["primary","supporting","check"],"tag.role")
            evidence(tag.get("evidence"),"tag.evidence")
    for c in array(r.get("checks_shortcuts"),"checks_shortcuts"):
        c=obj(c,"check",["id","route_id","evidence"])
        enum(c.get("id"),[x for x in REGISTRY if x.startswith(("check.","shortcut."))],"check.id")
        if c.get("route_id") not in route_ids: error("check.route_id","unknown_route")
        evidence(c.get("evidence"),"check.evidence")
    for m in array(r.get("misconceptions"),"misconceptions"):
        m=obj(m,"misconception",["id","option_index","evidence"])
        enum(m.get("id"),[x for x in REGISTRY if x.startswith("mis.")],"misconception.id")
        if type(m.get("option_index")) is not int or not 0<=m["option_index"]<4: error("misconception.option_index","invalid_option")
        evidence(m.get("evidence"),"misconception.evidence")
    for u in array(r.get("unresolved_labels"),"unresolved_labels"):
        u=obj(u,"unresolved_label",["axis","reason"])
        enum(u.get("axis"),["knowledge","technique","representation","objective","misconception","difficulty"],"unresolved_label.axis")
        evidence(u.get("reason"),"unresolved_label.reason")
        holds.append("unresolved_labels")
    a=obj(r.get("annotator"),"annotator",["kind","identifier","model","prompt_version"])
    enum(a.get("kind"),["human","model"],"annotator.kind")
    if not string(a.get("identifier")): error("annotator.identifier","required_string")
    if a.get("kind")=="model" and (not string(a.get("model")) or not string(a.get("prompt_version"))): error("annotator","model_and_prompt_required")
    review=obj(r.get("review"),"review",["annotation_state","source_state","scientific_state","human_reviewed","issues","eligibility"])
    enum(review.get("annotation_state"),["candidate","unresolved"],"review.annotation_state")
    enum(review.get("source_state"),["candidate","synthetic","unresolved"],"review.source_state")
    enum(review.get("scientific_state"),["not_checked","unresolved"],"review.scientific_state")
    if review.get("human_reviewed") is not False or review.get("eligibility")!="held": error("review","draft_cannot_promote")
    for issue in array(review.get("issues"),"review.issues"):
        if not string(issue): error("review.issues","required_string")
    d=obj(r.get("intended_difficulty"),"intended_difficulty",["level","rationale"])
    if d.get("level") is not None:
        enum(d.get("level"),["easy","konkur","hard","extreme"],"intended_difficulty.level")
        evidence(d.get("rationale"),"intended_difficulty.rationale")
    if r.get("empirical_difficulty") is not None: error("empirical_difficulty","separate_empirical_contract_required")
    if question is None: holds.append("current_question_not_bound")
    else:
        for field in ("question_ref","question_revision","source"):
            if r.get(field)!=question.get(field): error(field,"stale_question_evidence")
    return {"valid":not errors,"errors":errors,"holds":sorted(set(holds+["draft_vocabulary","not_approval"])),"eligible":False}
