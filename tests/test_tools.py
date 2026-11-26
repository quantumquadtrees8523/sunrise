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
    assert set(rooms) == {"Den", "Kitchen", "Loft", "Study", None}
    kitchen = {d["device"] for d in rooms["Kitchen"]["devices"]}
    assert {"Kitchen Island 1", "Kitchen Island 2", "Kitchen Island 3"} <= kitchen
    lamp = next(t for d in rooms["Den"]["devices"] for t in d["things"] if t["id"] == "light.den_lamp")
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
    res = await call(hass, "act", {"action": "light.turn_on", "entity_ids": ["light.kitchen_island_1"], "data": {"brightness_pct": 40}})
    row = res.data["results"][0]
    assert row["result"] == "CHECKED" and row["now"] == "on" and row["brightness_pct"] == 40


async def test_act_not_confirmed_when_state_doesnt_change(hass: HomeAssistant, house) -> None:
    _light_service(hass, lands=False)
    res = await call(hass, "act", {"action": "light.turn_on", "entity_ids": ["light.kitchen_island_1"]})
    assert res.data["results"][0]["result"] == "NOT CONFIRMED"


async def test_act_never_tries_unavailable_things(hass: HomeAssistant, house) -> None:
    calls = async_mock_service(hass, "light", "turn_off")
    res = await call(hass, "act", {"action": "light.turn_off", "entity_ids": ["light.kitchen_island_2"]})
    assert res.data["results"][0]["result"] == "UNREACHABLE"
    assert calls == []


async def test_act_refuses_locks_without_a_yes_and_unknown_ids(hass: HomeAssistant, house) -> None:
    hass.states.async_set("lock.front_door", "locked", {"friendly_name": "Front door"})
    calls = async_mock_service(hass, "lock", "unlock")
    async_mock_service(hass, "light", "turn_on")
    res = await call(hass, "act", {"action": "lock.unlock", "entity_ids": ["lock.front_door"]})
    assert res.data["results"][0]["result"] == "REFUSED" and calls == []
    res = await call(hass, "act", {"action": "light.turn_on", "entity_ids": ["light.kitchen_island_9"]})
    row = res.data["results"][0]
    assert row["result"] == "NOT FOUND" and "light.kitchen_island_1" in row["nearest"]
    bad = await call(hass, "act", {"action": "light.explode", "entity_ids": ["light.kitchen_island_1"]})
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
    assert "Voice Satellite 1" in d["unroomed"]["devices"]
    # A second audit says what changed.
    hass.states.async_set("light.kitchen_island_2", "off", {"friendly_name": "Kitchen Island 2"})
    for eid in ("sensor.kitchen_island_2_signal_strength",):
        hass.states.async_set(eid, "-70")
    again = await call(hass, "audit")
    assert "Kitchen Island 2" in again.data["changed_since_last"]["back_now"]


async def test_house_map_says_how_the_house_is_set_up(hass: HomeAssistant, house) -> None:
    res = await call(hass, "house_map")
    p = res.data["setup"]
    assert "isp_guess" not in p  # the router by its own maker and model, never a guessed provider
    assert p["router"]["devices"][0]["manufacturer"] == "Acme Networks" and p["router"]["devices"][0]["found_by"] == "integration"
    assert "binary_sensor.acme_ax3000_wan_status" in p["router"]["sensors"]
    assert not any("external_ip" in s for s in p["router"]["sensors"])
    assert res.data["counts"]["entities"] == 167  # the sample house plus sensor.sunrise_memory
    assert p["access"]["sunrise_tools"] is True and p["access"]["mcp_server"] is False
    assert "setup" not in (await call(hass, "house_map", {"room": "Kitchen"})).data


async def test_setup_install_type(hass: HomeAssistant, house) -> None:
    with patch("homeassistant.helpers.system_info.async_get_system_info", return_value={"installation_type": "Home Assistant Container"}):
        res = await call(hass, "house_map")
    assert res.data["setup"]["install_type"] == "container"


def _network(monkeypatch, answers: dict[str, str] | None = None) -> list:
    """No real connections: each address answers a TCP check as given (default "silent"); WiZ bulbs don't answer."""
    from custom_components.sunrise import net as N  # noqa: PLC0415

    asked: list = []

    def reach(host, port, timeout=1.0):
        asked.append((N._lan(host), port))
        return (answers or {}).get(host, "silent")

    monkeypatch.setattr(N, "tcp_reach", reach)
    monkeypatch.setattr(N, "tcp_open", lambda host, port, timeout=1.0: reach(host, port, timeout) == "open")
    monkeypatch.setattr(N, "wiz_probe", lambda host, net: {"answers": False})
    return asked


