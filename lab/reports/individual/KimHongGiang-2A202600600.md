# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Kim Hong Giang  
**Vai trò:** All roles (Ingestion + Cleaning + Embed + Monitoring)  
**Ngày nộp:** 2026-06-10  
**Độ dài:** ~600 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- `transform/cleaning_rules.py` — phân tích raw data, xác định failure mode, verify cleaning rules
- `quality/expectations.py` — verify expectations hoạt động đúng
- `etl_pipeline.py` — chạy pipeline, debug lỗi, verify embed
- `grading_run.py` + `eval_retrieval.py` — verify kết quả retrieval

**Kết nối với thành viên khác:**
Làm individual nên tự phụ trách toàn bộ pipeline. Trọng tâm: phân tích raw CSV (247 rows, 14 doc_id unique), xác định tại sao pipeline baseline halt, và fix để đạt 10/10 grading.

**Bằng chứng:**
- Run ID `2026-06-10T07-00Z` trong `artifacts/logs/`
- `artifacts/eval/grading_run.jsonl` — 10/10 pass
- Commit fix: re-run `etl_pipeline.py run` để rebuild ChromaDB

---

## 2. Một quyết định kỹ thuật

**Quyết định: Tại sao dùng `--skip-validate` cho inject-bad run?**

Khi demo Sprint 3 (inject corruption), cần embed dữ liệu "xấu" vào ChromaDB để so sánh before/after. Nếu không có `--skip-validate`, expectation `refund_no_stale_14d_window` (severity: halt) sẽ chặn pipeline → không embed được stale data → không có baseline "xấu" để so sánh.

Tuy nhiên, quyết định này tạo ra rủi ro: nếu ai đó quên chạy lại pipeline chuẩn sau demo, ChromaDB sẽ chứa stale data. Đây chính là bug thực tế tôi phát hiện — grading `gq_d10_01` có `hits_forbidden: true` vì ChromaDB vẫn chứa "14 ngày làm việc" từ inject-bad run.

**Bài học:** `--skip-validate` nên đi kèm warning rõ ràng và bắt buộc rerun pipeline chuẩn sau khi demo. Có thể thêm flag `--force-rebuild` để xóa ChromaDB trước khi embed inject data.

---

## 3. Một lỗi hoặc anomaly đã xử lý

**Triệu chứng:** Grading câu `gq_d10_01` có `hits_forbidden: true` — top-k retrieval chứa "14 ngày làm việc" (keyword cấm).

**Phát hiện:** Chạy `python grading_run.py` → đọc JSONL output → thấy `hits_forbidden: true` cho câu hỏi refund window.

**Diagnosis:**
1. Query ChromaDB trực tiếp → top-1 doc là `Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn.`
2. Kiểm tra cleaned CSV → tất cả file `cleaned_*.csv` đều KHÔNG chứa "14 ngày" (ngoại trừ `cleaned_inject-bad.csv`)
3. Kiểm tra `run_id` trong ChromaDB metadata → tất cả docs có `run_id: "inject-bad"`

**Root cause:** ChromaDB được build từ inject-bad run (`--no-refund-fix --skip-validate`). Cleaning rule fix "14 ngày → 7 ngày" bị bỏ qua. Pipeline không prune doc cũ vì inject-bad run có cùng chunk_id structure.

**Fix:** Chạy lại `python etl_pipeline.py run` (không flag) → prune 1 doc stale (`embed_prune_removed=1`) → upsert 36 docs sạch → grading 10/10.

---

## 4. Bằng chứng trước / sau

**Run ID:** `inject-bad` (trước) vs `2026-06-10T07-00Z` (sau)

**Trước (inject-bad):**
```
gq_d10_01: contains_expected=true, hits_forbidden=true, top1_doc_matches=true
→ FAIL: top-k chứa "14 ngày làm việc"
```

**Sau (clean run):**
```
gq_d10_01: contains_expected=true, hits_forbidden=false, top1_doc_matches=true
→ PASS: top-1 là "7 ngày làm việc"
```

**Log snippet (clean run):**
```
expectation[refund_no_stale_14d_window] OK (halt) :: violations=0
embed_prune_removed=1
embed_upsert count=36 collection=day10_kb
```

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ thêm **LLM judge** vào eval pipeline: dùng Claude/GPT để đánh giá câu trả lời semantic thay vì chỉ keyword matching. Ví dụ: câu trả lời "một tuần rưỡi" cho refund window cũng đúng (7 ngày) nhưng keyword check sẽ miss. LLM judge sẽ bắt được edge case này.
