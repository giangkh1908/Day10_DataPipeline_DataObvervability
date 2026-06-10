# Lab Day 10 — Data Pipeline & Data Observability

**Môn:** AI in Action (AICB-P1)
**Chủ đề:** ETL / cleaning / expectation suite / embed / freshness / before-after evidence
**Thời gian:** 4 giờ (4 sprints × ~60 phút)
**Tiếp nối:** Day 08 RAG · Day 09 Multi-agent — **cùng case CS + IT Helpdesk**, hôm nay làm **tầng dữ liệu** trước khi agent "đọc đúng version".

**Slide:** [`../lecture-10.html`](../lecture-10.html)

---

## Bài toán là gì?

Bạn có **hệ thống RAG** (Day 08/09) — agent đọc tài liệu để trả lời câu hỏi. Nhưng nếu **dữ liệu bẩn** (sai, cũ, trùng lặp) → agent trả lời sai.

**Ví dụ thực tế:** Chính sách hoàn tiền đã đổi từ 14 ngày → 7 ngày, nhưng vector store vẫn còn chunk "14 ngày" → agent nói sai cho khách hàng.

**Bài toán:** Xây pipeline ETL để **ingest → clean → validate → embed** dữ liệu sạch vào vector store, đảm bảo agent trả lời đúng **tất cả 10 câu hỏi đánh giá** trong `data/grading_questions.json`.

---

## Cấu trúc tổng thể

```
┌──────────────────────────────────────────────────────────┐
│                    RAW DATA (247 rows)                    │
│         data/raw/policy_export_dirty.csv                  │
│   (5 hệ thống: policy, SLA, IT FAQ, HR, access control)  │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│                    CLEANING RULES                         │
│              transform/cleaning_rules.py                  │
│                                                          │
│  1. Strip noise prefix ("Nội dung không rõ ràng:")      │
│  2. Strip noise suffix ("Chú ý:", "FAQ bổ sung:")       │
│  3. Collapse repeated words ("làm việc làm việc")        │
│  4. Filter doc_id không thuộc allowlist                  │
│  5. Normalize ngày (DD/MM/YYYY → YYYY-MM-DD)            │
│  6. Filter HR cũ (effective_date < 2026)                 │
│  7. Filter HR content cũ ("10 ngày phép năm")            │
│  8. Remove duplicate chunks                              │
│  9. Fix refund window (14 ngày → 7 ngày)                 │
│  10. Normalize exported_at                               │
└────────────────────────┬─────────────────────────────────┘
                         ▼
              ┌──────────┴──────────┐
              ▼                     ▼
    ┌─────────────────┐   ┌──────────────────┐
    │  CLEANED (31)   │   │ QUARANTINE (216) │
    └────────┬────────┘   └──────────────────┘
             ▼
┌──────────────────────────────────────────────────────────┐
│                   EXPECTATIONS (8 checks)                │
│              quality/expectations.py                      │
│                                                          │
│  E1: ≥1 row sau clean                    (halt)         │
│  E2: Không doc_id rỗng                   (halt)         │
│  E3: Refund không còn "14 ngày"          (halt)         │
│  E4: Chunk text ≥ 8 ký tự               (warn)         │
│  E5: effective_date đúng ISO             (halt)         │
│  E6: HR không còn "10 ngày phép năm"     (halt)         │
│  E7: ≥5 doc_id unique                    (halt)         │
│  E8: Không còn noise prefix              (warn)         │
└────────────────────────┬─────────────────────────────────┘
                         ▼
              ┌──────────┴──────────┐
              ▼                     ▼
    ┌─────────────────┐   ┌──────────────────┐
    │  PASS → EMBED   │   │ FAIL → HALT      │
    └────────┬────────┘   └──────────────────┘
             ▼
┌──────────────────────────────────────────────────────────┐
│                     EMBED                                │
│  - ChromaDB PersistentClient                             │
│  - Model: all-MiniLM-L6-v2 (SentenceTransformer)        │
│  - Upsert theo chunk_id (idempotent)                    │
│  - Prune ID cũ không còn trong cleaned                   │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│                    EVALUATION                             │
│  grading_run.py (10 câu) → grading_run.jsonl            │
│  eval_retrieval.py (21 câu) → eval CSV                   │
└──────────────────────────────────────────────────────────┘
```

