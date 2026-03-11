from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "fetch_recent_feeds.sh"


class FetchRecentFeedsTests(unittest.TestCase):
    def test_fetches_multiple_feeds(self) -> None:
        if shutil.which("bash") is None or shutil.which("curl") is None or shutil.which("jq") is None:
            self.skipTest("bash, curl, and jq are required")

        now = datetime.now(timezone.utc)
        recent = now.isoformat(timespec="seconds")
        older = (now - timedelta(hours=72)).isoformat(timespec="seconds")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            feed_dir = tmp_path / "feed"
            feed_dir.mkdir()

            (feed_dir / "gh_first.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "First feed recent article",
                                "url": "https://example.com/1",
                                "updated": recent,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (feed_dir / "gh_second.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "Second feed recent article",
                                "url": "https://example.com/2",
                                "updated": recent,
                            },
                            {
                                "title": "Second feed old article",
                                "url": "https://example.com/3",
                                "updated": older,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            feeds_file = tmp_path / "feeds.md"
            output_file = tmp_path / "raw.json"

            feeds_file.write_text(
                "gh_first 第一条\n"
                "gh_second 第二条\n",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "bash",
                    str(SCRIPT_PATH),
                    "--feeds-file",
                    str(feeds_file),
                    "--output-file",
                    str(output_file),
                    "--api-host",
                    f"file://{tmp_path}",
                ],
                check=True,
            )

            articles = json.loads(output_file.read_text(encoding="utf-8"))

        self.assertEqual(len(articles), 2)
        self.assertEqual({article["mpId"] for article in articles}, {"gh_first", "gh_second"})
        self.assertEqual(
            {article["sourceTitle"] for article in articles},
            {"First feed recent article", "Second feed recent article"},
        )

    def test_tolerates_trailing_commas_and_duplicate_feed_ids(self) -> None:
        if shutil.which("bash") is None or shutil.which("curl") is None or shutil.which("jq") is None:
            self.skipTest("bash, curl, and jq are required")

        now = datetime.now(timezone.utc)
        recent = now.isoformat(timespec="seconds")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            feed_dir = tmp_path / "feed"
            feed_dir.mkdir()

            (feed_dir / "gh_first.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "First deduped article",
                                "url": "https://example.com/first",
                                "updated": recent,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (feed_dir / "gh_second.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "Second comma article",
                                "url": "https://example.com/second",
                                "updated": recent,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            feeds_file = tmp_path / "feeds.md"
            output_file = tmp_path / "raw.json"

            feeds_file.write_text(
                "gh_first 第一条\n"
                "gh_second, 第二条\n"
                "gh_first 重复条目\n",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "bash",
                    str(SCRIPT_PATH),
                    "--feeds-file",
                    str(feeds_file),
                    "--output-file",
                    str(output_file),
                    "--api-host",
                    f"file://{tmp_path}",
                ],
                check=True,
            )

            articles = json.loads(output_file.read_text(encoding="utf-8"))

        self.assertEqual(len(articles), 2)
        by_id = {article["mpId"]: article for article in articles}
        self.assertEqual(set(by_id), {"gh_first", "gh_second"})
        self.assertEqual(by_id["gh_first"]["sourceTitle"], "First deduped article")
        self.assertEqual(by_id["gh_first"]["mpName"], "第一条")
        self.assertEqual(by_id["gh_second"]["sourceTitle"], "Second comma article")
        self.assertEqual(by_id["gh_second"]["mpName"], "第二条")


if __name__ == "__main__":
    unittest.main()
