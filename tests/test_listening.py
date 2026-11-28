"""Listening (listening.py): the house hears its doors, motion and people, pairs each with what someone
switches by hand in the next two minutes, and `usage` reports the pairs that held often enough, each
with the routine that would do it. Coincidences, an automation's own changes and a pair a routine
already covers are left out."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.core import Context, HomeAssistant, State
from homeassistant.util import dt as dt_util

from custom_components.sunrise import listening
from custom_components.sunrise.listening import Heard

from .conftest import call, setup_integration

DOOR, HALL = "binary_sensor.front_door", "light.hall"


def _at(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    start = dt_util.start_of_local_day() - timedelta(days=10)
    return start + timedelta(days=day, hours=hour, minutes=minute, seconds=second)


def _open(heard: Heard, when: datetime, entity_id: str = DOOR, kind: str = "door", to: str = "on") -> None:
    heard.sensor(State(entity_id, to, {"device_class": kind}, last_changed=when))


def _evenings(heard: Heard, days=range(5), after_s: int = 40, context: Context | None = None) -> None:
    for d in days:
        _open(heard, _at(d, 19, 5 + d * 4))
        heard.change(HALL, "on", context or Context(user_id="someone"), _at(d, 19, 5 + d * 4, after_s))


class _NoStore:
    def get(self, key, default=None):
        return default

    def put(self, key, data):
        self.saved = data


def _house(hass: HomeAssistant) -> None:
    hass.states.async_set(DOOR, "off", {"friendly_name": "Front door", "device_class": "door"})
    hass.states.async_set(HALL, "off", {"friendly_name": "Hall light"})


async def test_a_door_then_a_light_on_five_evenings_is_a_pattern_with_its_routine(hass: HomeAssistant) -> None:
    _house(hass)
    heard = Heard(_NoStore())
    _evenings(heard)
    _open(heard, _at(5, 19, 30))  # one evening nobody did
    _open(heard, _at(2, 8, 0))  # a morning: outside the evening's hours, so it doesn't count against it
    found = listening.patterns(hass, heard)
    assert len(found) == 1
    p = found[0]
    assert p["when"] == {"id": DOOR, "to": "on"} and p["then"] == {"id": HALL, "to": "on"}
    assert (p["days"], p["times"], p["of"], p["between"]) == (5, 5, 6, ["18:35", "19:51"])
    assert "5 of the 6 times the Front door opens between 18:35 and 19:51" in p["evidence"] and "within 40 seconds" in p["evidence"]
    assert p["routine"] == {
        "alias": "Turn the Hall light on when the Front door opens", "description": p["evidence"],
        "triggers": [{"trigger": "state", "entity_id": DOOR, "to": "on"}],
        "conditions": [{"condition": "time", "after": "18:35:00", "before": "19:51:00"}],
        "actions": [{"action": "light.turn_on", "target": {"entity_id": HALL}}], "mode": "single"}
    # A routine that already starts on the door and switches the hall light: nothing to suggest.
    assert listening.patterns(hass, heard, [{"triggers": [{"entity_id": DOOR}], "actions": [{"target": {"entity_id": HALL}}]}]) == []


async def test_too_few_days_too_slow_too_rare_or_an_automations_own_change_is_nothing(hass: HomeAssistant) -> None:
    _house(hass)
    few = Heard(_NoStore())
    _evenings(few, days=range(3))
    slow = Heard(_NoStore())
    _evenings(slow, after_s=300)
    rare = Heard(_NoStore())
    _evenings(rare)
    for d in range(5):
        _open(rare, _at(d, 19, 28))
        _open(rare, _at(d, 19, 45))
    automated = Heard(_NoStore())
    _evenings(automated, context=Context(parent_id="an-automation"))
    for heard in (few, slow, rare, automated):
        assert listening.patterns(hass, heard) == []


async def test_motion_that_keeps_firing_is_one_episode_and_a_wall_switch_counts(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.stairs_motion", "off", {"friendly_name": "Stairs motion", "device_class": "motion"})
    hass.states.async_set("light.stairs", "off", {"friendly_name": "Stairs light"})
    heard = Heard(_NoStore())
    for d in range(4):
        for k in range(6):  # fires every 20 s while someone walks through
            _open(heard, _at(d, 22, 0, k * 20), "binary_sensor.stairs_motion", "motion")
        heard.change("light.stairs", "on", Context(), _at(d, 22, 2, 30))  # at the wall: no user, no automation
    p = listening.patterns(hass, heard)[0]
    assert (p["times"], p["of"]) == (4, 4) and p["routine"]["alias"] == "Turn the Stairs light on when the Stairs motion notices someone"


async def test_across_midnight_the_hours_wrap_and_all_day_has_none(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.back_door", "off", {"friendly_name": "Back door", "device_class": "door"})
    hass.states.async_set("switch.porch", "on", {"friendly_name": "Porch"})
    hass.states.async_set("person.sam", "home", {"friendly_name": "Sam"})
    hass.states.async_set("cover.blinds", "closed", {"friendly_name": "Blinds"})
    heard = Heard(_NoStore())
    for d, (hh, mm) in enumerate([(23, 40), (0, 10), (23, 55), (0, 20)]):
        _open(heard, _at(d, hh, mm), "binary_sensor.back_door")
        heard.change("switch.porch", "off", Context(user_id="u"), _at(d, hh, mm, 30))
    for d, hh in enumerate([7, 12, 17, 22]):
        heard.sensor(State("person.sam", "home", {}, last_changed=_at(d, hh, 0)))
        heard.change("cover.blinds", "open", Context(user_id="u"), _at(d, hh, 1))
    by = {p["then"]["id"]: p for p in listening.patterns(hass, heard)}
    assert by["switch.porch"]["between"] == ["23:10", "00:50"]
    assert by["switch.porch"]["routine"]["conditions"] == [{"condition": "time", "after": "23:10:00", "before": "00:50:00"}]
    assert by["cover.blinds"]["between"] is None and by["cover.blinds"]["routine"]["conditions"] == []
    assert by["cover.blinds"]["routine"]["alias"] == "Open the Blinds when Sam comes home"
    assert by["cover.blinds"]["routine"]["actions"] == [{"action": "cover.open_cover", "target": {"entity_id": "cover.blinds"}}]


async def test_the_integration_hears_live_and_usage_carries_follows(hass: HomeAssistant, hass_admin_user) -> None:
    entry = await setup_integration(hass)
    _house(hass)
    hass.states.async_set("sensor.temperature", "20")
    hass.states.async_set("binary_sensor.leak", "off", {"device_class": "moisture"})
    await hass.async_block_till_done()
    hass.states.async_set(DOOR, "on", {"friendly_name": "Front door", "device_class": "door"})
    hass.states.async_set("binary_sensor.leak", "on", {"device_class": "moisture"})  # not a kind it listens to
    hass.states.async_set("sensor.temperature", "21")
    hass.states.async_set(HALL, "on", {"friendly_name": "Hall light"}, context=Context(user_id=hass_admin_user.id))
    await hass.async_block_till_done()
    heard = entry.runtime_data.heard
    assert list(heard.data["heard"]) == [f"{DOOR}|on"] and list(heard.data["pairs"]) == [f"{DOOR}|on>{HALL}|on"]
    res = await call(hass, "usage", {"days": 3})
    assert res.data["follows"] == []  # once isn't a pattern
    _evenings(heard)
    res = await call(hass, "usage", {"days": 3})
    assert res.data["follows"][0]["routine"]["triggers"][0]["entity_id"] == DOOR
    # The household turned that one down (a dismissed suggestion): it's never offered again.
    entry.runtime_data.store.put("turned_down", [{"when": [DOOR], "then": [HALL]}])
    assert (await call(hass, "usage", {"days": 3})).data["follows"] == []


async def test_what_it_heard_is_saved_and_old_days_are_dropped(hass: HomeAssistant) -> None:
    store = _NoStore()
    heard = Heard(store)
    _evenings(heard)
    heard.sensor(State(DOOR, "on", {"device_class": "door"}, last_changed=dt_util.utcnow() - timedelta(days=45)))
    heard.save()
    assert len(store.saved["heard"][f"{DOOR}|on"]) == 5 and len(store.saved["pairs"][f"{DOOR}|on>{HALL}|on"]) == 5
