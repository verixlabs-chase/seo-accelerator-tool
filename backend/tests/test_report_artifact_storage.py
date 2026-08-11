from __future__ import annotations

import sys
from types import ModuleType

from app.services.report_artifact_storage_service import (
    LocalReportArtifactStorage,
    S3ReportArtifactStorage,
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