async def test_diagnose_any_device_without_a_helper(hass: HomeAssistant, house, monkeypatch) -> None:
    """The general path: a Wi-Fi plug Sunrise has no helper for gets HA's record, a check of its
    address, and advice tailored to its maker and model."""
    asked = _network(monkeypatch)
    res = await call(hass, "diagnose_device", {"target": "Garage plug"})
    row = res.data["devices"][0]
    assert (row["integration"], row["manufacturer"], row["model"], row["connection"]) == ("shelly", "Shelly", "Plug US", "network")
    assert row["cause"] == "unreachable" and row["answers"] is False and asked == [("127.0.0.234", 80)]  # its integration's port
    assert "no helper for shelly" in row["tailor"] and "Shelly Plug US" in row["tailor"]
    assert any("Garage plug" in line for line in res.data["for_the_person"])
    assert res.data["errors_since_start"] == {"shelly": 12} and "helpers" not in res.data
    # Still silent after a power cycle: its maker's own steps to reconnect it, remembered next time.
    again = await call(hass, "diagnose_device", {"target": "Garage plug", "power_cycled": True})
    assert again.data["devices"][0]["cause"] == "still_unreachable" and "maker's own steps" in again.data["devices"][0]["fix"]["person"]
    assert (await call(hass, "diagnose_device", {"target": "Garage plug"})).data["devices"][0]["cause"] == "still_unreachable"
    # Back on the network (a refused port means the device itself answered): reconnect in software.
    _network(monkeypatch, {"127.0.0.234": "refused"})
    back = (await call(hass, "diagnose_device", {"target": "Garage plug"})).data["devices"][0]
    assert back["cause"] == "not_loaded" and back["fix"]["op"] == "reload_entry" and "tailor" not in back
    # Moving it to a new address is only for kinds with a helper.
    moved = await call(hass, "fix_device", {"op": "update_host", "target": back["device_id"], "host": "127.0.0.240"})
    assert moved.error and "helper" in moved.data["error"] and "wiz" in moved.data["error"]


async def test_diagnose_a_radio_device(hass: HomeAssistant, house, monkeypatch) -> None:
    asked = _network(monkeypatch)
    door = (await call(hass, "diagnose_device", {"target": "Back door sensor"})).data["devices"][0]
    assert door["connection"] == "zigbee" and door["cause"] == "radio_silent" and "battery" in door["fix"]["person"]
    assert "IKEA of Sweden PARASOLL door sensor" in door["tailor"] and asked == []  # no address to check
    lamp = (await call(hass, "diagnose_device", {"target": "Loft reading light"})).data["devices"][0]
    assert (lamp["manufacturer"], lamp["connection"], lamp["cause"]) == ("Signify Netherlands B.V.", "zigbee", "ok")


async def test_network_check_reads_any_router_and_any_signal(hass: HomeAssistant, house, monkeypatch) -> None:
    _network(monkeypatch)
    d = (await call(hass, "network_check")).data
    assert d["router"]["devices"] == [{"name": "Acme AX3000", "manufacturer": "Acme Networks", "model": "AX3000",
                                       "integration": "upnp", "found_by": "integration"}]
    assert d["internet"] == "on" and "Acme AX3000 Download speed" in d["router"]["sensors"]
    assert not any("External IP" in k for k in d["router"]["sensors"])
    plug = next(s for s in d["signal"] if s["device"] == "Study plug")
    assert plug == {"device": "Study plug", "room": "Study", "rssi": -65, "signal": "good", "from": "home_assistant"}
    assert d["errors_since_start"]["shelly"] == 12 and d["network_devices"]["unreachable"] >= 9


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


async def test_a_checkpoint_never_goes_to_a_cloud_location(hass: HomeAssistant, house) -> None:
    """Checkpoints are local only: with cloud locations set up beside the local one, only the local one is used;
    with no local one, nothing is made."""
    class Manager:
        local_backup_agents = {"backup.local": object()}
        backup_agents = {"cloud.cloud": object(), "backup.local": object(), "remote_drive.main": object()}
        asked: list = []

        async def async_get_backups(self):
            return {}, {}

        async def async_create_backup(self, **kw):
            self.asked.append(kw["agent_ids"])

    from homeassistant.components.backup.const import DATA_MANAGER

    hass.config.components.add("backup")
    hass.data[DATA_MANAGER] = m = Manager()
    await call(hass, "backup", {"op": "create"})
    assert m.asked == [["backup.local"]]
    m.local_backup_agents = {}
    res = await call(hass, "backup", {"op": "create"})
    assert res.data["confirmed"] is False and "no local" in res.data["error"] and len(m.asked) == 1


