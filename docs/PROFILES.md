# Curated sound profiles

โปรไฟล์เป็น tonal starting point ไม่ใช่การเพิ่มกำลังแอมป์หรือปลด limiter ค่าอ้างอิงเจ็ดจุดอยู่ที่ 125, 250, 500, 1k, 2k, 4k และ 8kHz จากนั้น resolver จะ interpolate ตาม log-frequency และ quantize ให้ตรงกับ model profile:

- Charge 6 และ Grip-style: band แรกใช้ step บวก 0.5/ลบ 0.75 dB; band อื่นใช้ 0.5 dB
- Protocol 4/legacy parametric ทั่วไป: 0.5 dB ภายในช่วง -6..+6
- simple 3-band และ advanced level: จำนวนเต็ม -6..+6
- รุ่น 5-band ใช้ความถี่จริงจาก preset asset ของรุ่น ไม่ได้ตัดเอาห้าแถบแรก

| Key | ชื่อ | Reference curve (125 → 8kHz) | ลักษณะ |
|---|---|---|---|
| `flat` | Flat / Reference | 0, 0, 0, 0, 0, 0, 0 | ไม่แต่งโทน |
| `balanced` | Balanced | 1, .5, 0, 0, 0, .5, 1 | สมดุลสำหรับฟังทุกวัน |
| `bass` | Bass Heavy | 6, 4, 1, -1, -1, 0, 1 | เบสหนักแต่คุม low-mid |
| `deep-bass` | Deep Bass | 6, 3, 0, -2, -1, 0, .5 | ต่ำลึกและเว้นพื้นที่กลาง |
| `punch` | Punch Bass | 4, 5, 2, -1, -1, .5, 1 | kick กระชับ มีแรงปะทะ |
| `warm` | Warm | 3, 2, 1, .5, 0, -.5, -1 | อุ่น นุ่ม ฟังนาน |
| `loudness` | Low-volume Loudness | 4, 2, 0, -1, 0, 1.5, 3 | ชดเชยการฟังระดับเบา |
| `clear` | Crystal Clear | 0, -1, -2, 0, 2, 3, 4 | ลดความอับ เพิ่ม presence/air |
| `bright` | Bright | -.75, -.5, -1, 0, 2, 4, 5 | เปิดปลายเสียงสำหรับ source ทึบ |
| `detail` | Detail Monitor | -1.5, -1, -1, 1, 2, 2.5, 2 | ตรวจรายละเอียดและ texture |
| `vocal` | Vocal Focus | -.75, -1, -1, 3, 4, 2, 0 | เสียงร้องเด่น |
| `podcast` | Podcast / Speech | -3, -2, -1, 3, 4, 2, -1 | คำพูดชัด ลด rumble |
| `acoustic` | Acoustic | 1, 1, .5, 1, 1.5, 2, 2 | body และรายละเอียดเครื่องสาย |
| `rock` | Rock | 4, 3, -1, 1, 3, 3, 2 | kick/guitar ชัด |
| `metal` | Metal | 3, 1, -2, 0, 3, 4, 2 | แยกกีตาร์และเพิ่ม attack |
| `hip-hop` | Hip-Hop | 6, 4, 0, -1, 1, 2, 3 | เบสใหญ่ เสียงร้องและ hi-hat ยังชัด |
| `edm` | EDM | 6, 4, -1, -2, 0, 3, 5 | V-shape สำหรับ electronic |
| `pop` | Pop | 3, 2, 0, 1, 2, 2.5, 3 | สด กระชับ เสียงร้องชัด |
| `jazz` | Jazz | 2, 1, .5, 1, 1, 1.5, 2 | อุ่น เป็นธรรมชาติ มี ambience |
| `classical` | Classical | 0, 0, -.5, 0, 1, 2, 3 | ตำแหน่งชิ้นดนตรีและอากาศ |
| `movie` | Cinema | 5, 3, 0, 1, 3, 2, 3 | impact, dialogue และบรรยากาศ |
| `gaming` | Gaming / Footsteps | 0, -1, -2, 0, 4, 5, 2 | ลดเบสบังรายละเอียด เน้น footsteps |
| `outdoor` | Outdoor | 6, 4, 1, 0, 2, 3, 3 | ชดเชยการสูญเสียเบสกลางแจ้ง |
| `night` | Night / Apartment | -4.5, -3, -1, 1, 2, 1, 0 | ลดแรงต่ำที่ส่งผ่านผนัง |

## แนวทางเลือก

- เปิดดังมาก: เริ่มจาก Balanced/Punch แทน Bass Heavy เพราะ limiter มี headroom น้อยลงเมื่อยกหลายแถบ
- ฟังเบา: Loudness ให้สมดุลกว่าการเร่ง bass อย่างเดียว
- เสียงทึบ: Clear ก่อน Bright; Bright อาจคมเกินกับ source ที่มี treble มากอยู่แล้ว
- ห้อง/โต๊ะที่บวม: Deep Bass หรือ Night จะลด 500Hz-1kHz และแรงสั่นสะเทือนมากกว่า Warm
- ทุก profile ควร preview และเริ่มด้วย volume ต่ำ รุ่นที่ยังไม่ hardware-confirmed อ้างอิง static APK profile เท่านั้น
