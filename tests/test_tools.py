"""Each tool's happy path and refusal paths, on the sample house (fixture)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from .conftest import call, load_house, setup_integration


@pytest.fixture
async def house(hass: HomeAssistant):
    h = await load_house(hass)
    await setup_integration(hass)
    return h


async def test_house_map_rooms_devices_states(hass: HomeAssistant, house) -> None:
    res = await call(hass, "house_map")
    assert not res.error
    rooms = {r["room"]: r for r in res.data["rooms"]}
    assert set(rooms) == {"Living Room", "Kitchen", "Bedroom", "Office", None}
    kitchen = {d["device"] for d in rooms["Kitchen"]["devices"]}
    assert {"Kitchen Pendant 1", "Kitchen Pendant 2", "Kitchen Pendant 3"} <= kitchen
    lamp = next(t for d in rooms["Living Room"]["devices"] for t in d["things"] if t["id"] == "light.living_room_lamp")
    assert lamp["state"] == "on"
    # diagnostic and config things stay out of the compact map
    assert not any("signal_strength" in t["id"] for r in res.data["rooms"] for d in r["devices"] for t in d["things"])
    c = res.data["counts"]
    assert (c["entities"], c["unavailable"] + c["unknown"], c["no_area"], c["devices"], c["areas"], c["floors"]) == (167, 80, 69, 28, 4, 0)  # the sample house plus sensor.sunrise_memory
    one = await call(hass, "house_map", {"room": "kitchen"})
    assert [r["room"] for r in one.data["rooms"]] == ["Kitchen"]


def _light_service(hass: HomeAssistant, lands: bool = True):
    async def handle(call: ServiceCall) -> None:
        if not lands:
            return
        for eid in call.data["entity_id"]:
            on = call.service == "turn_on"
            attrs = dict(hass.states.get(eid).attributes)
            if on and "brightness_pct" in call.data:
                attrs["brightness"] = round(call.data["brightness_pct"] * 255 / 100)
            hass.states.async_set(eid, "on" if on else "off", attrs)

    hass.services.async_register("light", "turn_on", handle)
    hass.services.async_register("light", "turn_off", handle)


async def test_act_checked_after_read_back(hass: HomeAssistant, house) -> None:
    _light_service(hass)
    res = await call(hass, "act", {"action": "light.turn_on", "entity_ids": ["light.kitchen_pendant_1"], "data": {"brightness_pct": 40}})
    row = res.data["results"][0]
    assert row["result"] == "CHECKED" and row["now"] == "on" and row["brightness_pct"] == 40


async def test_act_not_confirmed_when_state_doesnt_change(hass: HomeAssistant, house) -> None:
    _light_service(hass, lands=False)
    res = await call(hass, "act", {"action": "light.turn_on", "entity_ids": ["light.kitchen_pendant_1"]})
    assert res.data["results"][0]["result"] == "NOT CONFIRMED"


async def test_act_never_tries_unavailable_things(hass: HomeAssistant, house) -> None:
    calls = async_mock_service(hass, "light", "turn_off")
    res = await call(hass, "act", {"action": "light.turn_off", "entity_ids": ["light.kitchen_pendant_2"]})
    assert res.data["results"][0]["result"] == "UNREACHABLE"
    assert calls == []


async def test_act_refuses_locks_without_a_yes_and_unknown_ids(hass: HomeAssistant, house) -> None:
    hass.states.async_set("lock.front_door", "locked", {"friendly_name": "Front door"})
    calls = async_mock_service(hass, "lock", "unlock")
    async_mock_service(hass, "light", "turn_on")
    res = await call(hass, "act", {"action": "lock.unlock", "entity_ids": ["lock.front_door"]})
    assert res.data["results"][0]["result"] == "REFUSED" and calls == []
    res = await call(hass, "act", {"action": "light.turn_on", "entity_ids": ["light.kitchen_pendant_9"]})
    row = res.data["results"][0]
    assert row["result"] == "NOT FOUND" and "light.kitchen_pendant_1" in row["nearest"]
    bad = await call(hass, "act", {"action": "light.explode", "entity_ids": ["light.kitchen_pendant_1"]})
    assert bad.error


async def test_audit_finds_the_problems(hass: HomeAssistant, house) -> None:
    res = await call(hass, "audit")
    d = res.data
    wiz = next(g for g in d["dead"] if g["integration"] == "wiz")
    assert wiz["count"] == 8
    leftovers = {x["id"] for x in d["leftovers"]}
    assert len([x for x in leftovers if x.startswith("automation.")]) == 5
    assert "automation.night_mode" not in leftovers
    kinds = {x["kind"]: x for x in d["duplicates"]}
    assert set(kinds["automation"]["ids"]) == {"automation.night_mode", "automation.night_mode_2"}
    assert len(kinds["weather"]["ids"]) == 2
    assert d["noisy"]["wiz"]["count"] == 956
    assert "<address>" in d["noisy"]["wiz"]["top"]
    assert d["changed_since_last"] is None
    assert "Home Assistant Voice 01" in d["unroomed"]["devices"]
    # A second audit says what changed.
    hass.states.async_set("light.kitchen_pendant_2", "off", {"friendly_name": "Kitchen Pendant 2"})
    for eid in ("sensor.kitchen_pendant_2_signal_strength",):
        hass.states.async_set(eid, "-70")
    again = await call(hass, "audit")
    assert "Kitchen Pendant 2" in again.data["changed_since_last"]["back_now"]


async def test_profile_detects_and_merges(hass: HomeAssistant, house) -> None:
    res = await call(hass, "profile_get", {"refresh": True})
    p = res.data
    assert p["isp"] == "fios"
    assert "binary_sensor.fios_router_wan_status" in p["router"]["sensors"]
    assert p["counts"]["entities"] == 167  # the sample house plus sensor.sunrise_memory
    assert p["access"]["sunrise_tools"] is True and p["access"]["mcp_server"] is False
    upd = await call(hass, "profile_update", {"updates": {"access": {"ssh": True}, "quirks": ["hallway bulb is on the stairs switch"]}})
    assert upd.data["access"]["ssh"] is True and upd.data["access"]["sunrise_tools"] is True
    again = await call(hass, "profile_get", {"refresh": True})
    assert again.data["quirks"] == ["hallway bulb is on the stairs switch"]
    bad = await call(hass, "profile_update", {"updates": {"password": "x"}})
    assert bad.error


async def test_profile_install_type(hass: HomeAssistant, house) -> None:
    with patch("homeassistant.helpers.system_info.async_get_system_info", return_value={"installation_type": "Home Assistant Container"}):
        res = await call(hass, "profile_get", {"refresh": True})
    assert res.data["install_type"] == "container"


async def test_registry_edits_read_back_and_undo(hass: HomeAssistant, house) -> None:
    res = await call(hass, "registry_edit", {"op": "rename", "target": "light.hallway_light", "value": "Hall light"})
    assert res.data["ok"] and res.data["read_back"] == "Hall light"
    await call(hass, "undo", {"change_id": res.data["change_id"]})
    assert er.async_get(hass).async_get("light.hallway_light").name is None
    room = await call(hass, "registry_edit", {"op": "create_area", "value": "Hallway"})
    assert room.data["read_back"]
    dev_id = er.async_get(hass).async_get("light.hallway_light").device_id
    moved = await call(hass, "registry_edit", {"op": "set_area", "target": dev_id, "value": "Hallway"})
    assert moved.data["ok"] and moved.data["read_back"] == "Hallway"
    nope = await call(hass, "registry_edit", {"op": "set_area", "target": dev_id, "value": "Garage"})
    assert nope.error and "no room" in nope.data["error"]
    await call(hass, "undo", {"change_id": moved.data["change_id"]})
    await call(hass, "undo", {"change_id": room.data["change_id"]})
    assert ar.async_get(hass).async_get_area_by_name("Hallway") is None


async def test_remove_entity_only_for_leftovers_and_undo_puts_it_back(hass: HomeAssistant, house) -> None:
    refused = await call(hass, "registry_edit", {"op": "remove_entity", "target": "automation.night_mode_2"})
    assert refused.error and "isn't a leftover" in refused.data["error"]
    res = await call(hass, "registry_edit", {"op": "remove_entity", "target": "automation.vacation_lights"})
    assert res.data["ok"]
    assert er.async_get(hass).async_get("automation.vacation_lights") is None
    await call(hass, "undo", {"change_id": res.data["change_id"]})
    assert er.async_get(hass).async_get("automation.vacation_lights") is not None


async def test_backup_create_confirms_it_is_listed(hass: HomeAssistant, house) -> None:
    class B:
        def __init__(self, i):
            self.backup_id, self.name, self.date, self.size = f"b{i}", f"backup {i}", f"2026-11-24T20:0{i}:00", 1_000_000

    class Manager:
        local_backup_agents = {"backup.local": object()}

        def __init__(self):
            self.made = [B(1)]
            self.agents = None

        async def async_get_backups(self):
            return {b.backup_id: b for b in self.made}, {}

        async def async_create_backup(self, **kw):
            self.agents = kw["agent_ids"]
            self.made.append(B(2))

    from homeassistant.components.backup.const import DATA_MANAGER

    hass.config.components.add("backup")
    hass.data[DATA_MANAGER] = m = Manager()
    res = await call(hass, "backup", {"op": "create"})
    assert res.data["confirmed"] is True and res.data["backup"]["id"] == "b2"
    assert m.agents == ["backup.local"]  # local storage only, never a cloud location
    listed = await call(hass, "backup", {"op": "list"})
    assert listed.data["count"] == 2

    async def nothing(**kw):
        return None

    m.async_create_backup = nothing
    res = await call(hass, "backup", {"op": "create"})
    assert res.data["confirmed"] is False and "Don't make changes" in res.data["error"]


async def test_backup_without_backup_integration_says_dont_change(hass: HomeAssistant, house) -> None:
    assert "backup" not in hass.config.components
    res = await call(hass, "backup", {"op": "create"})
    assert res.data["confirmed"] is False


async def test_suggestions_are_remembered(hass: HomeAssistant, house) -> None:
    await call(hass, "suggestions", {"op": "record", "idea": "Porch light on at sunset", "status": "declined", "evidence": "11 of 14 days"})
    await call(hass, "suggestions", {"op": "record", "idea": "porch light  on at sunset", "status": "declined"})
    res = await call(hass, "suggestions", {"op": "list"})
    assert len(res.data["suggestions"]) == 1 and res.data["suggestions"][0]["status"] == "declined"


async def test_log_run_scores_lists_and_exports_stripped(hass: HomeAssistant, house) -> None:
    good = {c: True for c in ("R1", "R2", "R3", "R4", "R5", "R6")}
    ok = await call(hass, "log_run", {"skill": "build-a-skill", "request": "get my lights back", "checks": good,
                                      "outcome": "3 back"})
    assert ok.data["met_rubric"]
    bad = await call(hass, "log_run", {"skill": "build-a-skill", "request": "get my lights back",
                                       "checks": {**good, "R6": False}, "notes": "said 10.0.0.220 and light.kitchen_pendant_2 to Kitchen Pendant 2"})
    assert bad.data["run"]["score"] == 5 and "skill_update" in bad.data["next"]
    broke = await call(hass, "log_run", {"skill": "build-a-skill", "checks": good, "broke_rule": True})
    assert broke.data["run"]["score"] == 0
    listed = await call(hass, "log_run", {"op": "list", "below": 6})
    assert len(listed.data["runs"]) == 2
    exported = await call(hass, "log_run", {"op": "export"})
    text = open(exported.data["file"], encoding="utf-8").read()
    assert "10.0.0.220" not in text and "light.kitchen_pendant_2" not in text and "Kitchen Pendant 2" not in text
    calls = await call(hass, "log_run", {"op": "calls"})
    assert [c["tool"] for c in calls.data["calls"]][:2] == ["log_run", "log_run"]


async def test_non_admin_user_can_read_but_not_change(hass: HomeAssistant, house, hass_read_only_user) -> None:
    read = await call(hass, "house_map", user_id=hass_read_only_user.id)
    assert not read.error
    write = await call(hass, "registry_edit", {"op": "rename", "target": "light.hallway_light", "value": "x"},
                       user_id=hass_read_only_user.id)
    assert write.error and "administrator" in write.data["error"]
    assert er.async_get(hass).async_get("light.hallway_light").name is None


async def test_usage_without_recorder_says_so(hass: HomeAssistant, house) -> None:
    res = await call(hass, "usage")
    assert "no usage to learn from" in res.data["error"]