async def test_routines_are_checked_saved_tried_listed_and_undone(hass: HomeAssistant, house) -> None:
    from pathlib import Path

    from homeassistant.setup import async_setup_component

    Path(hass.config.path("configuration.yaml")).write_text("automation: !include automations.yaml\n", encoding="utf-8")
    Path(hass.config.path("automations.yaml")).write_text("[]\n", encoding="utf-8")
    assert await async_setup_component(hass, "automation", {"automation": []})
    calls = async_mock_service(hass, "light", "turn_off")
    lamp = "light.den_lamp"
    config = {"alias": "Lamp off at night", "triggers": [{"trigger": "time", "at": "23:15:00"}],
              "actions": [{"action": "light.turn_off", "target": {"entity_id": lamp}}]}

    bad = await call(hass, "routine", {"op": "check", "config": {"alias": "x", "triggers": [{"trigger": "nonsense"}], "actions": []}})
    assert bad.data["valid"] is False and bad.data["saved"] is False
    ghost = {**config, "actions": [{"action": "light.turn_off", "target": {"entity_id": "light.no_such_lamp"}}]}
    res = await call(hass, "routine", {"op": "save", "config": ghost})
    assert res.data["saved"] is False and res.data["missing"][0]["id"] == "light.no_such_lamp"
    dry = await call(hass, "routine", {"op": "check", "config": config})
    assert dry.data == {"ok": True, "valid": True, "saved": False, "missing": [], "guarded": [], "makes_sound": False}

    saved = await call(hass, "routine", {"op": "save", "config": config})
    rid, eid = saved.data["id"], saved.data["entity_id"]
    assert saved.data["ok"] and saved.data["on"] and hass.states.get(eid).name == "Lamp off at night"
    listed = await call(hass, "routine", {"op": "list"})
    assert any(r["id"] == rid and r["editable"] for r in listed.data["routines"])
    tried = await call(hass, "routine", {"op": "try", "id": rid})
    assert tried.data["ran"] and calls and calls[-1].data["entity_id"] == [lamp]

    log = await call(hass, "changes")
    assert log.data["changes"][0]["what"] == "routine_save" and log.data["changes"][0]["undone"] is False
    undone = await call(hass, "undo", {"change_id": saved.data["change_id"]})
    assert undone.data["ok"] and hass.states.get(eid) is None
    assert (await call(hass, "changes")).data["changes"][0]["undone"] is True


async def test_a_routine_that_moves_a_lock_or_makes_sound_needs_a_yes(hass: HomeAssistant, house) -> None:
    from pathlib import Path

    from homeassistant.setup import async_setup_component

    Path(hass.config.path("configuration.yaml")).write_text("automation: !include automations.yaml\n", encoding="utf-8")
    Path(hass.config.path("automations.yaml")).write_text("[]\n", encoding="utf-8")
    assert await async_setup_component(hass, "automation", {"automation": []})
    hass.states.async_set("lock.front_door", "locked")
    config = {"alias": "Unlock at 7", "triggers": [{"trigger": "time", "at": "07:00:00"}],
              "actions": [{"action": "lock.unlock", "target": {"entity_id": "lock.front_door"}}]}
    res = await call(hass, "routine", {"op": "save", "config": config})
    assert res.data["saved"] is False and res.data["guarded"] == ["lock.front_door"]
    yes = await call(hass, "routine", {"op": "save", "config": config, "confirmed": True})
    assert yes.data["saved"] is True
    assert (await call(hass, "routine", {"op": "try", "id": yes.data["id"]})).data["ran"] is False
    gone = await call(hass, "routine", {"op": "delete", "id": yes.data["id"]})
    assert gone.data["ok"] and hass.states.get(yes.data["entity_id"]) is None


async def test_backup_without_backup_integration_says_dont_change(hass: HomeAssistant, house) -> None:
    assert "backup" not in hass.config.components
    res = await call(hass, "backup", {"op": "create"})
    assert res.data["confirmed"] is False



async def test_log_run_scores_lists_and_exports_stripped(hass: HomeAssistant, house) -> None:
    good = {c: True for c in ("R1", "R2", "R3", "R4", "R5", "R6")}
    ok = await call(hass, "log_run", {"skill": "build-a-skill", "request": "get my lights back", "checks": good,
                                      "outcome": "3 back"})
    assert ok.data["met_rubric"]
    bad = await call(hass, "log_run", {"skill": "build-a-skill", "request": "get my lights back",
                                       "checks": {**good, "R6": False}, "notes": "said 10.0.0.220 and light.kitchen_island_2 to Kitchen Island 2"})
    assert bad.data["run"]["score"] == 5 and "skill_update" in bad.data["next"]
    broke = await call(hass, "log_run", {"skill": "build-a-skill", "checks": good, "broke_rule": True})
    assert broke.data["run"]["score"] == 0
    listed = await call(hass, "log_run", {"op": "list", "below": 6})
    assert len(listed.data["runs"]) == 2
    exported = await call(hass, "log_run", {"op": "export"})
    text = open(exported.data["file"], encoding="utf-8").read()
    assert "10.0.0.220" not in text and "light.kitchen_island_2" not in text and "Kitchen Island 2" not in text
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
