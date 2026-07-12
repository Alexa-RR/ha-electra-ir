# Electra AC (IR) for Home Assistant

A custom `climate` integration that controls an **Electra** air conditioner over
infrared, built as a consumer of Home Assistant's
[`infrared`](https://www.home-assistant.io/integrations/infrared/) building-block
platform (introduced in HA **2026.4**).

It does **not** talk to any cloud. It computes the Electra/Toshiba RC-3 IR code
from the requested state (a port of
[barakwei/IRelectra](https://github.com/barakwei/IRelectra)) and sends it through
any IR emitter exposed to the `infrared` platform — e.g. **Broadlink** or
**ESPHome**.

## Requirements

- Home Assistant **2026.4** or newer.
- An IR emitter integration already set up that exposes an infrared emitter
  entity (Broadlink RM4, ESPHome with an IR LED, …), positioned in line of sight
  of the AC.

## Installation

1. Copy `custom_components/electra_ir` into your Home Assistant `config`
   directory (or add this repository to HACS as a custom repository).
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Electra AC (IR)**.
4. Select the infrared emitter to transmit through (a receiver is optional and
   reserved for future state sync). The config flow mirrors the built-in LG
   Infrared integration.

## Notes

- **Current temperature.** IR is one-way, so the AC reports nothing back. You
  can attach an existing temperature sensor as the current temperature — either
  during setup or later via the integration's **Configure** dialog. Leave it
  empty for none.
- **Assumed state.** Home Assistant tracks the state it believes the AC is in.
  If you use the physical remote, the two can drift — set the entity back to
  match and continue.
- **Power.** The power bit is absolute, not a toggle: any on-state command
  turns the unit on and applies the settings, and OFF is a dedicated command.
  The 34-bit encoder is verified byte-for-byte against the captured RC-3 codes
  in [SmartIR 1946.json](https://github.com/smartHomeHub/SmartIR/blob/master/codes/climate/1946.json).
- **Carrier frequency.** 38 kHz (`CARRIER_HZ` in `electra.py`), confirmed
  against the captured Broadlink codes.
- Adjusting temperature/fan/swing while the unit is *off* only updates the
  assumed state; nothing is transmitted until the unit is turned on.

## Feelit button (iFeel)

A **Feelit** button is exposed alongside the climate entity. Pressing it sends
the current room temperature (from the attached temperature sensor, falling
back to the setpoint) to the AC with Electra's *iFeel* bit set, so the unit
regulates by that reading. This is **experimental** — Electra's iFeel is not
fully documented, so behaviour may vary by model.

## Supported features

Modes (cool, heat, dry, fan-only, auto, off), target temperature (16–30 °C),
fan speed (auto/low/medium/high), and swing (on/off).
