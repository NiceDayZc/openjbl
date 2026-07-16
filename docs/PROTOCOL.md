# JBL Portable 6.9.12 — protocol notes

วันที่วิเคราะห์: 2026-07-16
ไฟล์: `JBL+Portable_6.9.12_APKPure.xapk`
package: `com.harman.ble.jbllink`

เอกสารนี้แยก “ยืนยันจาก byte builder/parser ใน APK” ออกจาก “ต้องยืนยันกับ hardware” ชัดเจน

## Transport ที่ยืนยันจาก APK

| Layer | ค่า |
|---|---|
| BLE default service | `65786365-6C70-6F69-6E74-2E636F6D0000` |
| RX notify characteristic | `...0001` |
| TX write characteristic | `...0002` |
| CCCD | `00002902-0000-1000-8000-00805F9B34FB` |
| Classic SPP | `00001101-0000-1000-8000-00805F9B34FB` |
| requested MTU | 512 bytes (ตัวแอปอาจได้จริงต่ำกว่า) |
| command timeout | 2000 ms จาก asset `AppConfig.json` (class fallback 1500 ms) |
| rewrite count | 3 |

ชื่อ UUID `65786365-6C70-6F69-6E74-2E636F6D` ถอด ASCII ได้เป็น `excelpoint.com` ลำโพงบางรุ่นมี service UUID ซึ่ง encode PID/MID และแอปมี fallback กลับไป default UUID

BLE advertisement service IDs ที่ scan filter รู้จัก:

- `DFFD` — Harman service data Pro
- `FDDF` — Protocol 4
- `FC69` — Protocol 1
- `0ECB` — PartyBox

## Legacy frame

Normal:

```text
AA | command:1 | payload_length:1 | payload:N
```

Long frame (advanced EQ และ long response บางคำสั่ง):

```text
AA | command:1 | payload_length_be:2 | payload:N
```

ไม่มี CRC ใน EQ frame ชุดนี้ การตอบรับคำสั่ง set หลายตัวเป็น command `00` พร้อม payload `[original_command, status]`, status `00` คือสำเร็จ

## EQ command IDs

| Direction | Hex | ความหมาย |
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

### Simple EQ

Set payload:

```text
category | count | (parameter_type | signed_level) * count
```

parameter type: bass=1, mid=2, treble=3. Custom category คือ `C1`; custom อีก slot คือ `C2` ใน model เดียวกัน

Response payload:

```text
scope | active_category | [category | count | (type | value)*count]...
```

### Advanced level EQ

```text
active_category | C1 | scope | count | (band_index | signed_level)*count
```

APK ใช้ scope=6 เป็นค่าเริ่มต้น และรองรับ band index 1..7 แต่ product config เป็นตัวตัดสินว่ารุ่นใดเปิด feature นี้

### Parametric/C2 EQ (legacy transport)

SetAdvancedNewEQCommand สร้าง payload ดังนี้:

```text
active_category
active_category
band_count
sample_rate:u32 big-endian
bands...
```

แต่ละ band ยาว 13 bytes:

```text
filter_type:u8
gain:f32 big-endian
frequency:f32 big-endian
Q:f32 big-endian
```

filter type: low-shelf=0, peaking=1, high-shelf=2, low-pass=3, high-pass=4

การที่ active category ซ้ำ 2 byte ยืนยันจากทั้ง builder และ response parser: parser อ่าน count ที่ offset 2 และ sample rate ที่ offset 3..6

## Protocol 4

Header 8 bytes ใช้ little-endian:

```text
identifier:u16 = DD00 (bytes 00 DD; DD01 เมื่อ forward)
command_id:u16       GET=0001, SET=0002
packet_count:u8
packet_index:u8
payload_length:u16
payload
```

packet payload สูงสุด 490 bytes แอปจึงได้ ATT write ไม่เกินประมาณ 500 bytes

SET feature payload:

```text
feature_id:u16 little-endian
value_length:u16 little-endian
value
```

EQ feature IDs:

- `0E01` EQInfoQuery
- `0E02` EQInfo
- `0E7F` SetEQ (ใช้กับ Grip/Go5/บาง Essential SE)

ค่าขอ EQ ทั้งหมดคือ feature `0E01`, length=1, value=`FF`

Protocol 4 parametric EQ value ของ feature `0E02`:

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

แต่ละ band ยังยาว 13 bytes แต่ลำดับเปลี่ยนเป็น:

```text
filter_type | frequency:f32be | gain:f32be | Q:f32be
```

Protocol 4 map category ที่พบ: bass boost 1 `01→50`, vocal `03→02`, signature `06→80`, relaxing `07→81`, energetic `08→82`, extreme `09→83`, reserved 2 `22→85`, custom `C1/C2→C1`

รุ่น Grip/Go5/Essential SE บางตัวใช้ feature `0E7F` และ payload แบบ quantized 7 ค่าแทน parametric เต็มรูปแบบ รูปแบบ custom ที่ถอดจาก `getGripEQPayload` คือ:

```text
mapped_category:C1 | band1_index | band2_index | ... | band7_index | optional firmware tail
```

- band 1 index 0..12 แทน +6..0 ทีละ 0.5 และ index 13..24 แทน -0.75..-9 ทีละ 0.75
- band 2–7 index 0..24 แทน +6..-6 ทีละ 0.5
- PID ที่ APK แยกเป็น Grip-style: `2132`, `2168`, `2185`, `218A`

Python รองรับผ่าน `set-grip` และ `set-auto`; คำสั่งหลังบังคับเลือก variant จาก PID จึงไม่เดาจากชื่อ advertising

## สิ่งที่ต้องยืนยันกับลำโพงจริง

- PID/MID, firmware และ protocol generation ของเครื่อง
- service UUID แบบเฉพาะรุ่น
- ช่วง level ที่ UI อนุญาตจริง (model บอกเพียงชนิด byte/scope)
- 7-band frequency/Q ที่ firmware รุ่นนั้นยอมรับ
- bonding/authentication ที่ firmware บังคับใช้
- ลำโพงใช้ EQ feature `0E02` หรือ Grip-style `0E7F`

## แหล่งหลักในผล decompile

- `com/harman/sdk/setting/AppConfig.java`
- `com/harman/sdk/command/BaseCommand.java`
- `SetSimpleEqCommand.java`, `ReqSimpleEqCommand.java`
- `SetAdvancedEQCommand.java`, `SetAdvancedNewEQCommand.java`, `ReqAdvancedEQCommand.java`
- `com/harman/sdk/protocol4/cmd/AssembleCmd.java`
- `com/harman/sdk/protocol4/cmd/PortableControl.java`
- `com/harman/sdk/protocol4/cmd/imp/DeviceFeature.java`

ผล decompile ทั้งชุดอยู่ที่ `work/jadx/` และ XAPK ที่แยกแล้วอยู่ที่ `work/xapk/`
