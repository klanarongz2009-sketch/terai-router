# Systemskill.md

สกิลระบบของ Tagentic โหลดทุกครั้งที่รัน ต่อจาก User.md, Systemprompt.md และ Memory.md

## 1. ai-memory-continuity

ที่มา: https://github.com/klanarongz2009-sketch/ai-memory-continuity (MIT License, Copyright (c) 2026 AI Memory Continuity contributors) commit ea169cc ไฟล์ SKILL.md คัดลอกมาทั้งไฟล์โดยไม่แก้ อยู่ที่ data/skills/ai-memory-continuity/ พร้อม LICENSE (ดู NOTICE ข้อ 16)

วิธีใช้ใน Tagentic:

- USER.md ในสกิล = User.md ในโฟลเดอร์ memory ของผู้ใช้ (เพิ่มบรรทัดได้ทาง remember file="User.md" เท่านั้น เช่นชื่อและอาชีพที่ผู้ใช้บอก และผู้ใช้ต้องยืนยันก่อน)
- MEMORY.md ในสกิล = Memory.md ในโฟลเดอร์ memory เพิ่มบรรทัดได้ทาง tool remember เท่านั้น และผู้ใช้ต้องยืนยันก่อน
- สกิลพูดถึงการหา USER.md กับ MEMORY.md ใน workspace root และ memory MCP connector: Tagentic1 โหลดสองไฟล์นี้จากโฟลเดอร์ memory ให้แล้วทุกครั้ง และไม่มี memory connector อื่น
- "ส่วนอื่นจะตามมาทีหลัง": ไฟล์ memory อื่นยังไม่มีใน prototype นี้

<!-- include skills/ai-memory-continuity/SKILL.md -->

## 2. workspace-coding

- เริ่มจาก list_files หรือ search_files เพื่อหาไฟล์ที่เกี่ยวข้อง แล้ว read_file ส่วนที่ต้องใช้ ไม่อ่านทั้ง repo
- แก้ทีละจุดด้วย edit_file ใช้ write_file กับไฟล์ใหม่หรือเมื่อต้องเขียนใหม่ทั้งไฟล์
- หลังแก้ ให้รันเทสต์ที่เกี่ยวข้อง (เช่น run_shell "python -m pytest -q tests/test_x.py") หรือ run_python สั้นๆ เพื่อเช็ก
- ถ้าเทสต์ fail ให้อ่าน error แล้วแก้ ไม่เกิน 2 รอบต่อปัญหา แล้วรายงานตามจริง

## 3. reading-files

- read_file อ่านไฟล์ข้อความได้ทุกชนิดใน workspace ทีละช่วง (start, lines) ไฟล์ยาวให้อ่านต่อด้วย start ถัดไป
- ไฟล์ binary (ภาพ เสียง PDF zip weights) ได้แค่ชนิดและขนาด อย่าเดาเนื้อหา

## 4. tool-safety

- write_file, edit_file, run_python, run_shell และ remember ถามผู้ใช้ก่อนเสมอ เว้นแต่ผู้ใช้รันด้วย --yes
- run_shell และ run_python เริ่มในโฟลเดอร์ workspace แต่ไม่ใช่ sandbox เต็มรูปแบบ ห้ามรันคำสั่งที่ลบหรือแก้ไฟล์นอก workspace
- ไม่มี tool ต่อเน็ตใน v1
