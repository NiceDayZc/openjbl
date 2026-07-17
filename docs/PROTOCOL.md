# JBL Portable 6.9.12 protocol notes

Analysis date: 2026-07-16

Source: `JBL+Portable_6.9.12_APKPure.xapk`

Package: `com.harman.ble.jbllink`

This reference distinguishes facts confirmed by APK byte builders/parsers from behavior that still requires hardware validation.

## Transport confirmed from the APK

| Layer | Value |
|---|---|
| BLE default service | `65786365-6C70-6F69-6E74-2E636F6D0000` |
| RX notify characteristic | `...0001` |
| TX write characteristic | `...0002` |
| CCCD | `00002902-0000-1000-8000-00805F9B34FB` |
| Classic SPP | `00001101-0000-1000-8000-00805F9B34FB` |
| Requested MTU | 512 bytes; the negotiated value may be lower |
| Command timeout | 2000ms from `AppConfig.json`; class fallback is 1500ms |
| Rewrite count | 3 |

The UUID prefix `65786365-6C70-6F69-6E74-2E636F6D` decodes as ASCII `excelpoint.com`. Some models expose a service UUID encoding PID/MID; the app can fall back to the default UUID.

BLE advertisement service IDs recognized by the scan filter:

- `DFFD`: Harman service data Pro
- `FDDF`: Protocol 4
- `FC69`: Protocol 1
- `0ECB`: PartyBox

## Legacy frames

Normal frame:

```text
AA | command:1 | payload_length:1 | payload:N
```

Long frame, used by advanced EQ and some long responses:

```text
AA | command:1 | payload_length_be:2 | payload:N
```

These EQ frames have no CRC.

## EQ command IDs

| Direction | Hex | Meaning |
|---|---:|---|
| request | `61` | EQ mode |
| response | `62` | EQ mode |
| set | `63` | EQ mode |
| notify | `64` | EQ changed |
| request | `6C` | simple EQ |
| response | `6D` | simple EQ |
| set | `6E` | simple EQ |
| request | `98` | advanced EQ |
| response | `99` | advanced EQ |
| set | `97` | advanced EQ |

## Which reply answers which request

Nothing on the wire carries a correlation id, so a reply can only be matched to a
request by the command pairing. Each SDK command class declares its own answer in
`getResponseCommands()`, and they are not uniform -- guessing here is how a
speaker's unsolicited push gets counted as a write acknowledgement.

| Request | Answered by | Source |
|---|---|---|
| `41` REQ_VER | `42` REP_VER | `ReqVerCommand` |
| `61` REQ_EQ_MODE | `62` REP_EQ_MODE | `ReqEQModeCommand` |
| `6C` REQ_SIMPLE_EQ | `6D` RET_SIMPLE_EQ | `ReqSimpleEqCommand` |
| `98` REQ_ADVANCE_EQ | `99` RET_ADVANCE_EQ | `ReqAdvancedEQCommand` |
| **`97` SET_ADVANCE_EQ** | **`99` RET_ADVANCE_EQ** | `SetAdvancedEQCommand`, `SetAdvancedNewEQCommand` |
| `63` SET_EQ_MODE | `00` DEV_ACK, payload `[0x63, status]` | `SetEQModeCommand.onReceive` |
| `6E` SET_SIMPLE_EQ | `00` DEV_ACK payload `[0x6E, status]`, **or** a bare `6D` | `SetSimpleEqCommand.onReceive` |

Note the asymmetry: the two advanced setters are acknowledged by the `99` **RET**
frame, not by a `DEV_ACK`. A `00` acknowledgement echoes the command it answers in
`payload[0]` and its status in `payload[1]`; status `00` means success. `EE`
(`RET_UNSUPPORTED_CMD`) is a rejection and can answer anything.

`64` NOTIFY_EQ_CHANGE is device-initiated. It arrives whenever the speaker feels
like it, including between a write and its acknowledgement, and must never be
read as a reply.

### Protocol 4 replies

Protocol 4 carries its command id at byte offset 2, and `CommandProcessor` reads
it there. `SET_DEVICE_INFO_0002` responses are explicitly discarded by the app as
"only have Status Code, so skipped" -- the data comes back in a
`GET_DEVICE_INFO_0001` frame.

