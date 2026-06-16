from __future__ import annotations

import mimetypes
import posixpath
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import UUID

from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from deerflow.knowledge.ingestion.models import NormalizedSource, SourceInput


def canonicalize_url(raw_url: str) -> str:
    parts = urlsplit(raw_url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").rstrip(".").lower()
    if not scheme or not host:
        raise ValueError("URL must include scheme and host")
    port = parts.port
    netloc = host
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = posixpath.normpath(parts.path or "/")
    if parts.path.endswith("/") and not path.endswith("/"):
        path += "/"
    if path == ".":
        path = "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def _media_type_for_name(name: str, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    guessed, _ = mimetypes.guess_type(name)
    return guessed


class SourceNormalizer:
    def normalize(self, workspace_id: UUID, source_input: SourceInput) -> NormalizedSource:
        if source_input.kind == "url":
            canonical_uri = canonicalize_url(source_input.value)
            return NormalizedSource(
                source_type="url",
                canonical_uri=canonical_uri,
                display_name=source_input.display_name or canonical_uri,
                media_type=source_input.media_type,
                original_metadata={**source_input.metadata, "input_url": source_input.value},
                url=canonical_uri,
            )

        if source_input.kind not in {"upload_file", "virtual_file"}:
            raise ValueError(f"Unsupported source kind: {source_input.kind}")
        if not source_input.thread_id:
            raise ValueError("File sources require thread_id")

        virtual_path = source_input.value
        local_path = get_paths().resolve_virtual_path(source_input.thread_id, virtual_path, user_id=source_input.user_id)
        user_data_prefix = VIRTUAL_PATH_PREFIX.rstrip("/")
        relative_virtual = virtual_path.strip()
        if not (relative_virtual == user_data_prefix or relative_virtual.startswith(user_data_prefix + "/")):
            raise ValueError("File source must use DeerFlow user-data virtual path")
        relative_identity = relative_virtual[len(user_data_prefix) :].lstrip("/")
        stable_identity = _stable_file_identity(source_input.metadata)
        if stable_identity:
            canonical_uri = f"deerflow://workspace/{workspace_id}/files/{quote(stable_identity, safe='')}"
        else:
            canonical_uri = f"deerflow://workspace/{workspace_id}/threads/{source_input.thread_id}/user-data/{quote(relative_identity, safe='/')}"
        display_name = source_input.display_name or Path(relative_virtual).name
        return NormalizedSource(
            source_type="file",
            canonical_uri=canonical_uri,
            display_name=display_name,
            media_type=_media_type_for_name(display_name, source_input.media_type),
            original_metadata={
                **source_input.metadata,
                "thread_id": source_input.thread_id,
                "virtual_path": relative_virtual,
                "source_kind": source_input.kind,
            },
            local_path=local_path,
        )


def _stable_file_identity(metadata: dict[str, object]) -> str | None:
    for key in ("storage_object_id", "file_identity", "file_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
