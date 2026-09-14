import tempfile
import unittest
from pathlib import Path

from src.core.runtime import build_initial_state, create_run_directory
from src.core.utils import build_visible_slide_context, reset_slide_runtime
from src.graph import build_lecture_graph
from src.nodes.media import node_final_qa
from src.nodes.parser import validate_parser_state
from src.nodes.script import (
    build_previous_slide_tail,
    build_slide_flow_instruction,
    remove_repetitive_opening,
)
from src.nodes.search import search_router
from src.nodes.validation import (
    build_approved_visual_facts,
    build_validation_message_content,
    build_validation_preflight,
    validation_router,
)


class CoreContractTests(unittest.TestCase):
    def test_visible_context_excludes_notes_links_and_paths(self):
        slide = {
            "title": "테스트",
            "text": "본문",
            "notes": "발표자 노트",
            "links": ["https://example.com"],
            "tables": [],
            "charts": [],
            "shape_texts": [],
            "images": ["embedded.png"],
            "slide_image": "slide.png",
        }
        context = build_visible_slide_context(slide)
        self.assertNotIn("notes", context)
        self.assertNotIn("links", context)
        self.assertNotIn("images", context)
        self.assertNotIn("slide_image", context)
        self.assertEqual(context["embedded_image_count"], 1)

    def test_slide_runtime_reset_preserves_accumulated_results(self):
        state = {
            "slide_analysis": {"old": True},
            "script_final": "old",
            "validation_attempt": 2,
            "all_scripts": ["승인된 Script"],
            "video_paths": ["승인된 영상.mp4"],
        }
        reset_slide_runtime(state)
        self.assertEqual(state["slide_analysis"], {})
        self.assertEqual(state["script_final"], "")
        self.assertEqual(state["validation_attempt"], 0)
        self.assertEqual(state["all_scripts"], ["승인된 Script"])
        self.assertEqual(state["video_paths"], ["승인된 영상.mp4"])

    def test_runtime_builds_unique_run_directory_and_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = create_run_directory("sample.pptx", temp_dir)
            state = build_initial_state("sample.pptx", run_dir, {"speed": 1.0})
            self.assertTrue(run_dir.is_dir())
            self.assertTrue(run_dir.name.startswith("sample_"))
            self.assertEqual(state["work_dir"], str(run_dir.resolve()))
            self.assertEqual(state["lecture_config"]["speed"], 1.0)
            self.assertEqual(state["final_status"], "running")


class RouterAndGraphTests(unittest.TestCase):
    def test_search_router(self):
        task = {
            "claim_to_verify": "LangGraph 상태 관리 방식",
            "purpose": "definition",
            "query": "LangGraph state management official documentation",
            "source_policy": "official_only",
        }
        self.assertEqual(search_router({"search_needed": True, "search_tasks": [task]}), "search")
        self.assertEqual(search_router({"search_needed": False, "search_tasks": [task]}), "skip")
        self.assertEqual(search_router({"search_needed": True, "search_tasks": []}), "skip")

    def test_validation_router(self):
        self.assertEqual(
            validation_router({"validation_result": {"status": "PASS"}}),
            "pass",
        )
        self.assertEqual(
            validation_router({
                "validation_result": {"status": "FAIL"},
                "validation_attempt": 2,
                "max_validation_attempts": 2,
            }),
            "retry",
        )
        self.assertEqual(
            validation_router({
                "validation_result": {"status": "FAIL"},
                "validation_attempt": 3,
                "max_validation_attempts": 2,
            }),
            "exhausted",
        )
        self.assertEqual(
            validation_router({
                "validation_system_error": True,
                "validation_error_attempt": 2,
                "max_validation_error_retries": 1,
            }),
            "system_error",
        )

    def test_graph_contains_v4_nodes(self):
        graph = build_lecture_graph()
        expected = {
            "parse_ppt", "analyze_slide", "web_search", "generate_script",
            "validate_script", "accept_script", "mark_validation_failed",
            "tts", "make_video", "accumulate", "concat", "final_quality_check",
        }
        self.assertTrue(expected.issubset(set(graph.get_graph().nodes)))


class ValidationContractTests(unittest.TestCase):
    def test_visual_facts_are_deduplicated_and_limited(self):
        facts = ["A", "A", "B", "C", "D", "E", "F", "G", "H"]
        self.assertEqual(
            build_approved_visual_facts({"slide_facts": facts}),
            ["A", "B", "C", "D", "E", "F", "G"],
        )

    def test_validation_message_attaches_slide_and_embedded_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            slide_path = root / "slide.png"
            embedded_path = root / "embedded.png"
            slide_path.write_bytes(b"slide")
            embedded_path.write_bytes(b"embedded")
            state = {
                "slide_index": 0,
                "slides": [{
                    "title": "검증",
                    "text": "본문",
                    "notes": "노트",
                    "links": ["https://example.com"],
                    "tables": [],
                    "charts": [],
                    "shape_texts": [],
                    "images": [str(embedded_path)],
                    "slide_image": str(slide_path),
                }],
                "errors": [],
            }
            content = build_validation_message_content(state, {"slide": "visible"}, 0)
            self.assertEqual(len(content), 3)
            self.assertTrue(all(item["image_url"]["detail"] == "high" for item in content[1:]))
            self.assertNotIn("노트", content[0]["text"])
            self.assertNotIn("example.com", content[0]["text"])

    def test_unknown_evidence_id_fails_preflight(self):
        issues = build_validation_preflight(
            {"used_evidence_ids": ["missing"], "external_claims_used": ["외부 주장"]},
            [{"evidence_id": "valid"}],
        )
        self.assertTrue(any("missing" in issue for issue in issues))


class ParserScriptAndQaTests(unittest.TestCase):
    def test_parser_contract(self):
        slide = {
            "index": 0,
            "title": "계약 테스트",
            "text": "본문",
            "notes": "",
            "tables": [],
            "charts": [],
            "images": [],
            "slide_image": "",
            "shape_texts": [],
            "links": [],
            "extraction_errors": [],
        }
        validate_parser_state({"slides": [slide], "total_slides": 1})

    def test_script_flow_helpers(self):
        self.assertNotIn("오늘은", remove_repetitive_opening("오늘은 모델을 살펴봅니다."))
        self.assertIn("중간 슬라이드", build_slide_flow_instruction(1, 3, True))
        self.assertEqual(
            build_previous_slide_tail(["첫 문장입니다. 마지막 문장입니다."]),
            "첫 문장입니다. 마지막 문장입니다.",
        )

    def test_final_qa_without_media_fails(self):
        state = {
            "final_video": "",
            "total_slides": 1,
            "video_paths": [],
            "failed_slides": [0],
            "errors": [],
        }
        node_final_qa(state)
        self.assertEqual(state["final_status"], "failed")
        self.assertFalse(state["final_qa"]["passed"])
        self.assertEqual(state["final_qa"]["missing_slide_numbers"], [1])


if __name__ == "__main__":
    unittest.main()
