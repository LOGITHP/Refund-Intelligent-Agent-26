"""Lazy-initialized private MinIO client wrapper and injectable in-memory test backend."""

from __future__ import annotations

import io
from datetime import timedelta
from typing import Any, BinaryIO, Protocol

from minio import Minio

from app.core.config import settings


class MinIOClientError(RuntimeError):
    """Raised when an object storage operation fails."""


class _ObjectResponseProtocol(Protocol):
    def read(self) -> bytes: ...
    def close(self) -> None: ...
    def release_conn(self) -> None: ...


class ObjectStorageProtocol(Protocol):
    """Minimal protocol satisfied by both `minio.Minio` and `InMemoryObjectStorage`."""

    def bucket_exists(self, bucket_name: str) -> bool: ...
    def make_bucket(self, bucket_name: str) -> None: ...
    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> Any: ...
    def get_object(self, bucket_name: str, object_name: str) -> _ObjectResponseProtocol: ...
    def presigned_get_object(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = timedelta(seconds=300),
    ) -> str: ...


class _InMemoryObjectStream:
    """File-like stream implementing `read`/`close`/`release_conn` for `InMemoryObjectStorage`."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def close(self) -> None:
        return None

    def release_conn(self) -> None:
        return None


class InMemoryObjectStorage:
    """In-memory fake implementing `ObjectStorageProtocol` for unit testing."""

    def __init__(self, base_url: str = "http://minio.test") -> None:
        self.base_url = base_url.rstrip("/")
        self.buckets: dict[str, dict[str, tuple[bytes, str]]] = {}

    def bucket_exists(self, bucket_name: str) -> bool:
        return bucket_name in self.buckets

    def make_bucket(self, bucket_name: str) -> None:
        self.buckets.setdefault(bucket_name, {})

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        if bucket_name not in self.buckets:
            raise MinIOClientError(f"Bucket '{bucket_name}' does not exist")
        raw = data.read(length)
        self.buckets[bucket_name][object_name] = (raw, content_type)
        return {"bucket": bucket_name, "object_name": object_name, "size": len(raw)}

    def get_object(self, bucket_name: str, object_name: str) -> _InMemoryObjectStream:
        bucket_data = self.buckets.get(bucket_name)
        if bucket_data is None or object_name not in bucket_data:
            raise MinIOClientError(f"Object '{bucket_name}/{object_name}' not found")
        payload, _content_type = bucket_data[object_name]
        return _InMemoryObjectStream(payload)

    def presigned_get_object(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = timedelta(seconds=300),
    ) -> str:
        bucket_data = self.buckets.get(bucket_name)
        if bucket_data is None or object_name not in bucket_data:
            raise MinIOClientError(f"Object '{bucket_name}/{object_name}' not found")
        ttl = int(expires.total_seconds())
        return f"{self.base_url}/{bucket_name}/{object_name}?X-Amz-Expires={ttl}"


class AgentMinIOClient:
    """Private object-storage wrapper for evidence uploads and compliance reports."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool | None = None,
        client: ObjectStorageProtocol | None = None,
    ) -> None:
        self.endpoint = endpoint or settings.MINIO_ENDPOINT
        self.access_key = access_key if access_key is not None else settings.MINIO_ACCESS_KEY
        self.secret_key = secret_key if secret_key is not None else settings.MINIO_SECRET_KEY
        self.secure = settings.MINIO_SECURE if secure is None else secure
        self._client: ObjectStorageProtocol | None = client

    def _get_client(self) -> ObjectStorageProtocol:
        if self._client is None:
            if not self.access_key or not self.secret_key:
                raise MinIOClientError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be configured")
            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
        return self._client

    def ensure_buckets(self, buckets: tuple[str, ...] | None = None) -> list[str]:
        """Ensure private agent buckets exist (never applies public read policies)."""
        target_buckets = buckets or (settings.BUCKET_EVIDENCE, settings.BUCKET_REPORTS)
        client = self._get_client()
        ensured: list[str] = []
        try:
            for bucket in target_buckets:
                if not client.bucket_exists(bucket):
                    client.make_bucket(bucket)
                ensured.append(bucket)
        except MinIOClientError:
            raise
        except Exception as exc:
            raise MinIOClientError(f"Failed ensuring MinIO buckets: {exc}") from exc
        return ensured

    def upload_bytes(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload raw bytes to a private MinIO bucket and return the stored object key."""
        client = self._get_client()
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            stream = io.BytesIO(data)
            client.put_object(
                bucket,
                object_key,
                stream,
                length=len(data),
                content_type=content_type,
            )
            return object_key
        except MinIOClientError:
            raise
        except Exception as exc:
            raise MinIOClientError(
                f"Failed uploading object '{bucket}/{object_key}': {exc}"
            ) from exc

    def download_bytes(self, bucket: str, object_key: str) -> bytes:
        """Download raw bytes from MinIO and always release the HTTP connection."""
        client = self._get_client()
        response: _ObjectResponseProtocol | None = None
        try:
            response = client.get_object(bucket, object_key)
            return response.read()
        except MinIOClientError:
            raise
        except Exception as exc:
            raise MinIOClientError(
                f"Failed downloading object '{bucket}/{object_key}': {exc}"
            ) from exc
        finally:
            if response is not None:
                try:
                    response.close()
                finally:
                    if hasattr(response, "release_conn"):
                        response.release_conn()

    def presigned_get_url(
        self,
        bucket: str,
        object_key: str,
        expires_seconds: int = 300,
    ) -> str:
        """Generate a short-lived presigned GET URL (bounded to 1..3600 seconds)."""
        if expires_seconds < 1 or expires_seconds > 3600:
            raise ValueError("expires_seconds must be between 1 and 3600")
        client = self._get_client()
        try:
            return client.presigned_get_object(
                bucket,
                object_key,
                expires=timedelta(seconds=expires_seconds),
            )
        except MinIOClientError:
            raise
        except Exception as exc:
            raise MinIOClientError(
                f"Failed generating presigned URL for '{bucket}/{object_key}': {exc}"
            ) from exc
