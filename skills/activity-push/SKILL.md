---
name: activity-push
description: Extracts activity information from WeChat article feeds, lets the model judge whether each article is truly an activity by reading the article semantics, writes raw/activity/structured JSON files, renders reviewable Markdown plus push-ready text, and sends updates to WeCom external customer groups through the customer-contact/customer-group API workflow instead of webhook robots. Use this skill whenever the user mentions 公众号 feeds, 活动提取, 活动报名信息, 企业微信群外部群, 客户联系群发, 客户群 API, feed-to-activity workflows, or wants a repeatable bash/curl pipeline that reads feeds.md and emits raw.json / activity.json / activity-structured.json / activity-structured.md / activity-push.txt / push-result.md.
---

# Activity Push Skill

用于从公众号文章源中筛选活动类文章，提取结构化活动信息，并通过企业微信客户联系/客户群 API 推送到外部客户群。

这个 skill 适合以下任务：
- “根据 feeds.md 拉取最近 24 小时公众号文章并筛活动”
- “把活动文章提取成结构化 JSON”
- “把活动信息整理成适合外部群发送的内容”
- “按客户联系/客户群 API 推送到企业微信外部群”

## Why this skill

参考 Claude 的 skill 最佳实践，这个 skill 将工作拆成两层：
- `SKILL.md` 负责触发条件、判断标准、步骤、质量要求和异常处理
- 所有实际抓取与推送动作都用 bash + `curl` + `jq` 执行
- “这是不是活动”由模型阅读文章后做语义判断，不用关键字脚本筛选
- 外部群推送走客户联系群发任务，不再走 webhook 机器人
- 客户群 API 的复杂细节下沉到脚本和参考文档

这样做的好处是：
- 避免把“活动判断”硬编码成脆弱关键字规则
- 保持执行动作可审计，所有请求都能落回 bash 和 `curl`
- 输出路径和文件格式稳定
- 区分“审阅用 Markdown”和“API 发送用纯文本”，避免消息体格式不兼容
- 用户以后只要给 `feeds.md`、`.env` 和执行目录，就能复用整条链路

## Compatibility

默认依赖这些命令：
- `bash`
- `curl`
- `jq`
- `date`
- `awk`
- `sed`

如果缺少 `jq`，应先明确告诉用户当前环境不满足 skill 依赖，不要改用 Python 兜底。

复杂推送逻辑使用：
- [`wecom_customer_group_push.py`](/Users/yujian/Code/py/aj-skills/skills/activity-push/scripts/wecom_customer_group_push.py)

复杂 API 说明见：
- [`wecom-customer-group-api.md`](/Users/yujian/Code/py/aj-skills/skills/activity-push/references/wecom-customer-group-api.md)

使用规则：
- `SKILL.md` 先给出主流程
- 只有在执行第 6 步、调试客户群 API、解释字段假设时，才去读 `references/wecom-customer-group-api.md`

## Required Inputs

执行前确认以下输入存在：
- 执行目录 `EXEC_DIR`，默认使用当前工作目录
- `~/.aj-skills/.env`
- `feeds.md`

`~/.aj-skills/.env` 建议包含这些变量：

```bash
MP_API_HOST=...
MP_API_KEY=...
WE_COM_CORP_ID=wwxxxxxxxxxxxxxxxx
WE_COM_CONTACT_SECRET=xxxxxxxxxxxxxxxx
WE_COM_GROUPMSG_SENDER_USERIDS=zhangsan,lisi
WE_COM_TARGET_CHAT_IDS=wrOgQhDgAA...,wrOgQhDgBB...
WE_COM_TARGET_CHAT_NAME_KEYWORDS=活动,闭门会
```

