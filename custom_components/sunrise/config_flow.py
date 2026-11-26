"""One click to add: no fields, no token, no account. One option afterwards (Configure): whether the
read tools may also see things that aren't exposed to voice assistants."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import CONF_READ_UNEXPOSED, DOMAIN, NAME, READ_UNEXPOSED_DEFAULT


class SunriseFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title=NAME, data={})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SunriseOptions:
        return SunriseOptions()


class SunriseOptions(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        now = self.config_entry.options.get(CONF_READ_UNEXPOSED, READ_UNEXPOSED_DEFAULT)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({vol.Required(CONF_READ_UNEXPOSED, default=now): bool}))
