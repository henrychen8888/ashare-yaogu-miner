# -*- coding: utf-8 -*-
"""
五维加权妖股概率引擎。

权重（**来自原始看板披露**，不是拍脑袋）：
    主力资金净流入 30 / 龙虎榜 25 / 量能特征 25 / 题材级别 10 / 均线与K线形态 10
原始看板只给了资金 30、龙虎 25、形态 10 三个明确权重，以及「≥80 高分、60-79 潜力」
两档分级；量能 25 与题材 10 是按其展示的五维平均分（23.2/5.3/13.9/9.4/8.4）
反推补全的，使总和为 100。

**档位阈值由我设定**（原看板未公开），依据是当日涨停池的实际分布，
全部集中在本文件，便于审计与调整。见 references/scoring_model.md。

一条硬规则：任何维度拿不到数据时，返回 None 并在 warnings 里留痕，
**绝不 fallback 成中间分**——静默补一个「看起来合理」的分，是这类工具最危险的失败模式。
"""
from __future__ import annotations

from statistics import mean
from typing import Any

WEIGHTS = {"capital": 30.0, "lhb": 25.0, "volume": 25.0, "theme": 10.0, "pattern": 10.0}

TIERS = [
    (80.0, "S", "妖股候选", "#e5484d"),
    (70.0, "A", "强关注", "#f76808"),
    (60.0, "B", "潜力区间", "#f5a524"),
    (0.0, "C", "观察", "#8b8d98"),
]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _grade(value: float, steps: list[tuple[float, float]]) -> float:
    """steps 为 (阈值下限, 得分) 降序表，取第一个满足的档位。"""
    for lower, score in steps:
        if value >= lower:
            return score
    return 0.0


# ---------------------------------------------------------------- 各维度
# 档位锚点全部来自 2026-11-02 涨停池 125 只的实测分位（见 references/scoring_model.md）：
#   net_main      P10 0.13亿  P25 0.22亿  P50 0.47亿  P75 0.91亿  P90 1.90亿  P95 3.06亿
#   turnover      P25 3.42%   P50 6.62%   P75 10.97%  P90 17.30%
#   vol_ratio     P25 0.87x   P50 1.39x   P75 1.97x   P90 3.12x
#   seal_ratio    P25 0.19%   P50 0.56%   P75 1.26%   P90 2.07%
# 设计意图：中位票拿维度分的 ~65-70%，P90 以上接近满分，头部个股才有资格进 S 级。
def score_capital(net: float, cum5: float, float_cap: float) -> float:
    base = _grade(net, [
        (3.0e8, 29.0), (2.0e8, 27.5), (1.2e8, 25.5), (9.0e7, 24.5),
        (6.0e7, 22.0), (4.7e7, 20.0), (3.0e7, 17.0), (1.3e7, 13.5), (0.0, 9.0),
    ]) if net >= 0 else 3.0

    ratio = net / float_cap if float_cap > 0 else 0.0
    bonus = _grade(ratio, [(0.04, 1.5), (0.02, 1.0), (0.01, 0.6)])

    trend = 0.0
    if cum5 < 0:
        trend = -3.0
    elif cum5 > net:
        trend = 1.0

    return _clamp(base + bonus + trend, 0.0, WEIGHTS["capital"])


def score_lhb(info: dict | None) -> float:
    """
    未上榜给 4.0 基线分（占权重 16%）。理由：无龙虎榜记录同时意味着
    「未被异动监控」，既不是利空也不是利好，给 0 会让 94/125 只票在这一维
    完全无差别，等于把这 25 分权重白扔掉。基线分在文档里已显式标注。
    """
    if not info or not info.get("count"):
        return 4.0
    count = int(info.get("count") or 0)
    base = _grade(count, [(3, 18.0), (2, 15.0), (1, 10.0)])
    net = float(info.get("net_buy") or 0)
    bonus = _grade(net, [(2e8, 7.0), (1e8, 5.5), (5e7, 4.0)]) if net > 0 else (
        -2.0 if net < 0 else 2.0)
    inst = 2.5 if info.get("institution") else 0.0
    return _clamp(base + bonus + inst, 0.0, WEIGHTS["lhb"])