其中：
- `MP_API_HOST`：必填
- `MP_API_KEY`：可选；feed 接口需要鉴权时再提供
- `WE_COM_CORP_ID`：外部群推送必填
- `WE_COM_CONTACT_SECRET`：外部群推送必填；应使用客户联系 secret，或官方允许的可调用应用 secret
- `WE_COM_GROUPMSG_SENDER_USERIDS`：外部群推送建议提供；表示哪些成员将收到群发任务并负责确认发送
- `WE_COM_TARGET_CHAT_IDS`：可选；若已知目标客户群 chat_id，优先显式指定
- `WE_COM_TARGET_CHAT_NAME_KEYWORDS`：可选；已知 chat_id 不全时，可让 CLI 基于群名关键字二次过滤

`feeds.md` 约定：
- 每行一个公众号
- 第一列是公众号 `MP_ID`
- 后续内容视为公众号名称
- 空行和 `#` 注释行会被忽略

示例：

```text
gh_1234567890 科技早知道
gh_abcdef123456 AI 产品观察
```

## Default Workflow

按下面顺序执行，不要跳步：

### 1. 预检环境

```bash
EXEC_DIR="${EXEC_DIR:-$PWD}"
ENV_FILE="${HOME}/.aj-skills/.env"
FEEDS_FILE="${EXEC_DIR}/feeds.md"
TODAY="$(date +%Y%m%d)"
OUT_DIR="${EXEC_DIR}/${TODAY}"

test -f "${ENV_FILE}" || { echo "缺少 ${ENV_FILE}"; exit 1; }
test -f "${FEEDS_FILE}" || { echo "缺少 ${FEEDS_FILE}"; exit 1; }
command -v curl >/dev/null || { echo "缺少 curl"; exit 1; }
command -v jq >/dev/null || { echo "缺少 jq"; exit 1; }

set -a
source "${ENV_FILE}"
set +a

test -n "${MP_API_HOST}" || { echo "缺少 MP_API_HOST"; exit 1; }
test -n "${WE_COM_CORP_ID:-}" || { echo "缺少 WE_COM_CORP_ID"; exit 1; }
test -n "${WE_COM_CONTACT_SECRET:-}" || { echo "缺少 WE_COM_CONTACT_SECRET"; exit 1; }
test -n "${WE_COM_GROUPMSG_SENDER_USERIDS:-}" || { echo "缺少 WE_COM_GROUPMSG_SENDER_USERIDS"; exit 1; }

mkdir -p "${OUT_DIR}"
```

检查项：
- `~/.aj-skills/.env` 是否存在
- `MP_API_HOST` / `WE_COM_CORP_ID` / `WE_COM_CONTACT_SECRET` / `WE_COM_GROUPMSG_SENDER_USERIDS` 是否存在
- `MP_API_KEY` 是否存在取决于 feed 接口是否需要鉴权
- `WE_COM_TARGET_CHAT_IDS` 可选；未提供时可用客户群列表接口发现目标群
- `feeds.md` 是否存在且至少包含一个公众号

注意：
- 不要在回复里泄露完整密钥
- 只显示 secret 的掩码或目标群数量

### 2. 拉取 feed 并生成 `raw.json`

