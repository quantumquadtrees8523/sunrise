"""usage reads Home Assistant's recorded history: how often, at what hours and by whom."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant

from .conftest import call, setup_integration


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """The recorder must start before hass (the default fixture would set hass up first)."""
    yield


async def test_usage_reads_history_by_hour_and_who(hass: HomeAssistant, hass_admin_user) -> None:
    from homeassistant.core import Context
    from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

    await setup_integration(hass)
    person = Context(user_id=hass_admin_user.id)
    for state in ("on", "off", "on", "off", "on"):
        hass.states.async_set("light.porch", state, {"friendly_name": "Porch"}, context=person)
        await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    res = await call(hass, "usage", {"days": 3})
    porch = next(t for t in res.data["things"] if t["id"] == "light.porch")
    assert porch["turned_on"] == 3 and porch["days_used"] == 1 and porch["changes"] >= 5
    assert porch["by"] == {"person": 5}  # every change, on and off, was a person in the app
