from __future__ import annotations

import argparse

from dotenv import load_dotenv
from langsmith import Client

from evals.dataset_io import load_jsonl, verified_cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="검증된 JSONL을 LangSmith Dataset으로 업로드")
    parser.add_argument("--dataset", required=True, help="정답 Dataset JSONL")
    parser.add_argument("--name", required=True, help="LangSmith Dataset 이름")
    parser.add_argument("--description", default="Lecture Agent offline evaluation dataset")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    records = verified_cases(load_jsonl(args.dataset))
    if not records:
        raise ValueError("VERIFIED 라벨이 있는 평가 Case가 없습니다.")

    client = Client()
    dataset = client.create_dataset(dataset_name=args.name, description=args.description)
    examples = [
        {
            "inputs": {**(record.get("inputs") or {}), "case_id": record["case_id"]},
            "outputs": record.get("reference_outputs") or {},
            "metadata": record.get("metadata") or {},
        }
        for record in records
    ]
    client.create_examples(dataset_id=dataset.id, examples=examples)
    print(f"LangSmith Dataset 생성 완료: {dataset.name} ({len(examples)} cases)")


if __name__ == "__main__":
    main()