---

## Dữ liệu raw có gì?

247 rows từ 5 hệ thống + dữ liệu bẩn:

| doc_id | Số rows | Vấn đề |
|--------|---------|--------|
| `policy_refund_v4` | ~30 | Có chunk "14 ngày" (sai, phải 7 ngày) |
| `sla_p1_2026` | ~25 | Duplicate nhiều |
| `it_helpdesk_faq` | ~20 | Có chunk rỗng, whitespace |
| `hr_leave_policy` | ~40 | Xung đột version 2025 (10 ngày) vs 2026 (12 ngày) |
| `access_control_sop` | 9 | **Baseline bỏ sót** — bị quarantine nhầm |
| `security_policy` | ~15 | Không có file doc → invalid |
| `data_privacy_guideline` | ~25 | Không có file doc → invalid |
| `legacy_catalog_xyz_zzz` | ~25 | Hệ thống cũ, placeholder |
| `invalid_doc_*` | ~30 | Export lỗi |

---

## Cleaning Rules xử lý gì?

### Rule 1 — Strip noise prefix
```
"Nội dung không rõ ràng: Tài khoản bị khóa..." → "Tài khoản bị khóa..."
"!!!Yêu cầu hoàn tiền..." → "Yêu cầu hoàn tiền..."
```

### Rule 2 — Strip noise suffix
```
"Tài khoản bị khóa. Chú ý: effective_date không đồng nhất"
→ "Tài khoản bị khóa."

"Yêu cầu hoàn tiền... Nội dung có thể bị trùng do sync lại dữ liệu."
→ "Yêu cầu hoàn tiền..."
```

### Rule 3 — Collapse repeated words
```
"7 ngày làm việc làm việc làm việc" → "7 ngày làm việc"
"Yêu cầu. Yêu cầu. Yêu cầu." → "Yêu cầu."
```

### Rule 4 — Allowlist filter
```
doc_id="security_policy" → quarantine (không có trong 5 hệ thống)
doc_id="access_control_sop" → giữ (đã thêm vào allowlist)
```

### Rule 5 — Normalize ngày
```
"05/02/2025" → "2025-02-05"
```

### Rule 6 — Filter HR cũ (theo ngày)
```
hr_leave_policy, effective_date="2025-05-08" → quarantine (bản 2025)
```

### Rule 7 — Filter HR cũ (theo content)
```
"Nhân viên được 10 ngày phép năm" → quarantine (bản 2025)
"Nhân viên được 10 ngày làm việc phép năm" → quarantine (regex bắt cả 2)
```

### Rule 8 — Deduplicate
```
2 chunk giống nội dung → giữ chunk đầu, quarantine chunk sau
```

### Rule 9 — Fix refund window
```
"14 ngày làm việc" → "7 ngày làm việc [cleaned: stale_refund_window]"
```

### Rule 10 — Normalize exported_at
```
"2026/04/11T00:00:00" → "2026-04-11T00:00:00"
```

---

## Expectations kiểm tra gì?

Sau khi clean, expectations kiểm tra dữ liệu có sạch không:

| Expectation | Kiểm tra | Severity | Nếu fail |
|-------------|----------|----------|----------|
| E1 `min_one_row` | Có ≥1 row sau clean | halt | Pipeline dừng |
| E2 `no_empty_doc_id` | Không doc_id rỗng | halt | Pipeline dừng |
| E3 `refund_no_stale_14d_window` | Không còn "14 ngày làm việc" | halt | Pipeline dừng |
| E4 `chunk_min_length_8` | Chunk text ≥ 8 ký tự | warn | Cảnh báo |
| E5 `effective_date_iso_yyyy_mm_dd` | Ngày đúng format ISO | halt | Pipeline dừng |
| E6 `hr_leave_no_stale_10d_annual` | Không còn "10 ngày phép năm" | halt | Pipeline dừng |
| E7 `min_5_unique_doc_ids` | Có ≥5 doc_id unique | halt | Pipeline dừng |
| E8 `no_noise_prefix_in_text` | Không còn noise prefix | warn | Cảnh báo |

