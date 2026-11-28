"""A person's hand wins (hand.py). Owner, 2026-11-28: a phone-comes-home routine kept firing as the phone's
location bounced, and turned the lights back on after they'd been switched off for sleep. Now a routine that
switches something away from what a person just set is stopped and the thing put back, silently; when it keeps
happening at about the same time, the routine itself is changed to leave that thing alone then, as one undoable,
labelled change with its reason in the description, the change log and memory's log.md."""

from __future__ import annotations

import time
from datetime import timedelta
from pathlib import Path

import pytest

from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import dump, load_yaml

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.sunrise import hand as H
from custom_components.sunrise.hand import _leave_alone

from .conftest import call, owner, setup_integration

PHONE, LAMP, DESK = "device_tracker.pixel", "light.living_room", "light.desk"
ROUTINE = "automation.lights_when_the_phone_comes_home"


def _lights(hass: HomeAssistant) -> None:
    """Lights that do what they're told, carrying the caller's context as real ones do."""
    def turn(state: str):
        async def handler(call_: ServiceCall) -> None:
            ids = call_.data["entity_id"]
            for eid in [ids] if isinstance(ids, str) else ids:
                attrs = {"friendly_name": eid.split(".")[1].replace("_", " ").title()}
                if state == "on" and "brightness" in call_.data:
                    attrs["brightness"] = call_.data["brightness"]
                hass.states.async_set(eid, state, attrs, context=call_.context)
        return handler

    hass.services.async_register("light", "turn_on", turn("on"))
    hass.services.async_register("light", "turn_off", turn("off"))
    hass.states.async_set(PHONE, "home", {"friendly_name": "Pixel"})
    for eid in (LAMP, DESK):
        hass.states.async_set(eid, "on", {"friendly_name": eid.split(".")[1].replace("_", " ").title()})


async def _routines(hass: HomeAssistant, *rows: dict) -> None:
    Path(hass.config.path("configuration.yaml")).write_text("automation: !include automations.yaml\n", encoding="utf-8")
    Path(hass.config.path("automations.yaml")).write_text(dump(list(rows)), encoding="utf-8")
    assert await async_setup_component(hass, "automation", {"automation": list(rows)})
    await hass.services.async_call("automation", "reload", blocking=True)
    await hass.async_block_till_done()


PHONE_HOME = {"id": "phone_home", "alias": "Lights when the phone comes home", "mode": "single",
              "triggers": [{"trigger": "state", "entity_id": PHONE, "to": "home"}],
              "actions": [{"action": "light.turn_on", "target": {"entity_id": [LAMP, DESK]}, "data": {"brightness": 20}},
                          {"delay": {"minutes": 30}},
                          {"action": "light.turn_on", "target": {"entity_id": [LAMP, DESK]}, "data": {"brightness": 10}}]}


async def _bounce(hass: HomeAssistant) -> None:
    """The phone's location drifts out of the home zone and back: a fresh context, as the Companion app's is."""
    hass.states.async_set(PHONE, "not_home", context=Context())
    hass.states.async_set(PHONE, "home", context=Context())
    await hass.async_block_till_done()


async def _off_by_hand(hass: HomeAssistant, uid: str, eid: str = LAMP) -> None:
    await hass.services.async_call("light", "turn_off", {"entity_id": eid}, blocking=True, context=Context(user_id=uid))
    await hass.async_block_till_done()


async def test_the_phone_bounces_home_after_the_lights_went_off_by_hand_and_they_stay_off(hass: HomeAssistant) -> None:
    entry = await setup_integration(hass)
    _lights(hass)
    await _routines(hass, PHONE_HOME)
    uid = await owner(hass)
    await _off_by_hand(hass, uid)
    await _bounce(hass)
    await hass.async_block_till_done()
    # The lamp the person switched off is off again; the desk light, which nobody touched, the routine may set.
    assert hass.states.get(LAMP).state == "off"
    assert hass.states.get(DESK).state == "on" and hass.states.get(DESK).attributes.get("brightness") == 20
    # The run was stopped (no 30-minute step to come), and the routine is still on for its next real use.
    assert hass.states.get(ROUTINE).state == "on" and hass.states.get(ROUTINE).attributes.get("current") == 0
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=31))
    await hass.async_block_till_done()
    assert hass.states.get(LAMP).state == "off" and hass.states.get(DESK).attributes.get("brightness") == 20
    usage = await call(hass, "usage")
    won = usage.data["overruled"]
    assert len(won) == 1 and won[0]["thing"] == LAMP and won[0]["kept"] == "off" and won[0]["routine"] == ROUTINE
    assert usage.data["adapted"] == []
    # Nothing about the routine changed: once is the hand winning, not a pattern.
    assert (await call(hass, "routine", {"op": "get", "id": "phone_home"})).data["config"]["actions"] == PHONE_HOME["actions"]
    assert entry.runtime_data.hand.data["overruled"][0]["after_min"] >= 1


