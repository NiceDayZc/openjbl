# JBL PC Control

เครื่องมือ Python สำหรับอ่าน/วิเคราะห์/ปรับ EQ ของลำโพงที่รองรับแอป JBL Portable จากคอมพิวเตอร์ สร้างจากการวิเคราะห์แบบ static ของ `JBL Portable 6.9.12` โดยไม่แก้ APK ต้นฉบับ

> โครงการอิสระเพื่อการทำงานร่วมกันกับฮาร์ดแวร์ของผู้ใช้ ไม่เกี่ยวข้องหรือได้รับการรับรองจาก JBL/Harman เครื่องหมายการค้าเป็นของเจ้าของแต่ละราย ห้าม commit หรือแจก APK/firmware พร้อม repository นี้

รองรับ:

- BLE scan, ดู advertisement, manufacturer data และ UUID
- แสดง GATT service/characteristic ทั้งหมด
- BLE GATT ค่าเริ่มต้นของ Harman/JBL และ Bluetooth Classic SPP ผ่าน COM port
- EQ mode, simple 3-band, advanced level EQ, parametric 7-band
- Protocol 4 EQ สำหรับลำโพงรุ่นใหม่
- raw packet capture/decode และส่ง packet แบบผู้เชี่ยวชาญ
- dry-run เป็นค่าเริ่มต้นสำหรับทุกคำสั่งที่เปลี่ยนค่าลำโพง
- เลือก wire protocol อัตโนมัติจาก PID ด้วย `set-auto`

## ติดตั้ง

เปิด PowerShell ในโฟลเดอร์นี้:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

เปิด TUI:

```powershell
jbltui
```

TUI มี BLE device table, model/PID selector, read-only multi-generation probe, model-aware EQ read, packet preview, guarded apply และ JSONL audit log โดยการเขียนต้องเปิดสวิตช์และพิมพ์ `APPLY` ตรงตัว Audit log เก็บ hash ของ target แทน Bluetooth address

หน้าจอเป็น monochrome ขาวดำ พร้อม status strip แยก SYSTEM, DEVICE, PROTOCOL และ SAFETY, แสดง firmware/service/probe path, EQ curve แบบสด, reply count และ activity log แบบละเอียด เนื้อหาแบ่งเป็นสาม workspace tabs คือ DEVICE, EQUALIZER และ ACTIVITY จึงใช้งานได้ครบแม้ terminal ขนาด 80×24

