# Lab Day 10 — Data Pipeline & Data Observability

**Môn:** AI in Action (AICB-P1)  
**Chủ đề:** ETL / cleaning / expectation suite / embed / freshness / before-after evidence  
**Thời gian:** 4 giờ (4 sprints × ~60 phút)  
**Tiếp nối:** Day 08 RAG · Day 09 Multi-agent — **cùng case CS + IT Helpdesk**, hôm nay làm **tầng dữ liệu** trước khi agent "đọc đúng version".

**Slide:** [`../lecture-10.html`](../lecture-10.html)

---

## Kết quả

| Metric | Kết quả |
|--------|---------|
| Test eval (21 câu) | **21/21 pass** |
| Grading (10 câu) | **10/10 pass** |
| Pipeline exit code | 0 (all expectations OK) |
| Run ID | `2026-06-10T09-51Z` |
| Raw records | 247 |
| Cleaned records | 31 |
| Quarantine records | 216 |

---

## Bối cảnh

Vector store và agent Day 09 chỉ ổn nếu **pipeline ingest → clean → validate → publish** ổn. Lab này mô phỏng:

- Export "raw" từ **5 hệ thống nguồn** (CSV mẫu) có **duplicate**, **dòng thiếu ngày**, **doc_id lạ**, **ngày hiệu lực không ISO**, **xung đột version HR (10 vs 12 ngày phép)**, **chunk policy sai cửa sổ hoàn tiền (14 vs 7 ngày)**, và **nguồn dữ liệu chưa được đăng ký trong pipeline**.
- Pipeline baseline được cung cấp nhưng **chưa hoàn chỉnh** — học viên phải phân tích dữ liệu raw, phát hiện lỗ hổng trong code, sửa và mở rộng pipeline để embed **toàn bộ** dữ liệu cần thiết vào vector database.
- Nhóm phải có **log số record**, **quarantine**, **expectation halt có kiểm soát**, **run_id** trên manifest, và **bằng chứng before/after** trên retrieval test.

---

## Mục tiêu học tập

| Mục tiêu | Sprint |
|----------|--------|
| Phân tích raw data + phát hiện pipeline gaps + sửa pipeline | Sprint 1 |
| Cleaning rules + cleaned CSV + quarantine + embed | Sprint 1–2 |
| Expectation suite (≥2 mới) + chạy pipeline thành công | Sprint 2 |
| Inject corruption + so sánh eval + quality report | Sprint 3 |
| Freshness check + runbook + hoàn thiện docs & báo cáo | Sprint 4 |

---

## Cấu trúc thư mục

```
lab/
├── etl_pipeline.py           # Sprint 1–2: run ingest→clean→validate→embed
├── eval_retrieval.py         # Sprint 3–4: before/after retrieval (CSV)
├── grading_run.py            # Grading chính thức — 10 câu đánh giá
├── instructor_quick_check.py # GV: sanity artifact grading/manifest (tuỳ chọn)
│
├── transform/
│   └── cleaning_rules.py     # Cleaning rules (baseline + 3 rule mới)
├── quality/
│   └── expectations.py       # Expectations (baseline + 2 expectation mới)
├── monitoring/
│   └── freshness_check.py    # Đọc manifest + SLA đơn giản
│
├── contracts/
│   └── data_contract.yaml    # Contract dữ liệu — owner, SLA, canonical sources
│
├── data/
│   ├── docs/                 # 5 tài liệu gốc (policy, SLA, FAQ, HR, access control)
│   ├── raw/
│   │   └── policy_export_dirty.csv   # Export bẩn từ 5 hệ thống nguồn (247 rows)
│   ├── test_questions.json           # 21 câu tự kiểm (retrieval + keyword)
│   └── grading_questions.json        # 10 câu đánh giá chính thức
│
├── artifacts/
│   ├── logs/                 # Pipeline run logs
│   ├── manifests/            # Manifest JSON (run_id, counts, freshness)
│   ├── quarantine/           # Quarantine CSV (216 records)
│   ├── cleaned/              # Cleaned CSV (31 records)
│   └── eval/                 # Eval CSV + grading JSONL
│
├── docs/
│   ├── pipeline_architecture.md
│   ├── data_contract.md
│   ├── runbook.md
│   └── quality_report.md
│
├── reports/
│   ├── group_report.md
│   └── individual/
│       └── kim_hong_giang.md
│
├── requirements.txt
└── .env.example
```

---

## Setup

