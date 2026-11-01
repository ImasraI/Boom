"""Build the local roadmap from prompt documents and aggregate saved evidence.

Run with: backend/.venv/Scripts/python.exe docs/production-work-pack/build_roadmap.py
No provider requests, database imports, approvals, or production changes.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def section(file, code):
    text = (HERE / file).read_text(encoding="utf-8-sig")
    for part in re.split(r"(?m)^## ", text)[1:]:
        heading, _, body = part.partition("\n")
        if re.search(rf"\b{re.escape(code)}\b", heading):
            blocks = re.findall(r"```text\s*\n(.*?)```", body, flags=re.S)
            return "\n\n".join(blocks).strip() if blocks else body.strip()
    raise ValueError(f"Missing prompt {file}:{code}")


BASE = """Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.
Read AGENTS.md, docs/production-work-pack/README.md and
docs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.
Work locally with existing free resources; preserve other agents' files,
originals, completed checkpoints, frozen snapshots and credential quota state.
Keep secrets and private corpus data out of prompts/reports/Git. Do not infer
human review or scientific correctness from model agreement. This task does
not authorize deployment. Deliver changed files, actual checks, evidence,
remaining limitations and the next handoff. Complete only this step now.
"""


def run():
    tasks = []

    def add(id, title, owner, phase, deps, summary, outputs, checks, prompt=None,
            source=None, scope=None, priority="P0", optional=False):
        if id == "SR" or phase >= 4:
            phase += 1
        body = prompt or section(*source)
        if scope:
            body = ("SCOPE FOR THIS ROADMAP STEP (takes precedence over the broader stage below):\n"
                    + scope + "\n\nBROADER STAGE REFERENCE:\n" + body)
        tasks.append(dict(id=id, title=title, owner=owner, phase=phase,
                          priority=priority, deps=deps, summary=summary,
                          deliverables=outputs, acceptance=checks,
                          prompt=BASE + "\nTASK " + id + ": " + title + "\n\n" + body,
                          source=(source[0] + " / " + source[1]) if source else "Roadmap-specific task",
                          optional=optional))

    add("S0", "Establish contracts and file ownership", "Sol", 0, [],
        "Give the three workers one compatible specification and a shared baseline.",
        ["CONTRACTS.md with synthetic records", "TASK_BOARD.md with owners and writable paths"],
        ["Existing modified and untracked code accounted for", "No overlapping writes or assumed approvals"],
        source=("SOL_PROMPTS.md", "S0"))
    add("F0", "Inspect gaps and prepare the first helper", "Freebuff", 0, [],
        "Inspect the existing system and report specific gaps without changing core code.",
        ["FREEBUFF_HANDOFF.md", "Small synthetic failure scenarios"],
        ["Claims distinguish observation from old documentation", "Next helper files proposed to Sol"],
        source=("FREEBUFF_PROMPTS.md", "F0"))
    add("H0", "Identify one exam and its answer booklet", "You", 0, [],
        "Start with one complete, traceable exam; classify remaining source files afterward.",
        ["Source pairing record with year/session/major", "Uncertain matches listed"],
        ["Printed numbering and distributed samples agree", "Unknown identities remain unresolved"],
        source=("HUMAN_TASKS.md", "H0"))

    add("S1a", "Create source packets and pairing contracts", "Sol", 1, ["S0", "H0", "F0"],
        "Make the chosen question/answer pair inspectable and handle ambiguous numbering.",
        ["One source-bound development packet", "Versioned pairing and correction rules"],
        ["Question IDs use source identity and printed numbers", "Ambiguous joins are held"],
        source=("SOL_PROMPTS.md", "S1"), scope="Implement source records and question/answer pairing only. Use H0's chosen exam. Prepare review packets and split candidates; final curriculum/split approval and retrieval integration happen in H1/S1b.")
    add("F1", "Build the offline source validator", "Freebuff", 1, ["S0", "F0"],
        "Validate metadata, image references and review hashes without modifying the corpus.",
        ["Read-only validator CLI", "Synthetic pairing/hash/path tests"],
        ["No provider requests or automatic approvals", "Valid and malformed fixtures give expected findings"],
        source=("FREEBUFF_PROMPTS.md", "F1"))
    add("ST", "Define versioned reasoning-tag records", "Sol", 1, ["S0"],
        "Turn the new taxonomy draft into a small, testable annotation contract.",
        ["Tag registry and annotation schema", "Synthetic annotated example and validator"],
        ["Knowledge, technique, representation, objective and misconception are separate", "Multiple routes and tag roles supported", "Version/aliases/proposed changes preserve old records"],
        prompt="Implement the contract from docs/QUESTION_REASONING_TAXONOMY.md. Keep it a draft vocabulary pending human calibration. Include source/content revision, annotator identity/model, taxonomy version, primary/supporting/alternative/checking roles, short checkable evidence, unresolved labels and review state. Knowledge IDs must reference current book-backed catalogue nodes. Never treat technique presence as difficulty or a student's weakness. Provide a JSON schema or equivalent validator and synthetic fixtures for Freebuff. Preserve existing compatible question-design records; no bulk relabeling or promotion.")
    add("H1", "Confirm curriculum and seal evaluation sources", "You", 2, ["S1a", "F1"],
        "Approve source identity and scope, then keep evaluation papers separate before tuning.",
        ["Current book/Maze scope revision", "Development and final-holdout source manifest"],
        ["Duplicate originals in compilations are handled", "Final holdout remains outside authoring examples"],
        source=("HUMAN_TASKS.md", "H1"))
    add("F2", "Build the review interface", "Freebuff", 2, ["S0", "ST"],
        "Make original images, transcriptions, tags and distinct review states easy to compare.",
        ["Standalone view and synthetic fixtures", "Mobile/RTL/keyboard screenshots and checks"],
        ["Missing images and stale approvals are visible", "No raw HTML injection or blanket approval"],
        source=("FREEBUFF_PROMPTS.md", "F2"))
    add("S1b", "Wire source-specific retrieval", "Sol", 3, ["H1", "S1a", "F1"],
        "Route generation to eligible exam designs, facts to textbooks, and planning to Maze/test books.",
        ["Purpose-filtered retrieval", "Holdout/source-role leakage tests"],
        ["Unknown/unreviewed sources cannot enter via fallback", "Old syllabus topics cannot expand current scope"],
        source=("SOL_PROMPTS.md", "S1"), scope="Finish review of F1, curriculum/split enforcement and role-specific retrieval. Source pairing already exists from S1a; extend it only for documented remaining defects.")
    add("SR", "Integrate review records and safe decisions", "Sol", 3, ["S1b", "F2", "ST"],
        "Wire the interface to hash-bound records so reviewers can work on real development packets.",
        ["Integrated local review workflow", "Version-bound decision storage and access tests"],
        ["Decisions become stale after relevant edits", "Human/scientific/source states stay independent"],
        prompt="Review and integrate Freebuff F2 using the S0/ST contracts. Wire safe original-image lookups and version-bound decision writes. Keep access local or admin-protected as appropriate, preserve existing control-token rules, and never expose credentials or arbitrary paths. Supply separate blind-solve and answer-bearing packets. Test human review attribution, stale hashes, unauthorized writes and malformed records. Make the H2 reviewers able to inspect and record decisions without editing raw JSON manually.")
    add("H2", "Review the first source-question sample", "You", 4, ["SR", "H1"],
        "Check source fidelity and scientific validity before treating records as authoring evidence.",
        ["Up to 50 reviewed development question records", "Corrections and unresolved items"],
        ["Blind solving precedes answer revelation", "Critical symbols/options/figures checked against originals"],
        source=("HUMAN_TASKS.md", "H2"))

    add("HA", "Collect independent model annotations", "You", 5, ["H2", "ST"],
        "Give the same reviewed development packet separately to Claude and GPT Astra, if accessible.",
        ["Annotation A and B, separately attributed", "Model labels, source versions and explicit uncertainty"],
        ["Neither annotator sees the other's answers", "No holdout questions or credentials in the packet", "No new paid service required"],
        prompt="Use the independent annotation prompt in docs/QUESTION_REASONING_TAXONOMY.md with the same bounded development packet. Run it separately in Claude and GPT Astra using access you already have. Each must inspect the question, figures and checked solution, use stable tag IDs, justify roles with short evidence, and preserve uncertainty. Do not show one result to the other. If a model is unavailable, record that and use another available independent annotator or a human; do not buy access. Return both outputs with exact model/source/taxonomy versions for F4. These are candidate labels, not human-reviewed facts.")
    add("F4", "Compare labels and draft taxonomy changes", "Freebuff", 6, ["HA"],
        "Compare independent annotations, retaining legitimate alternative solution routes.",
        ["Disagreement table with evidence", "Proposed additions/merges/deprecations"],
        ["Agreements are also sampled for review", "No unilateral registry changes or automatic approval"],
        source=("FREEBUFF_PROMPTS.md", "F4"), scope="Compare the two HA annotation outputs using QUESTION_REASONING_TAXONOMY.md. Group differences into missing evidence, label ambiguity, real mathematical disagreement, and valid alternative routes. Propose registry changes with examples and migration impact. Do not generate new questions in this step or adjudicate human approval. Mark your conclusions as candidates.")
    add("HT", "Adjudicate labels and approve taxonomy v1", "You", 7, ["F4"],
        "Review disputed labels plus a sample of agreements with a subject expert.",
        ["Reviewed annotation sample", "Accepted/rejected taxonomy proposals"],
        ["Definitions include inclusion/exclusion examples", "Alternative solutions are preserved", "Unknowns are held rather than forced into tags"],
        prompt="Review F4's comparison using the original questions and checked solutions. Resolve the meaning of the label, not which model won. Sample agreements for shared mistakes. Approve, reject or hold each proposed addition/merge/deprecation and record its reason. Confirm stable IDs and aliases with Sol before changing the registry. Return reviewed source-bound labels and a taxonomy version suitable for a small authoring pilot. Do not label more data until the main definition disagreements are resolved.")
    add("F3", "Prepare adversarial and recovery tests", "Freebuff", 5, ["ST", "H2"],
        "Test the known failure classes while annotation and human review run independently.",
        ["Synthetic mathematical defect fixtures", "Provider/network/restart test cases"],
        ["Fixture mathematics independently checked", "No real VPN disruption or quota resets"],
        source=("FREEBUFF_PROMPTS.md", "F3"))

    add("S2", "Build checked question constructors", "Sol", 8, ["HT", "S1b", "H2"],
        "Construct valid mathematical specifications before writing Persian questions and options.",
        ["Small set of supported design families", "Parameter/solution/figure checks", "Unpublished generated examples"],
        ["Contradictory and underdetermined cases held", "Practice variants distinguished from new reasoning designs"],
        source=("SOL_PROMPTS.md", "S2"))
    add("S3", "Enforce verification and resumable bank lifecycle", "Sol", 9, ["S2", "F3"],
        "Make eligibility evidence-based and preserve every good question through worker failures.",
        ["Independent solve/audit and version invalidation", "Durable retry/claim behavior", "Question-level quarantine"],
        ["Correctness and difficulty failures are separate", "Missing verification cannot publish", "Concurrent claims and restarts tested"],
        source=("SOL_PROMPTS.md", "S3"))
    add("S4a", "Prepare blinded development comparison", "Sol", 10, ["S3"],
        "Compare topic-only, flat-tag and structured-design generation on equal development tasks.",
        ["Anonymous review packets", "Predeclared rubric and measured generation records"],
        ["Same task mix and bounded budgets", "Generated/source identity hidden during initial review"],
        source=("SOL_PROMPTS.md", "S4"), scope="Prepare the development comparison and representative retrieval evaluation only. Include topic-only versus flat technique tags versus reasoning dependencies. Use development examples and do not open final holdouts. Give H3 anonymous packets with answer-free solving first. Product integration and final holdout evaluation happen later.")
    add("H3", "Judge quality and return specific corrections", "You", 11, ["S4a"],
        "Use subject experts to assess correctness, useful difficulty, originality and exam likeness.",
        ["Blinded review results and disagreements", "Accepted question versions and corrections"],
        ["Wrong answers cannot be hidden by average ratings", "Reviewed corrections feed development only"],
        source=("HUMAN_TASKS.md", "H3"))
    add("S4b", "Fix review findings and integrate student workflows", "Sol", 12, ["H3", "S3"],
        "Close defects, then connect the qualified bank to practice, full mocks, Colosseum and planning.",
        ["Reviewed corrections and rerun evidence", "Integrated isolated admin/student QA harness", "Version/exposure and attempt records"],
        ["Requested scope and shortages are honestly displayed", "Answers hidden until allowed", "Experimental items excluded from scored matches"],
        source=("SOL_PROMPTS.md", "S4"), scope="Resolve H3's blocking findings with regression checks, obtaining renewed review for changed items. Then finish product integration and supply Freebuff's isolated admin/non-admin test harness. Store first-attempt, exposure and assignment data. Keep tag hints hidden in assessments and optional in guided practice. Final holdout evaluation is S5a; real student pilot follows F5.")
    add("F5", "Run independent end-to-end QA", "Freebuff", 13, ["S4b"],
        "Verify the integrated candidate using isolated accounts, realistic figures and failures.",
        ["Reproducible QA report", "Safe stop/resume runbook", "Mobile/RTL evidence"],
        ["Auth/account isolation and admin checks pass", "No real student data modified", "Harness gaps distinguished from app bugs"],
        source=("FREEBUFF_PROMPTS.md", "F5"))
    add("SQ", "Resolve QA blockers and prepare pilot build", "Sol", 14, ["F5"],
        "Integrate fixes and verify the exact build the pilot will use.",
        ["QA defect dispositions", "Pilot revision and approved item manifest"],
        ["Blocking QA issues fixed and retested", "Changed questions have renewed evidence"],
        prompt="Resolve F5 findings and retest the affected workflows. Do not mark defects fixed from an explanation alone. Produce the exact local pilot revision and eligible question/version manifest, participant instructions and defect-reporting path. Keep experimental pilot outcomes separate from public ranking. Ask the human to run H4 only when this candidate passes its required checks; missing resources must be explicit.")
    add("H4", "Run a controlled student pilot", "You", 15, ["SQ", "H3"],
        "Try the cleared questions with approximately 20 voluntary students and record actual problems.",
        ["Pseudonymous first-attempt/exposure feedback", "Defects, timings and uncertainty"],
        ["No precise psychometric claims from a small pilot", "Experimental results do not change public ranked scores"],
        source=("HUMAN_TASKS.md", "H4"))
    add("S5a", "Close pilot issues and freeze a release candidate", "Sol", 16, ["H4"],
        "Evaluate the frozen candidate and package only eligible resources with a rollback plan.",
        ["Pilot fixes and final held-out evaluation", "Release manifest and backup/restore plan", "Capacity plan and known limits"],
        ["No unresolved critical item defects", "Existing release gates and claimed subject coverage pass", "No holdout tuning disguised as final evaluation"],
        source=("SOL_PROMPTS.md", "S5"), scope="LOCAL PREPARATION ONLY. Resolve pilot issues with renewed review where needed, freeze the candidate, run final held-out evaluation once under the declared protocol, and prepare the release package. If final findings drive changes, retire affected cases to development and obtain replacement holdouts. Prepare target capacity/rollback checks; do not access VM, push, upload or activate. H5 reviews this concrete candidate.")
    add("H5", "Choose the exact release and authorize rollout", "You", 17, ["S5a"],
        "Review the release evidence and explicitly decide whether this candidate may be deployed.",
        ["Decision naming code revision and corpus snapshot", "Known limits and rollback owner"],
        ["Approval refers to this candidate, not a general plan", "Required scientific and operational gates satisfied"],
        source=("HUMAN_TASKS.md", "H5"))
    add("S5b", "Deploy the approved revision safely", "Sol", 18, ["H5"],
        "Perform the actual deployment only after explicit authorization for the exact candidate.",
        ["Backups and verified shared-data import", "Backend/frontend deployment revision", "Authenticated checks and rollback evidence"],
        ["Accounts/private uploads/JWT secret preserved", "Public frontend and API match candidate", "Health200 alone is not sufficient"],
        source=("SOL_PROMPTS.md", "S5"), scope="DEPLOYMENT STAGE: proceed only after the user's explicit H5 authorization naming the candidate. A roadmap checkbox alone is not deployment permission. Follow S5's backup, fast-forward, private-data preservation, compatible import and public verification steps. On failed verification, roll back or stop with a concrete recovery record.")
    add("F6", "Verify the published user experience", "Freebuff", 19, ["S5b"],
        "Check the approved public rollout against the release acceptance list.",
        ["Public release smoke-test report", "Any reproducible regression and ownership"],
        ["Only approved test accounts/actions used", "Actual revision checked", "No unauthorized OTP messages or destructive tests"],
        prompt="After the explicitly authorized deployment, verify the public frontend revision and approved test-account workflows from F5. Use only the accounts/actions permitted in the rollout instructions. Check mobile display, figures, practice pool delivery, Maze scope disclosure and error handling. No destructive tests, production data cleanup or unapproved SMS. Report evidence of the deployed version and immediate regressions to Sol; do not fix production independently.")
    add("H6", "Accept rollout and prioritize the next learning cycle", "You", 20, ["F6"],
        "Confirm the release outcome and choose the next supported topics and review batches.",
        ["Release acceptance or rollback decision", "Prioritized topic/quality backlog"],
        ["Known limits communicated", "Reported defects routed to question-version review"],
        prompt="Review Sol's deployment evidence and Freebuff's public checks. Confirm whether the rollout is accepted or needs rollback/correction. Choose the next source topics/design families based on missing coverage and student feedback. Retain per-version defect history, privacy and reviewer evidence. Any recurring monitoring should be explicitly commissioned; this roadmap does not start an automation.")
    add("S6", "Improve skill diagnosis with real student evidence", "Sol", 21, ["H6"],
        "Use repeated, exposure-aware observations to improve personalized practice selection.",
        ["Conservative skill estimates and uncertainty", "Transfer-practice comparison"],
        ["One wrong answer does not fail every tag", "Alternative correct routes respected", "Accuracy/retry/assignment effects distinguished"],
        priority="P1", optional=True,
        prompt="Use the new taxonomy and pilot/release attempt records to improve practice selection. Start with transparent aggregation and uncertainty rather than precise ability claims. Distinguish first attempts, hints, repeats, missing answers and different assignment policies. Validate suspected misconceptions with targeted follow-up tasks. Compare later performance on unfamiliar questions, not just repeated items. Preserve ranked fairness and obtain sufficient human/student evidence before advancing to calibrated models.")
    add("S7", "Evaluate whether fine-tuning adds value", "Sol", 21, ["H6"],
        "Consider training only after a reviewed design dataset and a strong retrieval baseline exist.",
        ["Reviewed dataset feasibility report", "Held-out comparison plan and free-resource feasibility"],
        ["No raw/unreviewed OCR used as trusted training targets", "No billing or compute purchase", "No training without adequate resources and explicit scope"],
        priority="P2", optional=True,
        prompt="Assess whether enough reviewed curriculum/design-to-question examples and expert corrections exist for fine-tuning. Compare with the strongest tested retrieval/prompting baseline first. Preserve whole-paper and family holdouts. Propose annotation, generation and correction tasks with versioned evidence. Check actual accessible model/license/hardware constraints and the user's free-only budget. Produce a go/no-go recommendation; this step does not enable billing, rent compute, upload private corpora or start training.")

    ids = {t["id"] for t in tasks}
    if len(ids) != len(tasks):
        raise ValueError("Duplicate task IDs")
    visited = set()
    active = set()

    def visit(id):
        if id in active:
            raise ValueError("Dependency cycle: " + id)
        if id in visited:
            return
        active.add(id)
        task = next(t for t in tasks if t["id"] == id)
        for dep in task["deps"]:
            if dep not in ids:
                raise ValueError("Unknown prerequisite " + dep)
            parent = next(t for t in tasks if t["id"] == dep)
            if parent["phase"] >= task["phase"]:
                raise ValueError("Phase is not topological: " + id)
            visit(dep)
        active.remove(id)
        visited.add(id)
    for id in ids:
        visit(id)
    for task in tasks:
        assert task["prompt"].strip() and task["deliverables"] and task["acceptance"]

    def saved(name):
        path = ROOT / "backend/data/exam_staging/batch-5000-v1" / name
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}

    embeddings = saved("embedding-status.json")
    retrieval = saved("retrieval-pilot.json")
    release = saved("release-readiness.json")
    completed = embeddings.get("phase") == "complete"
    phases = ["Start here", "Source and tag contracts", "Scope and reviewer interface",
              "Integrate trusted inputs", "Integrate review decisions", "Review original questions", "Independent annotation and tests",
              "Compare model labels", "Approve vocabulary", "Construct new questions",
              "Verify and preserve", "Prepare quality comparison", "Expert judgment",
              "Integrate student experience", "Independent QA", "Pilot candidate",
              "Student pilot", "Freeze and evaluate", "Release decision", "Deploy",
              "Public checks", "Accept and iterate", "Later improvements"]
    data = dict(version="karzar-roadmap-v1", checkedAt=datetime.now(timezone.utc).isoformat(),
                stage="Source qualification and reasoning-label design",
                notice="Saved-evidence snapshot, not a live worker monitor. Future task completion is manually reported; this page never runs agents, approves questions or deploys code.",
                milestones=[
                    dict(title="Frozen candidate embeddings", state="complete" if completed else "unknown",
                         detail=f"{embeddings.get('stored_chunks', 'Unknown')} / {embeddings.get('total_chunks', 'unknown')} stored vectors; {embeddings.get('pages', 'unknown')} question pages. Candidate OCR, not a reviewed bank.",
                         evidence="backend/data/exam_staging/batch-5000-v1/embedding-status.json"),
                    dict(title="Retrieval pilot", state="limited" if retrieval else "unknown",
                         detail=f"{retrieval.get('metrics', {}).get('dense', {}).get('queries', 'Unknown')} queries; {retrieval.get('gold_sources', 'unknown')} source questions. Not representative enough for release.",
                         evidence="backend/data/exam_staging/batch-5000-v1/retrieval-pilot.json"),
                    dict(title="Release readiness", state="blocked" if release.get("ready") is False else "unknown",
                         detail="Saved release gate remains blocked. Required source, curriculum, science, difficulty and novelty reviews are outstanding.",
                         evidence="backend/data/exam_staging/batch-5000-v1/release-readiness.json"),
                    dict(title="Prompt pack and taxonomy", state="draft",
                         detail="Instructions are available. Contracts, source pairing and human review have not been evidenced as complete by this roadmap.",
                         evidence="docs/production-work-pack and docs/QUESTION_REASONING_TAXONOMY.md")],
                phases=[dict(id=i, title=title) for i, title in enumerate(phases)], tasks=tasks,
                links=dict(taxonomy="../QUESTION_REASONING_TAXONOMY.md", guide="README.md"))
    serialized = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    (HERE / "roadmap-data.js").write_text("window.ROADMAP_DATA = " + serialized + ";\n", encoding="utf-8")
    print(f"Built {len(tasks)} tasks / {sum(len(t['deps']) for t in tasks)} dependencies. DAG and prompt references validated.")


if __name__ == "__main__":
    run()