```bash
CUTOFF_EPOCH="$(date -v-24H +%s 2>/dev/null || date -d '24 hours ago' +%s)"
RAW_TMP_DIR="$(mktemp -d)"

parse_epoch() {
  local raw="${1:-}"
  local normalized=""
  local epoch=""

  test -n "${raw}" || { echo 0; return; }

  # 把 +08:00 规范成 +0800，便于 BSD date 解析
  normalized="$(printf '%s' "${raw}" | sed -E 's/([+-][0-9]{2}):([0-9]{2})$/\1\2/')"

  # macOS / BSD date
  for fmt in \
    "%Y-%m-%dT%H:%M:%S%z" \
    "%Y-%m-%dT%H:%M%z" \
    "%Y-%m-%d %H:%M:%S%z" \
    "%Y-%m-%d %H:%M%z" \
    "%Y-%m-%dT%H:%M:%SZ" \
    "%Y-%m-%dT%H:%MZ" \
    "%Y-%m-%d %H:%M:%S" \
    "%Y-%m-%d %H:%M" \
    "%Y/%m/%d %H:%M:%S" \
    "%Y/%m/%d %H:%M" \
    "%Y-%m-%d" \
    "%Y/%m/%d"
  ; do
    epoch="$(date -j -f "${fmt}" "${normalized}" +%s 2>/dev/null)" && {
      echo "${epoch}"
      return
    }
  done

  # GNU date
  epoch="$(date -d "${raw}" +%s 2>/dev/null)" && {
    echo "${epoch}"
    return
  }
  epoch="$(date -d "${normalized}" +%s 2>/dev/null)" && {
    echo "${epoch}"
    return
  }

  echo 0
}

while IFS= read -r line; do
  case "${line}" in
    ""|\#*) continue ;;
  esac

  MP_ID="$(printf '%s\n' "${line}" | awk '{print $1}')"
  MP_NAME="$(printf '%s\n' "${line}" | cut -d' ' -f2-)"
  FEED_URL="${MP_API_HOST%/}/feed/${MP_ID}.json"
  OUT_FILE="${RAW_TMP_DIR}/${MP_ID}.json"

  CURL_ARGS=(-fsSL -H "Accept: application/json")
  if [ -n "${MP_API_KEY:-}" ]; then
    CURL_ARGS+=(
      -H "Authorization: Bearer ${MP_API_KEY}"
      -H "X-API-Key: ${MP_API_KEY}"
    )
  fi

  if ! curl "${CURL_ARGS[@]}" "${FEED_URL}" -o "${OUT_FILE}"; then
    echo "warning: 拉取失败 ${MP_ID} ${MP_NAME}" >&2
    continue
  fi

  JSONL_FILE="${RAW_TMP_DIR}/${MP_ID}.jsonl"

  jq -c \
    --arg mpId "${MP_ID}" \
    --arg mpName "${MP_NAME}" \
    --arg feedUrl "${FEED_URL}" '
      def article_list:
        if type == "array" then .
        elif .items? then .items
        elif .articles? then .articles
        elif .entries? then .entries
        elif (.data? | type) == "array" then .data
        elif (.data? | type) == "object" then (.data.items // .data.articles // .data.entries // [])
        else []
        end;

      [
        article_list[]
        | . + {
            mpId: $mpId,
            mpName: $mpName,
            feedUrl: $feedUrl,
            sourceUpdated: (.updated // .publish_time // .published // .pubDate // ""),
            sourceUrl: (.url // .link // .permalink // ""),
            sourceTitle: (.title // .name // ""),
            sourceSummary: (.summary // .description // .excerpt // .digest // "")
          }
      ][]
    ' "${OUT_FILE}" > "${JSONL_FILE}"

  : > "${OUT_FILE}.filtered"
  while IFS= read -r article_json; do
    UPDATED_RAW="$(printf '%s' "${article_json}" | jq -r '.sourceUpdated // empty')"
    UPDATED_EPOCH="$(parse_epoch "${UPDATED_RAW}")"
    if [ "${UPDATED_EPOCH}" -ge "${CUTOFF_EPOCH}" ] 2>/dev/null; then
      printf '%s\n' "${article_json}" >> "${OUT_FILE}.filtered"
    fi
  done < "${JSONL_FILE}"
done < "${FEEDS_FILE}"

if find "${RAW_TMP_DIR}" -name '*.filtered' -print -quit | grep -q .; then
  jq -s '.' "${RAW_TMP_DIR}"/*.filtered | jq -s 'add // []' > "${OUT_DIR}/raw.json"
else
  printf '[]\n' > "${OUT_DIR}/raw.json"
fi
```

默认输出目录：
- `{EXEC_DIR}/{yyyyMMdd}/raw.json`
- `{EXEC_DIR}/{yyyyMMdd}/activity.json`
- `{EXEC_DIR}/{yyyyMMdd}/activity-structured.json`
- `{EXEC_DIR}/{yyyyMMdd}/activity-structured.md`
- `{EXEC_DIR}/{yyyyMMdd}/activity-push.txt`
- `{EXEC_DIR}/{yyyyMMdd}/customer-groups.json`
- `{EXEC_DIR}/{yyyyMMdd}/groupmsg-create-result.json`
- `{EXEC_DIR}/{yyyyMMdd}/push-result.md`

