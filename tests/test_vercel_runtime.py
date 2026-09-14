import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pptx import Presentation

from src.core.utils import render_slide_fallback
from src.infrastructure.job_store import JobStore
from src.infrastructure.object_storage import ObjectStorage
from src.nodes.parser import node_parse_ppt


class VercelRuntimeAdapterTests(unittest.TestCase):
    def test_memory_job_store_round_trip(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            store = JobStore()
            self.assertFalse(store.is_durable)
            created = store.create("job-1", {"status": "pending"})
            self.assertEqual(created["status"], "pending")

            updated = store.update("job-1", status="running", current_slide=1)
            self.assertEqual(updated["status"], "running")
            self.assertEqual(store.get("job-1")["current_slide"], 1)

    def test_local_object_storage_keeps_file(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            storage = ObjectStorage()
            with tempfile.TemporaryDirectory() as directory:
                video = Path(directory) / "video.mp4"
                video.write_bytes(b"not-empty")
                result = storage.publish_video(video, "job-1")
                self.assertEqual(result["storage"], "local")
                self.assertEqual(Path(result["url"]), video.resolve())

    def test_fallback_slide_renderer_creates_full_hd_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "slide.png"
            rendered = render_slide_fallback(
                title="모델 모니터링",
                body_texts=["데이터 변화와 성능을 지속적으로 확인합니다."],
                tables=[[['항목', '설명'], ['성능', '정확도 확인']]],
                images=[],
                output_path=str(output),
            )
            self.assertEqual(Path(rendered), output)
            self.assertTrue(output.exists())
            with Image.open(output) as image:
                self.assertEqual(image.size, (1920, 1080))

    def test_parser_falls_back_when_office_renderer_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pptx_path = root / "sample.pptx"
            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[1])
            slide.shapes.title.text = "Vercel 슬라이드"
            slide.placeholders[1].text = "시스템 렌더러가 없어도 이미지가 생성됩니다."
            presentation.save(pptx_path)

            state = {
                "pptx_path": str(pptx_path),
                "work_dir": str(root / "work"),
                "lecture_config": {},
            }
            with patch(
                "src.nodes.parser.export_slide_as_png",
                side_effect=RuntimeError("soffice unavailable"),
            ):
                result = node_parse_ppt(state)

            rendered = Path(result["slides"][0]["slide_image"])
            self.assertTrue(rendered.exists())
            self.assertEqual(result["slides"][0]["extraction_errors"], [])


if __name__ == "__main__":
    unittest.main()
