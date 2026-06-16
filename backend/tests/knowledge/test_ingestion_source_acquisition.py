from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from deerflow.knowledge.ingestion.acquisition import SSRFBlockedError, assert_safe_http_url
from deerflow.knowledge.ingestion.models import SourceInput
from deerflow.knowledge.ingestion.source_normalizer import SourceNormalizer, canonicalize_url


def test_url_canonicalization_removes_fragment_tracking_query_and_default_port() -> None:
    assert canonicalize_url("HTTPS://Example.COM:443/a/../b/?utm_source=x&b=2&a=1#frag") == "https://example.com/b/?utm_source=x&b=2&a=1"


def test_url_canonicalization_preserves_query_order_duplicates_and_values() -> None:
    assert canonicalize_url("https://example.com/path?a=1&a=2") == "https://example.com/path?a=1&a=2"
    assert canonicalize_url("https://example.com/path?a=1&b=2") == "https://example.com/path?a=1&b=2"
    assert canonicalize_url("https://example.com/path?b=2&a=1") == "https://example.com/path?b=2&a=1"


def test_file_source_identity_uses_deerflow_virtual_path_without_host_path(monkeypatch, tmp_path: Path) -> None:
    workspace_id = uuid4()
    host_file = tmp_path / "secret.txt"
    host_file.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(
        "deerflow.knowledge.ingestion.source_normalizer.get_paths",
        lambda: SimpleNamespace(resolve_virtual_path=lambda thread_id, virtual_path, user_id=None: host_file),
    )

    source = SourceNormalizer().normalize(
        workspace_id,
        SourceInput(kind="upload_file", value="/mnt/user-data/uploads/secret.txt", thread_id="thread-1", user_id="user-1"),
    )

    assert source.source_type == "file"
    assert source.local_path == host_file
    assert str(host_file) not in source.canonical_uri
    assert source.canonical_uri == f"deerflow://workspace/{workspace_id}/threads/thread-1/user-data/uploads/secret.txt"


def test_file_source_identity_can_use_stable_storage_object_across_threads(monkeypatch, tmp_path: Path) -> None:
    workspace_id = uuid4()
    host_file = tmp_path / "report.txt"
    host_file.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(
        "deerflow.knowledge.ingestion.source_normalizer.get_paths",
        lambda: SimpleNamespace(resolve_virtual_path=lambda thread_id, virtual_path, user_id=None: host_file),
    )

    first = SourceNormalizer().normalize(
        workspace_id,
        SourceInput(kind="upload_file", value="/mnt/user-data/uploads/report.txt", thread_id="thread-a", user_id="user-1", metadata={"storage_object_id": "file-123"}),
    )
    second = SourceNormalizer().normalize(
        workspace_id,
        SourceInput(kind="upload_file", value="/mnt/user-data/uploads/report.txt", thread_id="thread-b", user_id="user-1", metadata={"storage_object_id": "file-123"}),
    )

    assert first.canonical_uri == second.canonical_uri
    assert "thread-a" not in first.canonical_uri
    assert "thread-b" not in first.canonical_uri


def test_file_source_identity_is_workspace_scoped_and_distinguishes_storage_objects(monkeypatch, tmp_path: Path) -> None:
    host_file = tmp_path / "same-name.txt"
    host_file.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(
        "deerflow.knowledge.ingestion.source_normalizer.get_paths",
        lambda: SimpleNamespace(resolve_virtual_path=lambda thread_id, virtual_path, user_id=None: host_file),
    )

    workspace_id = uuid4()
    first = SourceNormalizer().normalize(
        workspace_id,
        SourceInput(kind="upload_file", value="/mnt/user-data/uploads/same-name.txt", thread_id="thread", user_id="user-1", metadata={"storage_object_id": "file-a"}),
    )
    other_workspace = SourceNormalizer().normalize(
        uuid4(),
        SourceInput(kind="upload_file", value="/mnt/user-data/uploads/same-name.txt", thread_id="thread", user_id="user-1", metadata={"storage_object_id": "file-a"}),
    )
    other_object = SourceNormalizer().normalize(
        workspace_id,
        SourceInput(kind="upload_file", value="/mnt/user-data/uploads/same-name.txt", thread_id="thread", user_id="user-1", metadata={"storage_object_id": "file-b"}),
    )

    assert first.canonical_uri != other_workspace.canonical_uri
    assert first.canonical_uri != other_object.canonical_uri
    assert str(host_file) not in first.canonical_uri


@pytest.mark.asyncio
async def test_ssrf_blocks_localhost_before_fetch() -> None:
    with pytest.raises(SSRFBlockedError):
        await assert_safe_http_url("http://localhost/admin")


@pytest.mark.asyncio
async def test_ssrf_blocks_private_resolved_addresses(monkeypatch) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("10.0.0.5", 443))],
    )

    with pytest.raises(SSRFBlockedError):
        await assert_safe_http_url("https://example.com")


@pytest.mark.asyncio
async def test_ssrf_allows_public_http_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )

    await assert_safe_http_url("https://example.com/path")