注意：
- 不要再用 `jq fromdateiso8601` 解析带时区偏移的时间；它对 `+08:00` 这类格式并不可靠。
- 当前推荐做法是让 `jq` 只负责拆出文章，再由 bash 的 `date` 解析时间。
- 如果某个 feed 的 `updated` 仍然无法被 `date` 解析，保留已抓取结果并在回复中明确说明该 feed 的时间格式不兼容当前 bash 过滤逻辑。
- 如果没有任何文章，也要生成 `raw.json`，内容必须是 `[]`。
- 如果公开 feed 不需要鉴权，应允许在未设置 `MP_API_KEY` 的情况下继续执行。
- 如果接口返回 401 / 403，再明确提示用户补充 `MP_API_KEY`。

### 3. 由模型判断哪些文章真的是活动，并生成 `activity.json`

这里不要做关键字筛选。你要直接阅读 `raw.json` 里的文章内容，按语义判断。

判定为“活动”的标准是：
- 文章的主要目的，是邀请用户在某个时间段参与一个具体安排，而不是单纯传递资讯
- 文中存在明确或隐含的参与动作，例如报名、预约、到场、线上进入、提交申请、加入议程
- 文章围绕一次具体事件展开，通常能对应到时间、地点、参与方式、人数、议程、对象或组织方中的若干项
- 即便没有写出“活动”二字，只要本质上是在组织一次可参与的时间性事件，也算活动

不要判定为“活动”的内容：
- 活动复盘、会后总结、现场回顾
- 行业资讯、观点评论、融资新闻、产品公告
- 招聘、招生、课程长期售卖页，除非它明确对应一个具体场次或时间段
- 纯资料下载、白皮书发布、功能上线通知

边界情况按下面处理：
- “征集 / 招募 / 训练营 / 路演 / Demo Day / Webinar / 闭门会”：如果用户需要在某个时间窗口内参与，通常算活动
- “长期社群招募 / 常年报名”：如果没有明确场次或时间边界，通常不算活动
- “直播预告”：如果有具体播出时间和参与入口，算活动

生成 `activity.json` 时：
- 文件内容必须是 `raw.json` 子集组成的 JSON 数组
- 保留原文章对象，不要先结构化
- 只保留你确信属于活动的文章
- 无活动时写入 `[]`

`activity.json` 推荐保持这种形式：

```json
[
  {
    "mpId": "gh_xxx",
    "mpName": "某公众号",
    "sourceTitle": "活动原文标题",
    "sourceUrl": "https://example.com/post/1",
    "sourceUpdated": "2026-03-11T10:00:00+08:00",
    "summary": "原文摘要",
    "content": "原文正文或正文摘要"
  }
]
```

如果 `raw.json` 中原始文章对象字段更多：
- 可以原样保留
- 但不要在 `activity.json` 中发明新的结构化字段
- `activity.json` 的角色只是“被判定为活动的原文集合”

复核时优先保证这些字段：

```json
{
  "activityName": "活动名称",
  "activityType": "活动类型",
  "activityAddress": "活动地址",
  "activityStartTime": "活动开始时间",
  "activityEndTime": "活动结束时间",
  "activityLimitNum": "活动限制人数",
  "activityDescription": "活动说明",
  "activityImages": ["活动图片1", "活动图片2"]
}
```

### 4. 提取结构化活动信息并生成 `activity-structured.json`

这一步仍由模型阅读 `activity.json` 后完成，不要用关键字脚本推断。

要求：
- 按文章语义提取活动名称、类型、地址、开始时间、结束时间、限制人数、说明、图片
- 字段缺失时使用空字符串 `""`，图片缺失时使用空数组 `[]`
- 如果同一活动重复出现在多篇文章中，按“同一事件实体”去重，而不是只看标题是否完全一致
- 去重时综合活动名称、时间、地点、组织方、议程内容判断
- 输出必须是 JSON 数组

