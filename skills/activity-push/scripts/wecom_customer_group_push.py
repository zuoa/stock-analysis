#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib import parse, request


API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create WeCom customer-group mass-message tasks for external groups."
    )
    parser.add_argument("--corp-id", required=True, help="WeCom corp ID.")
    parser.add_argument("--contact-secret", required=True, help="Customer contact secret.")
    parser.add_argument("--sender-userids", required=True, help="Comma-separated sender userids.")
    parser.add_argument("--message-file", required=True, help="Path to push text file.")
    parser.add_argument("--out-dir", required=True, help="Output directory.")
    parser.add_argument("--target-chat-ids", default="", help="Comma-separated explicit chat IDs.")
    parser.add_argument(
        "--chat-name-keywords",
        default="",
        help="Comma-separated customer-group name keywords. Optional; used only when chat IDs are not explicit.",
    )
    parser.add_argument(
        "--status-filter",
        type=int,
        default=0,
        help="Customer group status filter for groupchat/list. Default 0.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="Page size for groupchat/list. Default 1000.",
    )
    parser.add_argument(
        "--poll-delay-seconds",
        type=float,
        default=1.0,
        help="Delay before querying groupmsg send result. Default 1s.",
    )
    parser.add_argument(
        "--skip-remind",
        action="store_true",
        help="Skip remind_groupmsg_send after task creation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send live requests. Requires --fixture-dir for deterministic responses.",
    )
    parser.add_argument(
        "--fixture-dir",
        default="",
        help="Directory containing canned JSON responses for dry-run and tests.",
    )
    return parser.parse_args()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def split_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def mask_secret(value: str) -> str:
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-3:]}"


