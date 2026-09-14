from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"JSONL 파일이 없습니다: {source}")

    records: List[Dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{line_number} JSON 오류: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{source}:{line_number} 레코드는 JSON object여야 합니다.")
            records.append(record)
    return records


def write_jsonl(path: str | Path, records: Iterable[Dict[str, Any]]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return destination


def verified_cases(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        record
        for record in records
        if str((record.get("metadata") or {}).get("label_status", "")).upper() == "VERIFIED"
    ]


def index_predictions(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for record in records:
        case_id = str(record.get("case_id") or (record.get("inputs") or {}).get("case_id") or "").strip()
        if not case_id:
            raise ValueError("Prediction 레코드에 case_id가 없습니다.")
        if case_id in indexed:
            raise ValueError(f"중복 Prediction case_id: {case_id}")
        indexed[case_id] = record
    return indexed

