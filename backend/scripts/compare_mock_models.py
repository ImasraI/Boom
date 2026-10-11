"""Resumable, private 20-question/model comparison. Never inserts bank stock.

Run from backend: python scripts/compare_mock_models.py --run quality-20
The same saved OCR excerpts and slots are used by both models. All parseable
drafts are retained for human review, including failures; there is no selection
of only passing examples. Provider quota state is honored across restarts.
"""
import argparse
import json
import os
import random
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings
from app.rag import exam_blueprint as blueprint, mock_generation as mg, provider_quota as quota, pool_usage
from app.rag.llm import FallbackLLMClient, get_llm_client

LOCK = threading.RLock()


def prepare_slots():
    # Scaled ریاضی‌فیزیک blueprint: seven math, seven physics, six chemistry.
    targets = [("ریاضی", "geometry", 2), ("ریاضی", "statistics", 1),
               ("ریاضی", "discrete", 1), ("ریاضی", "calculus", 3),
               ("فیزیک", "", 7), ("شیمی", "", 6)]
    slots = []
    for subject, branch, count in targets:
        row = {"name": subject, "branch": branch, "major": "riazi"}
        readable = []
        for node in blueprint.lessons_for(row, "دوازدهم"):
            source = blueprint.book_excerpt(node, limit=5500)
            if source:
                readable.append({"node": node, "source": source})
        if len(readable) < count:
            raise RuntimeError(f"Insufficient OCR-backed coverage for {subject}/{branch}")
        random.Random(20261011 + len(slots)).shuffle(readable)
        for item in readable[:count]:
            slots.append({"subject": subject, "branch": branch, **item})
    return slots


def fleet(provider, settings):
    if provider == "groq":
        keys = quota.groq_keys(settings, pool=True)
        model = settings.POOL_LLM_MODEL_NAME
    else:
        # POOL_LLM_API_KEY belongs to Groq here; never send it to Google.
        keys = [k.strip() for k in settings.POOL_GEMINI_API_KEYS.split(",") if k.strip()]
        if settings.POOL_LLM_PROVIDER == "gemini" and settings.POOL_LLM_API_KEY:
            keys.insert(0, settings.POOL_LLM_API_KEY)
        # Evaluation is an explicit request to exercise this model, so its
        # configured reviewer fleet is eligible too. Never use unrelated chat,
        # vision, embedding credentials or substitute a different provider.
        if getattr(settings, "POOL_VERIFY_LLM_PROVIDER", "") == "gemini":
            keys.extend(quota.pool_gemini_keys(settings, verification=True))
        model = settings.POOL_VERIFY_LLM_MODEL_NAME or settings.GEMINI_MODEL_NAME
    clients = [get_llm_client(provider=provider, api_key=k, model=model)
               for k in dict.fromkeys(keys)]
    if not clients:
        raise RuntimeError(f"No dedicated generation credentials for {provider}")
    for client in clients:
        client.reasoning_effort = "high"
        client.json_mode = True
        client.minimum_completion_tokens = 8192
        client.temperature = 0.2
    # Same-provider failover only: samples must actually come from this model.
    return FallbackLLMClient(clients, [provider] * len(clients), switch_on_rate_limit=True), model


def available(client):
    for child in client._clients:
        identity = child._quota_identity
        if not quota.blocked_access(identity) and not quota.blocked_quota(identity):
            return True
    return False


def save(path, state):
    with LOCK:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(path)


def draft_prompt(slot, difficulty):
    node, source = slot["node"], slot["source"]
    row = {"name": slot["subject"], "questions": 1, "minutes": 2}
    context = (f"[source_id: {node['id']} | کتاب: {source['book']} | صفحه: {source['page']} | مبحث: {node['title']}]\n"
               + source["quote"])
    return mg.build_booklet_prompt([row], [node["title"]], difficulty, context, grade="دوازدهم") + (
        f"\nفقط یک سوال از همین مبحث بساز؛ source_id باید {node['id']} باشد.")


