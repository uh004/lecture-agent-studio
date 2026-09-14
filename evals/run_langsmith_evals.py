from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv
from langsmith import evaluate

from evals.dataset_io import index_predictions, load_jsonl
from evals.evaluators.langsmith_evaluators import (
    make_script_quality_evaluator,
    make_search_quality_evaluator,
    parser_code_evaluator,
    search_decision_evaluator,
    validation_status_evaluator,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LangSmith Lecture Agent 평가 실행")
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--experiment-prefix", default="lecture-agent")
    parser.add_argument("--with-llm-judge", action="store_true")
    parser.add_argument("--judge-model", default=os.getenv("EVAL_JUDGE_MODEL", "gpt-4o-mini"))
    parser.add_argument("--max-concurrency", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    predictions = index_predictions(load_jsonl(args.predictions))

    def target(inputs: dict) -> dict:
        case_id = str(inputs.get("case_id", ""))
        if case_id not in predictions:
            raise KeyError(f"Prediction을 찾을 수 없습니다: {case_id}")
        record = predictions[case_id]
        return record.get("outputs") or record

    evaluators = [
        parser_code_evaluator,
        search_decision_evaluator,
        validation_status_evaluator,
    ]
    if args.with_llm_judge:
        evaluators.extend([
            make_search_quality_evaluator(args.judge_model),
            make_script_quality_evaluator(args.judge_model),
        ])

    results = evaluate(
        target,
        data=args.dataset_name,
        evaluators=evaluators,
        experiment_prefix=args.experiment_prefix,
        max_concurrency=args.max_concurrency,
        metadata={"judge_model": args.judge_model, "llm_judge": args.with_llm_judge},
    )
    print(results)


if __name__ == "__main__":
    main()

