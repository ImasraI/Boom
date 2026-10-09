"""Append-only provider usage, without prompts, credentials or user identifiers.

Record every billed HTTP response, including empty completions and retries.
Provider refusals have no reported token usage and are not counted as spending.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading

from app.utils.logger import get_logger

logger = get_logger(__name__)
_stage = ContextVar('pool_usage_stage', default='chat_planning')
_lock = threading.Lock()
STAGES = ('drafting', 'repair', 'verification', 'repair_verification', 'chat_planning')


def current_stage():
    return _stage.get()


def record_stream(provider, model, usage, has_content):
    record_response(provider, model, {'usage': usage,
        'choices': [{'message': {'content': 'stream' if has_content else ''}}]})


def _directory():
    return Path(__file__).resolve().parents[2] / 'data' / 'pool_usage'


@contextmanager
def stage(name):
    token = _stage.set(name)
    try:
        yield
    finally:
        _stage.reset(token)


def record_response(provider, model, data):
    """Called at the transport, before parsing/retrying a successful response."""
    try:
        usage = data.get('usage') or {}
        # APIs without usage fields are unknown, never estimated as zero cost.
        known = bool(usage) and isinstance(usage, dict)
        def number(name):
            return max(0, int(usage.get(name) or 0)) if known else 0
        prompt, completion = number('prompt_tokens'), number('completion_tokens')
        total = number('total_tokens') or prompt + completion
        model = str(model)
        if not re.fullmatch(r'[a-zA-Z0-9_./:-]{1,100}', model) or model.startswith(('gsk_', 'AQ.')):
            model = 'unknown'
        choices = data.get('choices') or []
        content = choices[0].get('message', {}).get('content') if choices else None
        now = datetime.now(timezone.utc)
        row = dict(at=now.isoformat(), stage=_stage.get(), provider=provider, model=model,
                   prompt_tokens=prompt, completion_tokens=completion, total_tokens=total,
                   usage_reported=known, empty=not bool(content))
        path = _directory() / (now.date().isoformat() + '.jsonl')
        payload = (json.dumps(row, separators=(',', ':')) + '\n').encode()
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, payload)
            finally:
                os.close(fd)
    except Exception:
        # Accounting must not break a student response. Never log provider data.
        logger.warning('Provider usage could not be recorded.')


def summary():
    """Today's UTC totals. Missing historical data is explicitly unmeasured."""
    day = datetime.now(timezone.utc).date().isoformat()
    groups = {}
    path = _directory() / (day + '.jsonl')
    try:
        with path.open(encoding='utf-8') as source:
            for line in source:
                try:
                    row = json.loads(line)
                    key = (row['stage'], row['provider'], row['model'])
                    if key[0] not in STAGES:
                        continue
                    group = groups.setdefault(key, dict(stage=key[0], provider=key[1], model=key[2],
                        responses=0, unmeasured_responses=0, empty_responses=0,
                        prompt_tokens=0, completion_tokens=0, total_tokens=0))
                    group['responses'] += 1
                    group['unmeasured_responses'] += not row['usage_reported']
                    group['empty_responses'] += row['empty']
                    for name in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                        group[name] += row[name]
                except (ValueError, KeyError, TypeError):
                    continue  # Interrupted/corrupt line does not erase other usage.
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning('Provider usage summary could not be read.')
    return {'date_utc': day, 'historical_backfill': False, 'groups': list(groups.values())}
