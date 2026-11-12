import os
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile

from app.core.config import settings
from app.core.minio_client import minio_storage
from app.core.security import get_current_user
from app.db.models import User

router = APIRouter()


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    bucket: str = Query(settings.BUCKET_PRODUCT_IMAGES),
    current_user: User = Depends(get_current_user),
):
    allowed_buckets = {
        settings.BUCKET_PRODUCT_IMAGES,
        settings.BUCKET_RETURN_EVIDENCE,
        settings.BUCKET_INVOICES,
    }
    if bucket not in allowed_buckets:
        raise HTTPException(status_code=400, detail=f"Invalid bucket. Allowed: {allowed_buckets}")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit")

    ext = os.path.splitext(file.filename or "upload.jpg")[1] or ".jpg"
    object_name = f"{uuid.uuid4().hex}{ext}"

    url = minio_storage.upload_bytes(
        bucket=bucket,
        object_name=object_name,
        data=content,
        content_type=file.content_type or "application/octet-stream",
    )

    return {
        "bucket": bucket,
        "object_name": object_name,
        "url": url,
    }


@router.get("/files/{bucket}/{object_name:path}")
def stream_file(bucket: str, object_name: str):
    data, content_type = minio_storage.get_file(bucket, object_name)
    if data is None:
        raise HTTPException(status_code=404, detail="File not found in storage")
    return Response(content=data, media_type=content_type)

