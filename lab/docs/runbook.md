# Runbook — Lab Day 10 (incident tối giản)

---

## Symptom

Agent RAG (Day 09) trả lời sai về chính sách hoàn tiền: nói "14 ngày làm việc" thay vì "7 ngày làm việc". User nhận thông tin chính sách cũ, có thể gây tranh chấp hoàn tiền.

**Hoặc:** Grading câu `gq_d10_01` có `hits_forbidden: true` — top-k retrieval chứa keyword cấm "14 ngày".

---

## Detection

| Metric / Check | Giá trị | Nguồn |
|----------------|---------|-------|
| `expectation[refund_no_stale_14d_window]` | FAIL (halt) | `artifacts/logs/run_*.log` |
| `hits_forbidden` trên `gq_d10_01` | `true` | `artifacts/eval/grading_run.jsonl` |
| `embed_prune_removed` | 0 (không prune doc cũ) | `artifacts/logs/run_*.log` |

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Kiểm tra `artifacts/manifests/*.json` — xem `run_id` | Xác nhận run nào đang active trong ChromaDB |
| 2 | Query ChromaDB: tìm doc chứa "14 ngày" | Nếu có → stale data chưa được prune |
| 3 | Kiểm tra `artifacts/cleaned/*.csv` — tìm "14 ngày" | Nếu có → cleaning rule không chạy (dùng `--no-refund-fix`) |
| 4 | Mở `artifacts/quarantine/*.csv` | Xác nhận record nào bị loại và vì sao |
| 5 | Chạy `python eval_retrieval.py` | Xem `hits_forbidden` và `top1_doc_expected` |

**Root cause thực tế (2026-06-10):** ChromaDB được build từ lần chạy `inject-bad` (`--no-refund-fix --skip-validate`). Stale "14 ngày" data vẫn trong collection vì cleaning rule bị bỏ qua.

---

## Mitigation

| Ưu tiên | Hành động | Lệnh |
|---------|----------|------|
| 1 | Rerun pipeline chuẩn (không flag) | `python etl_pipeline.py run` |
| 2 | Verify grading pass | `python grading_run.py --out artifacts/eval/grading_run.jsonl` |
| 3 | Nếu cần rollback ngay: xóa ChromaDB + rebuild | `rm -rf chroma_db && python etl_pipeline.py run` |

**Tạm thời:** Nếu chưa rerun được, có thể banner "data stale — đang cập nhật" cho user.

---

## Prevention

| Biện pháp | Mô tả |
|-----------|-------|
| Expectation `refund_no_stale_14d_window` (halt) | Chặn pipeline nếu chunk chứa "14 ngày làm việc" |
| Không chạy `--no-refund-fix` trong production | Flag này chỉ dùng cho demo inject corruption |
| Freshness check trên manifest | Phát hiện data quá cũ (>24h SLA) |
| Grading CI | Chạy `grading_run.py` sau mỗi pipeline run để verify |
| Alert khi `embed_prune_removed = 0` mà có data stale | Có thể thêm check trong pipeline |
