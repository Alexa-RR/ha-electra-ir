"""Climate platform for the Electra AC (IR) integration."""

from __future__ import annotations

import inspect
import logging
from typing import Any

from homeassistant.components import infrared
from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    SWING_OFF,
    SWING_ON,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ElectraIRConfigEntry
from .const import CONF_INFRARED_ENTITY_ID, DOMAIN, MAX_TEMP, MIN_TEMP
from .electra import ElectraACCommand, ElectraFan, ElectraMode, ElectraState

_LOGGER = logging.getLogger(__name__)

# Map Home Assistant HVAC modes <-> Electra protocol modes (excluding OFF, which
# is handled via the power toggle).
_HVAC_TO_ELECTRA: dict[HVACMode, ElectraMode] = {
    HVACMode.COOL: ElectraMode.COOL,
    HVACMode.HEAT: ElectraMode.HEAT,
    HVACMode.DRY: ElectraMode.DRY,
    HVACMode.FAN_ONLY: ElectraMode.FAN,
    HVACMode.AUTO: ElectraMode.AUTO,
}
_ELECTRA_TO_HVAC = {v: k for k, v in _HVAC_TO_ELECTRA.items()}

_FAN_TO_ELECTRA: dict[str, ElectraFan] = {
    FAN_LOW: ElectraFan.LOW,
    FAN_MEDIUM: ElectraFan.MEDIUM,
    FAN_HIGH: ElectraFan.HIGH,
    FAN_AUTO: ElectraFan.AUTO,
}
_ELECTRA_TO_FAN = {v: k for k, v in _FAN_TO_ELECTRA.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ElectraIRConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Electra AC climate entity."""
    # Controlling the AC requires an emitter. If only a receiver was configured
    # there is nothing to control, so no climate entity is created.
    emitter = entry.data.get(CONF_INFRARED_ENTITY_ID)
    if emitter is None:
        _LOGGER.warning(
            "No infrared emitter configured for %s; climate control unavailable",
            entry.title,
        )
        return
    async_add_entities([ElectraClimate(entry, emitter)])


class ElectraClimate(ClimateEntity, RestoreEntity):
    """Representation of an Electra AC controlled over IR."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_assumed_state = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1.0
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
        HVACMode.AUTO,
    ]
    _attr_fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_swing_modes = [SWING_OFF, SWING_ON]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, entry: ElectraIRConfigEntry, emitter: str) -> None:
        """Initialize the entity."""
        self._entry = entry
        self._emitter = emitter
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Electra",
        )

        # Assumed state. Default to a sensible powered-off configuration.
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = 24.0
        self._attr_fan_mode = FAN_AUTO
        self._attr_swing_mode = SWING_OFF
        # The Electra mode last used while powered on; remembered so OFF can keep
        # the mode and so turning back on restores it.
        self._last_mode: ElectraMode = ElectraMode.COOL

    async def async_added_to_hass(self) -> None:
        """Restore the assumed state from the last run."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is None:
            return

        try:
            self._attr_hvac_mode = HVACMode(last_state.state)
        except ValueError:
            self._attr_hvac_mode = HVACMode.OFF

        if (temp := last_state.attributes.get(ATTR_TEMPERATURE)) is not None:
            self._attr_target_temperature = float(temp)
        if (fan := last_state.attributes.get("fan_mode")) in self._attr_fan_modes:
            self._attr_fan_mode = fan
        if (swing := last_state.attributes.get("swing_mode")) in self._attr_swing_modes:
            self._attr_swing_mode = swing

        if self._attr_hvac_mode in _HVAC_TO_ELECTRA:
            self._last_mode = _HVAC_TO_ELECTRA[self._attr_hvac_mode]

    # --- Command building / sending ---------------------------------------

    def _build_state(self, power_toggle: bool) -> ElectraState:
        """Build the Electra state from the current entity attributes."""
        return ElectraState(
            mode=self._last_mode,
            fan=_FAN_TO_ELECTRA.get(self._attr_fan_mode, ElectraFan.AUTO),
            temperature=int(self._attr_target_temperature or 24),
            swing=self._attr_swing_mode == SWING_ON,
            power_toggle=power_toggle,
        )

    async def _async_transmit(self, power_toggle: bool) -> None:
        """Encode the current state and send it through the IR emitter."""
        command = ElectraACCommand(self._build_state(power_toggle))
        result = infrared.async_send_command(
            self.hass, self._emitter, command, context=self._context
        )
        if inspect.isawaitable(result):
            await result

    # --- Climate API -------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set a new HVAC mode."""
        was_on = self._attr_hvac_mode != HVACMode.OFF

        if hvac_mode == HVACMode.OFF:
            if was_on:
                # Power button is a toggle; send it to switch the unit off.
                await self._async_transmit(power_toggle=True)
            self._attr_hvac_mode = HVACMode.OFF
            self.async_write_ha_state()
            return

        self._last_mode = _HVAC_TO_ELECTRA[hvac_mode]
        self._attr_hvac_mode = hvac_mode
        # Toggle power only when transitioning from off to on.
        await self._async_transmit(power_toggle=not was_on)
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        self._attr_target_temperature = float(temp)
        await self._async_send_if_on()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set a new fan mode."""
        self._attr_fan_mode = fan_mode
        await self._async_send_if_on()
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set a new swing mode."""
        self._attr_swing_mode = swing_mode
        await self._async_send_if_on()
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn the AC on, restoring the last active mode."""
        await self.async_set_hvac_mode(_ELECTRA_TO_HVAC[self._last_mode])

    async def async_turn_off(self) -> None:
        """Turn the AC off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def _async_send_if_on(self) -> None:
        """Transmit the current state, but only when the unit is on.

        Adjusting temperature/fan/swing while the unit is off only updates the
        assumed state; the real remote ignores those without powering on.
        """
        if self._attr_hvac_mode != HVACMode.OFF:
            await self._async_transmit(power_toggle=False)
