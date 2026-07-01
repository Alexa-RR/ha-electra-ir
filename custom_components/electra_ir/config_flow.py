"""Config flow for the Electra AC (IR) integration.

Mirrors the LG Infrared config flow: an emitter and a receiver are both
optional, at least one must be selected, and duplicates are rejected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.components.infrared import (
    DOMAIN as INFRARED_DOMAIN,
    async_get_emitters,
    async_get_receivers,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
)

from .const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_INFRARED_RECEIVER_ENTITY_ID,
    DOMAIN,
)


class ElectraIrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Electra AC (IR)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: pick an IR emitter and/or receiver."""
        emitter_entity_ids = async_get_emitters(self.hass)
        receiver_entity_ids = async_get_receivers(self.hass)
        if not emitter_entity_ids and not receiver_entity_ids:
            return self.async_abort(reason="no_infrared_entities")

        errors: dict[str, str] = {}

        if user_input is not None:
            emitter_id = user_input.get(CONF_INFRARED_ENTITY_ID)
            receiver_id = user_input.get(CONF_INFRARED_RECEIVER_ENTITY_ID)
            if emitter_id or receiver_id:
                if emitter_id:
                    self._async_abort_entries_match(
                        {CONF_INFRARED_ENTITY_ID: emitter_id}
                    )
                if receiver_id:
                    self._async_abort_entries_match(
                        {CONF_INFRARED_RECEIVER_ENTITY_ID: receiver_id}
                    )

                # Build a friendly title from the chosen entity's name.
                title_entity_id = emitter_id or receiver_id
                if TYPE_CHECKING:
                    assert title_entity_id is not None
                ent_reg = er.async_get(self.hass)
                entry = ent_reg.async_get(title_entity_id)
                title_entity_name = (
                    entry.name or entry.original_name or title_entity_id
                    if entry
                    else title_entity_id
                )
                title = f"Electra AC via {title_entity_name}"

                return self.async_create_entry(title=title, data=user_input)

            errors["base"] = "missing_infrared_entity"

        schema_dict: dict[vol.Marker, Any] = {
            vol.Optional(CONF_INFRARED_ENTITY_ID): EntitySelector(
                EntitySelectorConfig(
                    domain=INFRARED_DOMAIN,
                    include_entities=emitter_entity_ids,
                )
            ),
            vol.Optional(CONF_INFRARED_RECEIVER_ENTITY_ID): EntitySelector(
                EntitySelectorConfig(
                    domain=INFRARED_DOMAIN,
                    include_entities=receiver_entity_ids,
                )
            ),
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )
