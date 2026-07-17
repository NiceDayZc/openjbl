# Model coverage from JBL Portable 6.9.12

"Supported" means OpenJBL can build or parse packets for the path declared by the APK. It does not mean every firmware revision has been tested on hardware. Run `probe` first and always begin with a dry run.

| PID | Model | APK transport | EQ path |
|---|---|---|---|
| 0023 | JBL Flip 3 | SPP | No EQ declared by APK |
| 0024 | JBL Xtreme | SPP | No EQ declared by APK |
| 1ebc | JBL Charge 3 | BLE | No EQ declared by APK |
| 1ed1 | JBL Flip 4 | BLE | No EQ declared by APK |
| 1ed2 | JBL Pulse 3 | BLE | No EQ declared by APK |
| 1ee7 | JBL Boombox | CSR BLE | No EQ declared by APK |
| 1efc | JBL Xtreme 2 | CSR BLE | No EQ declared by APK |
| 1f17 | JBL Charge 4 | CSR BLE | No EQ declared by APK |
| 1f26 | JBL Xtreme 2 | QCC BLE | No EQ declared by APK |
| 1f27 | JBL Boombox | QCC BLE | No EQ declared by APK |
| 1f29 | JBL Charge 4 | QCC BLE | No EQ declared by APK |
| 1f31 | JBL Flip 5 | BLE | No EQ declared by APK |
| 1f53 | JBL Boombox 2 | GATT/BR-EDR | Simple 3-band (`0x6E`) |
| 1f56 | JBL Pulse 4 | BLE | No EQ declared by APK |
| 202f | JBL Xtreme 3 | BLE | Simple 3-band (`0x6E`) |
| 2038 | JBL Xtreme 2 GM | BLE | No EQ declared by APK |
| 2040 | JBL Charge 5 | BLE | Simple 3-band (`0x6E`) |
| 204f | JBL Flip 6 | GATT/BR-EDR | Simple 3-band (`0x6E`) |
| 2050 | JBL Pulse 5 | GATT/BR-EDR | Simple 3-band (`0x6E`) |
| 206d | JBL Boombox 3 | GATT/BR-EDR | Simple 3-band (`0x6E`) |
| 2075 | JBL Boombox 3 Wi-Fi | redirect product | Not controlled through Portable protocol |
| 208c | JBL Charge 5 Wi-Fi | redirect product | Not controlled through Portable protocol |
| 20dc | JBL Xtreme 4 | BLE | Advanced level/preset (`0x97`) |
| 20e3 | JBL Charge 6 | BLE | Legacy parametric 7-band (`0x97`), hardware confirmed |
| 20e4 | JBL Go 4 | BLE | Advanced level/preset (`0x97`) |
| 20f5 | JBL Clip 5 | BLE | Advanced level/preset (`0x97`) |
| 2107 | JBL Flip 7 | BLE | Legacy parametric 7-band (`0x97`) |
| 210a | JBL Go 4 | BLE | Advanced level/preset (`0x97`) |
| 2132 | JBL Grip | BLE Protocol 4 | Quantized 7-band (`0E7F`) |
| 214c | JBL Tuner 3 | BLE | Advanced 7-level/preset (`0x97`) |
| 214e | JBL Boombox 4 | BLE Protocol 4 | Parametric 7-band (`0E02`) |
| 215c | JBL Go 4 Duo L | BLE | Advanced level/preset (`0x97`) |
| 2168 | JBL Go 5 | BLE Protocol 4 | Quantized 7-band (`0E7F`) |
| 2169 | JBL Xtreme 5 | BLE Protocol 4 | Parametric 7-band (`0E02`) |
| 2181 | JBL Go 4 Duo R | BLE | Advanced level/preset (`0x97`) |
| 2185 | JBL Flip Essential 3 SE | BLE Protocol 4 | Quantized 7-band (`0E7F`) |
| 218a | JBL Charge Essential 3 SE | BLE Protocol 4 | Quantized 7-band (`0E7F`) |

## Automatic routing

`openjbl set-auto --pid PID GAIN...` selects in this order:

1. Grip, Go 5, and Essential SE Protocol 4 models: feature `0E7F`, with gain quantized through the APK table.
2. Other Protocol 4 models: feature `0E02`, seven-band parametric.
3. `7_BANDS_EQ`: legacy `0x97` with floating-point gain, frequency, and Q.
4. `EQ_BALANCE_SUPPORT`: legacy `0x6E` bass/mid/treble.
5. `PRESET_EQ`: legacy `0x97` signed-byte levels.

Some devices use a random, changing BLE address. Always use the latest result from `openjbl scan`; do not persist a BLE MAC as a permanent identity.
