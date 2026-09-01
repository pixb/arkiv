"""Regression tests for the MCP security hardening (PR A).

These guard the three security invariants introduced in this PR and
prevent accidental regressions (e.g. someone re-enabling DNS rebinding
protection, switching BIND back to 0.0.0.0, or restoring ?token= auth).
"""


def test_mcp_server_uses_disabled_dns_rebinding_protection():
    """MCP SDK 1.29+ default-rejects all Host headers; we must opt out.

    Without this, no LAN client can connect — every request returns 421.
    """
    import mcp_server
    sec = mcp_server.mcp.settings.transport_security
    assert sec.enable_dns_rebinding_protection is False


def test_mcp_http_server_binds_to_loopback_by_default():
    """mcp_http_server must default-bind to 127.0.0.1.

    LAN exposure must be an opt-in via ARKIV_MCP_BIND=0.0.0.0, not the
    default — a `docker compose up` shouldn't hand the LAN full read
    access to the media library.
    """
    import importlib
    import mcp_http_server
    importlib.reload(mcp_http_server)
    assert mcp_http_server.BIND == "127.0.0.1"


def test_mcp_http_server_rejects_url_token():
    """mcp_http_server must NOT accept ?token= as a fallback auth path.

    A token in the URL persists in uvicorn access logs, reverse-proxy
    logs, and browser history — three places that outlive the request
    and are not scrubbed. Only Authorization: Bearer <token> is allowed.
    """
    import mcp_http_server
    scope = {
        "type": "http",
        "headers": [],
        "query_string": b"token=secret123",
    }
    assert mcp_http_server._extract_token(scope) == ""
