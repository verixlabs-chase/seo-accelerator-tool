from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import ModuleType

from app.services.report_artifact_storage_service import (
    DatabaseReportArtifactStorage,
    LocalReportArtifactStorage,
    S3ReportArtifactStorage,
    get_report_artifact_storage,
)


def test_local_report_storage_round_trips_bytes(tmp_path):
    storage = LocalReportArtifactStorage(root=tmp_path)
    stored = storage.put_bytes(
        tenant_id="tenant-a",
        report_id="report-a",
        filename="report.html",
        content_type="text/html; charset=utf-8",
        content=b"<html>owner report</html>",
    )

    assert stored.storage_mode == "local_disk"
    assert stored.durable is False
    assert stored.byte_size == 25
    assert storage.exists(stored.storage_key, stored.storage_path) is True
    assert storage.read_bytes(stored.storage_key, stored.storage_path) == b"<html>owner report</html>"


def test_local_report_storage_uses_writable_temp_directory_on_vercel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")

    storage = LocalReportArtifactStorage()

    assert storage.root == Path(tempfile.gettempdir()) / "insightos-generated-reports"


def test_database_report_storage_keeps_private_bytes_for_the_artifact_row():
    storage = DatabaseReportArtifactStorage()
    stored = storage.put_bytes(
        tenant_id="tenant-a",
        report_id="report-a",
        filename="report.pdf",
        content_type="application/pdf",
        content=b"%PDF-durable-owner-report",
    )

    assert stored.storage_mode == "database_private"
    assert stored.durable is True
    assert stored.ready is True
    assert stored.storage_key == "database://reports/report-a/report.pdf"
    assert stored.content == b"%PDF-durable-owner-report"


def test_serverless_report_storage_defaults_to_database(monkeypatch):
    from app.core.settings import get_settings

    monkeypatch.setenv("VERCEL", "1")
    get_settings.cache_clear()
    try:
        storage = get_report_artifact_storage()
        assert isinstance(storage, DatabaseReportArtifactStorage)
    finally:
        get_settings.cache_clear()


def test_private_s3_report_storage_uses_tenant_scoped_keys(monkeypatch):
    objects: dict[tuple[str, str], dict] = {}

    class FakeBody:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def read(self) -> bytes:
            return self.content

    class FakeClient:
        def put_object(self, **kwargs) -> None:  # noqa: ANN003
            objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs

        def head_object(self, *, Bucket: str, Key: str) -> dict:  # noqa: N803
            return objects[(Bucket, Key)]

        def get_object(self, *, Bucket: str, Key: str) -> dict:  # noqa: N803
            return {"Body": FakeBody(objects[(Bucket, Key)]["Body"])}

    fake_client = FakeClient()
    boto3 = ModuleType("boto3")
    boto3.client = lambda *args, **kwargs: fake_client  # type: ignore[attr-defined]
    botocore = ModuleType("botocore")
    botocore_config = ModuleType("botocore.config")
    botocore_config.Config = lambda **kwargs: kwargs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    monkeypatch.setitem(sys.modules, "botocore", botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", botocore_config)

    storage = S3ReportArtifactStorage(
        endpoint="https://project.storage.example/storage/v1/s3",
        bucket="reports",
        access_key="access",
        secret_key="secret",
        region="us-east-1",
    )
    stored = storage.put_bytes(
        tenant_id="tenant-a",
        report_id="report-a",
        filename="report.pdf",
        content_type="application/pdf",
        content=b"%PDF-owner-report",
    )

    assert stored.storage_mode == "s3_private"
    assert stored.durable is True
    assert stored.storage_key == "tenants/tenant-a/reports/report-a/report.pdf"
    assert storage.exists(stored.storage_key, stored.storage_path) is True
    assert storage.read_bytes(stored.storage_key, stored.storage_path) == b"%PDF-owner-report"
