"""Sunrise: agent skills for Home Assistant, plus the tools an agent needs to use them well.

Setting up the entry copies the built-in skills into <config>/sunrise/skills/ (a person's
edited copy is never replaced), keeps the agent's memory files in <config>/sunrise/memory/
(shown as sensor.sunrise_memory) and registers the "Sunrise" LLM API, which Home Assistant's
MCP Server serves to any agent at /api/mcp/sunrise. No token, no account, no internet.
"""

from __future__ import annotations

from pathlib import Path

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import llm
from homeassistant.helpers.event import async_track_time_interval

from .api import SunriseAPI, Runtime
from .const import DATA_FOLDER, SHIPPED_SKILLS, VERSION
from .house import USAGE_DOMAINS, UsageTally
from .store import Store

PLATFORMS = ["sensor"]

type SunriseEntry = ConfigEntry[Runtime]


async def async_setup_entry(hass: HomeAssistant, entry: SunriseEntry) -> bool:
    store = Store(Path(hass.config.path(DATA_FOLDER)))
    await hass.async_add_executor_job(store.install_shipped, Path(__file__).parent / SHIPPED_SKILLS, VERSION)
    rt = Runtime(store=store, options=dict(entry.options))
    entry.runtime_data = rt
    entry.async_on_unload(llm.async_register_api(hass, SunriseAPI(hass, rt)))

    rt.tally = tally = UsageTally(store)
    await hass.async_add_executor_job(tally.load)

    @callback
    def counted(event: Event) -> None:
        new, old = event.data.get("new_state"), event.data.get("old_state")
        if new is None or new.domain not in USAGE_DOMAINS or (old is not None and old.state == new.state):
            return
        if new.state in ("unavailable", "unknown") or (old is not None and old.state in ("unavailable", "unknown")):
            return
        tally.add(new.entity_id, new.state, new.context, new.last_changed)

    entry.async_on_unload(hass.bus.async_listen(EVENT_STATE_CHANGED, counted))
    async def save(_now) -> None:
        await hass.async_add_executor_job(tally.save)

    entry.async_on_unload(async_track_time_interval(hass, save, timedelta(minutes=10)))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SunriseEntry) -> bool:
    if entry.runtime_data.tally:
        await hass.async_add_executor_job(entry.runtime_data.tally.save)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
