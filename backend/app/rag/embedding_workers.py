"""Load laptop OCR worker credentials without logging or copying their keys."""
from pathlib import Path

from dotenv import dotenv_values

from app.rag.gemini_embeddings import EmbeddingError, EmbeddingRateLimiter, GeminiEmbeddingModel


def build_worker_models(env_dir, count, *, model_name, dimensions, batch_size, rpm,
                        base_url, activity=lambda worker, event: None,
                        report=lambda event: None, auto_rate=False):
    specs, unique = [], {}
    for index in range(1, count + 1):
        path = Path(env_dir) / f"worker{index}" / "worker.env"
        values = dotenv_values(path) if path.is_file() else {}
        key = (values.get("GEMINI_API_KEY") or "").strip()
        if not key:
            report({"credential_source": f"worker{index}", "status": "missing_key"})
            continue
        spec = {"key": key, "proxy": values.get("GEMINI_PROXY") or "", "source": f"worker{index}"}
        specs.append(spec)
        unique.setdefault(key, spec)
    working, limiters = {}, {}
    for key, spec in unique.items():
        limiter = EmbeddingRateLimiter(rpm, adaptive=auto_rate)
        probe = GeminiEmbeddingModel(key, model_name, dimensions, batch_size, rpm, base_url,
                                     spec["proxy"], rate_limiter=limiter,
                                     on_activity=lambda event, source=spec["source"]: activity(int(source.removeprefix("worker")), event))
        try:
            probe.probe_query("تابع و حد")
            working[key] = spec
            limiters[key] = limiter
            report({"credential_source": spec["source"], "status": "verified"})
        except EmbeddingError as error:
            report({"credential_source": spec["source"], "status": "refused", "reason": str(error)})
        finally:
            probe.close()
    if not working:
        raise EmbeddingError("None of the configured OCR worker keys passed the embedding probe.")
    valid_specs = [spec for spec in specs if spec["key"] in working]
    models, assignments = [], []
    for index in range(count):
        spec = valid_specs[index % len(valid_specs)]
        worker = index + 1
        group = list(working).index(spec["key"]) + 1
        models.append(GeminiEmbeddingModel(spec["key"], model_name, dimensions, batch_size, rpm,
            base_url, spec["proxy"], on_activity=lambda event, w=worker: activity(w, event),
            rate_limiter=limiters[spec["key"]]))
        assignments.append({"worker": worker, "credential_source": spec["source"], "key_group": group})
    report({"worker_count": count, "distinct_working_keys": len(working), "assignments": assignments})
    return models
