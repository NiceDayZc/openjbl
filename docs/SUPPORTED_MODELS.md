# Model coverage จาก JBL Portable 6.9.12

คำว่า “รองรับ” ในตารางนี้หมายถึงโปรแกรมสร้าง/อ่าน packet ตามเส้นทางที่ APK ประกาศได้ ไม่ได้หมายความว่าทุก firmware ถูกทดสอบกับฮาร์ดแวร์จริงแล้ว ควรรัน `probe` ก่อนและเริ่มจาก dry-run เสมอ

| PID | รุ่น | transport จาก APK | เส้นทาง EQ |
|---|---|---|---|
| 0023 | JBL Flip 3 | SPP | APK ไม่ประกาศ EQ |
| 0024 | JBL Xtreme | SPP | APK ไม่ประกาศ EQ |
| 1ebc | JBL Charge 3 | BLE | APK ไม่ประกาศ EQ |
| 1ed1 | JBL Flip 4 | BLE | APK ไม่ประกาศ EQ |
| 1ed2 | JBL Pulse 3 | BLE | APK ไม่ประกาศ EQ |
| 1ee7 | JBL Boombox | CSR BLE | APK ไม่ประกาศ EQ |
| 1efc | JBL Xtreme 2 | CSR BLE | APK ไม่ประกาศ EQ |
| 1f17 | JBL Charge 4 | CSR BLE | APK ไม่ประกาศ EQ |
| 1f26 | JBL Xtreme 2 | QCC BLE | APK ไม่ประกาศ EQ |
| 1f27 | JBL Boombox | QCC BLE | APK ไม่ประกาศ EQ |
| 1f29 | JBL Charge 4 | QCC BLE | APK ไม่ประกาศ EQ |
| 1f31 | JBL Flip 5 | BLE | APK ไม่ประกาศ EQ |
| 1f53 | JBL Boombox 2 | GATT/BR-EDR | simple 3-band (`0x6E`) |
| 1f56 | JBL Pulse 4 | BLE | APK ไม่ประกาศ EQ |
| 202f | JBL Xtreme 3 | BLE | simple 3-band (`0x6E`) |
| 2038 | JBL Xtreme 2 GM | BLE | APK ไม่ประกาศ EQ |
| 2040 | JBL Charge 5 | BLE | simple 3-band (`0x6E`) |
| 204f | JBL Flip 6 | GATT/BR-EDR | simple 3-band (`0x6E`) |
| 2050 | JBL Pulse 5 | GATT/BR-EDR | simple 3-band (`0x6E`) |
| 206d | JBL Boombox 3 | GATT/BR-EDR | simple 3-band (`0x6E`) |
| 2075 | JBL Boombox 3 Wi-Fi | redirect product | ไม่ควบคุมผ่าน Portable protocol |
| 208c | JBL Charge 5 Wi-Fi | redirect product | ไม่ควบคุมผ่าน Portable protocol |
| 20dc | JBL Xtreme 4 | BLE | advanced level/preset (`0x97`) |
| 20e3 | JBL Charge 6 | BLE | legacy parametric 7-band (`0x97`) — ยืนยันเครื่องจริง |
| 20e4 | JBL Go 4 | BLE | advanced level/preset (`0x97`) |
| 20f5 | JBL Clip 5 | BLE | advanced level/preset (`0x97`) |
| 2107 | JBL Flip 7 | BLE | legacy parametric 7-band (`0x97`) |
| 210a | JBL Go 4 | BLE | advanced level/preset (`0x97`) |
| 2132 | JBL Grip | BLE Protocol 4 | quantized 7-band (`0E7F`) |
| 214c | JBL Tuner 3 | BLE | advanced 7-level/preset (`0x97`) |
| 214e | JBL Boombox 4 | BLE Protocol 4 | parametric 7-band (`0E02`) |
| 215c | JBL Go 4 Duo L | BLE | advanced level/preset (`0x97`) |
| 2168 | JBL Go 5 | BLE Protocol 4 | quantized 7-band (`0E7F`) |
| 2169 | JBL Xtreme 5 | BLE Protocol 4 | parametric 7-band (`0E02`) |
| 2181 | JBL Go 4 Duo R | BLE | advanced level/preset (`0x97`) |
| 2185 | JBL Flip Essential 3 SE | BLE Protocol 4 | quantized 7-band (`0E7F`) |
| 218a | JBL Charge Essential 3 SE | BLE Protocol 4 | quantized 7-band (`0E7F`) |

## การเลือกอัตโนมัติ

`jblctl set-auto --pid PID GAIN...` ใช้ลำดับนี้:

1. Protocol 4 รุ่น Grip/Go 5/Essential SE → feature `0E7F` และแปลง gain เป็นดัชนีตามตาราง APK
2. Protocol 4 รุ่นอื่น → feature `0E02` แบบ parametric 7 แถบ
3. feature `7_BANDS_EQ` → legacy `0x97` แบบ float gain/frequency/Q
4. feature `EQ_BALANCE_SUPPORT` → legacy `0x6E` แบบ bass/mid/treble
5. feature `PRESET_EQ` → legacy `0x97` แบบ signed-byte levels

บริการ BLE บางเครื่องมี address แบบสุ่มและเปลี่ยนได้ ให้ใช้ address ล่าสุดจาก `jblctl scan` ไม่ควรบันทึก BLE MAC แบบถาวร
