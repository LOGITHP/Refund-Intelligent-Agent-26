import io
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple
import urllib3
from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)

FALLBACK_DIR = Path("./data/minio_fallback")


class MinIOStorageService:
    def __init__(self) -> None:
        self.client: Optional[Minio] = None
        self.available: bool = False
        self._last_attempt: float = 0.0
        self._connect()

    def _effective_endpoint(self) -> str:
        endpoint = (settings.MINIO_ENDPOINT or "").strip()
        if not endpoint:
            return ""
        if os.getenv("RENDER", "").strip().lower() == "true" and (
            endpoint.startswith("localhost") or endpoint.startswith("127.0.0.1")
        ):
            return ""
        return endpoint

    def _connect(self) -> None:
        self._last_attempt = time.time()
        endpoint = self._effective_endpoint()
        if not endpoint:
            self.available = False
            logger.info("MinIO disabled (empty or local-only endpoint). Using local filesystem fallback at %s.", FALLBACK_DIR)
            return
        try:
            http_client = urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=1.0, read=3.0),
                retries=urllib3.Retry(total=0),
            )
            self.client = Minio(
                endpoint,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
                http_client=http_client,
            )
            self.client.list_buckets()
            self.available = True
            logger.info("Connected to MinIO at %s", endpoint)
        except Exception as exc:
            self.available = False
            logger.warning(
                "MinIO unavailable at %s (%s). Using local filesystem fallback at %s.",
                endpoint,
                exc,
                FALLBACK_DIR,
            )

    def ensure_connection(self) -> bool:
        if not self._effective_endpoint():
            return False
        if not self.available and (time.time() - self._last_attempt > 30.0):
            self._connect()
        return self.available

    def init_buckets(self) -> None:
        buckets = [
            settings.BUCKET_PRODUCT_IMAGES,
            settings.BUCKET_INVOICES,
            settings.BUCKET_RETURN_EVIDENCE,
        ]
        # In Docker Compose (e.g., minio:9000), briefly wait for MinIO readiness
        endpoint = self._effective_endpoint()
        if not self.available and endpoint and not endpoint.startswith("localhost"):
            for _ in range(10):
                self._connect()
                if self.available:
                    break
                time.sleep(1.5)

        if not self.ensure_connection():
            for bucket in buckets:
                (FALLBACK_DIR / bucket).mkdir(parents=True, exist_ok=True)
            return

        assert self.client is not None
        for bucket in buckets:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                    logger.info("Created MinIO bucket: %s", bucket)
                if bucket == settings.BUCKET_PRODUCT_IMAGES:
                    policy = {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"AWS": ["*"]},
                                "Action": ["s3:GetObject"],
                                "Resource": [f"arn:aws:s3:::{bucket}/*"],
                            }
                        ],
                    }
                    self.client.set_bucket_policy(bucket, json.dumps(policy))
            except Exception as exc:
                logger.error("Failed ensuring bucket %s: %s", bucket, exc)

    def upload_bytes(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Uploads binary payload to MinIO (or fallback) and returns the canonical proxy URL path."""
        if self.ensure_connection() and self.client is not None:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                self.client.put_object(
                    bucket,
                    object_name,
                    io.BytesIO(data),
                    length=len(data),
                    content_type=content_type,
                )
                return f"/api/v1/media/files/{bucket}/{object_name}"
            except Exception as exc:
                logger.warning("MinIO upload failed (%s), saving to fallback.", exc)

        target_path = FALLBACK_DIR / bucket / object_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(data)
        return f"/api/v1/media/files/{bucket}/{object_name}"

    def get_file(self, bucket: str, object_name: str) -> Tuple[Optional[bytes], str]:
        """Retrieves file bytes and inferred content type from MinIO or fallback."""
        content_type = self._infer_content_type(object_name)

        if self.ensure_connection() and self.client is not None:
            try:
                response = self.client.get_object(bucket, object_name)
                try:
                    data = response.read()
                    ct = response.headers.get("Content-Type", content_type)
                    return data, ct
                finally:
                    response.close()
                    response.release_conn()
            except S3Error as exc:
                if exc.code != "NoSuchKey":
                    logger.warning("MinIO read error for %s/%s: %s", bucket, object_name, exc)
            except Exception as exc:
                logger.warning("MinIO connection error during read: %s", exc)

        fallback_path = FALLBACK_DIR / bucket / object_name
        if fallback_path.exists():
            return fallback_path.read_bytes(), content_type
        return None, content_type

    def _infer_content_type(self, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        mapping = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".pdf": "application/pdf",
            ".json": "application/json",
        }
        return mapping.get(ext, "application/octet-stream")


minio_storage = MinIOStorageService()
