"""Run from backend/: python scripts/migrate_gemini_embeddings.py --activate

The synchronous embedding endpoint uses the project's normal/free-tier
quota. This does NOT use Google's paid asynchronous Batch API. A failed run
exits safely; rerunning skips completed, unchanged chunks.
"""
import argparse
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.rag.embedding_migration import activate_gemini, migrate_collection, migrate_collection_parallel, validate_migration
from app.rag.gemini_embeddings import EmbeddingError, GeminiEmbeddingModel, EmbeddingRateLimiter
from app.rag.embedding_progress import MigrationLock, collection_counts, write_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", help="Existing Chroma directory; defaults to CHROMA_DIR")
    parser.add_argument("--model", default="gemini-embedding-2")
    parser.add_argument("--dimensions", type=int, default=768)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--rpm", type=int)
    parser.add_argument("--auto-rate", action="store_true", help="Start at --rpm (default 100) and adapt to actual quota responses")
    parser.add_argument("--wait-for-quota", action="store_true", help="Keep the worker alive and resume after the provider's explicit daily-quota retry time")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--activate", action="store_true", help="Switch backend/.env only after the complete rebuild")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=1)
    parser.add_argument("--worker-env-dir", help="Local OCR worker directory (never commit its keys)")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if Path.cwd() != root:
        parser.error("Run this command from backend/ so it reads backend/.env.")
    settings = get_settings()
    source_dir = Path(args.source_dir or settings.CHROMA_DIR).resolve()
    if not (source_dir / "chroma.sqlite3").is_file() and not args.probe_only:
        parser.error("Existing source Chroma database not found.")
    if args.activate and source_dir != Path(settings.CHROMA_DIR).resolve():
        parser.error("Activation requires the configured CHROMA_DIR as the destination.")
    state_dir = root / "data" / "embedding_migrations"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = MigrationLock(state_dir / "gemini.lock")
    try:
        lock.acquire()
    except BlockingIOError:
        print("Another embedding migration is already running; no duplicate job started.", flush=True)
        return 2
    state_path = state_dir / "gemini-status.json"
    state = {"status": "starting", "model": args.model, "dimensions": args.dimensions,
             "started_at": datetime.now(timezone.utc).isoformat(), "collections": [], "worker_pid": os.getpid()}
    rpm = args.rpm or (100 if args.auto_rate else min(5, settings.EMBEDDING_REQUESTS_PER_MINUTE))
    state.update(requests_per_minute_ceiling=rpm, batch_size=args.batch_size or min(8, settings.EMBEDDING_BATCH_SIZE), auto_rate=args.auto_rate)
    record_lock = threading.RLock()

    def record(values):
        with record_lock:
            state.update(values)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            write_status(state_path, state)
            print(json.dumps(values, ensure_ascii=False), flush=True)

    def worker_activity(worker, event):
        with record_lock:
            workers = dict(state.get("workers", {}))
            workers[str(worker)] = {**event, "updated_at": datetime.now(timezone.utc).isoformat()}
            if event.get("quota_limits"):
                state["provider_limits"] = event["quota_limits"]
                state["provider_retry_seconds"] = event.get("wait_seconds", 0)
            record({"workers": workers, "phase": "parallel_indexing"})

    def worker_report(event):
        with record_lock:
            reports = list(state.get("credential_checks", []))
            reports.append(event)
            record({"credential_checks": reports})

    model = None
    models = []
    try:
        counts = collection_counts(source_dir) if not args.probe_only else {}
        source_names = [settings.CHROMA_COLLECTION, settings.CHROMA_QA_COLLECTION]
        state["overall_total"] = sum(counts.get(name, 0) for name in source_names)
        from app.rag.gemini_embeddings import gemini_collection_name
        state["overall_completed"] = sum(counts.get(gemini_collection_name(name, args.model, args.dimensions), 0)
                                         for name in source_names)
        record({"status": "starting", "phase": "checking_gemini_access"})
        (state_dir / "gemini-process.pid").write_text(str(os.getpid()), encoding="utf-8")
        if args.workers > 1:
            from app.rag.embedding_workers import build_worker_models
            models = build_worker_models(args.worker_env_dir or root.parent / "ocr-workers", args.workers,
                model_name=args.model, dimensions=args.dimensions,
                batch_size=args.batch_size or min(8, settings.EMBEDDING_BATCH_SIZE),
                rpm=rpm, auto_rate=args.auto_rate,
                base_url=settings.EMBEDDING_GEMINI_BASE_URL, activity=worker_activity, report=worker_report)
            model = models[0]
        else:
            model = GeminiEmbeddingModel(
            api_key=(settings.EMBEDDING_API_KEY or settings.GEMINI_API_KEY) if settings.EMBEDDING_PROVIDER.lower() == "gemini" else settings.GEMINI_API_KEY,
            model_name=args.model, dimensions=args.dimensions,
            batch_size=args.batch_size or min(8, settings.EMBEDDING_BATCH_SIZE),
            requests_per_minute=rpm, rate_limiter=EmbeddingRateLimiter(rpm, adaptive=args.auto_rate),
            base_url=settings.EMBEDDING_GEMINI_BASE_URL,
            proxy=settings.EMBEDDING_PROXY or settings.GEMINI_PROXY,
            on_activity=record,
            )
            models = [model]
        vector = model.probe_query("برای یادگیری حد، کدام مباحث تابع را باید بلد باشم؟")
        if not vector:
            raise EmbeddingError("Query embedding probe returned no vector.")
        record({"status": "probe_passed", "query_dimensions": len(vector)})
        if args.probe_only:
            return 0
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        os.environ["CHROMA_TELEMETRY"] = "false"
        client = chromadb.PersistentClient(str(source_dir), settings=ChromaSettings(anonymized_telemetry=False))
        for name in source_names:
            client.get_collection(name, embedding_function=None)  # fail before writing if a source is missing
        if client.get_collection(source_names[0]).count() == 0:
            raise EmbeddingError("Source document collection is empty; nothing to migrate.")
        for name in source_names:
            finished = sum(row["chunks"] for row in state["collections"])
            callback = lambda p: record({"status": "running", "phase": "parallel_indexing" if args.workers > 1 else "indexing",
                                        "overall_completed": max(state.get("overall_completed", 0), finished + p["completed"]), **p})
            result = (migrate_collection_parallel(client, name, models, callback) if args.workers > 1
                      else migrate_collection(client, name, model, callback))
            state["collections"].append(result)
        for result in state["collections"]:
            validate_migration(client.get_collection(result["source"], embedding_function=None),
                               client.get_collection(result["target"], embedding_function=None))
        if args.activate:
            activate_gemini(root / ".env", model, state_dir)
        record({"status": "complete", "activated": args.activate,
                "phase": "finished", "overall_completed": state["overall_total"],
                "note": "Restart the backend after activation. Original vectors and image collections are intact."})
        return 0
    except KeyboardInterrupt:
        record({"status": "stopped", "phase": "interrupted", "reason": "Migration interrupted; rerun to resume.", "resumable": True})
        return 130
    except EmbeddingError as error:
        record({"status": "stopped", "reason": str(error), "resumable": True})
        return 1
    except ValueError:
        record({"status": "stopped", "reason": "Invalid migration/provider configuration.", "resumable": True})
        return 1
    except Exception as error:
        record({"status": "stopped", "reason": type(error).__name__, "resumable": True})
        return 1
    finally:
        for worker_model in models:
            worker_model.close()
        lock.close()


if __name__ == "__main__":
    if "--wait-for-quota" in sys.argv and not {"--help", "-h"}.intersection(sys.argv):
        from app.rag.embedding_supervisor import supervise_migration
        root = Path(__file__).resolve().parents[1]
        if Path.cwd().resolve() != root:
            raise SystemExit("Run from backend/ so the worker loads the correct .env and corpus paths.")
        raise SystemExit(supervise_migration(main, root / "data/embedding_migrations/gemini-status.json"))
    raise SystemExit(main())