允许保留这些可选来源字段，便于后续追踪：
- `sourceUrl`
- `sourceTitle`
- `sourceMpId`
- `sourceMpName`

`activity-structured.json` 必须尽量贴近下面的结构：

```json
[
  {
    "activityName": "活动名称",
    "activityType": "活动类型",
    "activityAddress": "活动地址",
    "activityStartTime": "2026-03-12 14:00",
    "activityEndTime": "2026-03-12 17:00",
    "activityLimitNum": "50",
    "activityDescription": "活动说明",
    "activityImages": [
      "https://example.com/image-1.jpg"
    ],
    "sourceUrl": "https://example.com/post/1",
    "sourceTitle": "活动原文标题",
    "sourceMpId": "gh_xxx",
    "sourceMpName": "某公众号"
  }
]
```

字段约束：
- `activityName`：必须是用户能直接识别的活动名，不要只写“报名通知”
- `activityType`：例如讲座、分享会、工作坊、训练营、路演、直播、闭门会
- `activityAddress`：线下写详细地点，线上写“线上”或具体参与方式
- `activityStartTime` / `activityEndTime`：尽量统一成 `YYYY-MM-DD HH:mm`
- `activityLimitNum`：仅保留数字；未知时写空字符串
- `activityDescription`：1 到 3 句，不要整段照抄原文
- `activityImages`：必须是数组

落盘时优先保证 JSON 合法。推荐用下面方式写入：

```bash
printf '%s\n' "${STRUCTURED_JSON}" | jq '.' > "${OUT_DIR}/activity-structured.json"
```

### 5. 生成审阅用 Markdown 和 API 推送用纯文本

将 `activity-structured.json` 保存为：
- `{EXEC_DIR}/{yyyyMMdd}/activity-structured.md`
- `{EXEC_DIR}/{yyyyMMdd}/activity-push.txt`

`activity-structured.md` 要求：
- 标题简洁，适合群消息
- 每个活动单独一节
- 优先展示：活动名称、时间、地点、人数、活动说明
- 若内容过长，先在文件中拆成多个二级标题段，便于人工审阅
- 无活动时明确写“最近 24 小时未发现新的活动文章”

`activity-structured.md` 推荐使用这个模板：

```markdown
# 活动情报速递（YYYY-MM-DD）

> 最近 24 小时筛选出的活动信息如下。

## 1. 活动名称
- 类型：活动类型
- 时间：2026-03-12 14:00 - 2026-03-12 17:00
- 地点：活动地址
- 人数：50
- 说明：活动说明
- 来源：某公众号 / https://example.com/post/1

## 2. 活动名称
- 类型：活动类型
- 时间：待补充
- 地点：线上
- 人数：未说明
- 说明：活动说明
- 来源：某公众号 / https://example.com/post/2
```

无活动时固定写成：

```markdown
# 活动情报速递（YYYY-MM-DD）

最近 24 小时未发现新的活动文章。
```

推荐用下面方式落盘：

```bash
cat > "${OUT_DIR}/activity-structured.md" <<'EOF'
${ACTIVITY_STRUCTURED_MARKDOWN}
EOF
```

`activity-push.txt` 是真正发给客户群 API 的文本内容，要求：
- 纯文本，不使用 Markdown 语法
- 适当压缩长度，避免过长导致成员端不愿发送
- 每条活动建议控制在 2 到 5 行
- 无活动时明确写“最近 24 小时未发现新的活动文章”

推荐模板：

```text
活动情报速递（YYYY-MM-DD）

1. 活动名称
类型：活动类型
时间：2026-03-12 14:00 - 2026-03-12 17:00
地点：活动地址
说明：活动说明
链接：https://example.com/post/1

2. 活动名称
类型：活动类型
时间：待补充
地点：线上
说明：活动说明
链接：https://example.com/post/2
```

推荐用下面方式落盘：

```bash
cat > "${OUT_DIR}/activity-push.txt" <<'EOF'
${ACTIVITY_PUSH_TEXT}
EOF
```

