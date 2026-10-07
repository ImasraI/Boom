"""Bounded, account-scoped jobs for generation that outlasts HTTP timeouts.

The application runs one backend process. Results live in the ordinary mock
database; this registry contains only transient progress and response metadata.
"""
import threading
import time
from uuid import uuid4

from fastapi import HTTPException

_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_MAX_ACTIVE = 3
_RETENTION_SECONDS = 7200


def reserve(user_id: int) -> tuple[dict, bool]:
    with _LOCK:
        now = time.monotonic()
        for job_id, job in list(_JOBS.items()):
            if job['status'] != 'running' and now - job['updated'] > _RETENTION_SECONDS:
                del _JOBS[job_id]
        active = [job for job in _JOBS.values() if job['status'] == 'running']
        existing = next((job for job in active if job['user_id'] == user_id), None)
        if existing:
            return public(existing), False
        if len(active) >= _MAX_ACTIVE:
            raise HTTPException(503, 'تولید دفترچه‌ها در حال انجام است؛ کمی بعد دوباره تلاش کنید.',
                                headers={'Retry-After':'60'})
        job_id = uuid4().hex
        job = dict(job_id=job_id, user_id=user_id, status='running', updated=now)
        _JOBS[job_id] = job
        return public(job), True


def public(job: dict) -> dict:
    return {k: job[k] for k in ('job_id', 'status', 'result') if k in job}


def get(job_id: str, user_id: int) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job['user_id'] != user_id:
            raise HTTPException(404, 'درخواست پیدا نشد؛ اگر سرور راه‌اندازی مجدد شده، دفترچه تازه درخواست کنید.')
        if job['status'] == 'failed':
            raise HTTPException(job['error_status'], job['error_detail'], headers=job.get('error_headers'))
        return public(job)


def finish(job_id: str, *, result=None, error: HTTPException | None = None) -> None:
    with _LOCK:
        job = _JOBS[job_id]
        job['updated'] = time.monotonic()
        if error:
            job.update(status='failed', error_status=error.status_code,
                       error_detail=error.detail, error_headers=error.headers)
        else:
            job.update(status='ready', result=result)


def discard(job_id: str) -> None:
    with _LOCK:
        _JOBS.pop(job_id, None)
