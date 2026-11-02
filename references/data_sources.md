# 数据源与接口口径

全部实测于 2026-11-02（周一，盘后 19:30 左右）。

---

## 1. 连通性矩阵（最重要的一节）

| 域名 | 用途 | 当日状态 |
|---|---|---|
| `push2ex.eastmoney.com` | 涨停池 / 炸板池 / 跌停池 | ✅ 通 |
| `push2his.eastmoney.com` | 个股日K / 资金流 / 指数 | ✅ 通 |
| `datacenter-web.eastmoney.com` | 龙虎榜 | ✅ 通 |
| `push2.eastmoney.com` | 全市场快照（clist） | ❌ 全链路 RemoteDisconnected |

`push2` 挂了**连 http 直连和 82.push2 / push2delay 备用域名一起挂**，
所以「换域名」不是有效兜底。本技能因此完全不依赖 clist：

- 全市场涨跌家数 → 不做（用涨停/炸板/跌停数 + 指数表达情绪）
- 主力资金净流入 → 逐票 `fflow`（125 只 × 1 请求，8 并发约 15 秒）
- 行业板块涨幅 → 不做（改用涨停股按 `hybk` 聚合的行业涨停家数，更贴「题材热度」本意）

`http_client.fetch_json` 对每个请求做「信任环境代理 → 直连」双通道 ×2 次重试。
本机代理对不同域名的连通性是随机的，不要假设某天通就一直通。

---

## 2. 涨停池

```
GET https://push2ex.eastmoney.com/getTopicZTPool
    ?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt
    &Pageindex=0&pagesize=300&sort=fbt:asc&date=YYYYMMDD
```

响应 `data.tc` = 全池数量，`data.pool` = 明细数组。

| 字段 | 含义 | 单位/坑 |
|---|---|---|
| `c` / `m` / `n` | 代码 / 市场 / 名称 | m=0 深、1 沪 |
| `p` | 最新价 | **×1000**（4940 = 4.94 元） |
| `zdp` | 涨跌幅 | % |
| `amount` | 成交额 | 元 |
| `ltsz` | 流通市值 | 元 |
| `tshare` | 总市值 | 元 |
| `hs` | 换手率 | % |
| `lbc` | 连板数 | 1 = 首板 |
| `fbt` / `lbt` | 首封 / 最后封板时间 | HHMMSS 整数（92500 = 09:25:00） |
| `fund` | 封板资金 | 元 |
| `zbc` | 炸板次数 | 次 |
| `hybk` | 行业板块 | 中文，东财行业分类 |
| `zttj` | 涨停统计 | `{days, ct}` |

`date` 参数生效（`20261030` 返回 47 只，`20261102` 返回 125 只）。
非交易日会返回最近交易日的数据，`qdate` 字段可核对。

---

## 3. 炸板池 / 跌停池

```
getTopicZBPool   sort=fbt:asc     → 明细正常
getTopicDTPool   sort=fbt:asc     → tc=8, pool=[]   ⚠ 空表
getTopicDTPool   sort=lbc:asc     → tc=8, pool=[]   ⚠ 空表
getTopicDTPool   sort=fund:asc    → tc=8, pool=8    ✅
getTopicDTPool   不带 sort        → tc=0, pool=[]   ⚠ 静默零值
```

**跌停数只能信 fund/zdp 排序下的 tc。** 不带 sort 时接口返回 `tc=0` 而不报错，
是本次开发踩到的最隐蔽的坑——看板会平静地显示「跌停 0 只」，而实际有 8 只。

---

## 4. 龙虎榜

```
GET https://datacenter-web.eastmoney.com/api/data/v1/get
    ?pageSize=500&pageNumber=1
    &reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL
    &filter=(TRADE_DATE%3D%272026-11-02%27)
    &source=WEB&client=WEB
```

⚠ **不能带 `sortColumns=NET_BUY_AMT`**，会返回
`{"success":false,"message":"NET_BUY_AMT排序列不存在"}`。不排序即可。

分页返回 `result.pages`（当日 81 页 @ pageSize 50），本实现用 pageSize=500 拉全量。

| 字段 | 含义 |
|---|---|
| `SECURITY_CODE` / `SECURITY_NAME_ABBR` | 代码 / 名称 |
| `EXPLANATION` | 上榜原因（同一股票可能多条：涨幅偏离、换手率、连续三日等） |
| `NET_BS_AMT` / `BILLBOARD_NET_AMT` | 净买入额（元） |
| `BILLBOARD_BUY_AMT` / `BILLBOARD_SELL_AMT` | 龙虎榜买入/卖出额（元） |
| `BUY_SEAT` / `SELL_SEAT` | 席位名串，含「机构专用」即为机构上榜 |

聚合口径：`count = 上榜原因去重条数`（原看板「4次」即此口径）。

---

## 5. 个股日K

```
GET https://push2his.eastmoney.com/api/qt/stock/kline/get
    ?secid=0.300563&klt=101&fqt=1&lmt=140&end=20500101
    &fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61
```

`secid`：6/5/9 开头 → `1.xxx`；其余 → `0.xxx`（北交所也用 0）。
`fqt=1` 前复权。返回行格式：

```
日期, 开, 收, 高, 低, 成交量(手), 成交额(元), 振幅, 涨跌幅, 涨跌额, 换手率
```

盘后调用时最后一根即当日。**代码里会核对 `k[-1].date == trade_date`**，
不一致则记 `K线滞后至 xxx` 告警（不静默接受）。

`lmt=140` 是为了留足 60 日新高判定 + 5 日均额计算所需的余量。

---

## 6. 资金流

```
GET https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get
    ?lmt=0&klt=101&secid=0.300563
    &fields1=f1,f2,f3,f7&fields2=f51,f52,...,f65
```

行格式（实测顺序）：

```
日期, 主力净流入, 小单, 中单, 大单, 超大单, 主力净占比, 小单占比, ...
```

**自洽校验**：`主力净流入 ≈ 大单 + 超大单`，差值记入 `check_gap`。
这条校验防的是「字段错位」——东财这套接口的 fields2 顺序不保证跨版本稳定，
错一位就会把「小单」当「主力」，而结果看起来依然是个合理的数字。

当前实现取 `fflow` 最后一条作为当日主力净流入，前 5 条求和作为 5 日累计。

---

## 7. 指数

用 `kline` 接口取最近 3 根日线自算涨跌幅（不依赖 clist 的实时快照）：

| 指数 | secid |
|---|---|
| 上证指数 | `1.000001` |
| 深证成指 | `0.399001` |
| 创业板指 | `0.399006` |
| 科创50 | `1.000688` |

指数日线也用于推导最近交易日（`trade_dates`），避免自己维护节假日表。

---

## 8. 已知未覆盖

- **北交所**：涨跌幅 30%，`limit_ratio` 已按 8/4/92 前缀处理，但涨停池里北交所
  标的极少，未做专项验证。
- **ST 股**：5% 限制，靠名称含 "ST" 判断。若东财返回的名称带 `*ST` 前缀可识别，
  但退市整理期（10%/20%/30% 特殊规则）未覆盖。
- **新股上市首日**：无涨跌幅限制，会被 `is_limit_up` 判为不通过，属预期行为。
- **历史回测**：`--date` 可拉任意历史交易日，但当时龙虎榜/资金流的可得性取决于
  东财历史数据保留策略，未做逐日完整性验证。
