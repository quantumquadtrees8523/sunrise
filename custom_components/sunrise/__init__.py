"""Sunrise: agent skills for Home Assistant, plus the tools an agent needs to use them well.

Setting up the entry copies the built-in skills into <config>/sunrise/skills/ (a person's
edited copy is never replaced), keeps the agent's memory files in <config>/sunrise/memory/
(shown as sensor.sunrise_memory), keeps both in a local git repository at <config>/sunrise/ (one
commit per change, no remote) and registers the "Sunrise" LLM API, which Home Assistant's
MCP Server serves to any agent at /api/mcp/sunrise. No token, no account, no internet.
"""

from __future__ import annotations

from pathlib import Path

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import llm
from homeassistant.helpers.event import async_track_time_interval

from .api import SunriseAPI, Runtime
from .const import DATA_FOLDER, SHIPPED_SKILLS, VERSION
from .hand import Hand
from .house import USAGE_DOMAINS, UsageTally
from .listening import Heard, hears
from .store import BehaviorError, Store

PLATFORMS = ["sensor"]

type SunriseEntry = ConfigEntry[Runtime]


async def async_setup_entry(hass: HomeAssistant, entry: SunriseEntry) -> bool:
    store = Store(Path(hass.config.path(DATA_FOLDER)))
    try:
        await hass.async_add_executor_job(store.install_shipped, Path(__file__).parent / SHIPPED_SKILLS, VERSION)
    except BehaviorError as exc:  # no git program on this machine (a hand-made install): say so plainly
        raise ConfigEntryError(str(exc)) from exc
    rt = Runtime(store=store, options=dict(entry.options))
    entry.runtime_data = rt
    entry.async_on_unload(llm.async_register_api(hass, SunriseAPI(hass, rt)))

    async def options_changed(_hass: HomeAssistant, changed: SunriseEntry) -> None:
        rt.options = dict(changed.options)  # read on every tool call: no reload needed

    entry.async_on_unload(entry.add_update_listener(options_changed))

    rt.tally = tally = UsageTally(store)
    await hass.async_add_executor_job(tally.load)
    rt.heard = heard = Heard(store)
    await hass.async_add_executor_job(heard.load)
    rt.hand = hand = Hand(hass, store)
    await hass.async_add_executor_job(hand.load)

    @callback
    def counted(event: Event) -> None:
        new, old = event.data.get("new_state"), event.data.get("old_state")
        if new is None or (old is not None and old.state == new.state):
            return
        hand.seen(new.context)
        if hears(new) and old is not None and old.state not in ("unavailable", "unknown"):
            heard.sensor(new)  # listening.py: what a routine could start from
        if new.domain not in USAGE_DOMAINS:
            return
        if new.state in ("unavailable", "unknown") or (old is not None and old.state in ("unavailable", "unknown")):
            return
        automated = hand.automated(new.context)
        tally.add(new.entity_id, new.state, new.context, new.last_changed, automated)
        if not automated:
            heard.change(new.entity_id, new.state, new.context, new.last_changed)
        hand.change(new)  # hand.py: a person's change outranks a routine's for a while

    entry.async_on_unload(hass.bus.async_listen(EVENT_STATE_CHANGED, counted))
    entry.async_on_unload(hass.bus.async_listen("automation_triggered", hand.triggered))
    async def save(_now) -> None:
        await hass.async_add_executor_job(tally.save)
        await hass.async_add_executor_job(heard.save)
        await hass.async_add_executor_job(hand.save)

    entry.async_on_unload(async_track_time_interval(hass, save, timedelta(minutes=10)))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SunriseEntry) -> bool:
    if entry.runtime_data.tally:
        await hass.async_add_executor_job(entry.runtime_data.tally.save)
    if entry.runtime_data.heard:
        await hass.async_add_executor_job(entry.runtime_data.heard.save)
    if entry.runtime_data.hand:
        await hass.async_add_executor_job(entry.runtime_data.hand.save)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