def score_volume(turnover: float, vol_ratio: float | None, seal_ratio: float,
                 first_seal: str, broken: int) -> float:
    # 换手率是区间型指标（不是单调指标），必须逐段判，不能用降序阈值表 ——
    # 否则 turnover=20 会命中「≥5」直接拿满分，把过热当最佳。
    # 4-25% 视为「充分换手」（妖股常态），>35% 才按过热处理。
    if 4 <= turnover < 25:
        t = 9.0
    elif 2 <= turnover < 4 or 25 <= turnover < 35:
        t = 7.0
    elif 1 <= turnover < 2 or 35 <= turnover < 50:
        t = 5.0
    else:
        t = 3.5

    if vol_ratio is None:
        v = 4.8  # 次新股历史不足，给中性偏低分（不静默补中间值）
    elif vol_ratio >= 2.5:
        v = 8.5
    elif vol_ratio >= 1.8:
        v = 7.2
    elif vol_ratio >= 1.2:
        v = 5.8
    elif vol_ratio >= 0.9:
        v = 4.2
    else:
        v = 2.8

    s = _grade(seal_ratio, [(0.03, 5.0), (0.015, 4.2), (0.008, 3.2), (0.003, 2.2)]) or 1.2

    try:
        hhmmss = int(first_seal)
    except (TypeError, ValueError):
        hhmmss = 150000
    f = 2.5 if hhmmss <= 100000 else 1.9 if hhmmss <= 110000 else 1.4 if hhmmss <= 140000 else 0.9

    penalty = -min(int(broken or 0), 3)
    return _clamp(t + v + s + f + penalty, 0.0, WEIGHTS["volume"])


def score_theme(industry_count: int, in_top3: bool, boards: int) -> float:
    base = _grade(industry_count, [(6, 7.0), (4, 6.5), (3, 6.0), (2, 5.5), (1, 5.0)])
    hot = 1.8 if in_top3 else 0.0
    relay = 1.2 if boards >= 3 else 0.6 if boards == 2 else 0.0
    return _clamp(base + hot + relay, 0.0, WEIGHTS["theme"])


def score_pattern(k: list[dict], trade_date: str, boards: int) -> tuple[float, dict]:
    """
    k 为前复权日线升序。返回 (得分, 明细)。
    不足 25 根 K 线时按「形态不可判定」给 3.0 并留 note，不假装形态成立。
    """
    detail = {"breakout": False, "ma_bull": False, "vol_break": False, "strong": False}
    if len(k) < 25:
        return 3.0, {**detail, "note": "K线不足25根"}

    closes = [x["close"] for x in k]
    today = k[-1]
    hist_close = closes[:-1]
    vol_ratio = _vol_ratio(k)

    p = 2.0
    if len(hist_close) >= 60 and today["close"] >= max(hist_close[-60:]):
        p, detail["breakout"] = 4.2, True
    elif len(hist_close) >= 20 and today["close"] >= max(hist_close[-20:]):
        p, detail["breakout"] = 3.4, True

    ma5, ma10, ma20 = mean(closes[-5:]), mean(closes[-10:]), mean(closes[-20:])
    if ma5 > ma10 > ma20:
        p += 3.0
        detail["ma_bull"] = True
    elif today["close"] > ma5 and today["close"] > ma10:
        p += 2.2
    elif today["close"] > ma5:
        p += 1.5

    if vol_ratio and vol_ratio >= 1.5 and today["close"] > ma20:
        p += 2.0
        detail["vol_break"] = True

    gain5 = (today["close"] / closes[-6] - 1) * 100 if len(closes) >= 6 else 0.0
    if boards >= 2 and gain5 >= 25:
        p += 0.8
        detail["strong"] = True

    return _clamp(p, 0.0, WEIGHTS["pattern"]), detail


def _vol_ratio(k: list[dict]) -> float | None:
    """当日成交额 / 前5日均成交额。"""
    if len(k) < 6:
        return None
    base = mean([x["amount"] for x in k[-6:-1]])
    if base <= 0:
        return None
    return k[-1]["amount"] / base


