"""
OAuth 2.0 Client Credentials support for MCP server authentication.

Usage:
    config = OAuthConfig(
        client_id="my-client",
        client_secret="my-secret",
        token_url="https://auth.example.com/oauth/token",
        scope="mcp:read",
    )
    manager = OAuthManager(config)
    token = await manager.get_token()  # cached; auto-refreshes before expiry
"""

import asyncio
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from utils.loging import logger


@dataclass
class OAuthConfig:
    """Configuration for OAuth 2.0 Client Credentials flow."""
    client_id: str
    client_secret: str
    token_url: str
    scope: Optional[str] = None
    # Seconds before actual expiry to treat token as stale (absorbs clock skew)
    expiry_buffer_seconds: int = 30


class OAuthError(RuntimeError):
    """Raised when OAuth token acquisition or refresh fails."""


class OAuthManager:
    """
    Manages OAuth 2.0 Client Credentials tokens with caching and auto-refresh.

    Thread-safe under a single asyncio event loop.
    """

    def __init__(self, config: OAuthConfig):
        self._config = config
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    def _is_valid(self) -> bool:
        return (
            self._token is not None
            and time.monotonic() < self._expires_at - self._config.expiry_buffer_seconds
        )

    async def get_token(self) -> str:
        """
        Return a valid Bearer token, fetching/refreshing as needed.
        Raises OAuthError on failure.
        """
        async with self._lock:
            if self._is_valid():
                return self._token  # type: ignore[return-value]
            return await self._fetch_token()

    async def _fetch_token(self) -> str:
        cfg = self._config
        data: dict = {
            "grant_type": "client_credentials",
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
        }
        if cfg.scope:
            data["scope"] = cfg.scope

        encoded = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(
            cfg.token_url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            loop = asyncio.get_running_loop()
            raw = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req, timeout=15).read(),
            )
            payload = json.loads(raw)
        except Exception as exc:
            raise OAuthError(
                f"Token request to {cfg.token_url} failed: {exc}"
            ) from exc

        token = payload.get("access_token")
        if not token:
            raise OAuthError(f"No access_token in OAuth response: {payload}")

        expires_in = int(payload.get("expires_in", 3600))
        self._token = token
        self._expires_at = time.monotonic() + expires_in
        logger.info(
            f"OAuthManager: token acquired, expires_in={expires_in}s "
            f"(buffer={cfg.expiry_buffer_seconds}s)"
        )
        return self._token  # type: ignore[return-value]

    def invalidate(self) -> None:
        """Force the next get_token() call to re-fetch (e.g. after a 401 response)."""
        self._token = None
        self._expires_at = 0.0
