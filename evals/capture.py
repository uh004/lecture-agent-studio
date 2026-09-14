from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from evals.dataset_io import write_jsonl


class NotebookEvalCapture:
    """LangGraph stream의 노드별 상태를 슬라이드 단위 Prediction으로 누적합니다."""

    def __init__(self, pptx_path: str) -> None:
        self.pptx_path = str(pptx_path)
        self.pptx_stem = Path(pptx_path).stem
        self._records: Dict[int, Dict[str, Any]] = {}
        self._workflow: Dict[str, Any] = {}

    def _case_id(self, slide_index: int) -> str:
        return f"{self.pptx_stem}_slide_{slide_index + 1:03d}"

    def _record(self, slide_index: int) -> Dict[str, Any]:
        if slide_index not in self._records:
            self._records[slide_index] = {
                "case_id": self._case_id(slide_index),
                "outputs": {
                    "parser": {},
                    "analysis": {},
                    "search": {},
                    "script": {"generation_history": []},
                    "validation": {"history": []},
                    "media": {},
                },
            }
        return self._records[slide_index]

    def observe(self, node_name: str, state: Dict[str, Any]) -> None:
        if node_name == "parse_ppt":
            for index, slide in enumerate(state.get("slides", []) or []):
                parser_output = {
                    "title": slide.get("title", ""),
                    "text": slide.get("text", ""),
                    "tables": deepcopy(slide.get("tables", [])),
                    "image_count": len(slide.get("images", []) or []),
                    "slide_image_created": bool(slide.get("slide_image")),
                    "extraction_errors": list(slide.get("extraction_errors", []) or []),
                }
                self._record(index)["outputs"]["parser"] = parser_output
            return

        index = int(state.get("slide_index", 0))
        if node_name == "accumulate":
            index -= 1
        if index < 0 or index >= int(state.get("total_slides", index + 1)):
            if node_name == "final_quality_check":
                self._workflow = {
                    "run_id": Path(str(state.get("work_dir", ""))).name,
                    "final_status": state.get("final_status", ""),
                    "final_qa": deepcopy(state.get("final_qa", {})),
                    "errors": list(state.get("errors", []) or []),
                }
            return

        outputs = self._record(index)["outputs"]
        if node_name == "analyze_slide":
            outputs["analysis"] = deepcopy(state.get("slide_analysis", {}))
            outputs["search"].update({
                "needed": bool(state.get("search_needed", False)),
                "tasks": deepcopy(state.get("search_tasks", [])),
            })
        elif node_name == "web_search":
            outputs["search"].update({
                "results": deepcopy(state.get("search_results", [])),
                "evidence": deepcopy(state.get("evidence", [])),
            })
        elif node_name == "generate_script":
            outputs["script"]["generation_history"].append({
                "draft": state.get("script_draft", ""),
                "meta": deepcopy(state.get("script_draft_meta", {})),
                "attempt": int(state.get("validation_attempt", 0)) + 1,
            })
            outputs["script"]["draft"] = state.get("script_draft", "")
        elif node_name == "validate_script":
            validation = deepcopy(state.get("validation_result", {}))
            is_first_validation = not outputs["validation"]["history"]
            outputs["validation"]["history"].append(validation)
            outputs["validation"]["status"] = validation.get("status", "FAIL")
            outputs["validation"]["error_types"] = [
                key
                for key in ("unsupported_claims", "missing_points", "distortions")
                if validation.get(key)
            ]
            if is_first_validation:
                outputs["validation"]["initial_status"] = validation.get("status", "FAIL")
                outputs["validation"]["initial_error_types"] = list(outputs["validation"]["error_types"])
        elif node_name == "accept_script":
            outputs["script"]["final"] = state.get("script_final", "")
            outputs["validation"]["final_status"] = "PASS"
        elif node_name == "mark_validation_failed":
            outputs["script"]["final"] = ""
            outputs["validation"]["final_status"] = "FAIL"
        elif node_name == "tts":
            outputs["media"]["audio_path"] = state.get("audio_path", "")
        elif node_name == "make_video":
            outputs["media"]["video_path"] = state.get("video_path", "")
        elif node_name == "accumulate":
            outputs["media"]["failed"] = index in (state.get("failed_slides", []) or [])

    def records(self) -> List[Dict[str, Any]]:
        records = []
        for index in sorted(self._records):
            record = deepcopy(self._records[index])
            record["outputs"]["workflow"] = deepcopy(self._workflow)
            records.append(record)
        return records

    def write(self, path: str | Path) -> Path:
        return write_jsonl(path, self.records())
