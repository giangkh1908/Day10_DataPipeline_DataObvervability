"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
Sinh viên thêm ≥3 rule mới: mỗi rule phải ghi `metric_impact` (xem README — chống trivial).
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Khớp export hợp lệ trong lab (mở rộng khi nhóm thêm doc mới — phải đồng bộ contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
        "access_control_sop",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _strip_noise_prefix(text: str) -> str:
    """Loại bỏ noise prefix: 'Nội dung không rõ ràng:', '!!!', ghi chú export lỗi."""
    t = text.strip()
    for prefix in ("Nội dung không rõ ràng: !!!", "Nội dung không rõ ràng:"):
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
    while t.startswith("!!!"):
        t = t[3:].strip()
    return t


def _strip_noise_suffix(text: str) -> str:
    """Loại bỏ ghi chú nội bộ ở cuối: 'Chú ý:', 'FAQ bổ sung:', 'Nội dung có thể bị trùng...'."""
    t = text.strip()
    # Loại suffix patterns
    suffixes = [
        r"\s*Chú ý:.*$",
        r"\s*FAQ bổ sung:.*$",
        r"\s*Nội dung có thể bị trùng do sync lại dữ liệu\.?",
        r"\s*Ghi chú:.*$",
        r"\s*Nguồn:.*$",
    ]
    for pat in suffixes:
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()
    return t


def _collapse_repeated_words(text: str) -> str:
    """Giảm 'làm việc làm việc làm việc' → 'làm việc' (collapse repeated phrases)."""
    # Collapse repeated single words: "the the the" → "the"
    t = re.sub(r"(\b\w+\b)(\s+\1)+", r"\1", text)
    # Collapse repeated multi-word phrases: "làm việc làm việc" → "làm việc"
    for length in range(5, 1, -1):
        pattern = re.compile(
            r"((?:\b\w+\b[\s.]+){1," + str(length) + r"})(?:\s*\1)+"
        )
        prev = None
        while prev != t:
            prev = t
            t = pattern.sub(r"\1", t)
    return t


def _normalize_exported_at(raw: str) -> str:
    """Chuyển 'YYYY/MM/DD...' thành 'YYYY-MM-DD...' (chuẩn ISO) cho freshness check."""
    s = (raw or "").strip()
    if re.match(r"^\d{4}/\d{2}/\d{2}", s):
        s = s[:4] + "-" + s[5:7] + "-" + s[8:]
    return s


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Baseline (mở rộng theo narrative Day 10):
    1) Strip noise prefix ('Nội dung không rõ ràng:', '!!!').
    2) Collapse repeated consecutive words ('làm việc làm việc' → 'làm việc').
    3) Quarantine: doc_id không thuộc allowlist (export lạ / catalog sai).
    4) Chuẩn hoá effective_date sang YYYY-MM-DD; quarantine nếu không parse được.
    5) Quarantine: chunk hr_leave_policy có effective_date < 2026-01-01 (bản HR cũ / conflict version).
    6) Quarantine: chunk_text rỗng hoặc effective_date rỗng sau chuẩn hoá.
    7) Loại trùng nội dung chunk_text (giữ bản đầu).
    8) Fix stale refund: policy_refund_v4 chứa '14 ngày làm việc' → 7 ngày.
    9) Normalize exported_at (YYYY/MM/DD → YYYY-MM-DD).
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        # --- Rule mới 1: Strip noise prefix ---
        text = _strip_noise_prefix(text)

        # --- Rule mới 1b: Strip noise suffix (ghi chú nội bộ) ---
        text = _strip_noise_suffix(text)

        # --- Rule mới 2: Collapse repeated words ---
        text = _collapse_repeated_words(text)

        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        if doc_id == "hr_leave_policy" and eff_norm < "2026-01-01":
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        # Content-based: HR 2026 nhưng vẫn chứa text bản cũ 10 ngày phép năm
        # Linh hoạt: bắt cả "10 ngày phép năm", "10 ngày làm việc phép năm", "10 ngày phép"
        if doc_id == "hr_leave_policy" and re.search(r"10\s+ngày(?:\s+làm\s+việc)?\s+phép", text):
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_content_10d",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        key = _norm_text(text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        fixed_text = text
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        # --- Rule mới 3: Normalize exported_at ---
        exported_at = _normalize_exported_at(exported_at)

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_at or "",
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
