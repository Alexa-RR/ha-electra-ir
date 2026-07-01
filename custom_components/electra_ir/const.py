"""Constants for the Electra AC (IR) integration."""

from __future__ import annotations

DOMAIN = "electra_ir"

# Config entry keys. Named to mirror the LG Infrared integration so the setup
# dialog behaves consistently across IR consumer integrations.
CONF_INFRARED_ENTITY_ID = "infrared_entity_id"
CONF_INFRARED_RECEIVER_ENTITY_ID = "infrared_receiver_entity_id"

# Options key: an existing temperature sensor whose value is surfaced as the
# climate entity's current temperature (IR is one-way, so there is no feedback
# from the AC itself).
CONF_TEMPERATURE_SENSOR = "temperature_sensor"

# Climate limits (degrees Celsius). The Electra protocol encodes temperature as
# a 4-bit value offset by -15, so the usable range is 16-30 inclusive.
MIN_TEMP = 16
MAX_TEMP = 30
