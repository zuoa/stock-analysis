# aj-skills

本仓库当前包含一个可直接运行的技能：`skills/stock-analysis`。  
它基于价值投资思路，使用 Tushare 公共数据提供 A 股筛选、个股分析、板块对比、估值计算与新闻舆情分析能力。


```bash
npx skills add https://github.com/zuoa/aj-skills --skill aj-stock-analysis
```

## 目录结构

```text
skills/stock-analysis/
  ├─ SKILL.md                     # 技能定义与工作流说明
  ├─ scripts/                     # 可执行脚本
  ├─ tests/                       # pytest 测试
  ├─ templates/analysis_report.md # 报告模板
  ├─ references/                  # 方法论参考资料
  └─ config/                      # 默认板块配置
```

## 快速开始

1. 创建并激活虚拟环境

```bash
cd skills/stock-analysis
python3 -m venv .venv
source .venv/bin/activate
```

2. 安装依赖

```bash
pip install -U pip
pip install tushare pandas numpy pytest
```

3. 配置 Tushare Token（任选其一）

方式 A：环境变量

```bash
export TUSHARE_TOKEN=your_token
```

方式 B：写入 `~/.aj-skills/.env`

```bash
mkdir -p ~/.aj-skills
cat > ~/.aj-skills/.env <<'EOF'
TUSHARE_TOKEN=your_token
EOF
```

4. 检查安装

```bash
python3 -c "import tushare; print(tushare.__version__)"
```

## 核心脚本

- `scripts/stock_screener.py`: 多指标股票筛选（PE/PB/ROE/负债率/市值等）
- `scripts/data_fetcher.py`: 拉取个股或多股基础数据、财务数据、估值与行情
- `scripts/financial_analyzer.py`: 财务健康度、成长性、杜邦分析、异常检测、评分
- `scripts/valuation_calculator.py`: DCF/DDM/相对估值与安全边际测算
- `scripts/sector_fetcher.py`: 按板块配置批量抓取股票数据
- `scripts/sector_analyze.py`: 板块统计、综合评分排名与 Markdown 报告
- `scripts/news_fetcher.py`: 新闻抓取（优先 Tushare，回退 RSS）
- `scripts/sentiment_analyzer.py`: 规则词典情绪与风险标签分析

## 常用命令

### 1) 股票筛选

```bash
python scripts/stock_screener.py \
  --scope hs300 \
  --pe-max 20 \
  --roe-min 12 \
  --debt-ratio-max 60 \
  --top 30 \
  --output output/screener.json
```

### 2) 拉取个股数据（附带新闻）

```bash
python scripts/data_fetcher.py \
  --code 600519 \
  --data-type all \
  --years 5 \
  --with-news \
  --news-days 7 \
  --news-limit 20 \
  --output output/600519_data.json
```

### 3) 财务分析并生成报告

```bash
python scripts/financial_analyzer.py \
  --input output/600519_data.json \
  --level standard \
  --output output/600519_financial.json \
  --report-md output/600519_report.md
```

### 4) 估值计算

```bash
python scripts/valuation_calculator.py \
  --input output/600519_data.json \
  --methods all \
  --discount-rate 10 \
  --terminal-growth 3 \
  --margin-of-safety 30 \
  --output output/600519_valuation.json
```

### 5) 板块分析

```bash
python scripts/sector_fetcher.py \
  --sector-name 算力板块 \
  --output output/sector_data.json

python scripts/sector_analyze.py \
  --input output/sector_data.json \
  --output output/sector_analysis.json \
  --report-md output/sector_analysis.md
```

### 6) 新闻舆情

```bash
python scripts/news_fetcher.py \
  --code 600519 \
  --name 贵州茅台 \
  --days 7 \
  --limit 20 \
  --output output/news.json

python scripts/sentiment_analyzer.py \
  --input output/news.json \
  --output output/sentiment.json
```

## 运行测试

```bash
cd skills/stock-analysis
source .venv/bin/activate
pytest -q
```

## 输出说明

- 绝大多数脚本支持 `--format json|table`
- 指定 `--output` 时会将结果落盘为 JSON 文件
- `financial_analyzer.py` 与 `sector_analyze.py` 支持额外输出 Markdown 报告

## 注意事项

- 本项目依赖外部数据源，接口限流或网络问题会影响抓取速度与成功率
- 新闻舆情模块是规则法（MVP），适合快速风险扫描，不等于完整研报结论
- 结果仅供研究与学习，不构成投资建议

