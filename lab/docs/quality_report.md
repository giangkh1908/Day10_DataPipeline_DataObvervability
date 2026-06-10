# Quality report — Lab Day 10

**run_id:** `2026-06-10T07-00Z`  
**Ngày:** 2026-06-10

---

## 1. Tóm tắt số liệu

| Chỉ số | Inject-bad run | Clean run | Ghi chú |
|--------|---------------|-----------|---------|
| `run_id` | `inject-bad` | `2026-06-10T07-00Z` | |
| `raw_records` | 247 | 247 | Cùng nguồn CSV |
| `cleaned_records` | 35 | 36 | Clean run có 1 record thêm (access_control_sop) |
| `quarantine_records` | 212 | 211 | |
| `expectation[refund_no_stale_14d_window]` | SKIP (--skip-validate) | OK (violations=0) | **Đây là root cause** |
| `expectation[hr_leave_no_stale_10d_annual]` | SKIP | OK (violations=0) | |
| `expectation[min_5_unique_doc_ids]` | SKIP | OK (5 doc_ids) | |
| `embed_prune_removed` | 0 | 1 | Prune doc stale "14 ngày" |
| Pipeline exit code | 0 (skip validate) | 0 | |

---

## 2. Before / after retrieval

### Câu hỏi then chốt: `gq_d10_01` — "Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền?"

**Trước (inject-bad run — stale data trong ChromaDB):**
```json
{
  "id": "gq_d10_01",
  "contains_expected": true,
  "hits_forbidden": true,        ← FAIL: top-k chứa "14 ngày"
  "top1_doc_matches": true
}
```
Top-1: `Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn.`

**Sau (clean run — data đã fix):**
```json
{
  "id": "gq_d10_01",
  "contains_expected": true,
  "hits_forbidden": false,       ← PASS
  "top1_doc_matches": true
}
```
Top-1: `Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng.`

### Câu hỏi `gq_d10_09` — HR version conflict

**Trước:** Không thể verify (inject-bad skip validate → HR stale data có thể trong collection).  
**Sau:** `contains_expected=true`, `hits_forbidden=false`, `top1_doc_matches=true` — HR 2026 (12 ngày) là top-1.

---

## 3. Freshness & monitor

```
freshness_check=FAIL {
  "latest_exported_at": "2026-04-10T00:00:00",
  "age_hours": 1471.021,
  "sla_hours": 24.0,
  "reason": "freshness_sla_exceeded"
}
```

**Giải thích:** Data mẫu có `exported_at` từ 2026-04, SLA 24h → FAIL là hợp lý. Trong production, data cần được export lại trong vòng 24h. Lab dùng data tĩnh nên freshness luôn FAIL — chấp nhận được.

---

## 4. Corruption inject (Sprint 3)

**Kịch bản inject:**
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```

- `--no-refund-fix`: bỏ qua rule fix "14 ngày → 7 ngày" → stale data vào ChromaDB
- `--skip-validate`: vẫn embed dù expectation halt

**Kết quả:**
- `expectation[refund_no_stale_14d_window]`: violations > 0 nhưng bị skip
- ChromaDB chứa chunk "14 ngày làm việc" → grading `gq_d10_01` có `hits_forbidden: true`
- Chạy lại pipeline chuẩn → prune 1 doc stale → grading 10/10

---

## 5. Hạn chế & việc chưa làm

- **Không có LLM judge**: grading dùng keyword matching, không đánh giá ngữ nghĩa
- **Freshness luôn FAIL**: data mẫu tĩnh, không có auto-refresh
- **Không có CI/CD**: pipeline chạy thủ công, không auto-trigger khi data thay đổi
- **Eval bộ nhỏ**: chỉ 10 câu grading + 21 câu test, chưa cover hết edge case
