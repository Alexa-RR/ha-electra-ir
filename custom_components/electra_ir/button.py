"""Button platform for the Electra AC (IR) integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ElectraIRConfigEntry
from .const import CONF_INFRARED_ENTITY_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ElectraIRConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Electra AC buttons."""
    # The Feelit button drives the climate entity, which only exists when an
    # emitter is configured.
    if entry.data.get(CONF_INFRARED_ENTITY_ID) is None:
        return
    async_add_entities([ElectraFeelitButton(entry)])


class ElectraFeelitButton(ButtonEntity):
    """Push the current room temperature to the AC via Electra's iFeel."""

    _attr_has_entity_name = True
    _attr_translation_key = "feelit"
    _attr_icon = "mdi:thermometer-check"

    def __init__(self, entry: ElectraIRConfigEntry) -> None:
        """Initialize the button."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_feelit"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

    async def async_press(self) -> None:
        """Send an iFeel update from the climate entity."""
        climate = self._entry.runtime_data.climate
        if climate is None:
            _LOGGER.warning("Feelit pressed but the climate entity is not ready")
            return
        await climate.async_send_ifeel()
