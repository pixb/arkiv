"""arkiv HTTP MCP server — LAN variant of mcp_server.py (Phase 14 addendum).

Serves the SAME 7 read-only tools as the stdio mcp_server, but over HTTP/SSE so
MCP clients anywhere on the LAN can connect without local DB access. The tools
are registered once, on mcp_server.mcp (imported below); this file only exposes
that instance over SSE behind a token gate.

Run (as the `arkiv-mcp` compose service):
    python mcp_http_server.py

Env:
    ARKIV_MCP_BIND    bind address   (default 0.0.0.0 — arkiv is LAN-hosted;
                                      the token gate is the security boundary. To
                                      lock down to localhost, set this to
                                      127.0.0.1 and remove the ports: mapping
                                      from docker-compose.yml)
    ARKIV_MCP_PORT    listen port    (default 8502)
    ARKIV_DB_PATH     sqlite db path (must match the arkiv service; token store lives here)
    ARKIV_CHROMA_PATH chroma dir     (for semantic search)

Auth: every request must carry a valid arkiv token via the `Authorization:
Bearer <token>` header (a token in a URL leaks into access logs, proxies and
browser history — never accept it as a query param). We reuse
auth.resolve_raw_token — the exact same token store + IP-allowlist + expiry as
the HTTP API — so the existing `ui-test` token works unchanged.

Security: this server is token-gated and LAN-bound by default. The token gate
is the real security boundary, not the bind address: every request must carry
Authorization: Bearer <token> and the token store is shared with the main HTTP
API. To lock MCP down to localhost (e.g. you SSH into the host to run MCP
clients locally), set ARKIV_MCP_BIND=127.0.0.1 and remove the ports: mapping
from docker-compose.yml. Never publish 8502 to the public internet. Read-only
tools only; no ingest/delete is ever exposed.
"""
from __future__ import annotations

import json
import os

from fastapi import HTTPException

import auth
import mcp_server

BIND = os.getenv("ARKIV_MCP_BIND", "0.0.0.0")
PORT = int(os.getenv("ARKIV_MCP_PORT", "8502"))


def _extract_token(scope):
    """Pull a raw bearer token from the Authorization header only.

    No `?token=` query param: a token in a URL persists in uvicorn access logs,
    any reverse proxy in front of it, and browser history — three places that
    outlive the request and are not scrubbed. Clients that can't set a header
    should do so on their side instead."""
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            raw = value.decode("latin-1", "replace")
            if raw.lower().startswith("bearer "):
                return raw[7:].strip()
            return raw.strip()
    return ""


async def token_gate(app, scope, receive, send):
    """ASGI middleware: 401/403 anything without a valid arkiv token.

    Implemented as a plain ASGI middleware (not Starlette BaseHTTPMiddleware) so
    the long-lived SSE stream is never buffered or consumed by the gate.
    """
    if scope["type"] in ("http", "websocket"):
        client_ip = (scope.get("client") or ("", 0))[0]
        raw = _extract_token(scope)
        try:
            auth.resolve_raw_token(raw, client_ip)
        except HTTPException as exc:
            status = getattr(exc, "status_code", 401)
            body = json.dumps({"error": str(exc.detail)}).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": body})
            return
        except Exception:
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return
    await app(scope, receive, send)


class _Wrapped:
    """Minimal ASGI middleware wrapper (avoids Starlette add_middleware quirks)."""

    def __init__(self, app, middleware):
        self.app = app
        self.middleware = middleware

    async def __call__(self, scope, receive, send):
        await self.middleware(self.app, scope, receive, send)


def main():
    mcp_server._prewarm_vectordb()
    app = mcp_server.mcp.sse_app()
    app = _Wrapped(app, token_gate)
    import uvicorn
    uvicorn.run(app, host=BIND, port=PORT)


if __name__ == "__main__":
    main()