def run_model(provider, state, path, once):
    settings = get_settings()
    client, model = fleet(provider, settings)
    with LOCK:
        progress = state["models"].setdefault(provider, {"model": model, "questions": [], "attempts": [], "status": "running"})
        if progress["model"] != model:
            raise RuntimeError("The saved comparison model changed; use a new run")
        save(path, state)
    try:
        while len(progress["questions"]) < len(state["slots"]):
            if not available(client):
                with LOCK:
                    progress["status"] = "waiting_for_quota_or_access"
                    save(path, state)
                if once:
                    return
                time.sleep(60)
                continue
            index = len(progress["questions"])
            slot = state["slots"][index]
            with LOCK:
                progress["status"] = "generating"
                progress["current_slot"] = index + 1
                save(path, state)
            # Fixed request budget/prompt and reasoning for both providers.
            with pool_usage.stage("model_evaluation"):
                raw = client.generate([{"role": "user", "content": draft_prompt(slot, state["difficulty"])}],
                                      max_tokens=8192, timeout=300)
            rows = mg.parse_booklet(raw)
            with LOCK:
                attempt = {"slot": index + 1, "time": time.time(),
                    "parseable": bool(rows), "error_code": getattr(client, "last_error_code", "") if not raw else ""}
                if raw and not rows:
                    diagnostic = path.parent / f"{provider}-slot-{index+1}-attempt-{len(progress['attempts'])+1}.txt"
                    diagnostic.write_text(raw, encoding="utf-8")
                    os.chmod(diagnostic, 0o600)
                    attempt["diagnostic"] = diagnostic.name
                progress["attempts"].append(attempt)
                if rows:
                    node, source = slot["node"], slot["source"]
                    progress["questions"].append({**rows[0], "_id": index + 1,
                        "subject": slot["subject"], "topic": node["title"],
                        "book": source["book"], "page": source["page"],
                        "source_quote": source["quote"], "curriculum_id": node["id"],
                        "branch": slot["branch"], "grounding_status": "book_ocr",
                        "verification_status": "human_review_pending"})
                save(path, state)
            if rows:
                print(f"{provider}: {len(progress['questions'])}/20 saved", flush=True)
            elif not raw:
                if once:
                    return
                time.sleep(60)  # Clients remember quota; no repeated terminal probes.
            else:
                # Format problems must be visible, not infinite retries or biased selection.
                failures = sum(a["slot"] == index + 1 for a in progress["attempts"])
                if failures >= 3:
                    progress["status"] = "needs_attention_format"
                    save(path, state)
                    return
        progress["status"] = "complete"
        save(path, state)
    finally:
        for child in client._clients:
            child.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="quality-20")
    parser.add_argument("--once", action="store_true", help="Exit instead of waiting for exhausted provider quota")
    args = parser.parse_args()
    if not args.run or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.run):
        parser.error("Use a simple run name")
    folder = Path("data/model_evaluations") / args.run
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "state.json"
    # Copy known blocks once, then keep this process's quota ledger separate.
    # A long-lived evaluation must not overwrite the API process's newer blocks.
    settings = get_settings()
    original_quota = Path(settings.POOL_QUOTA_STATE_PATH) if settings.POOL_QUOTA_STATE_PATH else None
    private_quota = folder / "provider_quota.json"
    if original_quota and original_quota.is_file() and not private_quota.exists():
        shutil.copy2(original_quota, private_quota)
        os.chmod(private_quota, 0o600)
    settings.POOL_QUOTA_STATE_PATH = str(private_quota)
    # O_EXCL prevents duplicate workers; dead PIDs permit a safe checkpoint resume.
    lockfile = folder / "worker.pid"
    if lockfile.exists():
        pid = int(lockfile.read_text())
        if os.name == "nt":
            raise RuntimeError("Remove the worker.pid only after verifying its previous process has stopped")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            lockfile.unlink()
        else:
            raise RuntimeError("Comparison already running")
    fd = os.open(lockfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(str(os.getpid()))
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "version": 1, "reasoning_effort": "high", "difficulty": "hard", "slots": prepare_slots(), "models": {}}
        save(path, state)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run_model, provider, state, path, args.once) for provider in ("groq", "gemini")]
            for future in futures:
                future.result()
        print(json.dumps({k: {"model": v["model"], "saved": len(v["questions"]), "status": v["status"]}
                          for k, v in state["models"].items()}), flush=True)
    finally:
        lockfile.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
