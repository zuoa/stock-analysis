# {{stock_name}} ({{stock_code}}) 投资分析报告

**总结标题**: {{summary_title}}

**分析日期**: {{analysis_date}}
**分析级别**: {{analysis_level}}
**综合评分**: {{overall_score}}/100
**财务基础面分**: {{fundamental_score}}/100
**实时指标分**: {{realtime_score}}/100
**评分权重**: 财务{{fundamental_weight_pct}}% + 实时{{realtime_weight_pct}}%

---

## 一、公司概况

| 项目 | 内容 |
|------|------|
| 股票代码 | {{stock_code}} |
| 股票名称 | {{stock_name}} |
| 所属行业 | {{industry}} |
| 总市值 | {{market_cap}} |
| 流通市值 | {{float_cap}} |
| 上市日期 | {{listing_date}} |

### 主营业务

{{main_business}}

---

## 二、财务健康分析

### 2.1 盈利能力

| 指标 | 当前值 | 行业均值 | 评价 |
|------|--------|----------|------|
| ROE | {{roe}}% | {{industry_roe}}% | {{roe_assessment}} |
| ROA | {{roa}}% | {{industry_roa}}% | {{roa_assessment}} |
| 毛利率 | {{gross_margin}}% | {{industry_gross_margin}}% | {{gross_margin_assessment}} |
| 净利率 | {{net_margin}}% | {{industry_net_margin}}% | {{net_margin_assessment}} |

**杜邦分析**:
- 净利率: {{net_margin}}%
- 资产周转率: {{asset_turnover}}
- 权益乘数: {{equity_multiplier}}
- **ROE驱动因素**: {{roe_driver}}

### 2.2 偿债能力

| 指标 | 当前值 | 参考标准 | 状态 |
|------|--------|----------|------|
| 资产负债率 | {{debt_ratio}}% | < 60% | {{debt_ratio_status}} |
| 流动比率 | {{current_ratio}} | > 1.5 | {{current_ratio_status}} |
| 速动比率 | {{quick_ratio}} | > 1 | {{quick_ratio_status}} |
| 利息覆盖倍数 | {{interest_coverage}} | > 3 | {{interest_coverage_status}} |

### 2.3 运营效率

| 指标 | 当前值 | 趋势 |
|------|--------|------|
| 应收账款周转天数 | {{ar_days}}天 | {{ar_trend}} |
| 存货周转天数 | {{inventory_days}}天 | {{inventory_trend}} |
| 总资产周转率 | {{asset_turnover}} | {{asset_turnover_trend}} |

---

## 三、成长性分析

### 3.1 增长指标

| 指标 | 最近一期 | 近3年平均 | 趋势 |
|------|----------|-----------|------|
| 营收增长率 | {{revenue_growth}}% | {{avg_revenue_growth}}% | {{revenue_trend}} |
| 净利润增长率 | {{profit_growth}}% | {{avg_profit_growth}}% | {{profit_trend}} |
| EPS增长率 | {{eps_growth}}% | {{avg_eps_growth}}% | {{eps_trend}} |

### 3.2 成长性评估

{{growth_assessment}}

---

## 四、实时指标看板

### 4.1 趋势与确认

| 维度 | 指标 | 数值 |
|------|------|------|
| 趋势 | 趋势分 | {{trend_score}} |
| 趋势 | 1/5/20/60日收益(%) | {{return_1d}} / {{return_5d}} / {{return_20d}} / {{return_60d}} |
| 趋势 | 相对基准1/5/20/60(%) | {{vs_benchmark_1d}} / {{vs_benchmark_5d}} / {{vs_benchmark_20d}} / {{vs_benchmark_60d}} |
| 确认 | 确认分 | {{confirm_score}} |
| 确认 | 成交额比20日均值 | {{amount_ratio_20d}} |
| 确认 | 量比 / 换手率 | {{volume_ratio}} / {{turnover_rate}} |
| 确认 | 资金净流入占比(%) | {{net_inflow_ratio}} |
| 确认 | 近5日净流入天数 | {{positive_days_5}} |

### 4.2 风险与筹码

