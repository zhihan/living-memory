"""Cloud storage helpers for uploading file attachments."""

from __future__ import annotations

import os
import uuid
from pathlib import Path


def upload_to_gcs(local_path: Path, *, bucket: str | None = None) -> str:
    """Upload a file to Google Cloud Storage and return its public URL.

    The bucket name is read from the ``GCS_BUCKET`` environment variable
    unless explicitly provided.  The file is stored under a unique key
    based on a UUID to avoid collisions.
    """
    from google.cloud import storage  # lazy import

    bucket_name = bucket or os.environ["GCS_BUCKET"]
    client = storage.Client()
    gcs_bucket = client.bucket(bucket_name)

    ext = local_path.suffix
    blob_name = f"attachments/{uuid.uuid4().hex}{ext}"
    blob = gcs_bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path))
    blob.make_public()
    return blob.public_url


def delete_from_gcs(public_url: str) -> None:
    """Delete a blob from GCS given its public URL.

    Parses a URL of the form
    ``https://storage.googleapis.com/<bucket>/<blob_path>`` to extract
    the bucket name and blob path, then deletes the blob.
    """
    from urllib.parse import urlparse

    from google.cloud import storage  # lazy import

    parsed = urlparse(public_url)
    # Path starts with /<bucket>/<blob_path>
    parts = parsed.path.lstrip("/").split("/", 1)
    bucket_name = parts[0]
    blob_path = parts[1]

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.delete()
