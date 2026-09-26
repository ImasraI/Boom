"""
Local disk storage wrapper.

Exposes put_object(key, data) and get_object(key) -> bytes.
Fallback to local disk only — no R2 or external dependencies.
"""

import os


def put_object(key: str, data: bytes) -> None:
    """Write bytes to local disk under data/<key>."""
    local_path = os.path.join("data", key.lstrip("/"))
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(data)


def get_object(key: str) -> bytes:
    """Read bytes from local disk at data/<key>."""
    local_path = os.path.join("data", key.lstrip("/"))
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Local file not found: {local_path}")
    with open(local_path, "rb") as f:
        return f.read()