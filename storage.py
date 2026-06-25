"""
Хранилище файлов в Cloudflare R2 (S3-совместимое API).
"""

import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

R2_BUCKET = os.environ.get("R2_BUCKET", "")
_r2_client = None


def get_r2():
    global _r2_client
    if _r2_client is None:
        endpoint = os.environ.get("R2_ENDPOINT_URL")
        key_id = os.environ.get("R2_ACCESS_KEY_ID")
        secret = os.environ.get("R2_SECRET_ACCESS_KEY")
        if not all([endpoint, key_id, secret, R2_BUCKET]):
            raise RuntimeError(
                "R2 не настроен: укажите R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY, R2_BUCKET"
            )
        _r2_client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _r2_client


def r2_stream(r2_key: str, filename: str) -> StreamingResponse:
    """Стримит файл из R2 клиенту."""
    try:
        obj = get_r2().get_object(Bucket=R2_BUCKET, Key=r2_key)
        return StreamingResponse(
            obj["Body"],
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("NoSuchKey", "404"):
            raise HTTPException(404, "Файл не найден")
        raise HTTPException(500, "Ошибка хранилища")
