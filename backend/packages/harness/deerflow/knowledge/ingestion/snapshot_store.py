from __future__ import annotations

from pathlib import Path
from uuid import UUID

from deerflow.config.paths import get_paths
from deerflow.runtime.user_context import get_effective_user_id

SNAPSHOT_URI_PREFIX = "deerflow-knowledge-snapshot://"


class SnapshotStore:
    def __init__(self, *, user_id: str | None = None) -> None:
        self.user_id = user_id or get_effective_user_id()

    def path_for(self, workspace_id: UUID, content_hash: str) -> Path:
        if not content_hash or "/" in content_hash or ".." in content_hash:
            raise ValueError("Invalid content hash")
        return get_paths().user_dir(self.user_id) / "knowledge" / "workspaces" / str(workspace_id) / "snapshots" / content_hash[:2] / content_hash

    def uri_for(self, workspace_id: UUID, content_hash: str) -> str:
        return f"{SNAPSHOT_URI_PREFIX}{self.user_id}/{workspace_id}/{content_hash}"

    def write(self, workspace_id: UUID, content_hash: str, data: bytes) -> str:
        path = self.path_for(workspace_id, content_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = path.read_bytes()
            if existing != data:
                raise ValueError("Snapshot hash collision or corrupted snapshot file")
            return self.uri_for(workspace_id, content_hash)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return self.uri_for(workspace_id, content_hash)

    def read(self, uri: str) -> bytes:
        return self.resolve(uri).read_bytes()

    def delete(self, uri: str) -> None:
        try:
            self.resolve(uri).unlink(missing_ok=True)
        except ValueError:
            return

    def resolve(self, uri: str) -> Path:
        if not uri.startswith(SNAPSHOT_URI_PREFIX):
            raise ValueError("Unsupported snapshot URI")
        rest = uri[len(SNAPSHOT_URI_PREFIX) :]
        parts = rest.split("/")
        if len(parts) != 3:
            raise ValueError("Invalid snapshot URI")
        user_id, workspace_id, content_hash = parts
        if user_id != self.user_id:
            raise ValueError("Snapshot URI belongs to another user")
        path = self.path_for(UUID(workspace_id), content_hash).resolve()
        base = get_paths().user_dir(self.user_id).resolve()
        path.relative_to(base)
        return path