class ApiClient:
    def __init__(self, fixture_dir: Optional[Path] = None, dry_run: bool = False) -> None:
        self.fixture_dir = fixture_dir
        self.dry_run = dry_run
        self.create_counter = 0

    def get(self, url: str) -> Dict[str, Any]:
        if self.fixture_dir:
            return self._fixture_get(url)
        if self.dry_run:
            raise RuntimeError("dry-run requires --fixture-dir")
        req = request.Request(url, headers={"Accept": "application/json", "User-Agent": "activity-push/1.0"})
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.fixture_dir:
            return self._fixture_post(url, payload)
        if self.dry_run:
            raise RuntimeError("dry-run requires --fixture-dir")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "activity-push/1.0"},
        )
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _fixture_get(self, url: str) -> Dict[str, Any]:
        parsed = parse.urlparse(url)
        if parsed.path.endswith("/gettoken"):
            return self._read_fixture("gettoken.json")
        raise RuntimeError(f"no fixture for GET {url}")

    def _fixture_post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        parsed = parse.urlparse(url)
        endpoint = parsed.path.split("/")[-1]
        if endpoint == "list":
            cursor = str(payload.get("cursor", ""))
            filename = "groupchat_list_page1.json" if not cursor else f"groupchat_list_{cursor}.json"
            return self._read_fixture(filename)
        if endpoint == "get":
            chat_id = str(payload.get("chat_id", ""))
            return self._read_fixture(f"groupchat_get_{chat_id}.json")
        if endpoint == "add_msg_template":
            self.create_counter += 1
            return self._read_fixture(f"add_msg_template_{self.create_counter}.json")
        if endpoint == "remind_groupmsg_send":
            msgid = str(payload.get("msgid", ""))
            return self._read_fixture(f"remind_groupmsg_send_{msgid}.json")
        if endpoint == "get_groupmsg_send_result":
            msgid = str(payload.get("msgid", ""))
            userid = str(payload.get("userid", ""))
            return self._read_fixture(f"get_groupmsg_send_result_{userid}_{msgid}.json")
        raise RuntimeError(f"no fixture for POST {url} payload={json.dumps(payload, ensure_ascii=False)}")

    def _read_fixture(self, filename: str) -> Dict[str, Any]:
        if not self.fixture_dir:
            raise RuntimeError("fixture_dir is not configured")
        path = self.fixture_dir / filename
        if not path.exists():
            raise RuntimeError(f"fixture not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))


def require_ok(payload: Dict[str, Any], action: str) -> Dict[str, Any]:
    if payload.get("errcode") != 0:
        raise RuntimeError(f"{action} failed: {json.dumps(payload, ensure_ascii=False)}")
    return payload


def get_access_token(client: ApiClient, corp_id: str, secret: str) -> Dict[str, Any]:
    url = f"{API_BASE}/gettoken?corpid={parse.quote(corp_id)}&corpsecret={parse.quote(secret)}"
    return require_ok(client.get(url), "gettoken")


def list_group_chats(client: ApiClient, access_token: str, owner_userids: List[str], status_filter: int, page_size: int) -> Dict[str, Any]:
    url = f"{API_BASE}/externalcontact/groupchat/list?access_token={parse.quote(access_token)}"
    cursor = ""
    pages: List[Dict[str, Any]] = []
    groups: List[Dict[str, Any]] = []

    while True:
        payload: Dict[str, Any] = {
            "status_filter": status_filter,
            "owner_filter": {"userid_list": owner_userids},
            "limit": page_size,
        }
        if cursor:
            payload["cursor"] = cursor
        result = require_ok(client.post(url, payload), "groupchat/list")
        pages.append(result)
        groups.extend(result.get("group_chat_list", []))
        cursor = result.get("next_cursor", "")
        if not cursor:
            break

    return {"pages": pages, "group_chat_list": groups}


def get_group_chat_detail(client: ApiClient, access_token: str, chat_id: str) -> Dict[str, Any]:
    url = f"{API_BASE}/externalcontact/groupchat/get?access_token={parse.quote(access_token)}"
    result = require_ok(client.post(url, {"chat_id": chat_id}), f"groupchat/get:{chat_id}")
    return result


def filter_chat_ids(
    client: ApiClient,
    access_token: str,
    chat_ids: List[str],
    chat_name_keywords: List[str],
) -> Dict[str, Any]:
    if not chat_name_keywords:
        return {"chat_ids": chat_ids, "details": []}

    lowered_keywords = [item.lower() for item in chat_name_keywords]
    matched_ids: List[str] = []
    details: List[Dict[str, Any]] = []
    for chat_id in chat_ids:
        detail = get_group_chat_detail(client, access_token, chat_id)
        details.append(detail)
        group_chat = detail.get("group_chat", {})
        name = str(group_chat.get("name", "")).lower()
        if any(keyword in name for keyword in lowered_keywords):
            matched_ids.append(chat_id)
    return {"chat_ids": matched_ids, "details": details}


def create_group_msg_task(client: ApiClient, access_token: str, sender: str, chat_ids: List[str], text_content: str) -> Dict[str, Any]:
    url = f"{API_BASE}/externalcontact/add_msg_template?access_token={parse.quote(access_token)}"
    payload = {
        "chat_type": "group",
        "sender": sender,
        "allow_select": False,
        "chat_id_list": chat_ids,
        "text": {"content": text_content},
    }
    return client.post(url, payload)


def remind_groupmsg_send(client: ApiClient, access_token: str, msgid: str) -> Dict[str, Any]:
    url = f"{API_BASE}/externalcontact/remind_groupmsg_send?access_token={parse.quote(access_token)}"
    return client.post(url, {"msgid": msgid})


def get_groupmsg_send_result(client: ApiClient, access_token: str, msgid: str, userid: str) -> Dict[str, Any]:
    url = f"{API_BASE}/externalcontact/get_groupmsg_send_result?access_token={parse.quote(access_token)}"
    return client.post(url, {"msgid": msgid, "userid": userid})


def build_push_result(rows: Iterable[Dict[str, Any]]) -> str:
    lines = [
        "# Push Result",
        "",
        "| sender | msgid | status | note |",
        "|---|---|---|---|",
    ]
    for row in rows:
        note = json.dumps(row.get("note", {}), ensure_ascii=False)
        lines.append(f"| {row.get('sender','')} | {row.get('msgid','-')} | {row.get('status','')} | {note} |")
    return "\n".join(lines) + "\n"


def run_push(args: argparse.Namespace) -> Dict[str, Any]:
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    token_path = out_dir / "wecom-token.json"
    group_list_path = out_dir / "customer-groups.json"
    group_detail_path = out_dir / "customer-group-details.json"
    task_result_path = out_dir / "groupmsg-create-result.json"
    push_result_path = out_dir / "push-result.md"

    sender_userids = split_csv(args.sender_userids)
    explicit_chat_ids = split_csv(args.target_chat_ids)
    chat_name_keywords = split_csv(args.chat_name_keywords)
    text_content = Path(args.message_file).expanduser().read_text(encoding="utf-8").strip()
    if not text_content:
        raise RuntimeError("message file is empty")

    fixture_dir = Path(args.fixture_dir).expanduser().resolve() if args.fixture_dir else None
    client = ApiClient(fixture_dir=fixture_dir, dry_run=args.dry_run)

    token_payload = get_access_token(client, args.corp_id, args.contact_secret)
    write_json(token_path, {**token_payload, "masked_secret": mask_secret(args.contact_secret), "dry_run": bool(args.dry_run)})
    access_token = token_payload["access_token"]

    if explicit_chat_ids:
        discovered = {"group_chat_list": [{"chat_id": item} for item in explicit_chat_ids], "pages": []}
        chat_ids = explicit_chat_ids
        details: List[Dict[str, Any]] = []
    else:
        discovered = list_group_chats(client, access_token, sender_userids, args.status_filter, args.page_size)
        base_chat_ids = [item.get("chat_id", "") for item in discovered.get("group_chat_list", []) if item.get("chat_id")]
        filtered = filter_chat_ids(client, access_token, base_chat_ids, chat_name_keywords)
        chat_ids = filtered["chat_ids"]
        details = filtered["details"]

    write_json(
        group_list_path,
        {
            "chat_ids": chat_ids,
            "source": "explicit" if explicit_chat_ids else "groupchat/list",
            "group_chat_list": discovered.get("group_chat_list", []),
            "chat_name_keywords": chat_name_keywords,
            "dry_run": bool(args.dry_run),
        },
    )
    if details:
        write_json(group_detail_path, details)

    if not chat_ids:
        write_json(task_result_path, [])
        rows = [{"sender": sender, "msgid": "-", "status": "skipped", "note": {"reason": "no target chat ids"}} for sender in sender_userids]
        write_text(push_result_path, build_push_result(rows))
        return {"chat_ids": chat_ids, "rows": rows}

    task_results: List[Dict[str, Any]] = []
    push_rows: List[Dict[str, Any]] = []

    for sender in sender_userids:
        result = create_group_msg_task(client, access_token, sender, chat_ids, text_content)
        task_results.append({"sender": sender, "create_result": result})
        msgid = result.get("msgid", "")

        if result.get("errcode") != 0 or not msgid:
            push_rows.append({"sender": sender, "msgid": "-", "status": "failed", "note": result})
            continue

        remind_result: Optional[Dict[str, Any]] = None
        if not args.skip_remind:
            remind_result = remind_groupmsg_send(client, access_token, msgid)

        time.sleep(max(args.poll_delay_seconds, 0))
        result_payload = get_groupmsg_send_result(client, access_token, msgid, sender)
        push_rows.append(
            {
                "sender": sender,
                "msgid": msgid,
                "status": "created",
                "note": {"create": result, "remind": remind_result, "result": result_payload},
            }
        )

    write_json(task_result_path, task_results)
    write_text(push_result_path, build_push_result(push_rows))
    return {"chat_ids": chat_ids, "rows": push_rows}


def main() -> int:
    args = parse_args()
    run_push(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
