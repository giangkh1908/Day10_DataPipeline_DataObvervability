# Data contract — Lab Day 10

> Nguồn: `contracts/data_contract.yaml`

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `policy_refund_v4` | CSV raw → clean → embed | Chunk stale "14 ngày làm việc" (bản v3) lẫn vào | `expectation[refund_no_stale_14d_window]` halt |
| `sla_p1_2026` | CSV raw → clean → embed | Chunk rỗng sau strip noise | `expectation[chunk_min_length_8]` warn |
| `it_helpdesk_faq` | CSV raw → clean → embed | Chunk rỗng (`"    "`) → quarantine | `expectation[no_empty_doc_id]` halt |
| `hr_leave_policy` | CSV raw → clean → embed | Version conflict: bản 2025 (10 ngày) lẫn bản 2026 (12 ngày) | `expectation[hr_leave_no_stale_10d_annual]` halt |
| `access_control_sop` | CSV raw → clean → embed | Thiếu trong allowlist baseline → bị quarantine nhầm | `expectation[min_5_unique_doc_ids]` halt |
| `invalid_doc_*`, `legacy_*`, `security_policy`, `data_privacy_guideline` | CSV raw → quarantine | Không thuộc 5 hệ thống nguồn | `ALLOWED_DOC_IDS` filter |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| `chunk_id` | string | Có | Hash: `{doc_id}_{seq}_{sha256[:16]}` |
| `doc_id` | string | Có | Khóa logic tài liệu nguồn |
| `chunk_text` | string | Có | Đã strip noise, collapse repeated words, fix refund window |
| `effective_date` | date (YYYY-MM-DD) | Có | Chuẩn hoá từ DD/MM/YYYY nếu cần |
| `exported_at` | datetime | Có | Chuẩn hoá từ YYYY/MM/DD → YYYY-MM-DD |

---

## 3. Quy tắc quarantine vs drop

| Điều kiện quarantine | Lý do | Có thể merge lại? |
|---------------------|-------|-------------------|
| `doc_id` không thuộc allowlist | Export lạ / catalog sai | Chỉ nếu đăng ký vào allowlist + contract |
| `effective_date` rỗng hoặc không parse được | Dữ liệu thiếu / format sai | Cần fix nguồn export |
| `hr_leave_policy` có `effective_date < 2026-01-01` | Bản HR cũ | Không — bản stale |
| `hr_leave_policy` chứa "10 ngày phép năm" | Content conflict version | Không — bản stale |
| `chunk_text` rỗng sau clean | Không có nội dung | Không |
| Duplicate `chunk_text` (normalized) | Trùng lặp export | Giữ bản đầu tiên |

Quarantine CSV lưu tại `artifacts/quarantine/` — review thủ công trước khi quyết định merge.

---

## 4. Phiên bản & canonical

| Document | Source of truth | Version hiện tại | Effective date |
|----------|----------------|-----------------|----------------|
| `policy_refund_v4` | `data/docs/policy_refund_v4.txt` | v4 | 2026-02-01 |
| `sla_p1_2026` | `data/docs/sla_p1_2026.txt` | 2026.1 | 2026-01-15 |
| `it_helpdesk_faq` | `data/docs/it_helpdesk_faq.txt` | 2026-01-20 | 2026-01-20 |
| `hr_leave_policy` | `data/docs/hr_leave_policy.txt` | 2026 | 2026-01-01 |
| `access_control_sop` | `data/docs/access_control_sop.txt` | 2026-01-01 | 2026-01-01 |

**Versioning rule**: `hr_leave_policy` — bản có `effective_date >= 2026-01-01` là canonical. Bản cũ bị quarantine theo date check và content check ("10 ngày phép năm").
