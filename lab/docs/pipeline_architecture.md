# Kiến trúc pipeline — Lab Day 10

**Nhóm:** Individual  
**Cập nhật:** 2026-06-10

---

## 1. Sơ đồ luồng

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ETL Pipeline (etl_pipeline.py)                   │
│                                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  INGEST  │───▶│  CLEAN   │───▶│  VALIDATE    │───▶│    EMBED     │  │
│  │          │    │          │    │              │    │              │  │
│  │ Raw CSV  │    │ Rules:   │    │ Expectations │    │ ChromaDB     │  │
│  │ 247 rows │    │ - strip  │    │ - 8 checks   │    │ - upsert     │  │
│  │          │    │ - fix    │    │ - halt/warn  │    │ - prune      │  │
│  │          │    │ - dedup  │    │              │    │              │  │
│  └──────────┘    └────┬─────┘    └──────────────┘    └──────────────┘  │
│                       │                                                 │
│                       ▼                                                 │
│              ┌────────────────┐    ┌──────────────────┐                │
│              │  CLEANED CSV   │    │  QUARANTINE CSV  │                │
│              │  36 records    │    │  211 records     │                │
│              └────────────────┘    └──────────────────┘                │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  MONITORING                                                      │  │
│  │  - manifest.json (run_id, counts, timestamps)                    │  │
│  │  - freshness_check (SLA 24h on latest_exported_at)               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  SERVING (Day 08/09)                                             │  │
│  │  - grading_run.py (10 câu đánh giá)                             │  │
│  │  - eval_retrieval.py (21 câu tự kiểm)                           │  │
│  │  - collection: day10_kb, model: all-MiniLM-L6-v2                │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | Owner |
|------------|-------|--------|-------|
| Ingest | `data/raw/policy_export_dirty.csv` (247 rows) | List[Dict] raw rows | etl_pipeline.py → load_raw_csv() |
| Transform | Raw rows | Cleaned rows + quarantine | transform/cleaning_rules.py |
| Quality | Cleaned rows | ExpectationResult[] + halt flag | quality/expectations.py |
| Embed | Cleaned CSV | ChromaDB collection (36 docs) | etl_pipeline.py → cmd_embed_internal() |
| Monitor | Manifest JSON | PASS/WARN/FAIL + detail dict | monitoring/freshness_check.py |

---

## 3. Idempotency & rerun

- **Upsert theo `chunk_id`**: mỗi chunk có ID hash dựa trên `doc_id + chunk_text + seq`. Rerun cùng dữ liệu → upsert đè, không duplicate.
- **Prune id thừa**: trước khi upsert, pipeline lấy tất cả ID hiện có trong collection, so với cleaned IDs, xóa những ID không còn. Log: `embed_prune_removed=N`.
- **Rerun 2 lần** → cùng 36 docs, không phình collection. Kiểm chứng: `col.count()` ổn định sau 2 lần run.

---

## 4. Liên hệ Day 09

Pipeline Day 10 cung cấp corpus cho retrieval trong Day 08/09:
- Collection `day10_kb` trong cùng ChromaDB path.
- Day 09 multi-agent query collection này để trả lời câu hỏi CS/IT/HR.
- Nếu Day 10 pipeline fail (stale data), agent Day 09 trả lời sai (vd: "14 ngày" thay vì "7 ngày").

---

## 5. Rủi ro đã biết

- **Freshness FAIL trên data mẫu**: `exported_at` trong CSV là 2026-04, SLA 24h → luôn FAIL. Chấp nhận được cho lab; production cần data thật.
- **Embedding model CPU**: `all-MiniLM-L6-v2` chạy CPU, đủ cho lab (<100 docs). Production cần GPU hoặc model lớn hơn.
- **Không có LLM judge**: grading dùng keyword matching, không đánh giá ngữ nghĩa. Có thể miss câu trả lời đúng nhưng dùng từ khác.
