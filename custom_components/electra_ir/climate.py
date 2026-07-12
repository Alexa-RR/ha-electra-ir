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
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from . import ElectraIRConfigEntry
from .const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_TEMPERATURE_SENSOR,
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
)
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
    entity = ElectraClimate(entry, emitter)
    entry.runtime_data.climate = entity
    async_add_entities([entity])


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
        # Optional external temperature sensor (options flow). IR gives no
        # feedback, so current_temperature is only known if a sensor is attached.
        self._sensor_entity_id: str | None = entry.options.get(
            CONF_TEMPERATURE_SENSOR
        )
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
        """Restore the assumed state and start tracking the temperature sensor."""
        await super().async_added_to_hass()

        if self._sensor_entity_id is not None:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._sensor_entity_id],
                    self._async_sensor_changed,
                )
            )
            self._update_current_temp(self.hass.states.get(self._sensor_entity_id))

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

    @callback
    def _async_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle temperature sensor state changes."""
        self._update_current_temp(event.data["new_state"])
        self.async_write_ha_state()

    @callback
    def _update_current_temp(self, state: State | None) -> None:
        """Set current_temperature from a sensor state."""
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        try:
            self._attr_current_temperature = float(state.state)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Could not parse temperature '%s' from %s",
                state.state,
                self._sensor_entity_id,
            )

    # --- Command building / sending ---------------------------------------

    def _build_state(self, off: bool) -> ElectraState:
        """Build the Electra state from the current entity attributes."""
        return ElectraState(
            mode=self._last_mode,
            fan=_FAN_TO_ELECTRA.get(self._attr_fan_mode, ElectraFan.AUTO),
            temperature=int(self._attr_target_temperature or 24),
            swing=self._attr_swing_mode == SWING_ON,
            off=off,
        )

    async def _async_send(self, state: ElectraState) -> None:
        """Encode a state and send it through the IR emitter."""
        command = ElectraACCommand(state)
        result = infrared.async_send_command(
            self.hass, self._emitter, command, context=self._context
        )
        if inspect.isawaitable(result):
            await result

    async def _async_transmit(self, off: bool) -> None:
        """Encode the current state and send it through the IR emitter."""
        await self._async_send(self._build_state(off))

    async def async_send_ifeel(self) -> None:
        """Send an iFeel update: current room temperature with the iFeel bit set.

        Experimental. Electra's iFeel normally has the remote report its own
        temperature sensor to the AC; here we push the attached HA sensor's
        reading (falling back to the setpoint) in the iFeel frame.
        """
        room_temp = self._attr_current_temperature
        if room_temp is None:
            room_temp = self._attr_target_temperature or 24
        state = self._build_state(off=False)
        state.ifeel = True
        state.temperature = int(round(room_temp))
        await self._async_send(state)

    # --- Climate API -------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set a new HVAC mode.

        The power bit is absolute (not a toggle): any on-state command turns the
        unit on and applies settings; OFF is a dedicated command.
        """
        if hvac_mode == HVACMode.OFF:
            await self._async_transmit(off=True)
            self._attr_hvac_mode = HVACMode.OFF
            self.async_write_ha_state()
            return

        self._last_mode = _HVAC_TO_ELECTRA[hvac_mode]
        self._attr_hvac_mode = hvac_mode
        await self._async_transmit(off=False)
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
        assumed state; nothing is transmitted until it is turned on.
        """
        if self._attr_hvac_mode != HVACMode.OFF:
            await self._async_transmit(off=False)
