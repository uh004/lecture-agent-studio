from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from evals.dataset_io import index_predictions, load_jsonl, verified_cases
from evals.evaluators.code_metrics import (
    aggregate_binary_classification,
    aggregate_set_detection,
    evaluate_parser,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lecture Agent 코드 기반 평가")
    parser.add_argument("--dataset", required=True, help="정답 Dataset JSONL")
    parser.add_argument("--predictions", required=True, help="노트북 실행 결과 JSONL")
    parser.add_argument("--output", help="평가 결과 JSON 경로")
    return parser.parse_args()


def _macro_average(rows: List[Dict[str, float]]) -> Dict[str, float]:
    if not rows:
        return {}
    keys = sorted({key for row in rows for key in row})
    return {
        key: mean(row[key] for row in rows if key in row)
        for key in keys
    }


def evaluate(dataset_path: str, prediction_path: str) -> Dict[str, Any]:
    cases = verified_cases(load_jsonl(dataset_path))
    if not cases:
        raise ValueError("VERIFIED 라벨이 있는 평가 Case가 없습니다.")
    predictions = index_predictions(load_jsonl(prediction_path))

    per_case: List[Dict[str, Any]] = []
    parser_rows: List[Dict[str, float]] = []
    search_pairs = []
    validation_pairs = []
    validation_error_pairs = []
    validation_attempt_counts: List[int] = []
    recovery_eligible = 0
    recovered = 0
    workflows: Dict[str, Dict[str, Any]] = {}
    missing_predictions: List[str] = []

    for case in cases:
        case_id = str(case.get("case_id") or (case.get("inputs") or {}).get("case_id") or "")
        prediction = predictions.get(case_id)
        if prediction is None:
            missing_predictions.append(case_id)
            continue

        reference = case.get("reference_outputs") or {}
        outputs = prediction.get("outputs") or prediction
        parser_metrics = evaluate_parser(reference.get("parser", {}), outputs.get("parser", {}))
        parser_rows.append(parser_metrics)

        expected_search = bool((reference.get("search") or {}).get("needed", False))
        actual_search = bool((outputs.get("search") or {}).get("needed", False))
        search_pairs.append((expected_search, actual_search))

        validation_reference = reference.get("validation") or {}
        expected_status = str(validation_reference.get("status", "")).upper()
        validation_output = outputs.get("validation") or {}
        actual_status = str(
            validation_output.get("initial_status") or validation_output.get("status") or ""
        ).upper()
        final_validation_status = str(
            validation_output.get("final_status") or validation_output.get("status") or ""
        ).upper()
        if expected_status in {"PASS", "FAIL"} and actual_status in {"PASS", "FAIL"}:
            validation_pairs.append((expected_status == "FAIL", actual_status == "FAIL"))

        if expected_status in {"PASS", "FAIL"} or "error_types" in validation_reference:
            expected_errors = validation_reference.get("error_types", []) or []
            actual_errors = validation_output.get(
                "initial_error_types", validation_output.get("error_types", []) or []
            )
            validation_error_pairs.append((expected_errors, actual_errors))

        validation_history = validation_output.get("history", []) or []
        if validation_output:
            validation_attempt_counts.append(len(validation_history))
        if validation_history and str(validation_history[0].get("status", "")).upper() == "FAIL":
            recovery_eligible += 1
            if final_validation_status == "PASS":
                recovered += 1

        workflow = outputs.get("workflow") or {}
        if workflow:
            workflow_key = str(workflow.get("run_id") or json.dumps(workflow, sort_keys=True, default=str))
            workflows[workflow_key] = workflow
        per_case.append({"case_id": case_id, "parser": parser_metrics})

    validation_summary = aggregate_binary_classification(validation_pairs, positive_value=True)
    workflow_status_counts = {"completed": 0, "partial_completed": 0, "failed": 0, "unknown": 0}
    for workflow in workflows.values():
        status = str(workflow.get("final_status", "unknown"))
        key = status if status in workflow_status_counts else "unknown"
        workflow_status_counts[key] += 1
    workflow_count = len(workflows)
    report = {
        "dataset": str(dataset_path),
        "predictions": str(prediction_path),
        "verified_cases": len(cases),
        "evaluated_cases": len(per_case),
        "missing_predictions": missing_predictions,
        "summary": {
            "parser": _macro_average(parser_rows),
            "search_decision": aggregate_binary_classification(search_pairs, positive_value=True),
            "validation": {
                **validation_summary,
                "false_pass_rate": validation_summary.get("false_negative_rate", 0.0),
                "false_fail_rate": validation_summary.get("false_positive_rate", 0.0),
                "error_detection": aggregate_set_detection(validation_error_pairs),
                "recovery_eligible_cases": recovery_eligible,
                "recovered_cases": recovered,
                "recovery_rate": recovered / recovery_eligible if recovery_eligible else 0.0,
                "average_validation_calls": mean(validation_attempt_counts) if validation_attempt_counts else 0.0,
            },
            "workflow": {
                "runs": workflow_count,
                "status_counts": workflow_status_counts,
                "completed_rate": (
                    workflow_status_counts["completed"] / workflow_count if workflow_count else 0.0
                ),
            },
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
        output_path = Path(__file__).resolve().parent / "results" / f"code_eval_{timestamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"평가 결과 저장: {output_path}")


if __name__ == "__main__":
    main()
