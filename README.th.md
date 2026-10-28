# TER-AI (ภาษาไทย)

[English README](README.md)

> **ทดลองใช้แบบจำกัดเวลา: TERM AI ซึ่งเป็น Terminal AI ตัวดั้งเดิม กลับมาให้ลองถึง 2027-01-01 00:00:00 เวลาประเทศไทย (UTC+7)** ลองได้ด้วย `terai term` ([v0.14.0](https://github.com/klanarongz2009-sketch/terai-router/releases/tag/v0.14.0), [ประกาศ](https://github.com/klanarongz2009-sketch/terai-router/issues/6)) พอถึงเวลานั้นจะใช้ไม่ได้และถูกถอดออกจาก repo [รายละเอียด](#term-ai-ทดลองใช้แบบจำกัดเวลา)

TER-AI เป็นโครงการวิจัยและพัฒนา AI ภาษาไทยแบบอิสระที่ใช้ AI agent ช่วยพัฒนา โดยทดลองตั้งแต่ typo-tolerant intent routing, local chat/vision บน CPU ไปจนถึง Thai TTS, SVG graphics และ music-generation tools โครงการเผยแพร่ test sets, evaluation scripts, parity/regression checks, ข้อจำกัดของแต่ละโมดูล, license แยกตามข้อมูล/โมเดล และ Project Notice เกี่ยวกับความต่อเนื่องของการดูแล

ขอบเขตของ offline: intent router, แชตแบบกฎ, TERM AI และ SANKPUP แบบ offline generator รันบน CPU โดยไม่ต่อเน็ตเลย ส่วน TTH (Wayu-Paxa-TTS-Edge และตั้งแต่ v0.17.0 มี engine เสริม TTH-MTL บน OmniVoice ขนาดราว 3.3 GB), TERAI1 (beta) และ SANKPUP "gemma" (Gemma 4 E2B บน llama-cpp-python), MUML 1.0 HIQ (ACE-Step 1.5, YuE2-3B) และ weights ของ network MuML 1.0 รันบน CPU ในเครื่องหลังโหลด weights ครั้งแรกครั้งเดียว TTH-MTL จะโหลด Whisper large-v3-turbo (ราว 1.6 GB) เพิ่มถ้าใส่ `--ref-audio` โดยไม่ใส่ `--ref-text` หลังโหลดครบแล้วไม่ต้องต่อเน็ต (`HF_HUB_OFFLINE=1` ปิดการเช็กอัปเดตกับ Hugging Face) ช่องทางที่ใช้เน็ตเป็นตัวเลือกทั้งหมด: edge-tts ที่เป็นตัวสำรองของ TTH ส่งข้อความไปที่ Microsoft, `terai chat --web` และสวิตช์ค้นเว็บในหน้า demo ส่งคำถามไปที่ Wikipedia และแท็บ Temmo ในหน้า demo (prototype ยังไม่ release) เรียกผู้ให้บริการโมเดลออนไลน์ด้วย API key ของผู้ใช้เอง (BYOK) ทำร่วมกับ Sesame

> **ประกาศเกี่ยวกับโปรเจกต์:** TER-AI เป็นโปรเจกต์อินดี้ อาจหยุดชั่วคราวหรือปิดได้โดยแจ้งล่วงหน้าเพียงเล็กน้อย อ่าน[ประกาศเกี่ยวกับโปรเจกต์](PROJECT_NOTICE.th.md)

## ส่วนที่ release แล้ว (v0.17.0)

| ส่วน | ทำอะไร | ตั้งแต่ |
|---|---|---|
| Intent router | อ่านข้อความภาษาไทยหรือไทยปนอังกฤษทีละข้อความ แก้คำพิมพ์ผิดที่เจอบ่อย แล้วบอกว่าเป็น intent ไหนใน 15 แบบ พร้อมคะแนนความมั่นใจ ตัวโมเดลขนาด 1.1 MB ไม่ต้องลง library เพิ่ม | v0.7.0 |
| Chat | แชตภาษาไทยที่รันบน CPU ในเครื่อง ไม่ต่อเน็ตถ้าไม่เปิดการค้นเว็บ ตั้งแต่ v0.16.0 คำตอบเขียนโดยโมเดล **TERAI1** (beta, Gemma 4 E2B รันบน CPU ในเครื่อง ก่อน v0.17.0 ชื่อ TERAI1BETA) ส่วนกฎเดิม (เครื่องคิดเลข วันที่และเวลา แปลงหน่วย ความจำ ชุดความรู้ Wikipedia ภาษาไทย) กลายเป็น tool ของโมเดล ทุกข้อเท็จจริงบอกแหล่งที่มา ถ้าไม่มีแหล่งจะตอบว่า "ไม่รู้" อ่านภาพได้ด้วย (`terai chat --image`) ถ้าไม่ได้ลงโมเดล จะกลับไปใช้แชตแบบกฎเดิม ค้นเว็บจาก Wikipedia ได้ถ้าเปิดเอง ตั้งแต่ v0.9.0 | v0.8.0 (โมเดล v0.16.0) |
| TTH | อ่านภาษาไทยออกเสียงด้วยโมเดลเสียงที่รันในเครื่อง (Wayu-Paxa-TTS-Edge) มี edge-tts เป็นตัวสำรองแบบออนไลน์ ตั้งแต่ v0.17.0 มี engine เสริม TTH-MTL (OmniVoice ในเครื่อง weights ห้ามใช้เชิงพาณิชย์) ที่พูดภาษาอื่นได้และโคลนเสียงได้ ยังไม่มีผลวัด ทุกตัวเลือกลงได้ตามต้องการ | v0.10.0 (TTH-MTL v0.17.0) |
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

## เวอร์ชันของ repo กับเวอร์ชันของโมเดล

เวอร์ชันของ repo กับเวอร์ชันของโมเดลแยกกัน MuML 1.0 เป็นโมเดลแรกที่มีชื่อรุ่นของตัวเอง (v0.15.0) และ v0.16.0 เขียนหลักนี้ไว้ให้ใช้กับทุกโมเดล

- **เวอร์ชันของ repo:** เป็น `0.X.Y` รอบนี้คือ v0.17.0 ขยับทุกครั้งที่ release เกณฑ์ที่ repo จะขึ้น 1.0 ยังเหมือนเดิมทุกข้อ
- **ชื่อรุ่นของโมเดล:** แต่ละโมเดลมีชื่อและเวอร์ชันของตัวเอง การ release repo ไม่เปลี่ยนชื่อรุ่นโมเดล และเลข 1.0 ในชื่อโมเดลไม่ใช่ 1.0 ของ repo

| ชื่อรุ่นโมเดล | คืออะไร | ตั้งแต่ |
|---|---|---|
| TERAI1 | โมเดลแชต (beta): Gemma 4 E2B ในเครื่องเขียนคำตอบ ใช้กฎของ TER-AI เป็น tool อ่านภาพได้ ใน v0.16.0 ชื่อ TERAI1BETA เปลี่ยนชื่อใน v0.17.0 ชื่อเดิมยังใช้เป็น alias ได้ | v0.16.0 |
| MuML 1.0 | ตัวเขียนโน้ตของ MuML 1.0 WA (network ที่ train แล้ว `muml-1.0-net` ตั้งแต่ v0.15.0) | v0.12.0 |
| MUML 1.0 HIQ | สร้างเพลงเป็นไฟล์เสียง | v0.13.0 |
| Temmo 1.0 | AI สร้างเกม indie ขนาดเล็ก (prototype ยังไม่ release) | - |
| TER-AI-0.5 | โมเดล intent ใน TERM AI (ทดลองใช้แบบจำกัดเวลา) | v0.14.0 |

`terai --version` แสดงทั้งสองอย่าง เช่น `terai-router 0.17.0 / model TERAI1` ส่วน `terai models` แสดงรายชื่อโมเดลทั้งหมด ชื่อรุ่นโมเดลต้องสะกดเหมือนเดิม ข้อยกเว้นเดียวคือ v0.17.0 เปลี่ยน TERAI1BETA เป็น TERAI1 ("beta" เป็นสถานะ ไม่ใช่ส่วนหนึ่งของชื่อ) `--brain terai1beta` และ `--engine terai1beta` ยังใช้ได้ และจะแสดงข้อความแจ้งว่าเลิกใช้แล้ว (deprecated)

## TERAI1 (beta)

ก่อน v0.16.0 คำตอบในแชตมาจาก template ตายตัว เลยฟังเหมือนตอบตามสคริปต์ TERAI1 (ก่อน v0.17.0 ชื่อ TERAI1BETA) ยังใช้กฎเดิม แต่ให้กฎเป็นคนหาข้อมูลด้วย tool แล้วให้ Gemma 4 E2B เขียนคำตอบเป็นภาษาไทยที่เป็นธรรมชาติ ก่อนส่งคำตอบจะเช็กว่าตัวเลขทุกตัวมาจากผลของ tool ข้อความของผู้ใช้ หรือความจำ ถ้าไม่ผ่านจะให้โมเดลเขียนใหม่ 1 รอบ ถ้ายังไม่ผ่านจะใช้คำตอบจากกฎแทน

```
pip install "terai-router[llm] @ git+https://github.com/klanarongz2009-sketch/terai-router.git@v0.17.0"
terai chat --setup                       # ครั้งแรก โหลดราว 4.3 GB
terai chat                               # ใช้ TERAI1 ถ้าลงไว้แล้ว ไม่อย่างนั้นใช้แชตแบบกฎ
terai chat --brain terai1                # ใช้ TERAI1 เสมอ (--brain terai1beta คือชื่อเดิม ยังใช้ได้)
terai chat --image menu.png              # ถามเรื่องภาพก่อน แล้วคุยต่อ
terai vision sign.jpg                    # บรรยายภาพและอ่านข้อความไทย/อังกฤษในภาพ
terai chat --brain rules                 # ใช้แชตแบบกฎอย่างเดียว
```

| | แชตแบบกฎ (ก่อน) | TERAI1 |
|---|---|---|
| ข้อที่มีคำตอบที่คาดไว้ ตอบถูก (30 ข้อจากชุดตายตัว 52 ข้อ) | 22/30 | 30/30 |
| Hallucination (52 ข้อ) | 1/52 | 1/52 |
| ตอบว่าไม่รู้เมื่อไม่มีแหล่ง | 9/10 | 9/10 |
| คุยเล่น: คำตอบไม่ซ้ำกันในกลุ่มข้อความคล้ายกัน | 6/12 | 12/12 |
| เวลาต่อคำตอบ p50 / p95 | ไม่ถึง 1 ms | 15.9 วินาที / 46.2 วินาที |
| RAM สูงสุด | 84 MB | 4.7 GB |

วัดบนชุดตายตัว `eval/terai1beta_cases_v15.json` (ชุดทดสอบของ TERAI1 ชื่อไฟล์ยังเป็นชื่อโมเดลตอน v0.16.0) (52 ข้อ) เครื่อง AMD EPYC 8 core ไม่มี GPU, Gemma 4 E2B Q4_0 บน llama-cpp-python, 4 threads ตอนวัดมีงานอื่นใช้ CPU อยู่ด้วย (load average ราว 15 บนเครื่อง 8 core) เวลาที่วัดได้จึงช้ากว่าปกติ รอบทดสอบแรกของ build ก่อนหน้าวัดได้ p50 2.4 วินาที p95 9.6 วินาที

การอ่านภาพ วัดด้วย `eval/vision_eval.py` บนภาพทดสอบ 12 ภาพ (14 ข้อ) ใช้ Gemma 4 E2B + vision projector, 4 threads บนเครื่องเดียวกันที่มีงานอื่นรันอยู่: อ่านข้อความได้ตรงทุกตัว 4 จาก 8 ภาพ ค่า CER เฉลี่ย 0.150 (ภาษาไทย 0.165) ตอบคำถามเกี่ยวกับภาพถูก 5/6 ข้อ ใช้เวลา 35.8 วินาทีต่อภาพ (p50, สูงสุด 58.0 วินาที) RAM สูงสุด 4.9 GB ภาพที่ยังอ่านพลาดมากคือตัวหนังสือไทยขนาดเล็ก ตัวหนังสือบนพื้นมืด และกราฟแท่ง

ข้อจำกัด: TERAI1 กับการอ่านภาพใช้ได้เฉพาะใน CLI หน้า demo บนเว็บยังเป็นแชตแบบกฎ ต้องมี RAM ว่างราว 5 GB และตอบช้ากว่าแชตแบบกฎมาก

**ตัวตนของโมเดล (v0.17.0):** ชื่อโมเดลคือ TERAI1 ส่วน "beta" เป็นสถานะ (ยังอยู่ระหว่างปรับปรุง) ชื่อเดิม TERAI1BETA ถูกเอาออกจาก code, CLI และเอกสารใน v0.17.0 เหลือไว้แค่เป็น alias โมเดลเรียกตัวเองว่า "TERAI1" และคำว่า "TERAI1BETA" ในคำตอบจะถูกแทนเป็น "TERAI1" ถ้าถูกถามว่าเป็นใคร ใครสร้าง หรือใช้โมเดลอะไร จะตอบจากข้อเท็จจริงที่กำหนดไว้: TERAI1 ของโปรเจกต์ TER-AI รันในเครื่องบน Gemma 4 E2B ซึ่งเป็น open model ที่ใช้เป็นฐาน และ TER-AI ไม่ได้ฝึกโมเดลนี้เอง ถ้าถูกถามเรื่องสถานะ จะตอบว่า TERAI1 ยังอยู่ระหว่างปรับปรุง คำตอบที่บอกว่าพัฒนาหรือสร้างโดย Google บอกว่าตัวเองคือ Gemma หรือบอกว่า TER-AI ฝึกโมเดลเอง ("พัฒนาโดย Google", "developed by Google", "I am Gemma" ฯลฯ) จะให้โมเดลเขียนใหม่ 1 รอบ ถ้ายังผิดจะใช้คำตอบที่กำหนดไว้แทน ใช้กับคำตอบเรื่องภาพด้วย ทดสอบด้วย output จำลองใน `tests/test_brain_identity.py` ผล eval ของ TERAI1 ตอน v0.16.0 ข้างบนไม่ได้รันซ้ำกับโมเดลจริงใน v0.17.0 (ใน 52 ข้อไม่มีคำถามเรื่องตัวตน) แชตแบบกฎก็แก้คำตอบของ "ใครพัฒนาคุณ" แล้ว: เดิมตอบว่า TER-AI เทรนโมเดลเองทั้งหมด ตอนนี้ตอบว่าแชตแบบกฎกับ intent router เขียนและฝึกในโปรเจกต์นี้ ส่วนแชตโมเดล TERAI1 รันบน Gemma 4 ซึ่ง TER-AI ไม่ได้ฝึกเอง (`tests/test_terai1_rename.py`)

## ที่มาของชื่อ

TER มาจากคำว่า "เธอ" ใช้ได้ทั้งสองทาง TER-AI เรียกผู้ใช้ว่าเธอ และผู้ใช้ก็เรียก TER-AI ว่าเธอ

## ผลทดสอบ (v0.16.0 วัดเมื่อ 22 ต.ค. 2026)

เครื่อง AMD EPYC 8 core ไม่มี GPU, Python 3.13.7 ใช้สคริปต์ใน repo นี้

- **Intent router:** test set ที่ freeze ไว้ของ TER-AI v0.7 (124 ประโยค) ได้ 97.6% (121/124) ใช้ 0.169 ms ต่อข้อความ (1 thread) ส่วน held-out set ของ v0.7 (112 ประโยค) ได้ 99.1% (111/112) ใช้ 0.26 ms ต่อข้อความ (1 thread)
- **Chat eval:** ชุด frozen 81/81 turns, held-out 37/37 turns, regression 16/16 turns
- **TERM AI (โมเดล TER-AI-0.5):** leave-one-out บนประโยค train 149 ประโยค ได้ 67.8% (101/149)
- **Unit test (v0.17.0 รันเมื่อ 28 ต.ค. 2026):** pytest ผ่าน 449 ข้าม 7 (ที่ข้ามคือเทสต์เสียงจริงและโมเดลจริงที่ต้องเปิดเอง) แถวอื่นในหัวข้อนี้วัดบน code ของ v0.16.0 ส่วน v0.17.0 แก้แค่ identity guard ของ TERAI1 กับคำตอบ "ใครพัฒนาคุณ" ของแชตแบบกฎ chat eval 81/81 และ browser parity 790/790 ยังผ่านเหมือนเดิม (รันซ้ำ 28 ต.ค. 2026)
- **โมเดล TERAI1 เทียบกับแชตแบบกฎเดิม:** 30/30 ข้อที่มีคำตอบที่คาดไว้ในชุดตายตัว 52 ข้อ (แชตแบบกฎ 22/30), hallucination 1/52 เท่ากัน, ตอบว่าไม่รู้เมื่อไม่มีแหล่ง 9/10 เท่ากัน รายละเอียดอยู่ในหัวข้อ TERAI1 (beta) ด้านบน
- **MUML 1.0 HIQ (วัดเมื่อ 21 ต.ค. ตอน v0.13.0 ไม่ได้เปลี่ยนตั้งแต่นั้น, เพลงเนื้อไทย 4 บรรทัด, yue2, seed 42, ไม่ใส่ `--duration`):** ใช้เวลา 24:53 นาที peak RSS 2.93 GB เพลงจบเองที่ 50.6 วินาทีแล้ว fade-out 2.5 วินาที CER 0.8598 ได้ยินคำจากเนื้อ 14/30 คำ ครบทั้ง 4 บรรทัด (วัดด้วย ASR ภาษาไทยบนเพลงที่มีดนตรีปน จึงเป็นค่าคร่าวๆ) โหมด split ได้ CER 0.2430 (20/30) แต่เป็นเสียงพูดบนจังหวะ ไม่ใช่การร้อง

ความตรงกันระหว่างเบราว์เซอร์กับ Python (parity, v0.16.0 รอบเดียวกัน, `python eval/parity.py`) เป็นการเช็กว่าเวอร์ชัน JavaScript ในเบราว์เซอร์กับเวอร์ชัน Python ให้ผลเหมือนกันเมื่อได้ input เดียวกัน เป็นความสอดคล้องระหว่างสอง implementation ไม่ใช่คุณภาพของคำตอบหรือความแม่นของโมเดล:

- **Intent router:** 607/607 ประโยคได้ intent และข้อความเหมือนกัน ค่า confidence ต่างกันสูงสุด 6.66e-16
- **Chat:** 790/790 turns เหมือนกัน และ 24/24 เมื่อ mock การค้นเว็บ
- **TTH text frontend:** 1,700/1,700 checks
- **SANKPUP offline generator:** 688/688 checks (SVG เหมือนกันทุก byte)
- **MuML 1.0 WA:** Markov v1 330/330 และ network MuML 1.0 30/30 เพลง (tokens, โน้ต และไฟล์ `.mid` เหมือนกันทุก byte)
- **Temmo remix rules (Temmo เป็น prototype ยังไม่ release):** 42/42 cases

รายละเอียดคำสั่งที่ใช้วัดอยู่ใน [README ภาษาอังกฤษ](README.md#results-v0160-measured-2026-10-22) และ [docs/MUML-HIQ.md](docs/MUML-HIQ.md)

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

## TTH-MTL: หลายภาษาและโคลนเสียง (v0.17.0)

TTH-MTL ("TTH หลายภาษา") เป็น engine เสริมของ TTH ที่ต้องเลือกใช้เอง สร้างบน OmniVoice ของ k2-fsa ซึ่งเป็นโมเดล text-to-speech แบบ zero-shot ที่เปิด weights และผู้พัฒนาบอกว่ารองรับมากกว่า 600 ภาษา รันบน CPU ในเครื่อง และ `--engine auto` จะไม่เลือก engine นี้เอง

```bash
# Python 3.10+ ต้องลง torch ด้วย weights ของ OmniVoice (ราว 3.3 GB) โหลดตอนใช้ครั้งแรก
pip install "terai-router[tth,tth-mtl] @ git+https://github.com/klanarongz2009-sketch/terai-router.git@v0.17.0"

terai tth --engine mtl "สวัสดีครับ ยินดีต้อนรับสู่ TER-AI" -o th.wav          # ภาษาไทย โคลนจากเสียง Wayu
terai tth --engine mtl --lang en "Hello from TER-AI" -o en.wav                 # ภาษาอื่น
terai tth --engine mtl --ref-audio me.wav --ref-text "สวัสดีครับ ผมกำลังทดสอบเสียง" "สวัสดีครับ" -o me_th.wav
terai tth --engine mtl --mtl-steps 32 "สวัสดีครับ" -o th32.wav                 # เพิ่ม diffusion steps (ค่าเริ่มต้น 16)
```

- **เสียง:** ภาษาไทยใช้เสียง Wayu ตาม `--voice` อ่านคลิปอ้างอิงภาษาไทยสั้นๆ ครั้งเดียว (เก็บ cache ไว้ที่ `~/.cache/terai/tth-mtl`) แล้วให้ OmniVoice โคลนเสียงนั้น ภาษาอื่น หรือภาษาไทยที่ไม่ได้ลง Wayu จะได้เสียงที่ออกแบบตามเพศของเสียงที่เลือก ถ้าใส่ `--ref-audio` คู่กับ `--ref-text` จะโคลนจากคลิปของผู้ใช้แทน
- **ข้อความ:** ภาษาไทยผ่าน text frontend ของ TTH ภาษาอื่นอ่านตามที่เขียน
- **การโหลดและการใช้เน็ต:** ใช้ครั้งแรกจะโหลด `k2-fsa/OmniVoice` จาก Hugging Face (ราว 3.3 GB: โมเดล 2.45 GB และ audio tokenizer 0.81 GB) ไม่มีไฟล์เหล่านี้อยู่ใน repo ถ้าใส่ `--ref-audio` โดยไม่ใส่ `--ref-text` จะโหลด Whisper large-v3-turbo (`openai/whisper-large-v3-turbo`, MIT, ราว 1.6 GB) เพิ่มเพื่อถอดข้อความจากคลิป หลังโหลดครบแล้วรันได้โดยไม่ต่อเน็ต ถ้ามีเน็ต huggingface_hub จะถาม Hugging Face ว่า weights มีอัปเดตไหม (ส่งแค่ชื่อโมเดล ไม่ส่งข้อความหรือเสียงของผู้ใช้) ตั้ง `HF_HUB_OFFLINE=1` เพื่อปิด
- **License:** code ของ omnivoice เป็น Apache-2.0 ส่วน weights ของ OmniVoice เป็น CC-BY-NC (ห้ามใช้เชิงพาณิชย์ ต้องให้เครดิต เพราะข้อมูลที่ใช้ train เช่น Emilia) audio tokenizer ใน repository เดียวกัน (Higgs Audio 2 ของ Boson AI) ใช้ Boson Higgs Audio 2 Community License ซึ่งอิงจาก Meta Llama 3 Community License และห้ามนำ output ไปปรับปรุง large language model ตัวอื่น เสียงที่สร้างด้วย TTH-MTL ใช้ได้แบบไม่เชิงพาณิชย์เท่านั้น ข้อความ attribution ที่ license บังคับ: "Built with Higgs Materials licensed from Boson AI USA, Inc., Copyright Boson AI USA, Inc., All Rights Reserved and Meta Llama 3 licensed under the Meta Llama 3 Community License, Copyright Meta Platforms, Inc., All Right Reserved." รายละเอียดอยู่ใน [NOTICE](NOTICE) ข้อ 15
- **ยังไม่มีผลวัด:** repo นี้ยังไม่มีผลวัดคุณภาพเสียง (CER) ความเร็ว หรือ memory ของ TTH-MTL ใน v0.17.0 `tests/test_tth_mtl.py` เช็กการต่อสายของ engine ด้วยโมเดลจำลอง ส่วนเทสต์กับโมเดลจริงใน `tests/test_tth_real.py` รันเฉพาะเมื่อตั้ง `TERAI_TTH_REAL=1 TERAI_TTH_MTL_REAL=1`
- **การโคลนเสียง:** โคลนได้เฉพาะเสียงของตัวเอง หรือเสียงที่เจ้าของยินยอม เสียงที่ได้เป็นเสียงที่เครื่องสร้าง ห้ามอ้างว่าเป็นเสียงของคนจริง

## กำลังทำ (ยังไม่ release)

- **MuML 1.0 (training code):** สคริปต์ train โมเดล MuML 1.0 ยังไม่อยู่ใน repo ตอนนี้มีแค่สคริปต์ export weights (`training/muml_wa/export_net.py`)
- **ผลวัดของ TTH-MTL:** TTH-MTL release แล้วใน v0.17.0 (ดูหัวข้อ [TTH-MTL](#tth-mtl-หลายภาษาและโคลนเสียง-v0170)) แต่ใน repo ยังไม่มีผลวัดคุณภาพเสียง ความเร็ว หรือ memory
- **Temmo 1.0:** AI สร้างเกม indie ขนาดเล็ก มี prototype (ยังไม่ release) อยู่ใน repo และในแท็บ Temmo ของหน้า demo พร้อมเกมตัวอย่าง 1 เกมที่สร้างด้วย Gemma 4 E2B ในเครื่อง
- **Tagentic (รุ่นแรก Tagentic1, beta):** โมเดล thinking + agentic ของ TER-AI รันในเครื่องบน Gemma 4 E2B (open model ที่ใช้เป็นฐาน TER-AI ไม่ได้ฝึกเอง) คิดเป็นข้อความสั้นทีละบรรทัดพร้อม tool ที่ใช้และผลที่ได้ อ่าน ค้นหา เขียน และแก้ไฟล์ในโฟลเดอร์ workspace ได้ และรัน Python หรือ shell เพื่อเช็กโค้ด การเขียน การแก้ การรันโค้ด และการบันทึก memory จะถามก่อนทุกครั้ง (`--yes` อนุญาตทั้งหมด) โหลด memory 4 ไฟล์ตามลำดับ: `User.md`, `Systemprompt.md`, `Memory.md`, `Systemskill.md` (มีสกิล [ai-memory-continuity](https://github.com/klanarongz2009-sketch/ai-memory-continuity) สัญญาอนุญาต MIT) โดย `User.md` กับ `Memory.md` อยู่ในเครื่องของคุณ (`~/.terai/tagentic`) ไม่อยู่ใน repository นี้ `terai tagentic` เปิด session ที่โมเดลทักก่อน แล้วคุยหรือสั่งงานต่อได้ ส่วน `terai tagentic "งาน"` รันงานเดียว โหมด relay รันทีละ turn ต่อหนึ่งคำสั่ง สำหรับแอปแชตที่ส่งข้อความต่อให้: `terai tagentic --session NAME --start --json`, `--message "TEXT"`, `--approve` / `--deny` (การเขียนหรือการรันที่รอผู้ใช้อนุญาต), `--reset` โดยเก็บ session ไว้ที่ `<memory folder>/sessions/NAME.json` และแต่ละคำสั่งพิมพ์ JSON หนึ่ง object (`trace`, `answer`, `pending_action`, `timing_s`) ถ้าแอป relay เรียกทีละ turn ให้ใช้ `python -m terai_router.tagentic.server call -- <argument ชุดเดิม>` คำสั่งจะรันบน server ถาวรในเครื่อง (unix socket ใน `<memory folder>/run/` ไม่เปิด port เครือข่าย) ที่โหลดโมเดลค้างไว้ ใช้ KV cache ของ prompt ส่วนต้นที่ทุก turn ใช้ร่วมกันซ้ำ และปิดตัวเองเมื่อไม่มีคำสั่ง 30 นาที (`TERAI_TAGENTIC_IDLE`) output และ exit code เหมือน `terai tagentic` ทุกอย่าง วัดบน VM 8 vCPU ไม่มี GPU (2026-10-28): turn แรกโหลดโมเดลจาก disk ราว 66 วินาที บวกอีก 45 วินาที turn ถัดไป 7-24 วินาที และราว 50 วินาทีสำหรับ turn เดียวหลัง `User.md` หรือ `Memory.md` เปลี่ยน (ต้องอ่าน prompt ใหม่ทั้งหมด) ทุกคำตอบเป็นข้อความที่โมเดลเขียนเอง ไม่มีข้อความตายตัวและไม่มี filter กับคำตอบ ตัวตน (Tagentic จาก TER-AI / Klanarongz2009 บน GitHub ไม่ได้พัฒนาโดย Google) กำหนดด้วย system prompt อย่างเดียว ดังนั้นโมเดลฐาน Gemma 4 อาจตอบว่าตัวเองพัฒนาโดย Google ได้ในบางครั้ง ยังเป็น prototype ไม่ release

## กำลังจะถอดออก

- **TERM AI:** ทดลองใช้ได้ถึง 2027-01-01 00:00:00 เวลาประเทศไทย (UTC+7) แล้วจะถอดออกจาก repo

## License

แต่ละส่วนใช้ license ต่างกัน ข้อความเต็มอยู่ใน [LICENSE](LICENSE), [DATA_LICENSE](DATA_LICENSE) และ [NOTICE](NOTICE) ถ้าสรุปตรงนี้ไม่ตรงกับไฟล์เหล่านั้น ให้ยึดไฟล์เป็นหลัก ตารางเต็มอยู่ใน [README ภาษาอังกฤษ](README.md#license)

- **Code:** MIT ใช้เชิงพาณิชย์ได้ ยกเว้นไฟล์ใหม่ที่ใช้ TER-AI License 1.0 ตามข้อถัดไป
- **Code ใหม่ที่ใช้ TER-AI License 1.0 ([LICENSE-TER-AI.md](LICENSE-TER-AI.md)):** ใช้กับไฟล์ใหม่ที่มีบรรทัด `SPDX-License-Identifier: LicenseRef-TER-AI-1.0` บนหัวไฟล์เท่านั้น ไฟล์ที่ release ถึง v0.17.0 ยังเป็น MIT ใช้เชิงพาณิชย์ได้ เทรน AI ได้ ต้องให้เครดิต "TER-AI (klanarongz2009-sketch)" ไฟล์ที่ถูกแก้ต้องใช้ license เดิมและเปิด source license นี้ไม่เปลี่ยน license ของข้อมูล GPL-3.0, ชุดความรู้ CC BY-SA 4.0 และ weights ของโมเดลที่ห้ามใช้เชิงพาณิชย์
- **โมเดล intent และข้อมูลของโปรเจกต์ (รวมโมเดลและข้อมูลของ TERM AI):** MIT ใช้เชิงพาณิชย์ได้
- **ชุดความรู้จาก Wikipedia ภาษาไทย:** CC BY-SA 4.0 ใช้เชิงพาณิชย์ได้ แต่ต้องให้เครดิตผู้เขียน Wikipedia และแจกต่อด้วย license เดียวกัน
- **ตารางโน้ตและ weights ของโมเดล MuML 1.0 ใน MuML 1.0 WA (จาก Nottingham Music Database, `docs/muml-1.0-int8.bin`):** GPL-3.0 ใช้เชิงพาณิชย์ได้ตามเงื่อนไขของ GPL-3.0
- **Weights ของ Wayu-Paxa-TTS-Edge (TTH):** CC-BY-NC-4.0 **ห้ามใช้เชิงพาณิชย์** ต้องให้เครดิต Paxa Labs / Wayu Research ไม่ได้อยู่ใน repo จะโหลดจาก Hugging Face ตอนใช้งานครั้งแรก
- **Weights ของ Gemma 4 และ vision projector (SANKPUP และโมเดล TERAI1):** Apache License 2.0 ตามหน้า license ของ Google ไม่ได้อยู่ใน repo
- **ACE-Step 1.5 และ Qwen3-Embedding (MUML 1.0 HIQ engine ace):** MIT และ Apache License 2.0 ใช้เชิงพาณิชย์ได้ ไม่ได้อยู่ใน repo โหลดด้วย `--setup`
- **Weights ของ YuE2-3B และ YuE2-Vae (MUML 1.0 HIQ engine yue2 ซึ่งเป็นค่าเริ่มต้นของเนื้อไทย):** CC-BY-NC-4.0 **ห้ามใช้เชิงพาณิชย์** ต้องให้เครดิต m-a-p ไม่ได้อยู่ใน repo โหลดด้วย `--setup` เพลงที่สร้างด้วย yue2 หรือโหมด split (เสียง Wayu) ก็ห้ามใช้เชิงพาณิชย์ด้วย
- **Weights ของ OmniVoice (TTH-MTL, engine "mtl" ของ k2-fsa):** CC-BY-NC **ห้ามใช้เชิงพาณิชย์** ไม่ได้อยู่ใน repo โหลดจาก Hugging Face (`k2-fsa/OmniVoice`) ตอนใช้ครั้งแรก ([NOTICE](NOTICE) ข้อ 15)
- **Audio tokenizer Higgs Audio 2 (อยู่ใน `k2-fsa/OmniVoice` ของ Boson AI):** Boson Higgs Audio 2 Community License ซึ่งอิงจาก Meta Llama 3 Community License ต้องใส่ attribution ใช้ได้ภายใต้เงื่อนไขของ license นี้เท่านั้น เสียงที่สร้างด้วย TTH-MTL ยังห้ามใช้เชิงพาณิชย์เพราะ weights ([NOTICE](NOTICE) ข้อ 15)
- **Code ของ omnivoice:** Apache-2.0 ลงมากับ extra `tth-mtl` ใช้เชิงพาณิชย์ได้
- **Whisper large-v3-turbo (เฉพาะตอนใช้ `--ref-audio` โดยไม่ใส่ `--ref-text`):** MIT omnivoice โหลดให้ตอนใช้ครั้งแรก ใช้เชิงพาณิชย์ได้
- **acestep.cpp และ yue2.cpp:** MIT build จาก source ตอน `--setup`
- **edge-tts:** library เป็น LGPL-3.0 แต่ส่งข้อความไปที่บริการอ่านออกเสียงออนไลน์ของ Microsoft เสียงที่ได้ใช้ตามเงื่อนไขของ Microsoft

Copyright (c) 2026 Klanarong Tammakatuek (klanarongz2009-sketch)
