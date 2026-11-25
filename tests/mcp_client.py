"""A tiny MCP client for Home Assistant's MCP Server (Streamable HTTP, stateless: one JSON-RPC
request per POST). Standard library only, so the test needs nothing installed.

    ha = MCP("http://10.0.0.213:8123", token)   # a long-lived token of an admin user
    ha.call("backup", {"op": "create"})            # -> the tool's JSON result
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

API = "sunrise"


class ToolError(RuntimeError):
    pass


class MCP:
    def __init__(self, url: str, token: str, api: str = API, timeout: float = 70.0) -> None:
        self.endpoint = f"{url.rstrip('/')}/api/mcp/{api}"
        self.token = token
        self.timeout = timeout
        self._id = 0

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}).encode()
        req = urllib.request.Request(self.endpoint, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310  (the house's own HA on the LAN)
            out = json.loads(resp.read().decode())
        if "error" in out:
            raise ToolError(out["error"].get("message", str(out["error"])))
        return out["result"]

    def tools(self) -> list[dict[str, Any]]:
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "sunrise-tests", "version": "0"}})
        return self._rpc("tools/list")["tools"]

    def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        res = self._rpc("tools/call", {"name": name, "arguments": args or {}})
        data = json.loads(res["content"][0]["text"]) if res.get("content") else {}
        if res.get("isError"):
            raise ToolError(data.get("error") if isinstance(data, dict) else str(data))
        return data
