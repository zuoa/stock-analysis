---
name: stock-sector-monitoring
description: Monitors China A-share concept sectors and Dragon Tiger List (龙虎榜) via Tushare, then generates structured markdown reports. Use when users ask to track sector momentum, fetch top_list (doc_id=106), remove ST stocks, rank movers, or save monitoring output as .md files.
---

# Stock Sector Monitoring Skill

用于基于 Tushare 的 A 股市场监测，重点支持：
- 概念板块监测（`sector`）
- 龙虎榜每日明细（`lhb`，`top_list` / doc_id=106）
- 将结果输出并保存为 Markdown 文件

## When to Use

当用户出现以下意图时使用本 skill：
- “监控概念板块/行业热度/涨幅榜”
- “查询龙虎榜数据”
- “过滤 ST 股票后输出结果”
- “把监控结果保存成 markdown/md 文件”

## Prerequisites

在 skill 根目录执行：

```bash
cd /Users/yujian/Code/py/aj-skills/skills/stock-sector-monitoring
```

依赖准备：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install tushare pandas
```

Tushare token 约定从 `~/.aj-skills/.env` 读取：
```bash
# ~/.aj-skills/.env
TUSHARE_TOKEN=your_token
```


## Core Workflow

### 1) 采集龙虎榜数据（默认推荐）

```bash
source .venv/bin/activate
python3 scripts/sector-monitoring.py \
  --once \
  --data-source lhb \
  --trade-date 20260213 \
  --top 20 \
  --format json
```

说明：
- `--data-source lhb` 使用龙虎榜接口（`top_list`）
- `--trade-date YYYYMMDD` 指定交易日，默认是当天
- 当前脚本已内置过滤 ST / *ST / S*ST / SST 股票

### 2) 生成 Markdown 报告

将 JSON 输出整理成 Markdown，并保存到 `reports/` 目录。

文件命名规范：
- 龙虎榜日报：`reports/lhb-YYYYMMDD.md`
- 指定股票：`reports/lhb-YYYYMMDD-TS_CODE.md`
- 概念板块：`reports/sector-YYYYMMDD.md`

Markdown 最低结构：

```markdown
# 龙虎榜监测日报（YYYY-MM-DD）

## 参数
- 数据源: lhb
- 交易日: YYYYMMDD
- Top N: 20
- ST 过滤: 已启用

## 涨幅榜 Top N
| 排名 | 代码 | 名称 | 涨跌幅 | 龙虎榜净买入额(亿) | 净买额占比(%) | 上榜理由 |
|---|---|---|---:|---:|---:|---|

## 综合评分 Top N
| 排名 | 代码 | 名称 | 综合评分 | 涨跌幅 | 龙虎榜净买入额(亿) |
|---|---|---|---:|---:|---:|

## 预警
- 列出超过阈值的标的（若无则写“无”）
```

### 3) 保存要求（必须）

每次响应都应：
- 明确输出文件路径
- 将最终结果落盘为 `.md`
- 在回复中给出“已保存到：`<path>`”

## Output Rules

- 默认输出 Markdown，不仅在对话中展示。
- 如用户未指定文件名，按命名规范自动生成。
- 如用户指定日期或 TS 代码，文件名必须反映该条件。
- 若当日无数据，仍生成 Markdown，并在正文写明“无可用数据（非交易日/无上榜）”。

## Quality Checklist

- 已使用 `lhb` 模式并指定 `trade_date`（或说明默认日期）
- 已过滤 ST 类股票
- 表格列名完整、单位清晰（金额统一“亿元”）
- 报告已保存为 `.md`
- 回复中包含保存路径

## Notes

- 龙虎榜接口权限要求较高（`top_list` 通常需积分权限）。
- 若接口返回为空，优先提示交易日与权限问题，再输出空报告模板。
