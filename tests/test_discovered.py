"""`discovered`: Home Assistant's Discovered list, read and (for a plain confirm only) accepted, with undo.
Real config flows of stand-in integrations, started the way discovery starts them."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockModule, mock_config_flow, mock_integration, mock_platform

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .conftest import call, setup_integration


class ConfirmFlow(config_entries.ConfigFlow):
    """Found on the network; asks only "add it?"."""

    async def _found(self, info):
        self.context["title_placeholders"] = {"name": info.get("name", "Porch Bulb")}
        return await self.async_step_confirm()

    async_step_zeroconf = async_step_dhcp = async_step_user = _found

    async def async_step_confirm(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title=self.context["title_placeholders"]["name"], data={})
        return self.async_show_form(step_id="confirm", description_placeholders={"model": "A19"})


class PinFlow(config_entries.ConfigFlow):
    async def async_step_homekit(self, info):
        self.context["title_placeholders"] = {"name": "Front Door"}
        return await self.async_step_pair()

    async def async_step_pair(self, user_input=None):
        return self.async_show_form(step_id="pair", data_schema=vol.Schema({vol.Required("pairing_code"): str}))


class SignInFlow(config_entries.ConfigFlow):
    async def async_step_ssdp(self, info):
        return await self.async_step_auth()

    async def async_step_auth(self, user_input=None):
        return self.async_external_step(step_id="auth", url="http://127.0.0.1/sign-in")


def _integration(hass: HomeAssistant, domain: str, name: str, files: set[str] | None = None) -> None:
    mock_integration(hass, MockModule(domain, async_setup_entry=AsyncMock(return_value=True),
                                      async_unload_entry=AsyncMock(return_value=True),
                                      partial_manifest={"config_flow": True, "name": name}), top_level_files=files)
    mock_platform(hass, f"{domain}.config_flow", None)


@pytest.fixture
async def found(hass: HomeAssistant):
    await setup_integration(hass)
    _integration(hass, "bulbco", "BulbCo")
    _integration(hass, "doorco", "DoorCo", {"lock.py"})
    _integration(hass, "pinco", "PinCo")
    _integration(hass, "cloudco", "CloudCo")
    with (mock_config_flow("bulbco", ConfirmFlow), mock_config_flow("doorco", ConfirmFlow),
          mock_config_flow("pinco", PinFlow), mock_config_flow("cloudco", SignInFlow)):
        ids = {}
        for domain, source, info in (("bulbco", "zeroconf", {"name": "Porch Bulb"}), ("doorco", "dhcp", {"name": "Side Door"}),
                                     ("pinco", "homekit", {}), ("cloudco", "ssdp", {})):
            r = await hass.config_entries.flow.async_init(domain, context={"source": source}, data=info)
            ids[domain] = r["flow_id"]
        mine = await hass.config_entries.flow.async_init("bulbco", context={"source": "user"}, data={})  # someone's own Add: not a discovery
        ids["user"] = mine["flow_id"]
        yield ids


async def test_list_shows_discoveries_only_with_what_each_needs(hass: HomeAssistant, found) -> None:
    res = await call(hass, "discovered", {"op": "list"})
    rows = {r["integration"]: r for r in res.data["discovered"]}
    assert set(rows) == {"bulbco", "doorco", "pinco", "cloudco"}  # the user-started flow is left out
    assert found["user"] not in {r["flow_id"] for r in res.data["discovered"]}
    bulb = rows["bulbco"]
    assert bulb["integration_name"] == "BulbCo" and bulb["source"] == "zeroconf"
    assert bulb["device"] == {"name": "Porch Bulb", "model": "A19"} and bulb["needs"] == {"kind": "confirm"}
    assert rows["pinco"]["needs"]["kind"] == "fields" and rows["pinco"]["needs"]["secret"]
    assert rows["pinco"]["needs"]["fields"][0]["name"] == "pairing_code" and rows["pinco"]["needs"]["fields"][0]["type"] == "string"
    assert rows["cloudco"]["needs"] == {"kind": "sign_in"}
    assert rows["doorco"]["guarded"] == ["lock"] and "guarded" not in bulb
    assert res.data["note"].endswith("Changes nothing.")


async def test_accept_needs_yes_then_adds_and_undo_removes(hass: HomeAssistant, found) -> None:
    no = await call(hass, "discovered", {"op": "accept", "flow_id": found["bulbco"]})
    assert no.data["accepted"] is False and "confirmed=true" in no.data["error"]
    assert not hass.config_entries.async_entries("bulbco")
    yes = await call(hass, "discovered", {"op": "accept", "flow_id": found["bulbco"], "confirmed": True})
    assert yes.data["accepted"] is True and yes.data["added"]["title"] == "Porch Bulb"
    entry_id = yes.data["added"]["entry_id"]
    assert hass.config_entries.async_get_entry(entry_id)
    log = await call(hass, "changes")
    assert log.data["changes"][0]["what"] == "add_integration"
    await call(hass, "undo", {"change_id": yes.data["change_id"]})
    assert hass.config_entries.async_get_entry(entry_id) is None


async def test_accept_refuses_fields_sign_in_and_guarded_without_yes(hass: HomeAssistant, found) -> None:
    pin = await call(hass, "discovered", {"op": "accept", "flow_id": found["pinco"], "confirmed": True})
    assert pin.data["accepted"] is False and "Discovered" in pin.data["error"] and "PinCo" in pin.data["error"]
    cloud = await call(hass, "discovered", {"op": "accept", "flow_id": found["cloudco"], "confirmed": True})
    assert cloud.data["accepted"] is False and "sign-in" in cloud.data["error"]
    door = await call(hass, "discovered", {"op": "accept", "flow_id": found["doorco"]})
    assert door.data["accepted"] is False and "lock" in door.data["error"]
    assert not hass.config_entries.async_entries("doorco") and not hass.config_entries.async_entries("pinco")
    mine = await call(hass, "discovered", {"op": "accept", "flow_id": found["user"], "confirmed": True})
    assert mine.error and "no discovered device" in mine.data["error"]
    door_yes = await call(hass, "discovered", {"op": "accept", "flow_id": found["doorco"], "confirmed": True})
    assert door_yes.data["accepted"] is True
