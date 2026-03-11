from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.amap_geocode_wgs84 import build_static_map_url, gcj02_to_wgs84, is_precise_address, run_geocode


FIXTURE_FILE = Path(__file__).parent / "fixtures" / "amap-geocode" / "responses.json"


class AMapGeocodeWgs84Tests(unittest.TestCase):
    def test_build_static_map_url_returns_v3_staticmap_url(self) -> None:
        url = build_static_map_url("test-key", 121.436525, 31.194729)
        self.assertIn("https://restapi.amap.com/v3/staticmap?", url)
        self.assertIn("key=test-key", url)
        self.assertIn("location=121.436525%2C31.194729", url)
        self.assertNotIn("markers=", url)

    def test_gcj02_to_wgs84_returns_reasonable_offset(self) -> None:
        lng, lat = gcj02_to_wgs84(121.473701, 31.230416)
        self.assertAlmostEqual(lng, 121.469177, places=3)
        self.assertAlmostEqual(lat, 31.232342, places=3)

    def test_is_precise_address_rejects_vague_locations(self) -> None:
        self.assertFalse(is_precise_address(""))
        self.assertFalse(is_precise_address("线上"))
        self.assertFalse(is_precise_address("上海市徐汇区，报名后通知具体地点"))
        self.assertFalse(is_precise_address("浦东新区某地"))
        self.assertTrue(is_precise_address("上海市徐汇区漕溪北路398号"))
        self.assertTrue(is_precise_address("上海中心大厦"))

    def test_run_geocode_with_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "activity-structured.json"
            output_path = Path(tmpdir) / "activity-structured-geo.json"
            input_path.write_text(
                json.dumps(
                    [
                        {
                            "activityName": "AI 工作坊",
                            "activityAddress": "上海市徐汇区漕溪北路398号",
                        },
                        {
                            "activityName": "线上分享会",
                            "activityAddress": "",
                        },
                        {
                            "activityName": "模糊地址活动",
                            "activityAddress": "上海市徐汇区，报名后通知具体地点",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            args = Namespace(
                input=str(input_path),
                output=str(output_path),
                amap_key="test-key",
                city_hint_field="",
                fixture_file=str(FIXTURE_FILE),
            )

            result = run_geocode(args)
            self.assertEqual(result[0]["activityGeoStatus"], "ok")
            self.assertEqual(result[1]["activityGeoStatus"], "skipped")
            self.assertEqual(result[2]["activityGeoStatus"], "skipped_vague")
            self.assertIn("activityLongitudeWGS84", result[0])
            self.assertEqual(result[0]["activityStaticMapStatus"], "ok")
            self.assertIn("restapi.amap.com/v3/staticmap", result[0]["activityStaticMapUrl"])
            self.assertEqual(result[1]["activityStaticMapStatus"], "skipped")
            self.assertEqual(result[2]["activityStaticMapStatus"], "skipped_vague")
            self.assertTrue(output_path.exists())


if __name__ == "__main__":
    unittest.main()