**halt** = dừng pipeline, không embed. **warn** = ghi log, vẫn tiếp tục.

---

## Cấu trúc thư mục

```
lab/
├── etl_pipeline.py           # Entry point: run ingest→clean→validate→embed
├── eval_retrieval.py         # 21 câu test retrieval (tự kiểm)
├── grading_run.py            # 10 câu grading chính thức (GV chấm)
├── instructor_quick_check.py # GV: sanity artifact (tuỳ chọn)
│
├── transform/
│   └── cleaning_rules.py     # 10 cleaning rules (4 mới + 6 baseline)
├── quality/
│   └── expectations.py       # 8 expectations (2 mới + 6 baseline)
├── monitoring/
│   └── freshness_check.py    # Kiểm tra SLA freshness từ manifest
│
├── contracts/
│   └── data_contract.yaml    # Contract dữ liệu (owner, SLA, schema)
│
├── data/
│   ├── docs/                 # 5 tài liệu gốc (policy, SLA, FAQ, HR, access)
│   ├── raw/
│   │   └── policy_export_dirty.csv   # 247 rows bẩn từ 5 hệ thống
│   ├── test_questions.json           # 21 câu tự kiểm
│   └── grading_questions.json        # 10 câu grading chính thức
│
├── artifacts/
│   ├── logs/                 # Log mỗi lần chạy pipeline
│   ├── manifests/            # Manifest JSON (run_id, counts, timestamps)
│   ├── quarantine/           # Rows bị loại (có lý do)
│   ├── cleaned/              # Rows đã clean
│   └── eval/                 # Kết quả eval CSV + grading JSONL
│
├── docs/
│   ├── pipeline_architecture.md  # Sơ đồ pipeline + ranh giới
│   ├── data_contract.md          # Source map + schema + versioning
│   ├── runbook.md                # Symptom→Detection→Diagnosis→Fix→Prevention
│   └── quality_report.md         # Before/after evidence
│
├── reports/
│   └── individual/
│       └── kim_hong_giang.md     # Báo cáo cá nhân
│
├── requirements.txt
└── .env.example
```

---

## Setup

```bash
cd lab
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
cp .env.example .env
```

**Lần đầu** SentenceTransformers sẽ tải model `all-MiniLM-L6-v2` (~90MB) — cần mạng.

---

## Chạy Pipeline

### Bước 1: Chạy pipeline (ingest → clean → validate → embed)

```bash
python etl_pipeline.py run
```

Output:
```
run_id=2026-06-10T05-09Z
raw_records=247
cleaned_records=31
quarantine_records=216
expectation[min_one_row] OK (halt)
expectation[refund_no_stale_14d_window] OK (halt)
...
embed_upsert count=31 collection=day10_kb
PIPELINE_OK
```

### Bước 2: Grading chính thức (10 câu)

```bash
python grading_run.py --out artifacts/eval/grading_run.jsonl
```

Xem kết quả:
```bash
python -c "
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open('artifacts/eval/grading_run.jsonl', encoding='utf-8') as f:
    for line in f:
        r = json.loads(line)
        ok = r['contains_expected'] and not r['hits_forbidden']
        top1 = r.get('top1_doc_matches', True)
        status = 'PASS' if (ok and top1) else 'FAIL'
        print(f\"{r['id']}: {status} | top1={r['top1_doc_id']}\")
"
```

### Bước 3: Eval retrieval (21 câu tự kiểm)

```bash
python eval_retrieval.py --out artifacts/eval/eval.csv
```

### Bước 4: Freshness check

```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
```

**Lưu ý:** `<run-id>` là placeholder — thay bằng tên file manifest thật. VD:
```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_2026-06-10T05-09Z.json
```

Freshness check trên data mẫu luôn **FAIL** vì `exported_at` từ tháng 4/2026, quá 24h SLA. Đây là kết quả mong muốn — cần ghi trong runbook.

---

## Sprint 3 — Inject Corruption (Before/After)

### Chạy pipeline với dữ liệu xấu

```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```

- `--no-refund-fix`: bỏ rule fix "14 ngày → 7 ngày" → stale data vào ChromaDB
- `--skip-validate`: vẫn embed dù expectation halt

