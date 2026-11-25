"""The integration's shell: one-click config flow, the LLM API it registers, the tools' names,
schemas and honest annotations as Home Assistant's MCP Server would list them, and its prompt."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.components.mcp_server.server import _format_tool
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import llm

from custom_components.sunrise.api import SPECS
from custom_components.sunrise.const import DOMAIN, LLM_API_ID, LLM_API_NAME

from .conftest import call, setup_integration

EXPECTED_TOOLS = {"house_map", "act", "audit", "diagnose_device", "fix_device", "registry_edit", "undo", "changes", "routine",
                  "backup", "network_check", "usage", "list_skills", "get_skill", "skill_update", "log_run", "memory_list",
                  "memory_read", "memory_write", "memory_delete", "behavior_log", "behavior_revert"}


async def test_config_flow_one_click_and_single_instance(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {}
    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert again["type"] is FlowResultType.ABORT


async def test_registers_llm_api_and_unregisters_on_unload(hass: HomeAssistant) -> None:
    entry = await setup_integration(hass)
    apis = {a.id: a for a in llm.async_get_apis(hass)}
    assert LLM_API_ID in apis and apis[LLM_API_ID].name == LLM_API_NAME
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert LLM_API_ID not in {a.id for a in llm.async_get_apis(hass)}


async def test_tools_listed_with_schemas_and_annotations(hass: HomeAssistant) -> None:
    await setup_integration(hass)
    ctx = llm.LLMContext(platform="mcp_server", context=None, language="en", assistant="conversation", device_id=None)
    api = await llm.async_get_api(hass, LLM_API_ID, ctx)
    ours = [t for t in api.tools if t.integration == DOMAIN]
    assert {t.name for t in ours} == EXPECTED_TOOLS
    for tool in ours:
        mcp = _format_tool(tool, api.custom_serializer)  # exactly what the MCP Server sends
        assert mcp.description and mcp.title
        assert mcp.inputSchema["type"] == "object"
        ann = mcp.annotations
        if ann.readOnlyHint:
            assert ann.destructiveHint is False
    by = {t.name: t.annotations for t in ours}
    for name in ("house_map", "audit", "diagnose_device", "network_check", "list_skills", "get_skill", "behavior_log", "usage"):
        assert by[name].read_only, name
    for name in ("act", "fix_device", "registry_edit", "skill_update", "undo", "behavior_revert"):
        assert not by[name].read_only and by[name].destructive, name
    assert by["act"].open_world  # it can call any action, some of which reach outside
    assert all(not by[n].open_world for n in EXPECTED_TOOLS - {"act"})
    act = _format_tool(next(t for t in ours if t.name == "act"), api.custom_serializer)
    assert act.inputSchema["required"] == ["action"]
    assert act.inputSchema["properties"]["entity_ids"]["type"] == "array"


async def test_prompt_has_rules_and_skill_index(hass: HomeAssistant) -> None:
    await setup_integration(hass)
    ctx = llm.LLMContext(platform="mcp_server", context=None, language="en", assistant="conversation", device_id=None)
    api = await llm.async_get_api(hass, LLM_API_ID, ctx)
    for words in ("never change router settings", "read back", "build-a-skill"):
        assert words in api.api_prompt


async def test_built_in_skills_installed_outside_custom_components(hass: HomeAssistant) -> None:
    await setup_integration(hass)
    res = await call(hass, "list_skills")
    names = {s["name"] for s in res.data["skills"]}
    assert names == {"add-a-device", "build-a-skill", "device-diagnosis", "improve-home", "learn-the-house", "routines", "undo", "wifi-diagnosis"}
    folder = hass.config.path("sunrise", "skills", "build-a-skill")
    assert "custom_components" not in folder
    got = await call(hass, "get_skill", {"name": "build-a-skill", "include_references": True})
    assert "Gap check" in got.data["text"]
    assert "R1" in got.data["references"]["RUBRIC.md"]


def test_every_spec_has_a_handler_and_description() -> None:
    assert len({s.name for s in SPECS}) == len(SPECS)
    for s in SPECS:
        assert len(s.description) > 40, s.name
