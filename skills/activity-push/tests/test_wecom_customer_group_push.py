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

from scripts.wecom_customer_group_push import run_push


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "wecom-push"


class WecomCustomerGroupPushTests(unittest.TestCase):
    def test_run_push_with_fixtures_and_name_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out"
            message_file = Path(tmpdir) / "activity-push.txt"
            message_file.write_text("活动情报速递\n\n1. AI 工作坊", encoding="utf-8")

            args = Namespace(
                corp_id="ww-test",
                contact_secret="secret-test",
                sender_userids="zhangsan,lisi",
                message_file=str(message_file),
                out_dir=str(out_dir),
                target_chat_ids="",
                chat_name_keywords="活动",
                status_filter=0,
                page_size=1000,
                poll_delay_seconds=0.0,
                skip_remind=False,
                dry_run=True,
                fixture_dir=str(FIXTURE_DIR),
            )

            result = run_push(args)

            self.assertEqual(result["chat_ids"], ["chat-1"])
            self.assertTrue((out_dir / "wecom-token.json").exists())
            self.assertTrue((out_dir / "customer-groups.json").exists())
            self.assertTrue((out_dir / "customer-group-details.json").exists())
            self.assertTrue((out_dir / "groupmsg-create-result.json").exists())
            self.assertTrue((out_dir / "push-result.md").exists())

            push_md = (out_dir / "push-result.md").read_text(encoding="utf-8")
            self.assertIn("zhangsan", push_md)
            self.assertIn("msg-001", push_md)
            self.assertIn("lisi", push_md)
            self.assertIn("msg-002", push_md)

            groups = json.loads((out_dir / "customer-groups.json").read_text(encoding="utf-8"))
            self.assertEqual(groups["chat_ids"], ["chat-1"])
            self.assertEqual(len(groups["group_chat_list"]), 2)

    def test_run_push_with_explicit_chat_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out"
            message_file = Path(tmpdir) / "activity-push.txt"
            message_file.write_text("活动情报速递\n\n无新增活动", encoding="utf-8")

            args = Namespace(
                corp_id="ww-test",
                contact_secret="secret-test",
                sender_userids="zhangsan",
                message_file=str(message_file),
                out_dir=str(out_dir),
                target_chat_ids="chat-explicit-1,chat-explicit-2",
                chat_name_keywords="",
                status_filter=0,
                page_size=1000,
                poll_delay_seconds=0.0,
                skip_remind=True,
                dry_run=True,
                fixture_dir=str(FIXTURE_DIR),
            )

            result = run_push(args)
            self.assertEqual(result["chat_ids"], ["chat-explicit-1", "chat-explicit-2"])
            push_md = (out_dir / "push-result.md").read_text(encoding="utf-8")
            self.assertIn("created", push_md)


if __name__ == "__main__":
    unittest.main()
