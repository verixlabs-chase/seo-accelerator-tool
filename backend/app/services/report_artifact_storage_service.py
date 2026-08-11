from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from app.core.settings import get_settings


@dataclass(frozen=True)
class StoredReportArtifact:
    storage_mode: str
    storage_path: str
    storage_key: str
    content_type: str
    byte_size: int
    checksum_sha256: str
    durable: bool
    ready: bool
    content: bytes | None = None


class ReportArtifactStorage(Protocol):
    storage_mode: str
    durable: bool

    def put_bytes(
        self,
        *,
        tenant_id: str,
        report_id: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> StoredReportArtifact: ...

    def exists(self, storage_key: str, storage_path: str) -> bool: ...

    def read_bytes(self, storage_key: str, storage_path: str) -> bytes: ...


def local_report_artifact_root() -> Path:
    settings = get_settings()
    if settings.hosted_serverless or os.getenv("VERCEL") == "1":
        return Path(tempfile.gettempdir()) / "insightos-generated-reports"
    return Path("generated_reports")


class LocalReportArtifactStorage:
    storage_mode = "local_disk"
    durable = False

    def __init__(self, root: Path | None = None) -> None:
        if root is not None:
            self.root = root
            return

        self.root = local_report_artifact_root()

    def put_bytes(
        self,
        *,
        tenant_id: str,
        report_id: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> StoredReportArtifact:
        del tenant_id
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{report_id}-{filename}"
        path.write_bytes(content)
        return StoredReportArtifact(
            storage_mode=self.storage_mode,
            storage_path=str(path),
            storage_key=str(path),
            content_type=content_type,
            byte_size=len(content),
            checksum_sha256=sha256(content).hexdigest(),
            durable=self.durable,
            ready=True,
        )

    def exists(self, storage_key: str, storage_path: str) -> bool:
        return Path(storage_path or storage_key).is_file()

    def read_bytes(self, storage_key: str, storage_path: str) -> bytes:
        return Path(storage_path or storage_key).read_bytes()


class DatabaseReportArtifactStorage:
    """Prepare small private report files for storage on the artifact row itself."""

    storage_mode = "database_private"
    durable = True

    def put_bytes(
        self,
        *,
        tenant_id: str,
        report_id: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> StoredReportArtifact:
        del tenant_id
        key = f"database://reports/{report_id}/{filename}"
        return StoredReportArtifact(
            storage_mode=self.storage_mode,
            storage_path=key,
            storage_key=key,
            content_type=content_type,
            byte_size=len(content),
            checksum_sha256=sha256(content).hexdigest(),
            durable=self.durable,
            ready=True,
            content=content,
        )

    def exists(self, storage_key: str, storage_path: str) -> bool:
        del storage_key, storage_path
        return False

    def read_bytes(self, storage_key: str, storage_path: str) -> bytes:
        del storage_key, storage_path
        raise RuntimeError("Database report bytes are read from the artifact record")


class S3ReportArtifactStorage:
    storage_mode = "s3_private"
    durable = True

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - deployment packaging guard
            raise RuntimeError("boto3 is required for durable report storage") from exc

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def put_bytes(
        self,
        *,
        tenant_id: str,
        report_id: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> StoredReportArtifact:
        key = f"tenants/{tenant_id}/reports/{report_id}/{filename}"
        checksum = sha256(content).hexdigest()
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            Metadata={"sha256": checksum, "report-id": report_id},
        )
        return StoredReportArtifact(
            storage_mode=self.storage_mode,
            storage_path=key,
            storage_key=key,
            content_type=content_type,
            byte_size=len(content),
            checksum_sha256=checksum,
            durable=self.durable,
            ready=True,
        )

    def exists(self, storage_key: str, storage_path: str) -> bool:
        key = storage_key or storage_path
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return False
        return True

    def read_bytes(self, storage_key: str, storage_path: str) -> bytes:
        key = storage_key or storage_path
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()


def object_storage_configured() -> bool:
    settings = get_settings()
    required = (
        settings.object_storage_endpoint,
        settings.object_storage_bucket,
        settings.object_storage_access_key,
        settings.object_storage_secret_key,
    )
    return all(bool(str(value or "").strip()) for value in required)


def get_report_artifact_storage() -> ReportArtifactStorage:
    settings = get_settings()
    if object_storage_configured():
        return S3ReportArtifactStorage(
            endpoint=settings.object_storage_endpoint,
            bucket=settings.object_storage_bucket,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            region=settings.object_storage_region,
        )
    if settings.hosted_serverless or os.getenv("VERCEL") == "1":
        return DatabaseReportArtifactStorage()
    return LocalReportArtifactStorage()
