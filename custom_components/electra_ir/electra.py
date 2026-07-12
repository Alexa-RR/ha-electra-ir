"""Electra AC (RC-3) infrared protocol encoder.

This builds an :class:`infrared_protocols.commands.Command` that produces the raw
mark/space timing train for an Electra air conditioner, as a consumer of Home
Assistant's ``infrared`` building-block platform.

The protocol is a port of barakwei/IRelectra (the de-facto reference for the
Electra/Toshiba RC-3 remote common in Israel):

* 34-bit code, MSB first, Manchester encoded.
* Time unit ``UNIT`` = 992 us.
* Frame = ``[mark(3u), space(3u), manchester(code, 34)]`` repeated 3 times,
  followed by a trailing ``mark(4u)``.
* Manchester: a ``1`` bit is ``space(1u), mark(1u)``; a ``0`` bit is
  ``mark(1u), space(1u)``. Consecutive same-state runs are merged.

Bit layout (bit 33 = MSB):
    33      power toggle (the remote's power button toggles on/off)
    32-30   mode      (Cool 001, Heat 010, Auto 011, Dry 100, Fan 101, Off 111)
    29-28   fan       (Low 00, Medium 01, High 10, Auto 11)
    27-26   0
    25      swing
    24      iFeel
    23      0
    22-19   temperature (degrees C - 15)
    18      sleep
    17-2    0
    1       1  (fixed)
    0       0  (fixed)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from infrared_protocols.commands import Command

# --- Protocol timing -------------------------------------------------------

UNIT = 992  # microseconds, per barakwei/IRelectra
NUM_BITS = 34
REPEATS = 3

# Carrier frequency in Hz. The canonical IRelectra uses 33 kHz; the widely used
# liads ESPHome port uses 38 kHz. 38 kHz is the more common AC carrier and a
# good first try -- if the unit does not respond, switch this to 33000.
CARRIER_HZ = 38000


class ElectraMode(IntEnum):
    """Electra operating modes (3-bit field)."""

    COOL = 0b001
    HEAT = 0b010
    AUTO = 0b011
    DRY = 0b100
    FAN = 0b101
    OFF = 0b111


class ElectraFan(IntEnum):
    """Electra fan speeds (2-bit field)."""

    LOW = 0b00
    MEDIUM = 0b01
    HIGH = 0b10
    AUTO = 0b11


# Re-exported so callers don't need to import const.py just for the range.
MIN_TEMP = 16
MAX_TEMP = 30


@dataclass(slots=True)
class ElectraState:
    """The AC state to transmit.

    ``off`` is the power bit (bit 33). Verified against captured RC-3 codes
    (SmartIR 1946), this bit is *not* a toggle: every on/adjust command carries
    ``off=False`` (bit 33 = 0), and the AC is switched off by sending a command
    with ``off=True`` (bit 33 = 1). Sending any on-state command turns the unit
    on and applies the settings.
    """

    mode: ElectraMode = ElectraMode.COOL
    fan: ElectraFan = ElectraFan.AUTO
    temperature: int = 24
    swing: bool = False
    sleep: bool = False
    ifeel: bool = False
    off: bool = False

    def encode(self) -> int:
        """Pack the state into the 34-bit Electra code."""
        temp = max(MIN_TEMP, min(MAX_TEMP, int(self.temperature))) - 15
        num = 0
        num |= (1 if self.off else 0) << 33
        num |= (int(self.mode) & 0b111) << 30
        num |= (int(self.fan) & 0b11) << 28
        num |= (1 if self.swing else 0) << 25
        num |= (1 if self.ifeel else 0) << 24
        num |= (temp & 0b1111) << 19
        num |= (1 if self.sleep else 0) << 18
        num |= 1 << 1  # fixed ones bit
        return num


class ElectraACCommand(Command):
    """An :class:`infrared_protocols.commands.Command` for an Electra AC state."""

    def __init__(self, state: ElectraState, modulation: int = CARRIER_HZ) -> None:
        """Initialize from an :class:`ElectraState`."""
        # The 3x repeat is part of the protocol frame we build below, so the
        # platform-level repeat_count stays at its default of 0.
        super().__init__(modulation=modulation, repeat_count=0)
        self._code = state.encode()

    def get_raw_timings(self) -> list[int]:
        """Return the raw IR timings.

        Positive values are marks (carrier on) and negative values are spaces
        (carrier off), both in microseconds, as required by the infrared
        platform.
        """
        # Emit primitive (is_mark, units) segments, then merge same-state runs.
        segments: list[tuple[bool, int]] = []

        def mark(units: int) -> None:
            segments.append((True, units))

        def space(units: int) -> None:
            segments.append((False, units))

        def bit(value: int) -> None:
            if value:
                space(1)
                mark(1)
            else:
                mark(1)
                space(1)

        for _ in range(REPEATS):
            mark(3)
            space(3)
            for shift in range(NUM_BITS - 1, -1, -1):
                bit((self._code >> shift) & 1)
        mark(4)

        # Merge consecutive segments of the same state into single runs.
        merged: list[tuple[bool, int]] = []
        for is_mark, units in segments:
            if merged and merged[-1][0] == is_mark:
                merged[-1] = (is_mark, merged[-1][1] + units)
            else:
                merged.append((is_mark, units))

        # Convert run-lengths (in UNITs) to signed microseconds.
        return [
            units * UNIT if is_mark else -(units * UNIT)
            for is_mark, units in merged
        ]
