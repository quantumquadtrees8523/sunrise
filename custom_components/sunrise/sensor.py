"""sensor.sunrise_memory: what the agent remembers, where the owner can see it in Home Assistant.

State: the number of memory files. Attributes: each file's name, first line and when it last
changed, plus the folder they live in. The files themselves are plain Markdown on disk.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN

SHOWN = 50  # attributes stay small: the newest files


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    sensor = MemorySensor(entry.runtime_data)
    entry.runtime_data.memory_changed = sensor.changed
    async_add_entities([sensor], update_before_add=True)


class MemorySensor(SensorEntity):
    _attr_should_poll = False
    _attr_name = "Sunrise memory"
    _attr_unique_id = f"{DOMAIN}_memory"
    _attr_icon = "mdi:notebook-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "files"

    def __init__(self, rt) -> None:
        self._rt = rt
        self._files: list[dict[str, Any]] = []

    @callback
    def changed(self) -> None:
        if self.hass:
            self.async_schedule_update_ha_state(force_refresh=True)

    async def async_update(self) -> None:
        self._files = await self.hass.async_add_executor_job(self._rt.store.memory_list)

    @property
    def native_value(self) -> int:
        return len(self._files)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        newest = sorted(self._files, key=lambda f: f["changed"], reverse=True)[:SHOWN]
        return {"folder": str(self._rt.store.memory_dir),
                "files": [{"name": f["name"], "first_line": f["first_line"],
                           "changed": datetime.fromtimestamp(f["changed"], UTC).isoformat(timespec="seconds")} for f in newest]}