| 维度 | 指标 | 数值 |
|------|------|------|
| 风险 | 风险扣分 | {{risk_penalty}} |
| 风险 | 日内振幅(%) | {{intraday_amplitude_pct}} |
| 风险 | 实现波动率20日(%) | {{realized_volatility_20d_pct}} |
| 风险 | 下行波动率20日(%) | {{downside_volatility_20d_pct}} |
| 风险 | 窗口最大回撤(%) | {{max_drawdown_window_pct}} |
| 筹码 | 筹码扣分 | {{chip_penalty}} |
| 筹码 | 解禁30/90天占比(%) | {{unlock_30d_ratio}} / {{unlock_90d_ratio}} |
| 筹码 | 减持密度 / 回购占比 | {{reduction_density_30d}} / {{repurchase_ratio_90d}} |

### 4.3 实时结论

{{realtime_conclusion}}

### 4.4 事件窗口反应

| 项目 | 数值 |
|------|------|
| 事件窗口分 | {{event_window_score}} |
| 事件数 / 匹配数 | {{event_window_event_count}} / {{event_window_matched_count}} |
| 窗口设置 | 前{{event_window_pre_days}}日，后{{event_window_post_days}}日 |
| 后1/3/5日平均收益(%) | {{ew_avg_post_1d_pct}} / {{ew_avg_post_3d_pct}} / {{ew_avg_post_5d_pct}} |
| 后1/3/5日平均超额收益(%) | {{ew_avg_abnormal_1d_pct}} / {{ew_avg_abnormal_3d_pct}} / {{ew_avg_abnormal_5d_pct}} |
| 后3日上涨占比(%) | {{ew_positive_ratio_3d}} |
| 最差后5日收益(%) | {{ew_worst_post_5d_pct}} |

事件窗口结论：{{event_window_conclusion}}

