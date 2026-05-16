from datetime import timedelta
from functools import lru_cache
from typing import BinaryIO
from urllib.parse import urlparse, urlunparse

from minio import Minio

from app.config import settings


class ObjectStore:
    def __init__(self) -> None:
        parsed = urlparse(settings.object_storage_endpoint)
        endpoint = parsed.netloc or parsed.path
        secure = settings.object_storage_secure or parsed.scheme == "https"
        self.bucket = settings.object_storage_bucket
        self._client = Minio(
            endpoint,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            secure=secure,
        )

    def ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)

    def put_object(
        self,
        *,
        object_key: str,
        data: BinaryIO,
        length: int,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.ensure_bucket()
        self._client.put_object(
            self.bucket,
            object_key,
            data,
            length,
            content_type=content_type,
            metadata=metadata,
        )
        self._client.stat_object(self.bucket, object_key)

    def delete_object(self, object_key: str) -> None:
        self._client.remove_object(self.bucket, object_key)

    def get_object_bytes(self, object_key: str) -> bytes:
        response = self._client.get_object(self.bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def presigned_get_url(self, object_key: str) -> str:
        url = self._client.presigned_get_object(
            self.bucket,
            object_key,
            expires=timedelta(seconds=settings.object_storage_presigned_url_ttl_seconds),
        )
        if not settings.object_storage_public_endpoint:
            return url

        public = urlparse(settings.object_storage_public_endpoint)
        signed = urlparse(url)
        return urlunparse(
            (
                public.scheme or signed.scheme,
                public.netloc or public.path,
                signed.path,
                signed.params,
                signed.query,
                signed.fragment,
            )
        )


@lru_cache
def get_object_store() -> ObjectStore:
    return ObjectStore()
