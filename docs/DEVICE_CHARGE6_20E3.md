# Hardware-confirmed profile: JBL Charge 6

Validated over Windows BLE on 2026-07-16 using read-only requests, a no-op write/read-back cycle, and a controlled change/restore cycle.

| Field | Confirmed value |
|---|---|
| Windows name | Redacted device-specific advertising name |
| Model | JBL Charge 6 |
| PID | `20E3` |
| MID | `01` |
| Firmware | `3.0.7.1` |
| APK transport | `PROTOCOL_BLE` |
| EQ generation | Legacy long-frame parametric C2, not Protocol 4 |
| Read EQ | Command `98`, response `99` |
| Write EQ | Command `97`, response `99` |
| Active/category | `C2/C2` |
| Sample rate | 48000 |
| Authentication | Windows pairing/bonding was sufficient; no application-layer handshake preceded EQ reads or writes |

## GATT observed on hardware

- `65786365-6c70-6f69-6e74-2e636f6d0000`: primary vendor service
  - `...0001`: notify + read
  - `...0002`: write + write without response
- `65786365-6c70-6f69-6e74-2e636e6c0000`: secondary vendor service
  - `...0001`: notify + read
  - `...0002`: write + write without response
- `00001800`: GAP
- `00001801`: GATT
- `0000FE2C`: Google service with characteristics `FE2C1234..123A`

Windows also registered service UUID `65786365-6C70-6F69-6E74-2E04FFE32001` on the BR/EDR side. It encodes PID/MID (`E3 20`, `01`).

## Custom EQ read before validation

| Band | Type | Frequency | Gain | Q |
|---:|---|---:|---:|---:|
| 1 | low shelf | 125 | +5.0 dB | 0.7 |
| 2 | peaking | 250 | +3.0 dB | 2.0 |
| 3 | peaking | 500 | -2.5 dB | 2.0 |
| 4 | peaking | 1000 | -3.0 dB | 2.0 |
| 5 | peaking | 2000 | -2.0 dB | 2.0 |
| 6 | peaking | 4000 | -0.5 dB | 2.0 |
| 7 | high shelf | 8000 | +1.0 dB | 0.7 |

The same values were sent once in a `97` frame. Firmware returned `99`; a subsequent `98` request reproduced every byte, confirming no net EQ change.

`set-auto --pid 20e3` was also validated end to end with the same no-op values. The selector chose `legacy-parametric/0x97`, the `0x99` response matched the TX payload, and the next read-back matched byte for byte.

The verification pipeline was then tested with an actual state transition: band 7 changed from `0.0` to `+0.5` dB, returned one write response, and read back at `+0.5` with zero delta across all seven bands. The original `0.0` value was restored immediately, returned one response, and a second read-back again matched all seven original values with zero delta.

### Unresolved: shelf Q, 0.7 or 0.707

The Q values in the table above are what was read off the device and written down
as `0.7`. The APK's own `custom_c2_eq.json` ships `0.707` for both shelves, and
OpenJBL now sends `0.707`, on the reasoning that matching the app's bytes is the
safer default when the two disagree.

Which one the firmware actually holds is unknown. `0.707` as float32 is
`0.7070000171661377`, so a raw readback would not print as `0.7` on its own --
the recorded value was probably rounded when this table was written, but nobody
checked, and the readback was not kept.

It does not affect verification: `verify_eq_readback` compares gain only. Resolve
it by reading the raw `99` payload off the hardware and comparing bytes 9-12 of
band 1 against `struct.pack(">f", 0.707)` = `3F34FDF4`.

## APK UI limits

- Custom band 1: -9..+6 dB; negative values use 0.75 dB steps, while zero and positive values use 0.5 dB steps.
- Custom bands 2-7: -6..+6 dB in 0.5 dB steps.
- Custom frequency and Q are fixed by a table; the normal UI changes gain only.
- Built-in firmware/APK presets may exceed custom-UI frequency, Q, or gain limits. For example, Energetic includes +7 dB at 200Hz, so UI limits must not be interpreted as DSP hard limits.

## Unsupported on this device

- `61` EQ mode returned `EE 61`.
- `6C` simple EQ returned `EE 6C`.
- Protocol 4 feature `0E02` and Grip `0E7F` are not used by this model.

The latest full read-only probe used a random BLE address omitted from public documentation. That address can change and is not a permanent identity. Firmware and advanced requests responded, simple and mode returned `EE`, and Protocol 4 timed out, all consistent with this profile.
