# Hardware-confirmed profile: JBL Charge 6

ตรวจจริงผ่าน Windows/BLE วันที่ 2026-07-16 โดยส่ง read-only requests และ no-op write/read-back

| รายการ | ค่าที่ยืนยัน |
|---|---|
| Windows name | redacted (device-specific advertising name) |
| Model | JBL Charge 6 |
| PID | `20E3` |
| MID | `01` |
| Firmware | `3.0.7.1` |
| APK transport | `PROTOCOL_BLE` |
| EQ generation | legacy long-frame parametric C2, ไม่ใช่ Protocol 4 |
| Read EQ | command `98`, response `99` |
| Write EQ | command `97`, response `99` |
| Active/category | `C2/C2` |
| Sample rate | 48000 |
| Authentication | Windows pairing/bond เพียงพอใน session นี้; ไม่มี app-layer handshake ก่อน EQ read/write |

## GATT ที่อ่านจากเครื่องจริง

- `65786365-6c70-6f69-6e74-2e636f6d0000`: vendor service หลัก
  - `...0001`: notify + read
  - `...0002`: write + write-without-response
- `65786365-6c70-6f69-6e74-2e636e6c0000`: vendor service ชุดที่สอง
  - `...0001`: notify + read
  - `...0002`: write + write-without-response
- `00001800`: GAP
- `00001801`: GATT
- `0000FE2C`: Google service พร้อม characteristics `FE2C1234..123A`

Windows ยังลงทะเบียน service UUID `65786365-6C70-6F69-6E74-2E04FFE32001` บน BR/EDR side ซึ่ง encode PID/MID (`E3 20`, `01`)

## Custom EQ ที่อ่านได้ก่อนทดสอบ

| Band | Type | Frequency | Gain | Q |
|---:|---|---:|---:|---:|
| 1 | low shelf | 125 | +5.0 dB | 0.7 |
| 2 | peaking | 250 | +3.0 dB | 2.0 |
| 3 | peaking | 500 | -2.5 dB | 2.0 |
| 4 | peaking | 1000 | -3.0 dB | 2.0 |
| 5 | peaking | 2000 | -2.0 dB | 2.0 |
| 6 | peaking | 4000 | -0.5 dB | 2.0 |
| 7 | high shelf | 8000 | +1.0 dB | 0.7 |

ส่ง frame `97` ด้วยค่าข้างต้นกลับไปหนึ่งครั้ง จากนั้น firmware ตอบ `99` และ request `98` รอบใหม่ให้ค่าเดิมตรงทุก byte จึงไม่มี net EQ change

คำสั่ง `set-auto --pid 20e3` ถูกทดสอบ end-to-end ด้วยค่าเดิมชุดเดียวกันแล้ว: auto-selector เลือก `legacy-parametric/0x97`, response `0x99` ตรงกับ TX payload และ read-back รอบถัดไปตรงกันทุก byte

## UI limits จาก APK

- Custom band 1: -9..+6 dB; ค่าลบทีละ 0.75 dB, ค่าศูนย์/บวกทีละ 0.5 dB
- Custom bands 2–7: -6..+6 dB ทีละ 0.5 dB
- Custom frequency/Q ถูกกำหนดเป็นชุดในตาราง; UI ปกติแก้เฉพาะ gain
- preset ภายใน firmware/APK อาจใช้ frequency/Q และ gain นอก custom UI เช่น preset Energetic มี +7 dB ที่ 200 Hz จึงไม่ควรตีความ UI limit เป็น DSP hard limit

## Unsupported บนเครื่องนี้

- `61` EQ mode → `EE 61`
- `6C` simple EQ → `EE 6C`
- Protocol 4 feature `0E02`/Grip `0E7F` ไม่ใช่เส้นทางที่รุ่นนี้ใช้

การรัน full read-only probe รอบล่าสุดใช้ BLE random address ที่ถูกตัดออกจากเอกสาร public; address นี้เปลี่ยนได้และไม่ใช่ identity ถาวร ผล probe คือ firmware/advanced ตอบ, simple/mode ตอบ `EE`, และ Protocol 4 timeout ตรงกับ profile ข้างต้น