# ---------------------------------------------------------------- 汇总
def evaluate(stock: dict, k: list[dict] | None, flows: list[dict] | None,
             lhb_info: dict | None, industry_count: int, industry_top3: bool,
             trade_date: str) -> dict:
    warnings: list[str] = []
    dims: dict[str, float | None] = {}

    # ---- 资金
    net = cum5 = 0.0
    if not flows:
        warnings.append("无资金流数据")
        dims["capital"] = None
    else:
        if flows[-1]["date"] != trade_date:
            warnings.append(f"资金流滞后至 {flows[-1]['date']}")
        net = flows[-1]["main"]
        cum5 = sum(x["main"] for x in flows[-5:])
        dims["capital"] = round(score_capital(net, cum5, stock["float_cap"] or 1.0), 1)

    # ---- 龙虎榜
    dims["lhb"] = round(score_lhb(lhb_info), 1)

    # ---- 量能
    if not k:
        warnings.append("无K线数据")
        dims["volume"] = None
    else:
        if k[-1]["date"] != trade_date:
            warnings.append(f"K线滞后至 {k[-1]['date']}")
        vr = _vol_ratio(k)
        seal_ratio = (stock["seal_fund"] / stock["float_cap"]) if stock["float_cap"] else 0.0
        dims["volume"] = round(score_volume(
            stock["turnover"], vr, seal_ratio, stock["first_seal"], stock["broken"]), 1)

    # ---- 题材
    dims["theme"] = round(score_theme(industry_count, industry_top3, stock["boards"]), 1)

    # ---- 形态
    if k:
        pattern, detail = score_pattern(k, trade_date, stock["boards"])
        dims["pattern"] = round(pattern, 1)
    else:
        detail = {}
        dims["pattern"] = None

    # ---- 总分：任一维度缺失时不补分，按可得维度归一化后标注
    if any(v is None for v in dims.values()):
        avail = {k2: v for k2, v in dims.items() if v is not None}
        wsum = sum(WEIGHTS[k2] for k2 in avail)
        total = round(sum(avail.values()) / wsum * 100, 1) if wsum else 0.0
        warnings.append("部分维度缺失，总分按可得维度归一化")
    else:
        total = round(sum(dims.values()), 1)

    tier = next(t for t in TIERS if total >= t[0])

    return {
        **{k2: stock[k2] for k2 in ("code", "name", "close", "pct", "boards",
                                    "industry", "turnover", "amount", "float_cap",
                                    "seal_fund", "broken", "first_seal")},
        "net_main": net,
        "cum5_main": cum5,
        "vol_ratio": round(_vol_ratio(k), 2) if k else None,
        "lhb_count": (lhb_info or {}).get("count", 0),
        "lhb_net": (lhb_info or {}).get("net_buy", 0.0),
        "lhb_inst": bool((lhb_info or {}).get("institution")),
        "dims": dims,
        "total": total,
        "tier": tier[1],
        "tier_label": tier[2],
        "tier_color": tier[3],
        "pattern_detail": detail,
        "warnings": warnings,
        "reasons": build_reasons(stock, net, cum5, lhb_info, dims, detail, industry_count),
    }


def build_reasons(stock: dict, net: float, cum5: float, lhb_info: dict | None,
                  dims: dict, pattern: dict, industry_count: int) -> list[str]:
    rs: list[str] = []
    if net >= 1e8:
        rs.append(f"主力净流入 {net/1e8:.2f} 亿")
    elif net > 0:
        rs.append(f"主力净流入 {net/1e4:.0f} 万")
    else:
        rs.append(f"主力净流出 {abs(net)/1e4:.0f} 万")
    if cum5 > 0:
        rs.append(f"近5日累计净流入 {cum5/1e8:.2f} 亿")
    if lhb_info and lhb_info.get("count"):
        rs.append(f"龙虎榜 {lhb_info['count']} 次")
        if lhb_info.get("net_buy"):
            rs.append(f"席位净买 {lhb_info['net_buy']/1e8:.2f} 亿")
    if lhb_info and lhb_info.get("institution"):
        rs.append("机构席位现身")
    if stock["boards"] >= 2:
        rs.append(f"{stock['boards']} 连板")
    if industry_count >= 3:
        rs.append(f"所属行业当日涨停 {industry_count} 家")
    if pattern.get("breakout"):
        rs.append("突破前高")
    if pattern.get("ma_bull"):
        rs.append("均线多头排列")
    if stock["broken"] == 0 and stock["first_seal"] <= "110000":
        rs.append("早盘一次封停未炸板")
    return rs[:6]
