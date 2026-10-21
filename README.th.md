# TER-AI (ภาษาไทย)

[English README](README.md)

TER-AI คือชุด AI ภาษาไทยที่รันออฟไลน์บน CPU ได้ฟรี ไม่ต้องใช้ GPU และไม่ต้องส่งข้อมูลขึ้น cloud ทำร่วมกับ Sesame

## ส่วนที่ release แล้ว (v0.13.0)

| ส่วน | ทำอะไร | ตั้งแต่ |
|---|---|---|
| Intent router | อ่านข้อความภาษาไทยหรือไทยปนอังกฤษทีละข้อความ แก้คำพิมพ์ผิดที่เจอบ่อย แล้วบอกว่าเป็น intent ไหนใน 15 แบบ พร้อมคะแนนความมั่นใจ ตัวโมเดลขนาด 1.1 MB ไม่ต้องลง library เพิ่ม | v0.7.0 |
| Chat | แชตภาษาไทยแบบออฟไลน์ มี tool จริง (เครื่องคิดเลข วันที่และเวลา แปลงหน่วย) ตอบจากชุดความรู้ Wikipedia ภาษาไทยที่แนบมาพร้อมบอกแหล่ง จำข้อมูลข้ามการเปิดใหม่ได้ และตอบว่า "ไม่รู้" แทนการเดา ข้างในไม่มีโมเดลภาษา (LLM) | v0.8.0 |
| TTH | อ่านภาษาไทยออกเสียงด้วยโมเดลเสียงที่รันในเครื่อง (Wayu-Paxa-TTS-Edge) มี edge-tts เป็นตัวสำรองแบบออนไลน์ ทั้งสองตัวเลือกลงได้ตามต้องการ | v0.10.0 |
| SANKPUP | สร้างภาพด้วยการเขียน code SVG (ใช้ Gemma 4 ในเครื่อง หรือตัวสร้างแบบออฟไลน์ที่ฝังมา) กรอง code ให้ปลอดภัย แล้วแปลงเป็น PNG หรือ JPG ไม่ใช่โมเดลสร้างภาพ | v0.11.0 |
| MuML 1.0 WA | แต่งและเล่นเพลงในเบราว์เซอร์จากคำสั่งภาษาไทยหรืออังกฤษ โน้ตมาจากตัวเขียนโน้ตแบบ Markov (Markov v1 ยังไม่ใช่โมเดล MuML 1.0 ที่ train เอง) เสียงทุกเสียงสร้างด้วย Web Audio API | v0.12.0 |
| MUML 1.0 HIQ | สร้างเพลงเป็นไฟล์เสียงจริง (.mp3/.wav) บน CPU จากคำสั่งภาษาไทยหรืออังกฤษ ใส่เนื้อร้องได้ ใช้ ACE-Step 1.5 กับเพลงบรรเลงและเพลงอังกฤษ และ YuE2-3B กับเนื้อไทย โหลด weights ครั้งเดียวด้วย `terai muml --hiq --setup` ยังช้าบน CPU และเนื้อไทยฟังออกแค่บางส่วน | v0.13.0 |

- หน้า demo: https://klanarongz2009-sketch.github.io/terai-router/
- Repository: https://github.com/klanarongz2009-sketch/terai-router
- Wiki: https://github.com/klanarongz2009-sketch/terai-router/wiki

```
$ terai "เส็ดหรือยัง"
status  1.00  เสร็จหรือยัง
```

## ที่มาของชื่อ

TER มาจากคำว่า "เธอ" ใช้ได้ทั้งสองทาง TER-AI เรียกผู้ใช้ว่าเธอ และผู้ใช้ก็เรียก TER-AI ว่าเธอ

## ผลทดสอบ (v0.13.0 วัดเมื่อ 21 ต.ค. 2026)

เครื่อง AMD EPYC 8 core ไม่มี GPU, Python 3.13.7 ใช้สคริปต์ใน repo นี้

- **Intent router:** test set ที่ freeze ไว้ได้ 97.6% (121/124) ใช้ 0.167 ms ต่อข้อความ ส่วน held-out ได้ 99.1% (111/112)
- **Chat eval:** ชุด frozen 81/81 turns, held-out 37/37 turns, regression 16/16 turns
- **เบราว์เซอร์เทียบกับ Python (parity):** router 607/607, chat 790/790, TTH 1,700/1,700, SANKPUP 688/688, MuML 1.0 WA 330/330, Temmo remix 42/42
- **Unit test:** pytest ผ่าน 293 ข้าม 4
- **MUML 1.0 HIQ (เพลงเนื้อไทย 4 บรรทัด, yue2, seed 42, ไม่ใส่ `--duration`):** ใช้เวลา 24:53 นาที peak RSS 2.93 GB เพลงจบเองที่ 50.6 วินาทีแล้ว fade-out 2.5 วินาที CER 0.8598 ได้ยินคำจากเนื้อ 14/30 คำ ครบทั้ง 4 บรรทัด (วัดด้วย ASR ภาษาไทยบนเพลงที่มีดนตรีปน จึงเป็นค่าคร่าวๆ) โหมด split ได้ CER 0.2430 (20/30) แต่เป็นเสียงพูดบนจังหวะ ไม่ใช่การร้อง