### 6. 使用 Python CLI 封装客户联系/客户群 API 推送

```bash
python3 /Users/yujian/Code/py/aj-skills/skills/activity-push/scripts/wecom_customer_group_push.py \
  --corp-id "${WE_COM_CORP_ID}" \
  --contact-secret "${WE_COM_CONTACT_SECRET}" \
  --sender-userids "${WE_COM_GROUPMSG_SENDER_USERIDS}" \
  --target-chat-ids "${WE_COM_TARGET_CHAT_IDS:-}" \
  --chat-name-keywords "${WE_COM_TARGET_CHAT_NAME_KEYWORDS:-}" \
  --message-file "${OUT_DIR}/activity-push.txt" \
  --out-dir "${OUT_DIR}"
```

本地 dry-run 验证可用：

```bash
python3 /Users/yujian/Code/py/aj-skills/skills/activity-push/scripts/wecom_customer_group_push.py \
  --corp-id "ww-test" \
  --contact-secret "secret-test" \
  --sender-userids "zhangsan,lisi" \
  --chat-name-keywords "活动" \
  --message-file "${OUT_DIR}/activity-push.txt" \
  --out-dir "${OUT_DIR}/dry-run" \
  --dry-run \
  --fixture-dir /Users/yujian/Code/py/aj-skills/skills/activity-push/tests/fixtures/wecom-push
```

执行说明：
- CLI 使用标准库实现，不依赖第三方包
- CLI 会自动处理 `gettoken`、`groupchat/list` 分页、可选 `groupchat/get` 名称过滤、`add_msg_template`、`remind_groupmsg_send`、`get_groupmsg_send_result`
- CLI 的输出文件默认包括：`wecom-token.json`、`customer-groups.json`、`customer-group-details.json`、`groupmsg-create-result.json`、`push-result.md`
- CLI 支持 `--dry-run` + `--fixture-dir`，可在不访问真实企业微信 API 的情况下做本地回放验证
- 这里创建的是“群发任务”，不是 webhook 式即时直发
- 接口调用成功后，仍需要对应成员在企业微信侧完成发送
- `remind_groupmsg_send` 只是提醒成员，不能替代成员确认动作
- 24 小时内单个群发最多只能提醒 3 次
- `get_groupmsg_send_result` 返回可能有延迟，必要时可稍后再次轮询
- 复杂限制、字段假设和调试说明，见 [`wecom-customer-group-api.md`](/Users/yujian/Code/py/aj-skills/skills/activity-push/references/wecom-customer-group-api.md)

目标群选择规则：
- 若 `WE_COM_TARGET_CHAT_IDS` 已提供，优先按显式 chat_id 发送
- 若未提供，CLI 会先用 `groupchat/list` 按 `WE_COM_GROUPMSG_SENDER_USERIDS` 发现目标客户群
- 如需按群名进一步过滤，可设置 `WE_COM_TARGET_CHAT_NAME_KEYWORDS`

关于 `chat_id_list`：
- 我这里采用的是当前客户群相关资料和常见 SDK 中一致使用的字段名 `chat_id_list`
- 如果你的租户当前接口定义返回参数错误，先查看 [`wecom-customer-group-api.md`](/Users/yujian/Code/py/aj-skills/skills/activity-push/references/wecom-customer-group-api.md) 中的调试说明，再按官方当前文档或控制台返回信息修正字段；不要自动回退到全量群发

## Output Rules

- `raw.json` 必须是最近 24 小时文章组成的 JSON 数组
- `activity.json` 必须是活动候选文章组成的 JSON 数组
- `activity-structured.json` 必须是去重后的活动对象数组
- `activity-structured.md` 必须用于人工审阅，默认中文
- `activity-push.txt` 必须用于客户群 API 的 `text.content`
- `push-result.md` 必须记录每个 sender 的群发任务结果

