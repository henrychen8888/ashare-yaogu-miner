# -*- coding: utf-8 -*-
"""
交付前自检。全绿才算完成，任一 ❌ 必须如实报告，不允许用文字描述替代实际检查。

检查项设计针对本工具最容易出的四类静默错误：
  1. 涨停判定错（20cm 票当 10cm 校验、ST 漏判）→ 算术复核
  2. 分数不自洽（五维和 ≠ 总分）→ 逐股比对
  3. 渲染泄漏（None / nan / 键缺失）→ HTML 文本扫描
  4. 数据覆盖率虚高（部分票没拉到却算完）→ 覆盖率核对
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import engine
import sources
from run import WORK  # 产物目录与 run.py 保持单一来源，避免两边指向不同位置

PASS, FAIL = "✅", "❌"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def main() -> int:
    files = sorted(WORK.glob("yaogu_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        print(f"{FAIL} 未找到快照 JSON，请先运行 run.py")
        return 1

    snap = files[-1]
    data = json.loads(snap.read_text(encoding="utf-8"))
    html_path = WORK / (snap.stem + ".html")
    html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    rows = data["rows"]
    stats = data["stats"]

    # 1 结构完整
    check("快照可解析且非空", bool(rows), f"{snap.name} / {len(rows)} 行")
    check("HTML 已生成", len(html) > 5000, f"{len(html)} 字符")

    # 2 总分自洽
    bad = []
    for r in rows:
        dims = r["dims"]
        if any(v is None for v in dims.values()):
            continue
        total = round(sum(dims.values()), 1)
        if abs(total - r["total"]) > 0.15:
            bad.append(f"{r['name']} {total}≠{r['total']}")
    check("五维之和 == 总分", not bad, "；".join(bad[:3]) or f"全部 {len(rows)} 只一致")

    # 3 维度边界
    over = []
    for r in rows:
        for k, v in r["dims"].items():
            if v is None:
                continue
            if v < -0.01 or v > engine.WEIGHTS[k] + 0.01:
                over.append(f"{r['name']}.{k}={v}")
    check("各维度不越界", not over, "；".join(over[:3]) or "全部在 [0, 权重] 内")

    # 4 总分区间
    out = [r for r in rows if not (0 <= r["total"] <= 100)]
    check("总分落在 0-100", not out, f"{len(out)} 只越界")

    # 5 涨停算术复核（全量）
    bad_limit = []
    for r in rows:
        if not sources.is_limit_up(r["close"], r["pct"], r["code"], r["name"]):
            bad_limit.append(f"{r['name']}({r['code']}) {r['pct']:+.2f}%")
    check("涨停股算术校验通过", not bad_limit,
          f"{len(bad_limit)} 只未通过：" + "；".join(bad_limit[:3]) if bad_limit
          else f"全部 {len(rows)} 只符合涨跌幅限制")

    # 6 数据覆盖率
    ready = stats.get("data_ready", {})
    cov_k = ready.get("kline", 0) / max(stats.get("scored", len(rows)), 1) * 100
    cov_f = ready.get("flow", 0) / max(stats.get("scored", len(rows)), 1) * 100
    check("K线覆盖率 ≥98%", cov_k >= 98, f"{cov_k:.1f}%")
    check("资金流覆盖率 ≥98%", cov_f >= 98, f"{cov_f:.1f}%")

    # 7 HTML 渲染泄漏（必须带词边界：裸 "nan" 会命中 SVG 的 dominant-baseline）
    leaks = [w for w in ("None", "nan", "NaN", "Traceback")
             if re.search(rf"(?<![\w-]){w}(?![\w-])", html)]
    check("HTML 无 None/nan/异常泄漏", not leaks, "；".join(leaks) or "干净")

    # 8 关键锚点
    anchors = ["妖股挖掘", "五维", "不构成任何投资建议", "<table>", "<svg"]
    miss = [a for a in anchors if a not in html]
    check("HTML 关键锚点齐全", not miss, "缺：" + "、".join(miss) if miss else f"{len(anchors)} 项全present")

    # 9 表格行数
    trs = len(re.findall(r"<tr>", html)) - 1  # 去掉表头
    expect = min(data.get("top_n", 20), len(rows))
    check("表格行数符合预期", trs == expect, f"实际 {trs} / 期望 {expect}")

    # 10 行业统计自洽
    ind_sum = sum(c for _, c in stats["industry_top"])
    check("行业分布不超涨停总数", ind_sum <= stats["zt_count"] + 1,
          f"行业合计 {ind_sum} / 涨停 {stats['zt_count']}（Top15 截断属正常）")

    # 11 分档计数自洽
    tsum = stats["tier_s"] + stats["tier_a"] + stats["tier_b"] + stats["tier_c"]
    check("分档计数 == 评分只数", tsum == len(rows), f"{tsum} / {len(rows)}")

    # 12 数值有限性
    nonfinite = []
    for r in rows:
        for k in ("total", "net_main", "turnover"):
            v = r.get(k)
            if v is not None and (math.isnan(v) or math.isinf(v)):
                nonfinite.append(f"{r['name']}.{k}")
    check("无 NaN/Inf 数值", not nonfinite, "；".join(nonfinite[:3]) or "全部有限")

    print(f"\n自检对象：{snap.name}（交易日 {data['trade_date']}，{len(rows)} 只）\n")
    for name, ok, detail in results:
        print(f"  {PASS if ok else FAIL} {name}  —  {detail}")
    failed = [r for r in results if not r[1]]
    print(f"\n结果：{len(results) - len(failed)} 通过 / {len(failed)} 失败\n")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