รายละเอียดคำสั่งที่ใช้วัดอยู่ใน [README ภาษาอังกฤษ](README.md#results-v0130-measured-2026-10-21) และ [docs/MUML-HIQ.md](docs/MUML-HIQ.md)

## MUML 1.0 HIQ

```
pip install git+https://github.com/klanarongz2009-sketch/terai-router.git@v0.13.0
terai muml --hiq --setup     # ครั้งแรกครั้งเดียว: โหลด weights และ build acestep.cpp กับ yue2.cpp (ต้องมี git, cmake, C++17)
terai muml --hiq "เพลงลูกทุ่งสนุกๆ มีพิณกับแคน จังหวะ 130" -o song.mp3
terai muml --hiq "เพลงป๊อปช้าๆ ตอนกลางคืน" --lyrics lyrics_th.txt -o night.mp3
```

- **`--setup`:** เช็ก git, cmake และ C++ compiler ก่อนเริ่มโหลด ถ้าขาดตัวไหนจะบอกวิธีแก้ทันที และหา cmake ที่ลงด้วย pip ใน venv เจอ
- **`--fade-out`:** ค่าเริ่มต้น 2.5 วินาที ใส่ให้เองเมื่อตอนจบเพลงยังดังเกิน -40 dB (ต้องมี ffmpeg)
- **ความยาวเพลง yue2:** ถ้าไม่ใส่ `--duration` จะคำนวณจากจำนวนบรรทัดเนื้อร้อง เนื้อ 4 บรรทัดได้ 90 วินาที
- **ข้อจำกัด:** รันบน CPU ช้า (เพลงไทย 90 วินาทีใช้ราว 25 นาที) และเนื้อไทยยังฟังชัดแค่บางส่วน

## กำลังทำ (ยังไม่ release)

- **MuML 1.0:** โมเดลเขียนโน้ตที่ train เอง จะมาแทน Markov v1 ใน MuML 1.0 WA ยังไม่อยู่ใน repo
- **TTH-MTL:** เสียงไทยของ TTH ที่มากขึ้นและดีขึ้น ยังไม่อยู่ใน repo
- **Temmo 1.0:** AI สร้างเกม indie ขนาดเล็ก มี prototype อยู่ใน repo และในแท็บ Temmo ของหน้า demo พร้อมเกมตัวอย่าง 1 เกมที่สร้างด้วย Gemma 4 E2B ในเครื่อง

## License

แต่ละส่วนใช้ license ต่างกัน ข้อความเต็มอยู่ใน [LICENSE](LICENSE), [DATA_LICENSE](DATA_LICENSE) และ [NOTICE](NOTICE) ถ้าสรุปตรงนี้ไม่ตรงกับไฟล์เหล่านั้น ให้ยึดไฟล์เป็นหลัก ตารางเต็มอยู่ใน [README ภาษาอังกฤษ](README.md#license)

- **Code ทั้งหมด:** MIT ใช้เชิงพาณิชย์ได้
- **โมเดล intent และข้อมูลของโปรเจกต์:** MIT ใช้เชิงพาณิชย์ได้
- **ชุดความรู้จาก Wikipedia ภาษาไทย:** CC BY-SA 4.0 ใช้เชิงพาณิชย์ได้ แต่ต้องให้เครดิตผู้เขียน Wikipedia และแจกต่อด้วย license เดียวกัน
- **ตารางโน้ตของ MuML 1.0 WA (จาก Nottingham Music Database):** GPL-3.0 ใช้เชิงพาณิชย์ได้ตามเงื่อนไขของ GPL-3.0
- **Weights ของ Wayu-Paxa-TTS-Edge (TTH):** CC-BY-NC-4.0 **ห้ามใช้เชิงพาณิชย์** ต้องให้เครดิต Paxa Labs / Wayu Research ไม่ได้อยู่ใน repo จะโหลดจาก Hugging Face ตอนใช้งานครั้งแรก
- **Weights ของ Gemma 4 (SANKPUP):** Apache License 2.0 ตามหน้า license ของ Google ไม่ได้อยู่ใน repo
- **ACE-Step 1.5 และ Qwen3-Embedding (MUML 1.0 HIQ engine ace):** MIT และ Apache License 2.0 ใช้เชิงพาณิชย์ได้ ไม่ได้อยู่ใน repo โหลดด้วย `--setup`
- **Weights ของ YuE2-3B และ YuE2-Vae (MUML 1.0 HIQ engine yue2 ซึ่งเป็นค่าเริ่มต้นของเนื้อไทย):** CC-BY-NC-4.0 **ห้ามใช้เชิงพาณิชย์** ต้องให้เครดิต m-a-p ไม่ได้อยู่ใน repo โหลดด้วย `--setup` เพลงที่สร้างด้วย yue2 หรือโหมด split (เสียง Wayu) ก็ห้ามใช้เชิงพาณิชย์ด้วย
- **acestep.cpp และ yue2.cpp:** MIT build จาก source ตอน `--setup`
- **edge-tts:** library เป็น LGPL-3.0 แต่ส่งข้อความไปที่บริการอ่านออกเสียงออนไลน์ของ Microsoft เสียงที่ได้ใช้ตามเงื่อนไขของ Microsoft

Copyright (c) 2026 Clanarong Tammaketuek (klanarongz2009)