### Eval với dữ liệu xấu

```bash
python eval_retrieval.py --out artifacts/eval/eval_inject_bad.csv
```

### Chạy lại pipeline chuẩn

```bash
python etl_pipeline.py run --run-id after-fix
python eval_retrieval.py --out artifacts/eval/eval_after_fix.csv
```

### So sánh

| | Inject-bad (trước) | After-fix (sau) |
|--|-------------------|-----------------|
| `q_refund_window` | ❌ `forbidden=yes` | ✅ PASS |
| Tổng | 18/21 PASS | 19/21 PASS |

---

## Kết quả đạt được

```
Pipeline:     exit 0 ✅
Expectations: 8/8 pass ✅
Grading:      10/10 PASS ✅
Test eval:    19/21 PASS
Cleaned:      31 records
Quarantine:   216 records
```

### 10 câu grading

| Câu | Doc top-1 | Status |
|-----|-----------|--------|
| gq_d10_01 | policy_refund_v4 | ✅ |
| gq_d10_02 | policy_refund_v4 | ✅ |
| gq_d10_03 | policy_refund_v4 | ✅ |
| gq_d10_04 | sla_p1_2026 | ✅ |
| gq_d10_05 | sla_p1_2026 | ✅ |
| gq_d10_06 | sla_p1_2026 | ✅ |
| gq_d10_07 | it_helpdesk_faq | ✅ |
| gq_d10_08 | it_helpdesk_faq | ✅ |
| gq_d10_09 | hr_leave_policy | ✅ |
| gq_d10_10 | access_control_sop | ✅ |

---

## Pipeline đã sửa gì so với baseline?

### Allowlist
- **Thêm** `access_control_sop` vào `ALLOWED_DOC_IDS` (baseline chỉ có 4 doc_id, thiếu nguồn này → grading gq_d10_10 fail)

### Cleaning Rules mới (4 rule)
| Rule | Mô tả | Metric impact |
|------|-------|---------------|
| Strip noise prefix | Loại "Nội dung không rõ ràng:", "!!!" | ~15 rows clean hơn |
| Strip noise suffix | Loại "Chú ý:", "FAQ bổ sung:", "Nội dung có thể bị trùng" | ~5 rows clean hơn |
| Collapse repeated words | "làm việc làm việc" → "làm việc" | 3 rows fix |
| Normalize exported_at | "2026/04/11" → "2026-04-11" | ~20 rows fix |

### Expectations mới (2 expectation)
| Expectation | Mô tả | Severity |
|-------------|-------|----------|
| `min_5_unique_doc_ids` | Đảm bảo ≥5 nguồn dữ liệu trong cleaned | halt |
| `no_noise_prefix_in_text` | Không còn noise prefix trong chunk_text | warn |

### HR Content Filter
- Regex linh hoạt: bắt cả "10 ngày phép năm" và "10 ngày làm việc phép năm"

---

## Tại sao 2 câu test fail mà grading vẫn 10/10?

| Câu hỏi | Test (top-5) | Grading (top-8) |
|---------|-------------|-----------------|
| "P1 auto escalate sau bao lâu?" | ❌ top-5 không có "10 phút" | ✅ top-8 có |
| "P1 cập nhật mỗi bao lâu?" | ❌ top-1 sai doc | Không có trong grading |

**Nguyên nhân:** Semantic search (embedding similarity) không hoàn hảo. Chunk "10 phút" có similarity thấp hơn chunk "90 phút" (P2) vì cả 2 đều nói về "escalation" và "phản hồi".

**Không phải lỗi pipeline** — là limitation của model embedding. Grading dùng top-k=8 (rộng hơn) nên pass.

---

## Debug order (nhắc từ slide Day 10)

```
Freshness / version → Volume & errors → Schema & contract → Lineage / run_id → mới đến model/prompt
```

---

## Tài nguyên tham khảo

- Slide: [`../lecture-10.html`](../lecture-10.html)
- Lab Day 09 (orchestration): [`../../day09/lab/README.md`](../../day09/lab/README.md)
- Great Expectations (tuỳ chọn nâng cao): https://docs.greatexpectations.io/
- ChromaDB: https://docs.trychroma.com/
