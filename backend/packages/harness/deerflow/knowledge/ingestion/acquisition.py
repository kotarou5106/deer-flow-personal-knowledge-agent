from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from deerflow.knowledge.ingestion.models import AcquiredContent, NormalizedSource


class AcquisitionError(RuntimeError):
    pass


class SSRFBlockedError(AcquisitionError):
    pass


@dataclass(frozen=True)
class AcquisitionConfig:
    max_response_bytes: int = 10 * 1024 * 1024
    timeout_seconds: float = 10.0
    max_redirects: int = 3


def _is_blocked_hostname(hostname: str) -> bool:
    lowered = hostname.rstrip(".").lower()
    return lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(".localhost") or lowered.endswith(".local")


def _is_blocked_ip(ip: str) -> bool:
    address = ipaddress.ip_address(ip)
    return any(
        [
            address.is_loopback,
            address.is_link_local,
            address.is_private,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        ]
    )


async def assert_safe_http_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise SSRFBlockedError("Only HTTP and HTTPS URLs are allowed")
    if parts.username or parts.password:
        raise SSRFBlockedError("URL credentials are not allowed")
    if not parts.hostname or _is_blocked_hostname(parts.hostname):
        raise SSRFBlockedError("Blocked unsafe hostname")
    try:
        if _is_blocked_ip(parts.hostname):
            raise SSRFBlockedError("Blocked unsafe IP address")
    except ValueError:
        pass

    def resolve() -> list[str]:
        infos = socket.getaddrinfo(parts.hostname, parts.port, type=socket.SOCK_STREAM)
        return sorted({info[4][0] for info in infos})

    try:
        addresses = await asyncio.to_thread(resolve)
    except socket.gaierror as exc:
        raise SSRFBlockedError("Unable to resolve URL host") from exc
    if not addresses or any(_is_blocked_ip(address) for address in addresses):
        raise SSRFBlockedError("Blocked unsafe resolved address")


class ContentAcquirer:
    def __init__(self, config: AcquisitionConfig | None = None) -> None:
        self.config = config or AcquisitionConfig()

    async def acquire(self, source: NormalizedSource) -> AcquiredContent:
        if source.local_path is not None:
            return await self._acquire_file(source)
        if source.url is not None:
            return await self._acquire_url(source)
        raise AcquisitionError("Normalized source has no acquisition target")

    async def _acquire_file(self, source: NormalizedSource) -> AcquiredContent:
        path = Path(source.local_path)
        stat = path.stat()
        if not path.is_file() or path.is_symlink():
            raise AcquisitionError("File source must be a regular file")
        if stat.st_size > self.config.max_response_bytes:
            raise AcquisitionError("File source exceeds maximum acquisition size")
        data = await asyncio.to_thread(path.read_bytes)
        return AcquiredContent(
            raw_bytes=data,
            media_type=source.media_type,
            source_metadata={**source.original_metadata, "size_bytes": len(data)},
            captured_at=datetime.now(UTC),
        )

    async def _acquire_url(self, source: NormalizedSource) -> AcquiredContent:
        assert source.url is not None
        current_url = source.url
        redirects = 0
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds, follow_redirects=False) as client:
            while True:
                await assert_safe_http_url(current_url)
                response = await client.get(current_url, headers={"User-Agent": "PersonalKnowledgeAgent-Ingestion/1.0"})
                if response.status_code in {301, 302, 303, 307, 308}:
                    redirects += 1
                    if redirects > self.config.max_redirects:
                        raise AcquisitionError("URL redirect limit exceeded")
                    location = response.headers.get("location")
                    if not location:
                        raise AcquisitionError("Redirect response missing Location")
                    current_url = str(response.url.join(location))
                    continue
                response.raise_for_status()
                size = int(response.headers.get("content-length") or "0")
                if size and size > self.config.max_response_bytes:
                    raise AcquisitionError("URL response exceeds maximum acquisition size")
                data = response.content
                if len(data) > self.config.max_response_bytes:
                    raise AcquisitionError("URL response exceeds maximum acquisition size")
                return AcquiredContent(
                    raw_bytes=data,
                    media_type=response.headers.get("content-type", source.media_type).split(";", 1)[0] if response.headers.get("content-type", source.media_type) else None,
                    source_metadata={**source.original_metadata, "final_url": str(response.url), "size_bytes": len(data), "redirects": redirects},
                    captured_at=datetime.now(UTC),
                )
