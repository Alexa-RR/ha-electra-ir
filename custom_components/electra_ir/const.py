"""Constants for the Electra AC (IR) integration."""

from __future__ import annotations

DOMAIN = "electra_ir"

# Config entry keys.
CONF_EMITTER = "emitter"

# Climate limits (degrees Celsius). The Electra protocol encodes temperature as
# a 4-bit value offset by -15, so the usable range is 16-30 inclusive.
MIN_TEMP = 16
MAX_TEMP = 30
