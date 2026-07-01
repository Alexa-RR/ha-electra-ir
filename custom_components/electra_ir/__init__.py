"""The Electra AC (IR) integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_INFRARED_ENTITY_ID

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE]

type ElectraIRConfigEntry = ConfigEntry[None]


async def async_setup_entry(
    hass: HomeAssistant, entry: ElectraIRConfigEntry
) -> bool:
    """Set up Electra AC (IR) from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ElectraIRConfigEntry
) -> None:
    """Reload the entry when options change (e.g. the temperature sensor)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: ElectraIRConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(
    hass: HomeAssistant, entry: ElectraIRConfigEntry
) -> bool:
    """Migrate old config entries."""
    if entry.version == 1:
        # v1 stored the emitter under the "emitter" key. v2 aligns with the LG
        # Infrared integration and uses "infrared_entity_id".
        _LOGGER.debug("Migrating Electra AC (IR) config entry from v1 to v2")
        data = {**entry.data}
        if (emitter := data.pop("emitter", None)) is not None:
            data[CONF_INFRARED_ENTITY_ID] = emitter
        hass.config_entries.async_update_entry(entry, data=data, version=2)

    return True
