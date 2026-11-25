"""End to end over HTTP: Home Assistant's own MCP Server serves this integration's API at
/api/mcp/sunrise, the same request any agent sends."""

from __future__ import annotations

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from .conftest import load_house, setup_integration

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


async def test_mcp_server_lists_and_calls_our_tools(hass: HomeAssistant, hass_client, hass_access_token, socket_enabled) -> None:
    await load_house(hass)
    await setup_integration(hass)
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "http", {})
    MockConfigEntry(domain="mcp_server", data={"llm_hass_api": ["sunrise"], "all_llm_apis": False,
                                               "require_admin": True}).add_to_hass(hass)
    assert await async_setup_component(hass, "mcp_server", {})
    await hass.async_block_till_done()
    client = await hass_client()

    async def rpc(method, params=None, i=1):
        resp = await client.post("/api/mcp/sunrise", headers=HEADERS,
                                 data=json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}}))
        assert resp.status == 200, await resp.text()
        return (await resp.json())["result"]

    init = await rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
    assert init["serverInfo"]["name"] == "home-assistant"
    tools = {t["name"]: t for t in (await rpc("tools/list"))["tools"]}
    assert "house_map" in tools and tools["house_map"]["annotations"]["readOnlyHint"] is True
    assert tools["act"]["annotations"]["destructiveHint"] is True
    prompts = (await rpc("prompts/list"))["prompts"]
    assert prompts[0]["name"] == "Sunrise"
    text = (await rpc("prompts/get", {"name": "Sunrise"}))["messages"][0]["content"]["text"]
    assert "never change router settings" in text
    res = await rpc("tools/call", {"name": "audit", "arguments": {}})
    data = json.loads(res["content"][0]["text"])
    assert not res["isError"] and data["counts"]["entities"] >= 166

    # A plain standard-library client (blocking) against the same endpoint.
    from mcp_client import MCP

    ha = MCP(str(client.make_url("/")), hass_access_token)
    listed = await hass.async_add_executor_job(ha.tools)
    assert {t["name"] for t in listed} >= {"backup", "log_run", "skill_revert"}
    skills = await hass.async_add_executor_job(ha.call, "list_skills", {})
    assert any(x["name"] == "build-a-skill" for x in skills["skills"])
