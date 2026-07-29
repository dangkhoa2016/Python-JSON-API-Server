from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send


class StripTrailingSlashMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path != "/" and path.endswith("/"):
                normalized = path.rstrip("/")
                if normalized:
                    scope["path"] = normalized
                    scope["raw_path"] = normalized.encode("utf-8")
                    scope["path_params"] = {}
        await self.app(scope, receive, send)
