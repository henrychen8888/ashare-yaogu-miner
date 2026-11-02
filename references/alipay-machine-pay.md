# 支付宝 AI 按量付费（Machine Pay / A2M）接入规范摘要

来源：支付宝 AI 付官方文档
- 产品接入指南 `https://aipay.alipay.com/docs/ai-receive/MACHINE_PAY.html`（更新 2026-10-21）
- AI Agent 按量付费接入指南 `https://aipay.alipay.com/article/388`（发布 2026-09-12）
- Skill Pay 接入架构与安全设计 `https://aipay.alipay.com/article/266`

> 本文是**二次整理**，不是官方文档。字段名照抄官方页面，但费率、准入、接口权限以
> 签约页面与开放平台当期文档为准。官方原文明确写着「对于官方没有公开的信息，我们不会自行推断」，
> 本文同样不推断。

---

## 1. 协议本质

一个**受 HTTP 保护的资源端点**：请求不带支付凭证时返回 `402 Payment Required`，
客户端付款后带 `Payment-Proof` 重试同一请求，服务端验付通过才返回资源。

```
Client                    Server                      Alipay
  │  GET /resource          │                            │
  │───────────────────────>│  需要付费                   │
  │                        │  payment.precreate ───────>│
  │                        │<── amt_pre_pay_id          │
  │  402 Payment Required  │                            │
  │  amtPaymentLink: amtpp_v1_xxx                       │
  │<───────────────────────│                            │
  │  用户在支付宝完成付款   │                            │
  │───────────────────────────────────────────────────>│
  │  GET /resource         │                            │
  │  Payment-Proof: <b64>  │                            │
  │───────────────────────>│  payment.verify ──────────>│
  │                        │<── active/amount/...       │
  │  200 OK + 资源         │                            │
  │<───────────────────────│  fulfillment.confirm ─────>│
```

## 2. 六个强制环节

| # | 环节 | 接口 / 头部 | 关键点 |
|---|---|---|---|
| 1 | 预下单 | `alipay.aipay.agent.payment.precreate` | 返回 `amt_pre_pay_id` |
| 2 | 下发账单 | HTTP `402` + 响应头 `amtPaymentLink` | 头值是预下单号，**不是账单 JSON** |
| 3 | 用户支付 | 支付宝客户端 | Agent 只编排，不代付 |
| 4 | 凭证重试 | 请求头 `Payment-Proof`（Base64） | 解出 `payment_proof` / `trade_no` / `client_session` |
| 5 | 验付 | `alipay.aipay.agent.payment.verify` | 不能只看调用成功，要核字段 |
| 6 | 履约回执 | `alipay.aipay.agent.fulfillment.confirm` | 交付完成后调用，失败需可重试且幂等 |

## 3. precreate 参数（官方原文）

| 参数 | 要求 | 说明 |
|---|---|---|
| `out_trade_no` | 必选 | 商户订单号，用于幂等控制 |
| `service_id` | 必选 | 按量付费注册分配的服务标识 |
| `goods_name` | 必选 | 商品或服务名称 |
| `amount` | 必选 | 接口付费金额，单位元，**不超过 50 元** |
| `pay_before` | 必选 | 支付截止时间 |
| `currency` | 可选 | 仅支持 `CNY` |
| `memo` | 可选 | 交易备注 |

## 4. Payment-Proof 结构（官方示例，Base64 解开后）

```json
{
  "protocol": {
    "payment_proof": "7cf8a6a9...",
    "trade_no": "20260409********************xxxx"
  },
  "method": {
    "client_session": "xxxx..."
  }
}
```

三字段即 verify 的入参。

## 5. verify 响应与**五项必核**

```json
{
  "alipay_aipay_agent_payment_verify_response": {
    "code": "10000", "msg": "Success",
    "amount": "0.01",
    "out_trade_no": "ORDER_1774598472720_etm5dy",
    "trade_no": "20260324********************2182",
    "resource_id": "out_res_id_0000123",
    "active": true
  }
}
```

官方明确写了，`code=10000` 不等于可以交付，必须逐条核：

1. `active` 必须为 `true`
2. `amount` 必须等于**本次资源价格**
3. `out_trade_no` 必须等于**你自己生成的商户订单号**
4. `resource_id` 必须与**用户本次访问的资源**一致
5. `trade_no` **不得被重复履约**（同一笔支付只能用一次）

## 6. 安全与工程红线（官方口径）

- **验签顺序**：验签 → 核单 → 幂等更新 → 交付权益。反例「先发货后异步验签」会导致
  伪造通知 / 金额不符 / 重复通知时重复发货。
- **金额由服务端算**，前端或 Agent 只提交商品选择，避免篡改参数错价购买。
- **应用私钥只存服务端**（环境变量 / KMS 注入），禁止进包内、日志、公开仓库。
  Java 用 PKCS#8，非 Java 用 PKCS#1。
- **RSA2 2048 位**（支付宝开放平台密钥方案）。
- **不把客户端展示结果当履约依据**：页面跳转、App 回跳、Agent 端显示成功都不算。
- **异步通知与主动查单不能替代 402 流程**，只能作为状态补偿，且必须进入同一套幂等逻辑。
- **测试环境的支付按钮 ≠ 生产权限已开通**。上线前要分别核对应用、商户、产品签约、密钥
  是否属于同一主体与同一环境。
- **退款**：先定位计量明细，再调权益与账本，不能只改支付金额而保留原额度。

## 7. 常见错误认知（社区流传版本 vs 官方）

搜索「支付宝 按量付费 改造」会看到大量技能页面写成这样：