| Command id | Meaning |
|---:|---|
| `0001` | GET_DEVICE_INFO -- carries data |
| `0002` | SET_DEVICE_INFO -- status only |
| `0003` | NOTIFICATION_TO_APP -- device-initiated, never a reply |
| `0004` | NOTIFICATION_TO_DEVICE |

### Simple EQ

Set payload:

```text
category | count | (parameter_type | signed_level) * count
```

Parameter types are bass=1, mid=2, and treble=3. Custom category is `C1`; a second custom slot appears as `C2` in the same model.

Response payload:

```text
scope | active_category | [category | count | (type | value)*count]...
```

### Advanced-level EQ

```text
active_category | C1 | scope | count | (band_index | signed_level)*count
```

The APK defaults to scope=6 and supports band indices 1..7. Product configuration determines whether a model exposes this feature.

### Legacy parametric/C2 EQ

`SetAdvancedNewEQCommand` builds:

```text
active_category
active_category
band_count
sample_rate:u32 big-endian
bands...
```

Each band occupies 13 bytes:

```text
filter_type:u8
gain:f32 big-endian
frequency:f32 big-endian
Q:f32 big-endian
```

Filter types: low-shelf=0, peaking=1, high-shelf=2, low-pass=3, high-pass=4.

Both builder and response parser confirm the repeated active-category byte. The parser reads band count at offset 2 and sample rate at offsets 3..6.

## Protocol 4

The eight-byte header is little-endian:

```text
identifier:u16 = DD00 (bytes 00 DD; DD01 when forwarded)
command_id:u16       GET=0001, SET=0002
packet_count:u8
packet_index:u8
payload_length:u16
payload
```

Maximum packet payload is 490 bytes, keeping the app's ATT write at approximately 500 bytes or less.

SET feature payload:

```text
feature_id:u16 little-endian
value_length:u16 little-endian
value
```

EQ feature IDs:

- `0E01`: EQInfoQuery
- `0E02`: EQInfo
- `0E7F`: SetEQ for Grip, Go 5, and some Essential SE models

The all-EQ request is feature `0E01`, length=1, value=`FF`.

Protocol 4 parametric value for feature `0E02`:

```text
mapped_category:u8
enabled:u8 = 1
band_count:u8 = 7
reserved:u32be = 0
sample_rate:u32be = 48000
reserved:u32be = 0
reserved:u32be = 0
7 * band
```

Each band remains 13 bytes, but field order is:

```text
filter_type | frequency:f32be | gain:f32be | Q:f32be
```

Observed category mapping: bass boost 1 `01->50`, vocal `03->02`, signature `06->80`, relaxing `07->81`, energetic `08->82`, extreme `09->83`, reserved 2 `22->85`, custom `C1/C2->C1`.

Some Grip, Go 5, and Essential SE devices use feature `0E7F` with seven quantized values rather than full parametric bands. The custom form reconstructed from `getGripEQPayload` is:

```text
mapped_category:C1 | band1_index | band2_index | ... | band7_index | optional firmware tail
```

- Band 1 indices 0..12 represent +6..0 in 0.5 dB steps; indices 13..24 represent -0.75..-9 in 0.75 dB steps.
- Band 2-7 indices 0..24 represent +6..-6 in 0.5 dB steps.
- APK-classified Grip-style PIDs: `2132`, `2168`, `2185`, `218A`.

OpenJBL exposes these through `set-grip` and `set-auto`. The latter selects by PID instead of guessing from the advertising name.

## Requires confirmation on physical hardware

- Device PID/MID, firmware, and protocol generation
- Model-specific service UUID
- Actual level range permitted by the firmware UI
- Seven-band frequency and Q values accepted by that firmware revision
- Required bonding or authentication behavior
- Whether the speaker uses EQ feature `0E02` or Grip-style `0E7F`

## Primary decompilation sources

- `com/harman/sdk/setting/AppConfig.java`
- `com/harman/sdk/command/BaseCommand.java`
- `SetSimpleEqCommand.java`, `ReqSimpleEqCommand.java`
- `SetAdvancedEQCommand.java`, `SetAdvancedNewEQCommand.java`, `ReqAdvancedEQCommand.java`
- `com/harman/sdk/protocol4/cmd/AssembleCmd.java`
- `com/harman/sdk/protocol4/cmd/PortableControl.java`
- `com/harman/sdk/protocol4/cmd/imp/DeviceFeature.java`

Local decompilation output is stored under ignored `work/jadx/` and extracted XAPK content under ignored `work/xapk/`.
