"""Config flow for the Electra AC (IR) integration."""

from __future__ import annotations

import inspect
from typing import Any

import voluptuous as vol

from homeassistant.components import infrared
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .const import CONF_EMITTER, DOMAIN


async def _async_emitters(hass: HomeAssistant) -> list[str]:
    """Return available IR emitter entity ids.

    ``async_get_emitters`` is a thin platform helper; tolerate it being either a
    coroutine or a plain callback across infrared platform versions.
    """
    result = infrared.async_get_emitters(hass)
    if inspect.isawaitable(result):
        result = await result
    return list(result)


class ElectraIRConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Electra AC (IR)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: pick an IR emitter and name the unit."""
        emitters = await _async_emitters(self.hass)
        if not emitters:
            return self.async_abort(reason="no_emitters")

        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_EMITTER] not in emitters:
                errors[CONF_EMITTER] = "unknown_emitter"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={CONF_EMITTER: user_input[CONF_EMITTER]},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Electra AC"): str,
                vol.Required(CONF_EMITTER): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=emitters,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )
