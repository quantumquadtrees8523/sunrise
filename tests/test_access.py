"""Sunrise sits behind Home Assistant's own permissions: it switches only what's exposed to voice
assistants, a voice speaker can't change the house's setup, and the owner can keep everything
unexposed out of view too (access.py)."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import llm

from custom_components.sunrise.const import CONF_READ_UNEXPOSED, LLM_API_ID

from .conftest import SPEAKER, call, load_house, setup_integration


@pytest.fixture
async def house(hass: HomeAssistant):
    h = await load_house(hass)
    entry = await setup_integration(hass)
    return entry


def _ids(res: llm.ToolResult) -> set[str]:
    return {t["id"] for r in res.data["rooms"] for d in r["devices"] for t in d["things"]} | \
           {t["id"] for r in res.data["rooms"] for t in r["other"]}


async def test_act_switches_only_what_is_exposed(hass: HomeAssistant, house) -> None:
    calls = async_mock_service(hass, "light", "turn_on")
    async_expose_entity(hass, "conversation", "light.den_lamp", False)
    res = await call(hass, "act", {"action": "light.turn_on", "entity_ids": ["light.den_lamp"]})
    row = res.data["results"][0]
    assert row["result"] == "NOT EXPOSED" and "Expose" in row["why"] and calls == []
    # The owner exposes it in Home Assistant: from then on it works, with nothing to change in Sunrise.
    async_expose_entity(hass, "conversation", "light.den_lamp", True)
    res = await call(hass, "act", {"action": "light.turn_on", "entity_ids": ["light.den_lamp"]})
    assert res.data["results"][0]["result"] != "NOT EXPOSED" and len(calls) == 1


async def test_act_takes_its_things_only_from_entity_ids(hass: HomeAssistant, house) -> None:
    calls = async_mock_service(hass, "light", "turn_on")
    async_expose_entity(hass, "conversation", "light.den_lamp", False)
    for key in ("entity_id", "area_id", "device_id"):
        res = await call(hass, "act", {"action": "light.turn_on", "entity_ids": ["light.den_ceiling_1"],
                                       "data": {key: "light.den_lamp"}})
        assert res.error and "entity_ids" in res.data["error"]
    assert calls == []


async def test_suggestions_for_a_wrong_id_are_only_exposed_things(hass: HomeAssistant, house) -> None:
    async_mock_service(hass, "light", "turn_on")
    async_expose_entity(hass, "conversation", "light.kitchen_island_1", False)
    res = await call(hass, "act", {"action": "light.turn_on", "entity_ids": ["light.kitchen_island_9"]})
    assert "light.kitchen_island_1" not in res.data["results"][0]["nearest"]


async def test_a_voice_speaker_switches_things_but_never_changes_the_setup(hass: HomeAssistant, house) -> None:
    calls = async_mock_service(hass, "switch", "turn_off")
    res = await call(hass, "act", {"action": "switch.turn_off", "entity_ids": ["switch.study_plug"]}, user_id=SPEAKER)
    assert not res.error and len(calls) == 1
    for tool, args in [("registry_edit", {"op": "rename", "target": "switch.study_plug", "value": "Desk plug"}),
                       ("routine", {"op": "save", "config": {"alias": "x", "triggers": [], "actions": []}}),
                       ("backup", {"op": "create"}), ("undo", {"change_id": "c1"}),
                       ("fix_device", {"op": "reload_entry", "target": "x"}), ("discovered", {"op": "accept", "flow_id": "x"})]:
        res = await call(hass, tool, args, user_id=SPEAKER)
        assert res.error and "administrator" in res.data["error"], tool
    assert er.async_get(hass).async_get("switch.study_plug").name is None
    # Looking is still fine from a speaker.
    for tool, args in [("routine", {"op": "list"}), ("backup", {}), ("discovered", {}), ("house_map", {})]:
        assert not (await call(hass, tool, args, user_id=SPEAKER)).error, tool


async def test_the_owner_can_keep_unexposed_things_out_of_view(hass: HomeAssistant, house, monkeypatch) -> None:
    from .test_tools import _network  # noqa: PLC0415

    _network(monkeypatch)  # the plug's address check stays in the test
    async_expose_entity(hass, "conversation", "switch.garage_plug", False)
    async_expose_entity(hass, "conversation", "sensor.garage_plug_signal_strength", False)
    # By default the read tools see it (diagnosis needs to), read only.
    assert "switch.garage_plug" in _ids(await call(hass, "house_map"))
    diag = await call(hass, "diagnose_device", {"target": "Garage plug"})
    assert len(diag.data["devices"]) == 1 and "Garage plug" in str(diag.data["devices"])
    # The owner says no in Sunrise's options: it's gone from every read, and nothing else is.
    result = await hass.config_entries.options.async_init(house.entry_id)
    assert result["data_schema"]({})[CONF_READ_UNEXPOSED] is True
    await hass.config_entries.options.async_configure(result["flow_id"], {CONF_READ_UNEXPOSED: False})
    await hass.async_block_till_done()
    seen = _ids(await call(hass, "house_map", {"everything": True}))
    assert "switch.garage_plug" not in seen and "switch.study_plug" in seen
    diag = await call(hass, "diagnose_device", {"target": "Garage plug"})
    assert diag.data["devices"] == []
    audit = await call(hass, "audit")
    assert "Garage plug" not in str(audit.data) and "Study" in str(audit.data)
    # And back on: it's there again, with no restart.
    result = await hass.config_entries.options.async_init(house.entry_id)
    await hass.config_entries.options.async_configure(result["flow_id"], {CONF_READ_UNEXPOSED: True})
    await hass.async_block_till_done()
    assert "switch.garage_plug" in _ids(await call(hass, "house_map"))


async def test_the_speakers_room_is_what_the_lights_means(hass: HomeAssistant, house) -> None:
    devs = dr.async_get(hass)
    sat = next(d for d in devs.devices if d.name == "Voice Satellite 1")
    devs.async_update_device(sat.id, area_id=ar.async_get(hass).async_get_area_by_name("Kitchen").id)
    res = await call(hass, "house_map", user_id=SPEAKER, device_id=sat.id)
    assert res.data["asking_from"] == "Kitchen"
    ctx = llm.LLMContext(platform="assist_pipeline", context=None, language="en", assistant="conversation", device_id=sat.id)
    api = await llm.async_get_api(hass, LLM_API_ID, ctx)
    assert "speaking from a device in Kitchen" in api.api_prompt
    assert "asking_from" not in (await call(hass, "house_map")).data
