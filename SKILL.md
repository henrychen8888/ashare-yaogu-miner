---
name: ashare-yaogu-miner
slug: ashare-yaogu-miner
displayName: 妖股挖掘量化看板
display_name: 妖股挖掘量化看板
display_name_zh: 妖股挖掘量化看板
display_name_en: "ASHare Monster Stock Miner"
summary: "涨停池五维加权妖股概率评分，输出零依赖深色 HTML 看板 + 结构化快照"
description: "对当日涨停池做五维加权妖股概率评分（主力资金30 / 龙虎榜25 / 量能25 / 题材10 / 形态10），输出可离线打开的深色 HTML 看板与结构化快照 JSON。当用户说「妖股」「妖股挖掘」「妖股概率」「今天哪些票能成妖」「涨停池评分」「连板接力」「打板候选」「妖股看板」「妖股分析」时使用。仅对当日涨停股评级，不做全市场选股，不给买卖建议。"
description_zh: "拉取东方财富涨停池/炸板池/跌停池/龙虎榜，逐票叠加资金流与前复权日线，按五维权重给出 0-100 妖股概率分与 S/A/B/C 分级，产出零依赖 HTML 看板。"
description_en: "Score every limit-up stock in today's pool on a five-factor weighted model (capital flow 30 / dragon-tiger list 25 / volume 25 / theme 10 / pattern 10) and render a dependency-free HTML dashboard plus a structured JSON snapshot."
tagline: "涨停池里挑妖，靠分数不靠感觉"
category: 金融投资
subcategory: A股 · 短线打板 / 妖股挖掘
tags: [A股, 妖股, 涨停, 连板, 龙虎榜, 资金流, 打板, 短线选股, 量化评分, 看板]
audience: "A股短线交易者 / 打板选手 / 需要每日涨停池复盘的技术型量化开发者"
version: 1.0.1
author: "莫扎特 ETH"
license: MIT
agent_created: true
---

# 妖股挖掘量化看板

## 何时使用

用户提到「妖股」「妖股挖掘」「妖股概率」「哪些票能成妖」「涨停池评分」
「连板接力」「打板候选」「妖股看板」时，指向本技能。

**定位先说清**：这是在**当日涨停池内部**做相对排序，不是全市场选股器。
150 只涨停股里哪 3 只最像妖股的早期形态——这是它回答的问题。
它不回答「明天买什么」，也不回答「这只票能涨到多少」。

## 一句话执行

```bash
python <skill>/scripts/run.py                # 最近交易日，全量涨停股
python <skill>/scripts/run.py --date 20261102 --top 30
python <skill>/scripts/run.py --limit 40     # 只评前 40 只（快速模式，行业统计仍用全池）
```

跑完必须接着跑自检，**全绿才算完成**：

```bash
python <skill>/scripts/selfcheck.py
```

自检会真的做四件事：涨停算术复核（10cm/20cm/30cm/5cm 分开判）、五维之和与总分比对、
HTML 里的 None/nan 泄漏扫描、K线/资金流覆盖率核对。任一项 ❌ 就如实报告，不要用
文字描述替代实际检查结果。

零第三方依赖，纯 Python 3.9+ 标准库（urllib），不需要 pip install。

## 必须先知道的五条坑

### 1. `push2.eastmoney.com` 可能整条链路不可达 —— 不要碰全市场快照

2026-11-02 实测：`push2.eastmoney.com`（clist 类接口）在本机代理下全部
`RemoteDisconnected`，连 http 直连也断；而 `push2ex` / `push2his` / `datacenter-web`
正常。另一天可能反过来。

所以本技能**完全不用 clist 全市场快照**：市场情绪用「涨停池 + 炸板池 + 跌停池 +
指数」表达，资金流逐票从 `push2his/fflow` 拿。任何「顺手加个全市场涨跌家数」
的想法都会在某天把整个看板拖垮。

`http_client.fetch_json` 已封装「信任代理 → 直连」双通道重试，不要简化成单 URL。

### 2. 跌停池不带 `sort=fund:asc` 会返回 `tc=0`（不是空表，是零值）

实测 `getTopicDTPool`：带 `fbt`/`lbc` 排序返回 `tc=8, pool=[]`；不带 sort 返回
`tc=0`。只有 `fund`/`zdp` 排序能同时拿到数量与明细。
**只信 `len(pool)` 会把跌停数误报成 0**，这种静默零值比报错危险得多。
`_pool_meta` 已做「pool 空但 tc>0 → 换 fund 排序重试」。

### 3. 涨停池价格要 ÷1000

`p: 4940` 表示 4.94 元。`amount` / `ltsz` / `fund` 都是元，`hs` 是百分数。
单位必须实测反推，别信表头直觉。

### 4. 涨停必须算术校验，10cm 和 20cm 要分开

`|round(昨收×(1+限制), 2) − 收盘| < 0.015`，其中昨收 = 收盘/(1+涨幅%/100)。
限制：主板 0.10、创业板(300/301)/科创板(688/689) 0.20、北交所(8/4/92) 0.30、ST 0.05。

用「涨幅≈10% 就算涨停」会把 +13% 的科创板票错判。`sources.is_limit_up` 已实现，
自检会对全池复核一遍。

### 5. 换手率是区间型指标，不能用降序阈值表

`_grade` 取「第一个满足的档位」，`turnover=35%` 会命中「≥5」直接拿满分，
把过热当成最佳。换手、封单占比这类都要逐段区间判断。

## 评分模型

