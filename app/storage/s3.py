"""S3-compatible storage backend using aiobotocore."""

from __future__ import annotations

import io

import aiobotocore.session

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.storage.base import BaseStorage

logger = get_logger(__name__)


class S3Storage(BaseStorage):
    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.s3_bucket
        self._session = aiobotocore.session.AioSession()
        self._client_kwargs = {
            "service_name": "s3",
            "endpoint_url": settings.s3_endpoint_url,
            "aws_access_key_id": settings.s3_access_key_id,
            "aws_secret_access_key": settings.s3_secret_access_key,
            "region_name": settings.s3_region,
        }

    def _client(self):
        return self._session.create_client(**self._client_kwargs)

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        async with self._client() as s3:
            try:
                await s3.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
            except Exception as exc:
                # Automatically initialize bucket if not created yet
                if "NoSuchBucket" in str(type(exc).__name__) or "NoSuchBucket" in str(exc) or "404" in str(exc):
                    try:
                        await s3.create_bucket(Bucket=self._bucket)
                    except Exception:
                        pass
                    await s3.put_object(
                        Bucket=self._bucket,
                        Key=key,
                        Body=data,
                        ContentType=content_type,
                    )
                else:
                    raise
        logger.info("s3_put", key=key, size=len(data))
        return key

    async def get(self, key: str) -> bytes:
        async with self._client() as s3:
            resp = await s3.get_object(Bucket=self._bucket, Key=key)
            body = await resp["Body"].read()
        return body

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)
        logger.info("s3_delete", key=key)

    async def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        async with self._client() as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        return url

    async def health_check(self) -> None:
        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self._bucket)
            except Exception:
                try:
                    await s3.create_bucket(Bucket=self._bucket)
                except Exception:
                    pass
