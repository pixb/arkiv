"""Regression tests for the MCP security hardening (PR A).

These guard the three security invariants introduced in this PR and
prevent accidental regressions (e.g. someone re-enabling DNS rebinding
protection, switching BIND back to 127.0.0.1, or restoring ?token= auth).

Why these tests skip on missing mcp / Python <3.10:
- `mcp` is a hard runtime dep of `mcp_server.py` and `mcp_http_server.py`,
  but in requirements.txt it carries a `python_version >= '3.10'` marker
  (MCP SDK 1.29+ dropped 3.9 support). The CI `test (3.9)` job therefore
  installs without mcp — importing mcp_server raises ModuleNotFoundError.
- We skip rather than fail so the 3.9 leg can still validate the rest of
  the suite. The 3.10/3.12 legs are the real gate; missing mcp on 3.9 is
  expected and intentional.
"""
import sys

import pytest

# All three tests depend on importing mcp_server / mcp_http_server, which
# both `import mcp`. Skip the whole module if mcp is not importable
# (Python 3.9) — the invariant they guard is a property of code that does
# not run there anyway.
pytest.importorskip("mcp", reason="mcp is not installed on this Python (>=3.10 required)")


def test_mcp_server_uses_disabled_dns_rebinding_protection():
    """MCP SDK 1.29+ default-rejects all Host headers; we must opt out.

    Without this, no LAN client can connect — every request returns 421.
    """
    import mcp_server
    sec = mcp_server.mcp.settings.transport_security
    assert sec.enable_dns_rebinding_protection is False


def test_mcp_http_server_binds_to_lan_by_default():
    """mcp_http_server must default-bind to 0.0.0.0.

    arkiv's deployment model is "one machine runs arkiv, the rest of the LAN
    connects via MCP clients". Loopback-bind must be an opt-in via
    ARKIV_MCP_BIND=127.0.0.1, not the default.
    """
    import importlib
    import mcp_http_server
    importlib.reload(mcp_http_server)
    assert mcp_http_server.BIND == "0.0.0.0"


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
