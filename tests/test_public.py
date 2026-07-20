from __future__ import annotations

import httpx


class TestPublicFavicon:
    async def test_favicon_ico(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/favicon.ico")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/x-icon"

    async def test_favicon_png(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/favicon.png")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    async def test_favicon_png_has_valid_signature(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/favicon.png")
        assert resp.status_code == 200
        assert resp.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(resp.content) > 256

    async def test_favicon_ico_has_valid_header(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/favicon.ico")
        assert resp.status_code == 200
        assert resp.content[:4] == b"\x00\x00\x01\x00"
        assert len(resp.content) > 256
