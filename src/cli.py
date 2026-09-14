"""Command-line runner for the modular Lecture Agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from evals.capture import NotebookEvalCapture
from src.core.utils import safe_print
from src.service import run_lecture_agent


print = safe_print


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PPTX를 AI 강의 영상으로 변환합니다.")
    parser.add_argument("--pptx", required=True, help="입력 PPTX 경로")
    parser.add_argument("--output-root", default="notebooks/runs", help="실행 폴더를 만들 상위 경로")
    parser.add_argument("--tone", default="에너지가 있으면서도 근거를 정확히 설명하는 전문 강사 톤")
    parser.add_argument(
        "--style",
        default="쉬운 비유를 사용하되 PPT와 Evidence에 없는 사례는 만들지 마세요.",
    )
    parser.add_argument("--target-duration-sec", type=int, default=70)
    parser.add_argument("--voice", default="친절한 튜토리얼")
    parser.add_argument("--speed", type=float, default=1.15)
    parser.add_argument(
        "--no-eval-capture",
        action="store_true",
        help="eval_predictions.jsonl 생성을 생략합니다.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    capture = None if args.no_eval_capture else NotebookEvalCapture(args.pptx)

    def observe(node_name, state):
        if capture is not None:
            capture.observe(node_name, state)
        print(
            f"[{node_name}] slide={state.get('slide_index', 0)}/"
            f"{state.get('total_slides', '?')} "
            f"status={state.get('final_status', 'running')}"
        )

    final_state = run_lecture_agent(
        args.pptx,
        {
            "tone": args.tone,
            "style": args.style,
            "target_duration_sec": args.target_duration_sec,
            "voice": args.voice,
            "speed": args.speed,
        },
        output_root=args.output_root,
        on_node=observe,
    )

    work_dir = Path(final_state["work_dir"])
    if capture is not None:
        prediction_path = capture.write(work_dir / "eval_predictions.jsonl")
        print(f"평가 Prediction: {prediction_path.resolve()}")

    print(f"최종 상태: {final_state.get('final_status')}")
    print(f"최종 영상: {final_state.get('final_video', '')}")
    print(json.dumps(final_state.get("final_qa", {}), ensure_ascii=False, indent=2))
    return 0 if final_state.get("final_status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