| 维度 | 权重 | 输入 | 数据源 |
|---|---|---|---|
| 主力资金净流入 | 30 | 当日主力净流入、近5日累计、占流通市值比 | `push2his/fflow` |
| 龙虎榜机构/游资 | 25 | 上榜次数、席位净买额、机构专用席 | `datacenter-web` |
| 量能特征 | 25 | 换手率、量比、封单额/流通市值、首封时间、炸板次数 | 涨停池 + 日K |
| 题材级别 | 10 | 所属行业当日涨停家数、是否前三行业、连板高度 | 涨停池聚合 |
| 均线与K线形态 | 10 | 突破60/20日新高、均线多头、放量突破、5日涨幅 | 前复权日线 |

分级：**≥80 S 妖股候选 / 70-79 A 强关注 / 60-69 B 潜力区间 / <60 C 观察**。

权重 30/25/10 与 80/60 两级阈值来自原始看板披露；量能 25 与题材 10 是按原看板
展示的五维平均分（23.2/5.3/13.9/9.4/8.4）反推补全。**每档的具体阈值是我按
2026-11-02 涨停池实测分位设定的**，不是原看板公开的数据——完整档位表、
分位锚点、以及与原看板的差异，见 `references/scoring_model.md`。

## 输出

产物落在 **`~/WorkBuddy/ashare-yaogu-miner/`**（Windows 即 `C:\Users\<你>\WorkBuddy\ashare-yaogu-miner\`），
不写进技能目录——技能包要发布，行情缓存不能跟着打包。可用环境变量 `YAOGU_WORK` 改位置。

| 文件 | 内容 |
|---|---|
| `yaogu_YYYYMMDD.html` | 深色看板，纯内联 CSS+SVG，断网可打开 |
| `yaogu_YYYYMMDD.json` | 全量评分快照，可程序化消费（含每只票五维得分与告警） |
| `cache/YYYYMMDD.json` | 当日行情缓存，重跑免二次拉取（`--no-cache` 跳过） |

看板含：6 个 KPI、指数条、Top20 评分表（分数/分级/连板/资金/龙虎/换手/行业/理由）、
Top1 五维雷达图、行业题材热度 Top12、主力净流入 Top12、评分分布直方图、数据告警。

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--date` | 最近交易日 | `YYYYMMDD` 或 `YYYY-MM-DD` |
| `--top` | 20 | 表格展示条数（快照仍含全量） |
| `--limit` | 0（全量） | 只评前 N 只涨停股，按连板数+成交额排序 |
| `--workers` | 8 | 并发拉取线程数 |
| `--no-cache` | 关 | 强制重拉行情 |

## 商业化状态：免费发布（未接入按量付费）

已以 **免费技能** 形式发布到 SkillHub：`ashare-yaogu-miner` v1.0.0，
skillId `304639`，命名空间 `user_2e8da43f`（审核通过后才可下载）。

本技能**当前没有**实现支付宝 AI 按量付费（Machine Pay / A2M）的 402 收款链路：
没有 `alipay.aipay.agent.payment.precreate` 预下单、没有 `402 + amtPaymentLink`、
没有 `Payment-Proof` 验付、没有 `fulfillment.confirm` 履约回执，也没有支付依赖包。

原因不是遗漏，而是**形态不匹配**：Machine Pay 的协议对象是「受 HTTP 保护的资源端点」，
而本技能是本地批处理 CLI（`python scripts/run.py`），没有服务端、没有订单概念，
也没有可对外的资源 URL。硬加一个 402 响应只会是装饰，收不到钱也验不了付。

要真正接入，三条路，代价差很多（详见 `references/alipay-machine-pay.md` §9）：

| 路径 | 真实代价 | 适配本技能 |
|---|---|---|
| **A. 免费发布** | CLI 打包 + 网页补详情页 | ✅ 当前形态即可 |
| **B. Pay Skill（接平台计费）** | 技能包内需自带 `payment_gate.py` 付费闸口、受保护资源端点、以及**复制走也跑不起来**的后端能力 | ❌ 需先把评分能力搬到服务端 |
| **C. 自建 402（直连支付宝）** | 商户资质（app_id / PKCS#8 私钥 / 支付宝公钥 / `service_id`）+ HTTPS 部署 + 250-300 行服务端代码 | ❌ 同上，改造量最大 |

**注意：平台托管不等于零改造。** SkillHub 上架入口明确区分「发布 Skill（最快上架）」与
「发布 Pay Skill（需支付改造）」，已有 Pay Skill 的包里都带着付费闸口与云端计费端点。
另外行业口径是「付费 Skill 要求能力依赖后端，文件被复制走也跑不起来」——纯本地脚本
复制走就能用，按这个标准不具备收费前提。

**不要在没有真实凭证、没有付费闸口的情况下声称「已完成付费改造」**——402 链路必须能跑通
precreate → 402 → 支付 → verify → 交付 → confirm 才算接入，缺凭证时只能写骨架，
骨架不构成接入。

## 边界（别越界承诺）

- **分数是同池内相对排序，不是次日上涨概率的绝对估计。** 别把它读成「80% 会涨」。
- **未经独立收益回测验证。** 区分度（能把票分开）≠ 收益率（能赚钱），两件事必须分开讲。
- 不适用：盘中实时预警（盘后快照）、单票基本面判断、仓位建议、非涨停股的妖股预测
  （模型训练域就是涨停池，对没涨停的票没有意义）。
- 龙虎榜未上榜的票给 4.0 基线分（占权重 16%），这是设计选择，不是遗漏——理由见
  `references/scoring_model.md`。若你要「无榜即 0 分」的严格口径，改 `engine.score_lhb` 一行即可。