async def test_after_two_hours_or_on_a_persons_behalf_the_routine_wins(hass: HomeAssistant) -> None:
    entry = await setup_integration(hass)
    _lights(hass)
    button = {"id": "button", "alias": "Lamp button", "triggers": [{"trigger": "event", "event_type": "lamp_button"}],
              "actions": [{"action": "light.turn_on", "target": {"entity_id": LAMP}}]}
    quick = {**PHONE_HOME, "actions": PHONE_HOME["actions"][:1]}  # no delay: a run that wins has to finish for the test to
    await _routines(hass, quick, button)
    uid = await owner(hass)
    await _off_by_hand(hass, uid)
    # A button press is the person's own hand: it turns the lamp on and nothing puts it back.
    hass.bus.async_fire("lamp_button", context=Context())
    await hass.async_block_till_done()
    assert hass.states.get(LAMP).state == "on"
    # The lamp's latest change is now the button's (theirs). Off by hand again, then two hours pass.
    await _off_by_hand(hass, uid)
    entry.runtime_data.hand.held[LAMP]["at"] -= H.HOLD_S + 1
    await _bounce(hass)
    assert hass.states.get(LAMP).state == "on"
    assert entry.runtime_data.hand.data["overruled"] == []


@pytest.mark.parametrize("expected_lingering_timers", [True])  # the time trigger re-arms for tomorrow
async def test_a_clock_started_run_is_the_routines_not_a_persons(hass: HomeAssistant) -> None:
    """A time trigger's run has no parent context; it still isn't a hand change (Listening and usage miscounted it)."""
    entry = await setup_integration(hass)
    _lights(hass)
    at = (dt_util.now() + timedelta(minutes=2)).strftime("%H:%M:00")
    await _routines(hass, {"id": "clock", "alias": "Lamp on by the clock", "triggers": [{"trigger": "time", "at": at}],
                           "actions": [{"action": "light.turn_on", "target": {"entity_id": LAMP}}]})
    uid = await owner(hass)
    await _off_by_hand(hass, uid)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=3))
    await hass.async_block_till_done()
    assert hass.states.get(LAMP).state == "off"  # the person's off won here too
    by = entry.runtime_data.tally.data[LAMP]["by"]
    assert by.get("automation") == 1 and by.get("person") == 1  # (the rest: the lamp's first state, and Sunrise putting it back)


