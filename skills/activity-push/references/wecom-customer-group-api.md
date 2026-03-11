# WeCom Customer Group API Notes

This reference supports the `activity-push` skill when pushing to WeCom external customer groups.

Read this file when:
- the user wants to push to 企业微信外部群 instead of robot webhooks
- you need to debug `add_msg_template`, `groupchat/list`, `groupchat/get`, `remind_groupmsg_send`, or `get_groupmsg_send_result`
- you need to explain why a call created a task but did not instantly reach the group

## Core model

The push flow is not:
- create markdown
- call webhook
- group instantly receives content

The push flow is:
1. get an access token with the customer-contact capable secret
2. discover or confirm the target customer-group `chat_id`
3. create a group-message task with `externalcontact/add_msg_template`
4. optionally remind the sender with `externalcontact/remind_groupmsg_send`
5. check task status with `externalcontact/get_groupmsg_send_result`
6. the member still needs to complete or confirm the send inside WeCom

This distinction matters. A successful API call usually means:
- the task was created
- not that the external group already received the content

## Required credentials

Typical variables:

```bash
WE_COM_CORP_ID=wwxxxxxxxxxxxxxxxx
WE_COM_CONTACT_SECRET=xxxxxxxxxxxxxxxx
WE_COM_GROUPMSG_SENDER_USERIDS=zhangsan
WE_COM_TARGET_CHAT_IDS=wrOgQhDgAA...,wrOgQhDgBB...
```

Notes:
- all WeCom push variables are optional at the skill level; they only become required when the user actually wants to execute the push step
- `WE_COM_CONTACT_SECRET` should be the secret that is allowed to call customer-contact endpoints
- `WE_COM_GROUPMSG_SENDER_USERIDS` must contain at least one internal member who will own or send the group message task
- one sender is enough; use commas only when you intentionally want to create tasks for multiple senders
- `WE_COM_TARGET_CHAT_IDS` is the safest targeting method when the exact groups are already known

## API sequence

### 1. Get token

Endpoint:
- `GET /cgi-bin/gettoken`

Purpose:
- obtain `access_token`

Failure patterns:
- wrong `corp_id`
- wrong secret
- secret lacks the needed scope

### 2. Discover groups

Endpoint:
- `POST /cgi-bin/externalcontact/groupchat/list`

Purpose:
- list customer groups owned by the selected members

Important behavior:
- paginated via `next_cursor`
- if the tenant has many groups, you must continue paging until `next_cursor` is empty

Useful follow-up:
- `POST /cgi-bin/externalcontact/groupchat/get`

Use it when:
- you need the group name
- you need member or owner details
- you want to filter by group name keywords instead of sending to every discovered group

## Group-message task creation

Endpoint:
- `POST /cgi-bin/externalcontact/add_msg_template`

Purpose:
- create a customer-contact group-message task

Current skill assumptions:
- `chat_type` is `"group"`
- `sender` is one of `WE_COM_GROUPMSG_SENDER_USERIDS`
- `allow_select` is `false`
- `chat_id_list` is used when the target groups are explicit
- message body uses plain `text.content`

If the API rejects `chat_id_list`:
- do not silently expand the target scope
- inspect the returned payload
- compare the payload against the current official doc for this tenant/version

## Reminder and result

Reminder endpoint:
- `POST /cgi-bin/externalcontact/remind_groupmsg_send`

Result endpoint:
- `POST /cgi-bin/externalcontact/get_groupmsg_send_result`

Operational notes:
- reminders do not send the content by themselves
- result APIs can lag behind task creation
- poll again later if the first status is incomplete or stale

## Why the skill separates Markdown and push text

`activity-structured.md` is for:
- review
- audit
- manual inspection

`activity-push.txt` is for:
- `text.content`
- compact messages that members are more likely to send
- avoiding markdown formatting assumptions in customer-group APIs

## Recommended debugging outputs

Keep these files:
- `wecom-token.json`
- `customer-groups.json`
- `customer-group-details.json`
- `groupmsg-create-result.json`
- `push-result.md`

They help answer:
- did token creation fail?
- which groups were targeted?
- which sender created which task?
- did remind succeed?
- what status came back from the result API?

## Dry-run and fixtures

The bundled CLI supports local replay:
- `--dry-run`
- `--fixture-dir <dir>`

Use it when:
- you want to validate pagination and filtering logic without live credentials
- you need to regression-test the CLI after editing the skill
- you want deterministic outputs for review

Fixture directory used in this repo:
- `/Users/yujian/Code/py/aj-skills/skills/activity-push/tests/fixtures/wecom-push`

## Sources

Official docs used for this reference:
- https://developer.work.weixin.qq.com/document/path/92135
- https://developer.work.weixin.qq.com/document/path/92113
- https://developer.work.weixin.qq.com/document/path/92114
- https://developer.work.weixin.qq.com/document/path/93338

Additional structure cross-checks:
- https://www.apifox.cn/apidoc/docs-site/406014/doc-1776833
- https://pkg.go.dev/github.com/ArtisanCloud/PowerWeChat/v3/src/work/externalContact/message
