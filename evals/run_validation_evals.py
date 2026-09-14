from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from evals.dataset_io import index_predictions, load_jsonl, verified_cases
from evals.evaluators.code_metrics import (
    aggregate_binary_classification,
    aggregate_set_detection,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="고정 Script를 사용한 Validation Agent 평가")
    parser.add_argument("--dataset", required=True, help="Validation 정답 Dataset JSONL")
    parser.add_argument("--predictions", required=True, help="Validation 실행 결과 JSONL")
    parser.add_argument("--output", help="평가 결과 JSON 경로")
    return parser.parse_args()


def evaluate(dataset_path: str, prediction_path: str) -> Dict[str, Any]:
    cases = verified_cases(load_jsonl(dataset_path))
    if not cases:
        raise ValueError("VERIFIED 라벨이 있는 Validation Case가 없습니다.")
    predictions = index_predictions(load_jsonl(prediction_path))

    status_pairs = []
    error_pairs = []
    per_case: List[Dict[str, Any]] = []
    missing_predictions: List[str] = []

    for case in cases:
        case_id = str(case.get("case_id", ""))
        prediction = predictions.get(case_id)
        if prediction is None:
            missing_predictions.append(case_id)
            continue

        reference = ((case.get("reference_outputs") or {}).get("validation") or {})
        outputs = prediction.get("outputs") or prediction
        actual = outputs.get("validation") or outputs

        expected_status = str(reference.get("status", "")).upper()
        actual_status = str(actual.get("initial_status") or actual.get("status") or "").upper()
        if expected_status not in {"PASS", "FAIL"}:
            raise ValueError(f"{case_id}: reference validation.status가 PASS/FAIL이 아닙니다.")
        if actual_status not in {"PASS", "FAIL"}:
            raise ValueError(f"{case_id}: prediction validation.status가 PASS/FAIL이 아닙니다.")

        expected_errors = reference.get("error_types", []) or []
        actual_errors = actual.get("initial_error_types", actual.get("error_types", [])) or []
        status_pairs.append((expected_status == "FAIL", actual_status == "FAIL"))
        error_pairs.append((expected_errors, actual_errors))
        per_case.append({
            "case_id": case_id,
            "expected_status": expected_status,
            "actual_status": actual_status,
            "expected_error_types": expected_errors,
            "actual_error_types": actual_errors,
            "status_correct": expected_status == actual_status,
        })

    status_summary = aggregate_binary_classification(status_pairs, positive_value=True)
    report = {
        "dataset": str(dataset_path),
        "predictions": str(prediction_path),
        "verified_cases": len(cases),
        "evaluated_cases": len(per_case),
        "missing_predictions": missing_predictions,
        "summary": {
            "validation": {
                **status_summary,
                "false_pass_rate": status_summary.get("false_negative_rate", 0.0),
                "false_fail_rate": status_summary.get("false_positive_rate", 0.0),
                "error_detection": aggregate_set_detection(error_pairs),
            }
        },
        "per_case": per_case,
    }
    return report


def main() -> None:
    args = parse_args()
    report = evaluate(args.dataset, args.predictions)
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(__file__).resolve().parent / "results" / f"validation_eval_{timestamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"평가 결과 저장: {output_path}")


if __name__ == "__main__":
    main()
