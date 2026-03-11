from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw, ImageFont

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.render_activity_image import build_meta_lines, draw_qr_block, font_candidates, has_coordinates, run_render


class RenderActivityImageTests(unittest.TestCase):
    def tearDown(self) -> None:
        font_candidates.cache_clear()

    def test_font_candidates_accept_env_override_on_linux(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            custom_font = tmp_path / "custom.ttf"
            custom_font.write_bytes(b"")

            with (
                mock.patch.dict(
                    "os.environ",
                    {"ACTIVITY_PUSH_FONT_REGULAR_PATH": str(custom_font)},
                    clear=False,
                ),
                mock.patch("scripts.render_activity_image.platform.system", return_value="Linux"),
                mock.patch("scripts.render_activity_image.shutil.which", return_value=None),
            ):
                self.assertEqual(font_candidates(False)[0], str(custom_font))

    def test_run_render_generates_png_for_activity_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            map_path = tmp_path / "map.png"
            Image.new("RGB", (600, 400), "#BFD7EA").save(map_path)

            input_path = tmp_path / "activity-structured-geo.json"
            output_path = tmp_path / "activity-summary.png"
            input_path.write_text(
                json.dumps(
                    [
                        {
                            "activityName": "AI 工作坊",
                            "activityType": "工作坊",
                            "activityAddress": "上海市徐汇区漕溪北路398号",
                            "activityStartTime": "2026-03-12 14:00",
                            "activityEndTime": "2026-03-12 17:00",
                            "activityLimitNum": "50",
                            "activityDescription": "面向产品和工程团队，集中讨论 AI 应用落地与评估方法。",
                            "activityLongitudeGCJ02": 121.436525,
                            "activityLatitudeGCJ02": 31.194729,
                            "sourceMpName": "某公众号",
                            "sourceTitle": "AI 工作坊报名通知",
                            "sourceUrl": "https://example.com/post/1",
                            "activityStaticMapUrl": map_path.as_uri(),
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            run_render(
                Namespace(
                    input=str(input_path),
                    output=str(output_path),
                    title="活动情报速递",
                    subtitle="2026-03-11",
                    watermark="潮匠里",
                    width=1280,
                    download_timeout=1.0,
                )
            )

            self.assertTrue(output_path.exists())
            with Image.open(output_path) as rendered:
                self.assertEqual(rendered.size[0], 1280)
                self.assertGreater(rendered.size[1], 400)

    def test_build_meta_lines_omits_missing_values(self) -> None:
        image = Image.new("RGB", (1280, 720), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        lines = build_meta_lines(
            {
                "activityType": "闭门会",
                "activityDescription": "只保留已有字段",
                "activityScore": 92,
                "activityScoreReason": "主题和目标用户高度匹配",
            },
            draw,
            font,
            600,
        )

        rendered = "\n".join(lines)
        self.assertIn("类型：", rendered)
        self.assertIn("说明：", rendered)
        self.assertNotIn("时间：", rendered)
        self.assertNotIn("地点：", rendered)
        self.assertNotIn("人数：", rendered)
        self.assertNotIn("评分：", rendered)
        self.assertNotIn("未说明", rendered)
        self.assertNotIn("待补充", rendered)

    def test_has_coordinates_requires_both_lng_and_lat(self) -> None:
        self.assertFalse(has_coordinates({}))
        self.assertFalse(has_coordinates({"activityLongitudeGCJ02": 121.4}))
        self.assertFalse(has_coordinates({"activityLatitudeGCJ02": 31.1}))
        self.assertFalse(has_coordinates({"activityLongitudeGCJ02": "abc", "activityLatitudeGCJ02": 31.1}))
        self.assertTrue(has_coordinates({"activityLongitudeGCJ02": 121.4, "activityLatitudeGCJ02": 31.1}))

    def test_draw_qr_block_uses_neutral_colors(self) -> None:
        image = Image.new("RGB", (500, 220), "white")
        draw = ImageDraw.Draw(image)
        fonts = {
            "section": ImageFont.load_default(),
            "small": ImageFont.load_default(),
        }

        height = draw_qr_block(image, draw, "https://example.com/post/1", 20, 20, fonts)

        self.assertEqual(height, 112)
        self.assertNotEqual(image.getpixel((24, 76)), (184, 92, 56))

    def test_run_render_generates_empty_state_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "activity-structured-geo.json"
            output_path = tmp_path / "activity-summary-empty.png"
            input_path.write_text("[]", encoding="utf-8")

            run_render(
                Namespace(
                    input=str(input_path),
                    output=str(output_path),
                    title="活动情报速递",
                    subtitle="",
                    watermark="潮匠里",
                    width=1280,
                    download_timeout=1.0,
                )
            )

            self.assertTrue(output_path.exists())
            with Image.open(output_path) as rendered:
                self.assertEqual(rendered.size[0], 1280)
                self.assertGreater(rendered.size[1], 250)


if __name__ == "__main__":
    unittest.main()
