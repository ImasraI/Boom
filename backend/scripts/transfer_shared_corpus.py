"""Run from backend: transfer_shared_corpus.py export|import --file <corpus.json>.

Stop ingestion/API writes first and back up the VM Chroma directory before import.
Only shared Gemini text collections are transferred. Existing collections and
private user vectors remain intact; no application database is opened.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings
from app.rag.embedding_progress import MigrationLock
from app.rag.gemini_embeddings import EmbeddingError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "import"])
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if Path.cwd().resolve() != root:
        parser.error("Run from backend/ to resolve the correct .env and corpus directory.")
    settings = get_settings()
    state_dir = root / "data/embedding_migrations"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = MigrationLock(state_dir / "gemini.lock")
    try:
        lock.acquire()
    except BlockingIOError:
        print("Embedding migration is running; wait for it to finish before transferring vectors.")
        return 2
    try:
        if args.action == "export" and settings.EMBEDDING_PROVIDER.lower() != "gemini":
            raise ValueError("Complete and activate the Gemini migration before exporting.")
        import chromadb
        from chromadb.config import Settings
        from app.rag.corpus_transfer import export_shared_corpus, import_shared_corpus
        client = chromadb.PersistentClient(settings.CHROMA_DIR, settings=Settings(anonymized_telemetry=False))
        names = [settings.CHROMA_COLLECTION, settings.CHROMA_QA_COLLECTION]
        if args.action == "export":
            result = export_shared_corpus(client, args.file, names, settings.EMBEDDING_MODEL_NAME,
                                          settings.EMBEDDING_DIMENSIONS, settings.DEMO_USER_ID)
        else:
            result = import_shared_corpus(client, args.file, names, settings.DEMO_USER_ID)
        print(json.dumps({"action": args.action, "verified_chunks": result}, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, TypeError, EmbeddingError) as error:
        print(f"Corpus transfer refused ({type(error).__name__}); inspect the file/configuration before activating it.")
        return 1
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