如果没有活动：
- 仍然生成所有目标文件
- `activity.json` 与 `activity-structured.json` 为空数组
- `activity-structured.md` 写明“最近 24 小时未发现新的活动文章”
- `activity-push.txt` 写明“最近 24 小时未发现新的活动文章”
- `push-result.md` 仍要记录群发任务结果

## Semantic Judgment Rules

判断“是否是活动”时，始终用下面的思路，而不是查词：

1. 先看文章的核心意图
如果文章的中心是在组织一次参与行为，它更可能是活动；如果中心只是表达观点、传递新闻或做总结，就不是活动。

2. 再看是否存在“参与闭环”
活动通常会形成一个闭环：谁可以参加、何时参加、在哪里参加、怎样参加、参加后发生什么。即使其中某些字段缺失，只要闭环大体成立，就可判为活动。

3. 再看时间性和事件性
活动是一个具体事件，通常有场次、时间窗口或明确排期。长期存在、没有明确场次的介绍页，通常不应视为活动。

4. 最后看文章是否要求读者采取行动
如果读者被要求报名、预约、进群、到场、观看直播、提交资料、参与议程，这通常说明它是活动。

## WeCom Push Rules

- 不再使用群机器人 webhook
- 使用客户联系 access token 调用客户群相关接口
- 优先调用 `externalcontact/groupchat/list` 或使用显式 `chat_id`
- 通过 `externalcontact/add_msg_template` 创建客户群群发任务
- 通过 `externalcontact/remind_groupmsg_send` 触发提醒
- 通过 `externalcontact/get_groupmsg_send_result` 记录结果
- 消息正文优先使用纯文本 `text.content`，不要把 Markdown 原样塞进客户群发接口
- 所有 sender 完成后，再写 `push-result.md`

## Quality Checklist

- 已完成环境预检
- 已用 bash + `curl` + `jq` 完成抓取
- 已按 `updated` 过滤最近 24 小时文章
- 已产出 `raw.json`
- 已由模型按语义判断活动候选并产出 `activity.json`
- 已提取结构化字段并去重
- 已产出 `activity-structured.json`
- 已产出审阅用 `activity-structured.md`
- 已产出推送用 `activity-push.txt`
- 已通过 bundled Python CLI 调用客户联系/客户群 API 创建群发任务
- 已产出 `push-result.md`
- 回复中明确给出所有输出文件路径
- 如处于开发或调试阶段，已至少运行一次 CLI dry-run 或本地测试

## Failure Handling

如果发生错误，按下面顺序处理：

1. 先定位是输入缺失、网络失败、字段不兼容，还是客户群 API 调用失败
2. 能继续的步骤继续执行，不要因为单个公众号失败就中止全部流程
3. 在 `push-result.md` 或终端输出中保留失败原因摘要
4. 如果 feed JSON 结构不兼容，先保存原始结果，再说明使用了什么字段假设
5. 如果客户群 API 返回鉴权、字段或权限错误，不要自动回退到 webhook 或扩大发送范围

## Optimization Notes

相对你原始草案，这里做了这些优化：
- 不再把“是不是活动”交给关键字规则，而是交给模型做语义判断
- 全流程回到 bash + `curl` + `jq`，更贴近你要求的执行方式
- `feeds.md` 支持空行和注释
- 活动去重改为事件实体判断，而不是字符串硬匹配
- 推送链路升级为客户联系/客户群 API，更适合企业微信外部群
- 审阅内容与发送内容分离，降低 API 消息体格式不兼容风险
- 所有步骤都落盘，便于二次检查和重跑

## Test Prompts

可用这些提示词测试 skill 是否会正确触发：

1. “根据当前目录的 feeds.md，把最近 24 小时公众号文章里的活动提取出来，并通过企业微信客户群 API 发到外部群。”
2. “读取 ~/.aj-skills/.env 和 feeds.md，输出 raw.json、activity.json、activity-structured.json、activity-structured.md、activity-push.txt，再创建客户群群发任务。”
3. “帮我做一个活动推送流水线：从公众号 feed 抓文章，筛活动，结构化提取，生成审阅 Markdown 和外部群发送文本，并推送到企业微信外部群。”
