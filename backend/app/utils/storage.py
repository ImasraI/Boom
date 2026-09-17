"""
Cloudflare R2 storage wrapper via S3-compatible boto3 client.

Expose put_object(key, bytes) and get_object(key) -> bytes,
plus generate_presigned_url(key) for direct URL access.
Fallback to local disk when R2 env vars aren't set, so local dev works.
"""

import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# R2 environment variables
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "")


def _r2_client():
    """Return an R2 boto3 client, or None if credentials aren't configured."""
    if not (R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME):
        return None
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    )


def put_object(key: str, data: bytes) -> None:
    """Upload bytes to R2 under the given key."""
    client = _r2_client()
    if client is None:
        # Fallback: write to local data/ directory
        local_path = os.path.join("data", key.lstrip("/"))
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)
        return
    try:
        client.put_object(Bucket=R2_BUCKET_NAME, Key=key, Body=data)
    except ClientError as e:
        logger.warning(f"R2 put_object failed: {e}. Falling back to local disk.")
        local_path = os.path.join("data", key.lstrip("/"))
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)


def get_object(key: str) -> bytes:
    """Download bytes from R2 for the given key."""
    client = _r2_client()
    if client is None:
        # Fallback: read from local data/ directory
        local_path = os.path.join("data", key.lstrip("/"))
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")
        with open(local_path, "rb") as f:
            return f.read()
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        return resp["Body"].read()
    except ClientError as e:
        raise FileNotFoundError(f"R2 get_object failed: {e}")


def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generate a direct URL for the given R2 key (valid for expires_in seconds)."""
    client = _r2_client()
    if client is None:
        # Fallback: return a local file URL
        local_path = os.path.join("data", key.lstrip("/"))
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")
        return f"file://{os.path.abspath(local_path)}"
    try:
        return client.generate_presigned_url(
            "get_object", Params={"Bucket": R2_BUCKET_NAME, "Key": key}, ExpiresIn=expires_in
        )
    except ClientError as e:
        raise RuntimeError(f"Failed to generate presigned URL: {e}")