async def test_three_nights_of_it_and_the_routine_leaves_that_light_alone_then_auditably_and_undoably(hass: HomeAssistant) -> None:
    entry = await setup_integration(hass)
    _lights(hass)
    await _routines(hass, PHONE_HOME)
    hand = entry.runtime_data.hand
    now = time.time()
    for d in (1, 2):  # the two nights before, at this time of day
        hand.data["overruled"].append({"at": round(now - d * 86400), "thing": LAMP, "kept": "off", "routine": ROUTINE,
                                       "name": "Lights when the phone comes home", "source": f"state of {PHONE}", "after_min": 3})
    uid = await owner(hass)
    await _off_by_hand(hass, uid)
    await _bounce(hass)
    await hass.async_block_till_done()
    assert hass.states.get(LAMP).state == "off"

    config = (await call(hass, "routine", {"op": "get", "id": "phone_home"})).data["config"]
    first = config["actions"][:2]
    # Only the lamp comes out of the first step, into its own copy that runs outside these hours; the desk stays as it was.
    assert first[0] == {"action": "light.turn_on", "target": {"entity_id": [DESK]}, "data": {"brightness": 20}}
    assert first[1]["if"][0]["condition"] == "not" and first[1]["if"][0]["conditions"][0]["condition"] == "time"
    assert first[1]["then"] == [{"action": "light.turn_on", "target": {"entity_id": LAMP}, "data": {"brightness": 20}}]
    assert first[1]["alias"].startswith("Sunrise: leave the Living Room alone")
    assert "Adapted by Sunrise on" in config["description"] and "on 3 days in the last 14" in config["description"]
    eid = er.async_get(hass).async_get_entity_id("automation", "automation", "phone_home")
    label = lr.async_get(hass).async_get_label_by_name("Adapted")
    assert label and label.label_id in er.async_get(hass).async_get(eid).labels
    # The agent sees it in the change log and usage, the person in memory's log.md (and HA's logbook, when it's loaded).
    changes = (await call(hass, "changes")).data["changes"]
    assert changes[0]["what"] == "routine_adapt" and changes[0]["target"] == "phone_home"
    assert (await call(hass, "usage")).data["adapted"][0]["thing"] == LAMP
    log = (await call(hass, "memory_read", {"name": "log.md"})).data
    assert "Adapted a routine: Lights when the phone comes home" in str(log)
    # The evidence is used up: the next overrule doesn't adapt it a second time.
    assert all(r.get("learned") for r in hand.data["overruled"])

    assert (await call(hass, "undo", {"change_id": changes[0]["change_id"]})).data["ok"]
    rows = load_yaml(hass.config.path("automations.yaml"))
    assert next(r for r in rows if r["id"] == "phone_home")["actions"] == PHONE_HOME["actions"]
    assert label.label_id not in er.async_get(hass).async_get(eid).labels


async def test_spread_over_the_day_or_a_routine_sunrise_cant_edit_is_left_as_it_is(hass: HomeAssistant) -> None:
    entry = await setup_integration(hass)
    _lights(hass)
    await _routines(hass, PHONE_HOME)
    hand = entry.runtime_data.hand
    now = time.time()
    for d, h in ((1, 3), (2, 11), (3, 19)):  # three days, but at no particular time
        hand.data["overruled"].append({"at": round(now - d * 86400 + h * 3600), "thing": LAMP, "kept": "off",
                                       "routine": ROUTINE, "name": "x", "source": "", "after_min": 1})
    assert await hand.learn(ROUTINE, LAMP) is None
    assert await hand.learn("automation.not_there", LAMP) is None


def test_leave_alone_takes_one_light_out_of_the_owners_phase_out_and_keeps_the_rest() -> None:
    """The shape of the owner's routine: a choose by time of day, lists of lights, delays between steps."""
    left, right, kitchen = "light.left", "light.right", "light.kitchen"
    steps = [{"choose": [
        {"conditions": [{"condition": "time", "after": "21:45:00"}],
         "sequence": [{"action": "light.turn_on", "target": {"entity_id": [left, right, kitchen]}, "data": {"brightness_pct": 8}},
                      {"action": "light.turn_off", "target": {"entity_id": ["light.hall"]}},
                      {"delay": {"minutes": 30}},
                      {"action": "light.turn_on", "data": {"entity_id": left, "brightness_pct": 6}}]}]}]
    out, changed = _leave_alone(steps, left, "22:15:00", "01:00:00", "Sunrise: leave the Left alone 22:15-01:00")
    assert changed
    seq = out[0]["choose"][0]["sequence"]
    assert seq[0]["target"]["entity_id"] == [right, kitchen]
    assert seq[1]["then"][0]["target"]["entity_id"] == left and seq[1]["if"][0]["conditions"][0] == {
        "condition": "time", "after": "22:15:00", "before": "01:00:00"}
    assert seq[2] == {"action": "light.turn_off", "target": {"entity_id": ["light.hall"]}}
    assert seq[4]["then"] == [{"action": "light.turn_on", "data": {"entity_id": left, "brightness_pct": 6}}]
    assert out[0]["choose"][0]["conditions"] == steps[0]["choose"][0]["conditions"]
    # Reached through an area: no step names it, so nothing to change.
    assert _leave_alone([{"action": "light.turn_on", "target": {"area_id": "living"}}], left, "a", "b", "x")[1] is False
