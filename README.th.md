# TER-AI (ภาษาไทย)

[English README](README.md)

> **ทดลองใช้แบบจำกัดเวลา: TERM AI ซึ่งเป็น Terminal AI ตัวดั้งเดิม กลับมาให้ลองถึง 2027-01-01 00:00:00 เวลาประเทศไทย (UTC+7)** ลองได้ด้วย `terai term` ([v0.14.0](https://github.com/klanarongz2009-sketch/terai-router/releases/tag/v0.14.0), [ประกาศ](https://github.com/klanarongz2009-sketch/terai-router/issues/6)) พอถึงเวลานั้นจะใช้ไม่ได้และถูกถอดออกจาก repo [รายละเอียด](#term-ai-ทดลองใช้แบบจำกัดเวลา)

TER-AI คือชุด AI ภาษาไทยที่รันออฟไลน์บน CPU ได้ฟรี ไม่ต้องใช้ GPU และไม่ต้องส่งข้อมูลขึ้น cloud ทำร่วมกับ Sesame

> **ประกาศเกี่ยวกับโปรเจกต์:** TER-AI เป็นโปรเจกต์อินดี้ อาจหยุดชั่วคราวหรือปิดได้โดยแจ้งล่วงหน้าเพียงเล็กน้อย อ่าน[ประกาศเกี่ยวกับโปรเจกต์](PROJECT_NOTICE.th.md)

## ส่วนที่ release แล้ว (v0.15.0)

| ส่วน | ทำอะไร | ตั้งแต่ |
|---|---|---|
| Intent router | อ่านข้อความภาษาไทยหรือไทยปนอังกฤษทีละข้อความ แก้คำพิมพ์ผิดที่เจอบ่อย แล้วบอกว่าเป็น intent ไหนใน 15 แบบ พร้อมคะแนนความมั่นใจ ตัวโมเดลขนาด 1.1 MB ไม่ต้องลง library เพิ่ม | v0.7.0 |
| Chat | แชตภาษาไทยแบบออฟไลน์ มี tool จริง (เครื่องคิดเลข วันที่และเวลา แปลงหน่วย) ตอบจากชุดความรู้ Wikipedia ภาษาไทยที่แนบมาพร้อมบอกแหล่ง จำข้อมูลข้ามการเปิดใหม่ได้ และตอบว่า "ไม่รู้" แทนการเดา ข้างในไม่มีโมเดลภาษา (LLM) | v0.8.0 |
| TTH | อ่านภาษาไทยออกเสียงด้วยโมเดลเสียงที่รันในเครื่อง (Wayu-Paxa-TTS-Edge) มี edge-tts เป็นตัวสำรองแบบออนไลน์ ทั้งสองตัวเลือกลงได้ตามต้องการ | v0.10.0 |
| SANKPUP | สร้างภาพด้วยการเขียน code SVG (ใช้ Gemma 4 ในเครื่อง หรือตัวสร้างแบบออฟไลน์ที่ฝังมา) กรอง code ให้ปลอดภัย แล้วแปลงเป็น PNG หรือ JPG ไม่ใช่โมเดลสร้างภาพ | v0.11.0 |
| MuML 1.0 WA | แต่งและเล่นเพลงในเบราว์เซอร์จากคำสั่งภาษาไทยหรืออังกฤษ ตั้งแต่ v0.15.0 โน้ตมาจากโมเดล MuML 1.0 ที่ train เอง (transformer 3.3M parameters, weights int8 ขนาด 3.4 MB รันด้วย JavaScript ในเบราว์เซอร์) ถ้าโหลด weights ไม่ได้จะใช้ Markov v1 แทน เสียงทุกเสียงสร้างด้วย Web Audio API | v0.12.0, โมเดล v0.15.0 |
| MUML 1.0 HIQ | สร้างเพลงเป็นไฟล์เสียงจริง (.mp3/.wav) บน CPU จากคำสั่งภาษาไทยหรืออังกฤษ ใส่เนื้อร้องได้ ใช้ ACE-Step 1.5 กับเพลงบรรเลงและเพลงอังกฤษ และ YuE2-3B กับเนื้อไทย โหลด weights ครั้งเดียวด้วย `terai muml --hiq --setup` ยังช้าบน CPU และเนื้อไทยฟังออกแค่บางส่วน | v0.13.0 |
| TERM AI (ทดลองใช้แบบจำกัดเวลา) | Terminal AI ตัวดั้งเดิมที่ TER-AI เติบโตมาจาก เป็น chatbot ภาษาไทยใน terminal ที่ใช้กฎกับโมเดลตัวแรกของโปรเจกต์ TER-AI-0.5 รันออฟไลน์ ไม่ต้องลง library เพิ่ม **ใช้ได้ถึง 2027-01-01 00:00:00 เวลาประเทศไทย (UTC+7) แล้วจะถอดออกจาก repo** | v0.14.0 |

- หน้า demo: https://klanarongz2009-sketch.github.io/terai-router/
- Repository: https://github.com/klanarongz2009-sketch/terai-router
- Wiki: https://github.com/klanarongz2009-sketch/terai-router/wiki

```
$ terai "เส็ดหรือยัง"
status  1.00  เสร็จหรือยัง
```

## ที่มาของชื่อ

TER มาจากคำว่า "เธอ" ใช้ได้ทั้งสองทาง TER-AI เรียกผู้ใช้ว่าเธอ และผู้ใช้ก็เรียก TER-AI ว่าเธอ

## ผลทดสอบ (v0.15.0 วัดเมื่อ 22 ต.ค. 2026)

เครื่อง AMD EPYC 8 core ไม่มี GPU, Python 3.13.7 ใช้สคริปต์ใน repo นี้

- **Intent router:** test set ที่ freeze ไว้ได้ 97.6% (121/124) ใช้ 0.169 ms ต่อข้อความ ส่วน held-out ได้ 99.1% (111/112)
- **Chat eval:** ชุด frozen 81/81 turns, held-out 37/37 turns, regression 16/16 turns
- **เบราว์เซอร์เทียบกับ Python (parity):** router 607/607, chat 790/790, TTH 1,700/1,700, SANKPUP 688/688, MuML 1.0 WA: Markov v1 330/330 และโมเดล MuML 1.0 30/30, Temmo remix 42/42
- **TERM AI (โมเดล TER-AI-0.5):** leave-one-out บนประโยค train 149 ประโยค ได้ 67.8% (101/149)
- **Unit test:** pytest ผ่าน 353 ข้าม 4
- **MUML 1.0 HIQ (วัดเมื่อ 21 ต.ค. ตอน v0.13.0 ไม่ได้เปลี่ยนตั้งแต่นั้น, เพลงเนื้อไทย 4 บรรทัด, yue2, seed 42, ไม่ใส่ `--duration`):** ใช้เวลา 24:53 นาที peak RSS 2.93 GB เพลงจบเองที่ 50.6 วินาทีแล้ว fade-out 2.5 วินาที CER 0.8598 ได้ยินคำจากเนื้อ 14/30 คำ ครบทั้ง 4 บรรทัด (วัดด้วย ASR ภาษาไทยบนเพลงที่มีดนตรีปน จึงเป็นค่าคร่าวๆ) โหมด split ได้ CER 0.2430 (20/30) แต่เป็นเสียงพูดบนจังหวะ ไม่ใช่การร้อง

รายละเอียดคำสั่งที่ใช้วัดอยู่ใน [README ภาษาอังกฤษ](README.md#results-v0150-measured-2026-10-22) และ [docs/MUML-HIQ.md](docs/MUML-HIQ.md)

## MuML 1.0 WA: โมเดล MuML 1.0 เขียนโน้ตเอง (v0.15.0)

ตั้งแต่ v0.15.0 โมเดล MuML 1.0 ที่ train จาก Nottingham folk tunes (decoder-only transformer 4 layers, d_model 256, context 512, 3,332,352 parameters, train 30 epochs, val loss 1.3780) เป็นตัวเขียนเมโลดี้ คอร์ด และจังหวะเอง ไม่ใช่ Markov ตามสคริปต์อีกต่อไป

- **ในเบราว์เซอร์:** กด Write หรือ Play ในแท็บ MuML แล้วเว็บจะโหลด weights `muml-1.0-int8.bin` (3,421,372 bytes) ครั้งเดียว โค้ด forward pass เขียนเองด้วย JavaScript ไม่ใช้ onnxruntime และไม่ต้องมี server
- **ใน Python:** `pip install numpy` แล้ว `terai muml-wa --setup` (โหลด weights และเช็ก SHA-256) จากนั้น `terai muml-wa "rock E minor 120 bpm 30 วินาที" --seed 1 -o rock.mid`
- **ผลเหมือนกันทั้งสองฝั่ง:** prompt และ seed เดียวกันได้ tokens, โน้ต และไฟล์ `.mid` ตรงกันทุก byte (parity 30/30)
- **ก่อน/หลัง** (`python eval/muml_wa_writers.py`, 10 prompts x 3 seeds):
  - distinct 4-gram: Markov v1 0.757 → โมเดล 0.927 (โน้ตหลากหลายขึ้น)
  - bar ที่ซ้ำ: 22.3% → 1.2%
  - โน้ตที่อยู่ในคีย์: 97.6% → 98.3% (ปิด key guard จะเหลือ 88.2%)
  - จบที่โน้ต tonic: 100% → 26.7%
  - เวลาเขียน 1 เพลง: 0.002 วินาที → 1.7 วินาที (Python, numpy) ส่วนในเบราว์เซอร์ เพลง waltz 30 วินาที (154 tokens) ใช้ 1.8 วินาที
- **ข้อจำกัด:** โมเดลแทบไม่ซ้ำ bar เลย เพลงจึงเดินไปเรื่อยๆ ไม่ได้แบ่งท่อน AABB ชัด, จบที่ tonic แค่ราว 1 ใน 4, เครื่องหมาย repeat ที่โมเดลเขียนไม่ได้ถูกขยาย, Python ต้องมี numpy, และโมเดล train จากเพลง folk สไตล์ Rock จึงเปลี่ยนแค่การเรียบเรียง ไม่ได้เปลี่ยนทำนอง

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

## TERM AI (ทดลองใช้แบบจำกัดเวลา)

> **ทดลองใช้ได้ถึง 2027-01-01 00:00:00 เวลาประเทศไทย (UTC+7)** ตั้งแต่เวลานั้นเป็นต้นไป `terai term` จะไม่ทำงาน และ TERM AI จะถูกถอดออกจาก repo

TERM AI คือโปรแกรมแรกที่ TER-AI เติบโตมา เขียนขึ้นวันที่ 10 ต.ค. 2026 ก่อนจะมี repo นี้ เป็น chatbot ภาษาไทยใน terminal ตอบด้วยกฎ (regex) ก่อน ถ้าไม่มีกฎไหนตรง จะให้โมเดล TER-AI-0.5 (Naive Bayes จาก n-gram ตัวอักษร 11 intent, train จาก 149 ประโยค) เลือก intent และตอบเฉพาะตอนที่มั่นใจ 90% ขึ้นไป ไม่อย่างนั้นจะบอกว่าไม่เข้าใจ ตัวที่ใส่มาเหมือนของเดิมทุกอย่าง ทั้งกฎ คำตอบ และไฟล์โมเดล

```
pip install git+https://github.com/klanarongz2009-sketch/terai-router.git@v0.15.0
terai term                      # โหมดคุยต่อเนื่อง พิมพ์ ออก, exit หรือ quit เพื่อจบ
terai term "คำนวณ (12+8)*3"
terai term --trial-info         # ดูเวลาที่หมดอายุ
```

- **ก่อนหมดเวลา:** ทุกครั้งที่รันจะพิมพ์ 1 บรรทัดบอกวันและเวลาที่หมดอายุ แล้วทำงานตามปกติ
- **ตั้งแต่ 2027-01-01 00:00:00 (UTC+7):** ไม่ว่าจะรันด้วย argument อะไร จะพิมพ์ว่าหมดช่วงทดลองแล้ว ไม่แตะไฟล์ memory และจบด้วย exit code 3 ถ้าเปิดค้างไว้ข้ามเที่ยงคืน ข้อความถัดไปจะไม่ได้คำตอบและจบแบบเดียวกัน
- **ไม่มีในหน้า demo:** เพราะ TERM AI ตอบเป็นภาษาไทยอย่างเดียว ส่วนหน้า demo เป็นภาษาอังกฤษ
- **License:** code และข้อมูลเป็น MIT

รายละเอียดเต็มอยู่ใน [docs/TERM-AI.md](docs/TERM-AI.md)

## กำลังทำ (ยังไม่ release)

- **MuML 1.0 (training code):** สคริปต์ train โมเดล MuML 1.0 ยังไม่อยู่ใน repo ตอนนี้มีแค่สคริปต์ export weights (`training/muml_wa/export_net.py`)
- **TTH-MTL:** เสียงไทยของ TTH ที่มากขึ้นและดีขึ้น ยังไม่อยู่ใน repo
- **Temmo 1.0:** AI สร้างเกม indie ขนาดเล็ก มี prototype อยู่ใน repo และในแท็บ Temmo ของหน้า demo พร้อมเกมตัวอย่าง 1 เกมที่สร้างด้วย Gemma 4 E2B ในเครื่อง

## กำลังจะถอดออก

- **TERM AI:** ทดลองใช้ได้ถึง 2027-01-01 00:00:00 เวลาประเทศไทย (UTC+7) แล้วจะถอดออกจาก repo

## License

แต่ละส่วนใช้ license ต่างกัน ข้อความเต็มอยู่ใน [LICENSE](LICENSE), [DATA_LICENSE](DATA_LICENSE) และ [NOTICE](NOTICE) ถ้าสรุปตรงนี้ไม่ตรงกับไฟล์เหล่านั้น ให้ยึดไฟล์เป็นหลัก ตารางเต็มอยู่ใน [README ภาษาอังกฤษ](README.md#license)

- **Code ทั้งหมด:** MIT ใช้เชิงพาณิชย์ได้
- **โมเดล intent และข้อมูลของโปรเจกต์ (รวมโมเดลและข้อมูลของ TERM AI):** MIT ใช้เชิงพาณิชย์ได้
- **ชุดความรู้จาก Wikipedia ภาษาไทย:** CC BY-SA 4.0 ใช้เชิงพาณิชย์ได้ แต่ต้องให้เครดิตผู้เขียน Wikipedia และแจกต่อด้วย license เดียวกัน
- **ตารางโน้ตและ weights ของโมเดล MuML 1.0 ใน MuML 1.0 WA (จาก Nottingham Music Database, `docs/muml-1.0-int8.bin`):** GPL-3.0 ใช้เชิงพาณิชย์ได้ตามเงื่อนไขของ GPL-3.0
- **Weights ของ Wayu-Paxa-TTS-Edge (TTH):** CC-BY-NC-4.0 **ห้ามใช้เชิงพาณิชย์** ต้องให้เครดิต Paxa Labs / Wayu Research ไม่ได้อยู่ใน repo จะโหลดจาก Hugging Face ตอนใช้งานครั้งแรก
- **Weights ของ Gemma 4 (SANKPUP):** Apache License 2.0 ตามหน้า license ของ Google ไม่ได้อยู่ใน repo
- **ACE-Step 1.5 และ Qwen3-Embedding (MUML 1.0 HIQ engine ace):** MIT และ Apache License 2.0 ใช้เชิงพาณิชย์ได้ ไม่ได้อยู่ใน repo โหลดด้วย `--setup`
- **Weights ของ YuE2-3B และ YuE2-Vae (MUML 1.0 HIQ engine yue2 ซึ่งเป็นค่าเริ่มต้นของเนื้อไทย):** CC-BY-NC-4.0 **ห้ามใช้เชิงพาณิชย์** ต้องให้เครดิต m-a-p ไม่ได้อยู่ใน repo โหลดด้วย `--setup` เพลงที่สร้างด้วย yue2 หรือโหมด split (เสียง Wayu) ก็ห้ามใช้เชิงพาณิชย์ด้วย
- **acestep.cpp และ yue2.cpp:** MIT build จาก source ตอน `--setup`
- **edge-tts:** library เป็น LGPL-3.0 แต่ส่งข้อความไปที่บริการอ่านออกเสียงออนไลน์ของ Microsoft เสียงที่ได้ใช้ตามเงื่อนไขของ Microsoft

Copyright (c) 2026 Clanarong Tammaketuek (klanarongz2009)