> 返回 402，`Payment-Needed` 头携带 Base64URL 编码的**账单 JSON**；
> `protocol` 层含 `seller_signature` / `seller_sign_type` / `seller_unique_id`，
> `method` 层含 `seller_name` / `seller_app_id` / `service_id`，商户按 key 字典序
> RSA2 自签名后下发。

**这与官方 MACHINE_PAY 文档不一致**，差异点：

| 项 | 官方当前文档 | 社区流传写法 |
|---|---|---|
| 402 响应头 | `amtPaymentLink`（值 = 预下单号 `amtpp_v1_xxx`） | `Payment-Needed`（值 = 完整账单 JSON 的 Base64） |
| 账单由谁生成 | 支付宝 `precreate` 生成 | 商户自己拼 JSON 并 RSA2 签名 |
| 商户签名 | 由 SDK 对接口请求签名（标准开放平台签名） | 在账单体内自定义 `seller_signature` |
| `protocol` / `method` | 出现在 **Payment-Proof** 结构中 | 被用在**账单**结构里 |

判断：`protocol`/`method` 双层结构确实是官方概念，但按官方文档它属于 **Payment-Proof**，
不是商户下发的账单。社区写法可能是旧版本、或某平台自封装的一层。

**接入时必须以 `aipay.alipay.com/docs/ai-receive/MACHINE_PAY.html` 当期内容为准**，
不要照抄第三方技能页面的字段名。

## 8. 本技能的接入差距

`ashare-yaogu-miner` 当前形态是**本地批处理 CLI**，不是 HTTP 服务：

| 官方要求 | 本技能现状 | 差距 |
|---|---|---|
| 受保护的 HTTP 资源端点 | `python scripts/run.py` 本地跑 | ❌ 需要新增 HTTP 门面 |
| 服务端可信计量 | 无计量层（本地执行） | ❌ 需要按次计量记录 |
| 订单持久化 + 幂等 | 无订单概念 | ❌ 需要订单表（文件/SQLite） |
| 商户凭证（app_id / 私钥 / service_id） | 无 | ❌ 需要你自己的商户资质 |
| 履约回执 | 有产出（HTML+JSON）可作交付物 | ✅ 可映射 |

最小改造路径：

1. 新增 `server/aipay_gateway.py`（建议 Flask/FastAPI），暴露
   `GET /api/yaogu/board?date=YYYYMMDD`
2. 无 `Payment-Proof` → `precreate` → `402 + amtPaymentLink`
3. 有 `Payment-Proof` → `verify` → 五项必核 → 调 `run.py` 生成看板 → 返回
4. 交付后 `fulfillment.confirm`
5. 订单落 SQLite（`out_trade_no` 唯一索引），`trade_no` 已履约则直接返回上次结果

工作量约 250-300 行 + 商户资质申请，**且必须有真实凭证才能联调**。

## 9. 什么情况下不要接这套

官方原文的「不适用场景」直接命中本技能的一部分情况：

- 「如果我们还不能稳定记录用量，不建议直接上线按量付费，可以先采用固定次数包或会员方案」
- 「如果单次服务无法量化……建议采用普通订单支付」
- 「如果 Agent 无法在付款前向用户展示金额、商品和计费依据，不会让它自动发起交易」

本技能**可以**稳定计量（一次看板生成 = 一次调用），符合按量条件；
但它当前没有服务端，也没有不可复制的后端能力。

### 关于「交给平台托管就不用改造」——**这个说法是错的**

SkillHub 的上架入口把发布类型分成两类：发布 Skill（最快上架）、
发布 **Pay Skill（需支付改造）**。

2026-09 一位创作者的上架复盘写得很直白：「普通的开源技能……可以通过官方 CLI 上传；
如果想要发布 pay skill 需要通过支付宝的改造，所以付费技能的第一次上传，不能通过官方
CLI 来进行，需要手动上传。」

已上架的 Pay Skill 实际长这样（技能包内自带）：

- `scripts/payment_gate.py` —— 本地付费闸口，处理 402 / 验签 / 持久化三件事
- `.pay_cache/state.json` —— 付费状态缓存，同一 Payment-Proof 24h 幂等窗口
- 云端计费端点（如 `https://pay.xxx.cn/api/resource`）—— 商户自建或改造工具生成

也就是说：**平台提供的是计费调度与收款通道，付费闸口和受保护的资源端点仍要自己实现。**
平台调度层负责把 probe → 402 → pay → complete → ack 串起来，脚本侧必须配合。

### 更硬的一条门槛：付费技能要求「被复制走也跑不起来」

公开的上架经验里有一条硬判断：

> 付费 Skill 要求能力依赖你自己的后端服务——文件被复制走也跑不起来，核心锁在你手里。
> 如果你拿得出手的只是一段提示词、一份方法论，它只能是免费 Skill 引流，收不了费。

`ashare-yaogu-miner` 目前是**纯本地脚本**：东财接口公开、评分逻辑在 `engine.py` 里，
整个目录复制走就能用。按上述口径，它**不具备做成 Pay Skill 的前提**——
除非把核心能力搬到服务端，技能包内只留调用桩。

### 三条路，选一条

| 路径 | 真实代价 | 是否适配本技能 |
|---|---|---|
| **免费发布** | CLI 打包上传，网页补详情页 | ✅ 当前形态即可 |
| **Pay Skill（接平台计费）** | 需内置付费闸口 + 受保护资源端点 + 不可复制后端 | ❌ 需先把能力搬到服务端 |
| **自建 402（直连支付宝）** | 商户资质 + HTTPS 服务 + 250-300 行服务端代码 | ❌ 同上，且改造量最大 |

「先免费引流、有需要再上后端」是这类本地工具的现实选择。