ไฟล์ config/audit อยู่ใต้ `%LOCALAPPDATA%\jbl-pc-control\` บน Windows และถูก `.gitignore` ไว้

Bluetooth ต้องเปิดอยู่ และ Windows ต้องอนุญาต Location/Bluetooth ให้โปรแกรมเดสก์ท็อป หากใช้ SPP ให้ pair ลำโพงใน Windows ก่อน แล้วดู COM port ใน Device Manager > Ports (COM & LPT)

## ขั้นตอนที่ปลอดภัยที่สุด

1. ปิดแอป JBL Portable บนโทรศัพท์ ไม่ให้แย่ง connection
2. สแกนหาอุปกรณ์:

```powershell
jblctl scan --seconds 10
```

3. ดู service โดยแทนค่า address จากผล scan:

```powershell
jblctl services --address "ADDRESS"
```

หรือให้โปรแกรมอ่านทุก generation ที่รู้จักโดยไม่เปลี่ยนค่าใด ๆ:

```powershell
jblctl probe --address "ADDRESS" --pid 20e3 --timeout 3
jblctl get-auto --address "ADDRESS" --pid 20e3
```

ถ้ารู้ชื่อรุ่นหรือ PID ให้ดู transport, feature และเส้นทาง EQ ที่ฐานข้อมูลจาก APK ระบุ:

```powershell
jblctl models "Flip 7"
jblctl models 204f
```

ค่า BLE ที่พบใน APK:

- Service: `65786365-6c70-6f69-6e74-2e636f6d0000`
- RX/notify: `...0001`
- TX/write: `...0002`
- CCCD: `00002902-0000-1000-8000-00805f9b34fb`
- SPP: `00001101-0000-1000-8000-00805f9b34fb`

บางรุ่นสร้าง service UUID ตาม PID จึงอาจไม่ใช้ service ค่าเริ่มต้น แต่ RX/TX มักเหมือนเดิม ให้ใช้ `services` หา UUID แล้วส่ง `--service`, `--rx`, `--tx` เพื่อ override

4. อ่าน EQ รุ่นเดิม:

```powershell
jblctl get-mode --address "ADDRESS"
jblctl get-firmware --address "ADDRESS"
jblctl get-simple --address "ADDRESS"
jblctl get-advanced --address "ADDRESS" --timeout 4
```

5. ถ้ารุ่นใหม่เป็น Protocol 4:

```powershell
jblctl get-p4-eq --address "ADDRESS"
```

## ปรับ EQ

ทุกคำสั่งด้านล่างจะแสดง TX packet อย่างเดียวก่อน ถ้าตรวจแล้วถูกต้องจึงเพิ่ม `--apply`

วิธีแนะนำสำหรับรุ่นที่อยู่ในฐานข้อมูล APK คือระบุ PID แล้วส่ง gain ตามจำนวนแถบของรุ่น โปรแกรมจะเลือก simple, advanced, legacy parametric, Protocol 4 `0E02` หรือ Grip-style `0E7F` ให้เอง:

```powershell
jblctl set-auto --pid 20e3 --address "ADDRESS" 5 3 -2.5 -3 -2 -0.5 1
jblctl set-auto --pid 20e3 --address "ADDRESS" 5 3 -2.5 -3 -2 -0.5 1 --apply
```

โปรไฟล์เสียงสำเร็จรูปจะ map curve ให้ตรงจำนวนแถบ/ความถี่/step ของแต่ละ PID โดยอัตโนมัติ:

```powershell
jblctl profiles
jblctl profiles --pid 20e3
jblctl set-profile --pid 20e3 --address "ADDRESS" bass
jblctl set-profile --pid 20e3 --address "ADDRESS" clear --apply
```

มี 24 profile เช่น Bass Heavy, Deep Bass, Punch Bass, Warm, Crystal Clear, Vocal, Podcast, Rock, Metal, Hip-Hop, EDM, Jazz, Classical, Cinema, Gaming, Outdoor และ Night รายละเอียดอยู่ใน [docs/PROFILES.md](docs/PROFILES.md)

ดูรุ่นและ preset ที่ APK มีให้ด้วย `jblctl models` และ `jblctl presets --pid PID` คำสั่ง `set-auto` จะปฏิเสธ PID ที่ APK ไม่ประกาศ EQ แทนการเดา packet

Simple 3-band (ค่าบน wire เป็น signed byte; ช่วงจริงขึ้นกับรุ่น):

```powershell
jblctl set-simple --address "ADDRESS" --bass 2 --mid 0 --treble 3
jblctl set-simple --address "ADDRESS" --bass 2 --mid 0 --treble 3 --apply
```

Advanced แบบระดับ 7 แถบ:

```powershell
jblctl set-levels --address "ADDRESS" 0 1 2 3 2 1 0
```

Parametric แบบเดิม รูปแบบ band คือ `type,frequency,gain,q`:

```powershell
jblctl set-parametric --address "ADDRESS" `
  --band low_shelf,125,1.5,0.707 `
  --band peaking,250,0,1.0 `
  --band peaking,500,-1,1.0 `
  --band peaking,1000,0,1.0 `
  --band peaking,2000,1,1.0 `
  --band peaking,4000,0,1.0 `
  --band high_shelf,8000,1.5,0.707
```

Protocol 4 ใช้ arguments ชุดเดียวกัน แต่เปลี่ยนคำสั่งเป็น `set-p4-parametric` และต้องมี 7 แถบพอดี

สำหรับ Charge 6 PID `20E3` ใช้คำสั่งเฉพาะรุ่นได้ โดยเรียง gain เป็น 125, 250, 500, 1k, 2k, 4k, 8k Hz:

```powershell
jblctl set-charge6 --address "ADDRESS" 5 3 -2.5 -3 -2 -0.5 1
jblctl set-charge6 --address "ADDRESS" 0 0 0 0 0 0 0 --apply
```

