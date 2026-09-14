import json
import tempfile
import unittest
from pathlib import Path

from evals.evaluators.code_metrics import (
    aggregate_binary_classification,
    aggregate_set_detection,
    evaluate_parser,
)
from evals.run_code_evals import evaluate
from evals.run_validation_evals import evaluate as evaluate_validation


class ParserEvaluatorTests(unittest.TestCase):
    def test_exact_parser_output_scores_one(self) -> None:
        reference = {
            "title": "제목",
            "text": "첫 번째 본문",
            "tables": [["A", "B"]],
            "image_count": 1,
        }
        actual = {
            **reference,
            "extraction_errors": [],
        }
        metrics = evaluate_parser(reference, actual)
        self.assertEqual(metrics["parser_slide_success"], 1.0)
        self.assertEqual(metrics["parser_text_f1"], 1.0)

    def test_missing_content_reduces_scores(self) -> None:
        reference = {
            "title": "제목",
            "text": "중요한 본문 내용",
            "tables": [["A", "B"]],
            "image_count": 2,
        }
        actual = {
            "title": "제목",
            "text": "중요한 본문",
            "tables": [["A"]],
            "image_count": 1,
            "extraction_errors": ["이미지 누락"],
        }
        metrics = evaluate_parser(reference, actual)
        self.assertLess(metrics["parser_text_recall"], 1.0)
        self.assertLess(metrics["parser_table_cell_accuracy"], 1.0)
        self.assertEqual(metrics["parser_image_extraction_success_rate"], 0.5)
        self.assertEqual(metrics["parser_slide_success"], 0.0)


class ClassificationEvaluatorTests(unittest.TestCase):
    def test_validation_false_pass_rate(self) -> None:
        metrics = aggregate_binary_classification(
            [(True, True), (True, False), (False, False)],
            positive_value=True,
        )
        self.assertEqual(metrics["false_negative_rate"], 0.5)

    def test_error_type_detection(self) -> None:
        metrics = aggregate_set_detection([
            (["unsupported_claims", "missing_points"], ["unsupported_claims"]),
        ])
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 0.5)


class EvaluationRunnerTests(unittest.TestCase):
    def test_report_includes_recovery_and_workflow(self) -> None:
        case = {
            "case_id": "case-1",
            "inputs": {"case_id": "case-1"},
            "reference_outputs": {
                "parser": {"title": "제목", "text": "본문", "tables": [], "image_count": 0},
                "search": {"needed": True},
                "validation": {"status": "FAIL", "error_types": ["unsupported_claims"]},
            },
            "metadata": {"label_status": "VERIFIED"},
        }
        prediction = {
            "case_id": "case-1",
            "outputs": {
                "parser": {
                    "title": "제목", "text": "본문", "tables": [], "image_count": 0,
                    "extraction_errors": [],
                },
                "search": {"needed": True},
                "validation": {
                    "initial_status": "FAIL",
                    "initial_error_types": ["unsupported_claims"],
                    "final_status": "PASS",
                    "history": [{"status": "FAIL"}, {"status": "PASS"}],
                },
                "workflow": {"run_id": "run-1", "final_status": "completed"},
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            dataset_path = Path(directory) / "dataset.jsonl"
            prediction_path = Path(directory) / "predictions.jsonl"
            dataset_path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
            prediction_path.write_text(
                json.dumps(prediction, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            report = evaluate(str(dataset_path), str(prediction_path))

        self.assertEqual(report["summary"]["validation"]["recovery_rate"], 1.0)
        self.assertEqual(report["summary"]["validation"]["false_pass_rate"], 0.0)
        self.assertEqual(report["summary"]["workflow"]["completed_rate"], 1.0)


class ValidationEvaluationRunnerTests(unittest.TestCase):
    def test_balanced_pass_fail_report(self) -> None:
        cases = [
            {
                "case_id": "pass-case",
                "inputs": {"case_id": "pass-case"},
                "reference_outputs": {"validation": {"status": "PASS", "error_types": []}},
                "metadata": {"label_status": "VERIFIED"},
            },
            {
                "case_id": "fail-case",
                "inputs": {"case_id": "fail-case"},
                "reference_outputs": {
                    "validation": {"status": "FAIL", "error_types": ["distortions"]}
                },
                "metadata": {"label_status": "VERIFIED"},
            },
        ]
        predictions = [
            {
                "case_id": "pass-case",
                "outputs": {"validation": {"status": "PASS", "error_types": []}},
            },
            {
                "case_id": "fail-case",
                "outputs": {
                    "validation": {"status": "FAIL", "error_types": ["distortions"]}
                },
            },
        ]

        with tempfile.TemporaryDirectory() as directory:
            dataset_path = Path(directory) / "validation_dataset.jsonl"
            prediction_path = Path(directory) / "validation_predictions.jsonl"
            dataset_path.write_text(
                "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n",
                encoding="utf-8",
            )
            prediction_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in predictions) + "\n",
                encoding="utf-8",
            )
            report = evaluate_validation(str(dataset_path), str(prediction_path))

        self.assertEqual(report["summary"]["validation"]["accuracy"], 1.0)
        self.assertEqual(report["summary"]["validation"]["error_detection"]["f1"], 1.0)


if __name__ == "__main__":
    unittest.main()