{{#if event_window_top_positive}}
事件窗口Top正向事件：
{{#each event_window_top_positive}}
- {{this.event_trade_date}} {{this.title}}（3日超额: {{this.abnormal_3d_pct}}%，3日收益: {{this.post_3d_pct}}%）
{{/each}}
{{/if}}

{{#if event_window_top_negative}}
事件窗口Top负向事件：
{{#each event_window_top_negative}}
- {{this.event_trade_date}} {{this.title}}（3日超额: {{this.abnormal_3d_pct}}%，3日收益: {{this.post_3d_pct}}%）
{{/each}}
{{/if}}

---

## 五、估值分析

### 5.1 当前估值

| 指标 | 当前值 | 历史分位数 | 行业均值 |
|------|--------|------------|----------|
| PE (TTM) | {{pe_ttm}} | {{pe_percentile}}% | {{industry_pe}} |
| PB | {{pb}} | {{pb_percentile}}% | {{industry_pb}} |
| PS | {{ps}} | {{ps_percentile}}% | {{industry_ps}} |

### 5.2 内在价值估算

| 估值方法 | 每股价值 | 说明 |
|----------|----------|------|
| DCF现金流折现 | ¥{{dcf_value}} | 折现率{{discount_rate}}%，永续增长{{terminal_growth}}% |
| DDM股息折现 | ¥{{ddm_value}} | 股息增长率{{dividend_growth}}% |
| 相对估值 | ¥{{relative_value}} | 基于历史PE均值 |
| **平均估值** | **¥{{avg_value}}** | - |

### 5.3 安全边际

| 项目 | 数值 |
|------|------|
| 当前价格 | ¥{{current_price}} |
| 平均内在价值 | ¥{{avg_value}} |
| 安全边际 | {{margin_of_safety}}% |
| 建议买入价 | ¥{{safety_price}} |

**估值结论**: {{valuation_conclusion}}

---

## 六、业绩与审计信号

| 项目 | 结论 |
|------|------|
| 业绩与审计综合评估 | {{performance_assessment}} |

{{#if performance_signals}}
关键信号：
{{#each performance_signals}}
- {{this}}
{{/each}}
{{else}}
- 暂无明显业绩与审计异常信号
{{/if}}

---

## 七、风险提示

### 7.1 财务异常检测

**风险等级**: {{risk_level}}

{{#if anomalies}}
| 异常类型 | 描述 | 严重程度 |
|----------|------|----------|
{{#each anomalies}}
| {{this.type}} | {{this.description}} | {{this.severity}} |
{{/each}}
{{else}}
未检测到明显财务异常
{{/if}}

### 7.2 新闻与舆情

| 指标 | 数值 |
|------|------|
| 新闻条数 | {{news_count}} |
| 综合情绪分 | {{overall_sentiment}} |
| 舆情风险等级 | {{news_risk_level}} |

{{#if top_negative_events}}
重点负面事件：
{{#each top_negative_events}}
- {{this.published_at}} {{this.title}}（{{this.source}}）
{{/each}}
{{else}}
- 最近窗口期未发现显著负面舆情
{{/if}}

### 7.3 股东相关风险

{{#if holder_risks}}
{{#each holder_risks}}
- {{this}}
{{/each}}
{{else}}
- 暂无明显股东相关风险
{{/if}}

### 7.4 行业/政策风险

{{industry_risks}}

---

## 八、投资结论

### 8.1 综合评分（实时优先）

| 层级 | 评分 | 权重 | 加权得分 |
|------|------|------|----------|
| 财务基础面 | {{fundamental_score}}/100 | 40% | {{fundamental_weighted_score}} |
| 实时指标 | {{realtime_score}}/100 | 60% | {{realtime_weighted_score}} |
| **综合评分** | **{{overall_score}}/100** | - | - |

### 8.2 基础面细分（用于财务分）

| 维度 | 评分 | 权重 | 加权得分 |
|------|------|------|----------|
| 盈利能力 | {{profitability_score}}/100 | 30% | {{profitability_weighted}} |
| 财务安全 | {{safety_score}}/100 | 20% | {{safety_weighted}} |
| 成长性 | {{growth_score}}/100 | 25% | {{growth_weighted}} |
| 估值水平 | {{valuation_score}}/100 | 25% | {{valuation_weighted}} |
| **财务基础面分** | **{{fundamental_score}}/100** | - | - |

### 8.3 投资建议

{{investment_recommendation}}

### 8.4 关键观察点

{{#each key_observations}}
- {{this}}
{{/each}}

---

## 免责声明

本报告基于公开财务数据分析，仅供参考，不构成投资建议。投资有风险，入市需谨慎。

**数据来源**: tushare (公开财务数据)
**分析工具**: china-stock-analysis skill
**报告生成时间**: {{report_time}}

---

# 报告模板使用说明

上述模板中的 `{{变量名}}` 需要在生成报告时替换为实际值。

## 报告级别说明

### 摘要级 (Summary)
只包含：
- 基本信息
- 关键财务指标
- 投资结论

### 标准级 (Standard)
包含：
- 完整财务分析
- 实时指标看板（趋势/确认/风险/筹码）
- 事件窗口分析（事件后1/3/5日反应与超额收益）
- 估值分析
- 风险提示
- 投资建议

### 深度级 (Deep)
在标准级基础上增加：
- 历史数据趋势图描述
- 详细财务报表分析
- 竞争对手对比
- 行业深度分析

## 评分标准

### 盈利能力评分
- ROE > 20%: +15分
- ROE 15-20%: +10分
- ROE 10-15%: +5分
- ROE < 10%: 0分

### 财务安全评分
- 无风险指标: +10分
- 每个风险指标: -5分

### 成长性评分
- 增长率 > 20%: +15分
- 增长率 10-20%: +10分
- 增长率 0-10%: +5分
- 负增长: -5分

### 估值水平评分
- 历史分位数 < 20%: +15分 (低估)
- 历史分位数 20-40%: +10分
- 历史分位数 40-60%: +5分
- 历史分位数 60-80%: 0分
- 历史分位数 > 80%: -10分 (高估)

### 实时指标评分
- 趋势分：多周期动量 + 相对强弱
- 确认分：成交额/量比/换手 + 资金净流入连续性
- 风险扣分：波动率、振幅、回撤恶化
- 筹码扣分：解禁压力、减持密度、回购对冲

### 事件窗口评分（补充维度）
- 事件后收益：1/3/5日平均收益
- 事件后超额：相对基准1/3/5日超额收益
- 稳定性：后3日上涨占比、最差后5日收益

### 最终综合评分（实时优先）
- 财务基础面分权重：40%
- 实时指标分权重：60%