Band แรกใช้ช่วง -9..+6 dB (ฝั่งลบทีละ 0.75, ฝั่งบวกทีละ 0.5); band 2–7 ใช้ -6..+6 dB ทีละ 0.5 ตาม mapping ของ UI ใน APK

ชนิด filter:

- `low_shelf` = 0
- `peaking` = 1
- `high_shelf` = 2
- `low_pass` = 3
- `high_pass` = 4

## จับและถอด packet

```powershell
jblctl listen --address "ADDRESS" --seconds 60 --log capture.txt
jblctl decode "AA 62 01 01"
```

ส่ง raw packet ถูกล็อกสองชั้น:

```powershell
jblctl raw --address "ADDRESS" "AA 61 00"
jblctl raw --address "ADDRESS" "..." --apply --i-understand
```

## Bluetooth Classic SPP

เมื่อ Windows สร้าง outgoing COM port แล้ว ใช้ `--port` แทน `--address`:

```powershell
jblctl get-simple --port COM7
jblctl set-simple --port COM7 --bass 1 --mid 0 --treble 1 --apply
```

baud rate ไม่มีผลกับ RFCOMM จริง แต่ pyserial ต้องรับค่า จึงใช้ 115200 เป็นค่าเริ่มต้น

## ข้อจำกัดสำคัญ

- APK รองรับลำโพงหลาย generation จึงไม่มี packet เดียวที่ถูกกับทุกรุ่น
- Windows อาจแสดง BLE address เป็น device identifier แทน MAC; ให้ใช้ค่าจาก `scan`
- ควรอ่านค่าปัจจุบันและเก็บ capture ก่อนเขียนเสมอ
- ไม่ได้ทำ OTA, authentication bypass, factory reset หรือคำสั่งทำลายข้อมูล
- การควบคุมเสียง A2DP/AVRCP ของ Windows (เล่น/หยุด/volume) เป็นคนละ protocol กับ EQ vendor command
- หากอ่านได้แต่เขียนไม่ได้ ลำโพงอาจต้อง pair/bond, ต้องใช้ write-with-response อีกแบบ หรือใช้ Protocol 4

รายละเอียด byte-level และหลักฐานจาก APK อยู่ใน [docs/PROTOCOL.md](docs/PROTOCOL.md)

ตารางความครอบคลุมทุกรุ่นอยู่ใน [docs/SUPPORTED_MODELS.md](docs/SUPPORTED_MODELS.md) และผลยืนยัน Charge 6 เครื่องจริงอยู่ใน [docs/DEVICE_CHARGE6_20E3.md](docs/DEVICE_CHARGE6_20E3.md)

## ใช้เป็น Python module

```python
from jbl_pc.models import auto_eq_frames, auto_read_frames
from jbl_pc.protocol import hex_bytes

read_path, read_frames = auto_read_frames("20e3")
write_path, write_frames = auto_eq_frames("20e3", [5, 3, -2.5, -3, -2, -0.5, 1])
print(read_path, [hex_bytes(frame) for frame in read_frames])
print(write_path, [hex_bytes(frame) for frame in write_frames])
```

builder ไม่ทำ Bluetooth I/O เอง จึงนำไปใช้ในโปรแกรมอื่นและทดสอบแบบ deterministic ได้ การส่งจริงอยู่ใน `jbl_pc.transport` และควรคง safety confirmation ของ application ชั้นบนไว้

## QA และเตรียมขึ้น GitHub

```powershell
pytest
ruff check .
ruff format --check .
mypy src/jbl_pc
bandit -q -c pyproject.toml -r src/jbl_pc
pip-audit .
python -m build
twine check dist/*
```

GitHub Actions รัน Windows/Linux บน Python 3.10/3.12 พร้อม test, coverage, lint, typing, security และ package validation ไฟล์ XAPK/APK, `work/`, `tools/`, captures, local config และ audit log จะไม่ถูก commit ดูผล audit ปัจจุบันใน [docs/AUDIT.md](docs/AUDIT.md)