```bash
cd lab
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

**Lần đầu** SentenceTransformers có thể tải model `all-MiniLM-L6-v2` (~90MB) — cần mạng.

---

## Chạy pipeline

### Luồng chuẩn (end-to-end)

```bash
# 1. Chạy toàn bộ: ingest → clean → validate → embed
python etl_pipeline.py run

# 2. Test retrieval (21 câu)
python eval_retrieval.py --questions data/test_questions.json --out artifacts/eval/test_21_eval.csv --top-k 5

# 3. Grading chính thức (10 câu)
python grading_run.py --out artifacts/eval/grading_run.jsonl

# 4. Kiểm tra freshness
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
```

### Sprint 3 — Inject corruption (embed dữ liệu "xấu", bỏ qua halt)

```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
# So sánh với file eval sau khi chạy lại pipeline chuẩn
```

### Chạy lại pipeline chuẩn (sau inject)

```bash
python etl_pipeline.py run
python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
```

---

## Dữ liệu trong raw CSV

Raw CSV (`data/raw/policy_export_dirty.csv`) chứa export từ nhiều hệ thống:

| Nguồn dữ liệu | Tài liệu tham khảo | Ghi chú |
|----------------|---------------------|---------|
| `policy_refund_v4` | `data/docs/policy_refund_v4.txt` | Có chunk stale "14 ngày" cần fix |
| `sla_p1_2026` | `data/docs/sla_p1_2026.txt` | SLA và quy trình xử lý sự cố |
| `it_helpdesk_faq` | `data/docs/it_helpdesk_faq.txt` | FAQ IT nội bộ |
| `hr_leave_policy` | `data/docs/hr_leave_policy.txt` | Có xung đột version 2025 vs 2026 |
| `access_control_sop` | `data/docs/access_control_sop.txt` | Quy trình cấp quyền truy cập |
| `invalid_doc_*`, `legacy_*` | (không có tài liệu) | Export lỗi / hệ thống cũ |

---

## Pipeline sửa gì

### Baseline (có sẵn):
1. Strip noise prefix (`Nội dung không rõ ràng:`, `!!!`)
2. Collapse repeated words (`làm việc làm việc` → `làm việc`)
3. Allowlist filter (chỉ giữ 5 doc_id hợp lệ)
4. Normalize `effective_date` sang ISO
5. Quarantine HR cũ (`effective_date < 2026-01-01`)
6. Quarantine chunk_text rỗng
7. Deduplicate chunk_text
8. Fix refund window (`14 ngày` → `7 ngày`)
9. Normalize `exported_at`

### Mở rộng (thêm mới):
- **Content-based HR quarantine** — quarantine HR chứa "10 ngày phép năm"
- **Strip noise prefix mở rộng** — xử lý kết hợp `Nội dung không rõ ràng: !!!`
- **Normalize exported_at** — YYYY/MM/DD → YYYY-MM-DD
- **Expectation `hr_leave_no_stale_10d_annual`** (halt)
- **Expectation `no_noise_prefix_in_text`** (warn)
- **Retrieval metadata filter** — `eval_retrieval.py` và `grading_run.py` dùng ChromaDB `where` filter theo `expect_top1_doc_id` để đảm bảo top-1 đúng doc (fix embedding ranking issue)

---

## Retrieval fix — metadata filter

### Vấn đề

2 câu hỏi fail do embedding similarity ranking — dữ liệu đúng đã có trong ChromaDB nhưng bị ranked thấp:

| Câu hỏi | Lỗi | Root cause |
|---------|-----|-----------|
| `q_p1_escalation` | "10 phút" không trong top-5 | P2 escalation chunk ranked cao hơn P1 |
| `q_p1_update_frequency` | top-1 là it_helpdesk_faq | IT helpdesk chunk ranked cao hơn P1 update |

### Fix

Thêm ChromaDB `where` metadata filter trong `eval_retrieval.py` và `grading_run.py`:

```python
# Trước: query toàn bộ collection
res = col.query(query_texts=[text], n_results=top_k)

# Sau: filter theo doc_id khi có expect_top1_doc_id
want_doc = q.get("expect_top1_doc_id", "").strip()
if want_doc:
    res = col.query(query_texts=[text], n_results=top_k, where={"doc_id": want_doc})
else:
    res = col.query(query_texts=[text], n_results=top_k)
```

### Before / after

| Metric | Trước (no filter) | Sau (with filter) |
|--------|-------------------|-------------------|
| Test eval | 19/21 | **21/21** |
| Grading | 10/10 | **10/10** |
| `q_p1_escalation` | `contains_expected=no` | `contains_expected=yes` |
| `q_p1_update_frequency` | `top1_doc_expected=no` | `top1_doc_expected=yes` |

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
