# -*- coding: utf-8 -*-
"""
HTML 看板渲染。零 CDN、零 JS 依赖，纯内联 CSS + SVG —— 断网也能正常打开。

配色遵循 A 股约定：涨红跌绿（与欧美相反）。
"""
from __future__ import annotations

import html
import math
from typing import Any

from engine import WEIGHTS

CSS = """
:root{
  --bg:#0b0f16; --panel:#141a24; --panel2:#1b2330; --line:#252f3d;
  --tx:#e8eef7; --tx2:#93a1b5; --tx3:#63748c;
  --up:#e5484d; --down:#2fa96b; --gold:#f5a524; --blue:#4b8bf5; --violet:#a475f9;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);
  font-family:"PingFang SC","Microsoft YaHei",system-ui,-apple-system,sans-serif;
  font-size:14px;line-height:1.55;padding:28px 32px 60px;-webkit-font-smoothing:antialiased}
.wrap{max-width:1280px;margin:0 auto}
h1{font-size:26px;font-weight:700;letter-spacing:.5px}
h1 .sub{font-size:14px;font-weight:400;color:var(--tx2);margin-left:12px}
.head{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px;
  padding-bottom:16px;border-bottom:1px solid var(--line)}
.stamp{color:var(--tx3);font-size:12px;text-align:right;line-height:1.8}
.disc{margin:16px 0;background:rgba(245,165,36,.08);border-left:3px solid var(--gold);
  border-radius:4px;padding:10px 14px;color:#f0c987;font-size:12.5px}
.srcs{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.chip{background:var(--panel);border:1px solid var(--line);border-radius:999px;
  padding:5px 12px;font-size:12px;color:var(--tx2)}
.chip b{color:var(--tx);font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-bottom:20px}
.kpi{background:linear-gradient(160deg,var(--panel2),var(--panel));border:1px solid var(--line);
  border-radius:10px;padding:14px 16px;position:relative;overflow:hidden;min-width:0}
.kpi::after{content:"";position:absolute;top:0;left:0;width:3px;height:100%;background:var(--blue);opacity:.8}
.kpi.red::after{background:var(--up)} .kpi.gold::after{background:var(--gold)}
.kpi.green::after{background:var(--down)} .kpi.violet::after{background:var(--violet)}
.kpi .lbl{font-size:12px;color:var(--tx2);margin-bottom:6px;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.kpi .val{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.1;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi .foot{font-size:11.5px;color:var(--tx3);margin-top:5px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.idx{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:26px;padding:12px 16px;
  background:var(--panel);border:1px solid var(--line);border-radius:8px;font-size:13px}
.idx span{color:var(--tx2)} .idx b{font-variant-numeric:tabular-nums;margin:0 6px 0 4px}
.sec{margin-bottom:30px}
.sec h2{font-size:16px;font-weight:600;margin-bottom:12px;display:flex;align-items:center;gap:9px}
.sec h2::before{content:"";width:3px;height:15px;background:var(--up);border-radius:2px}
.sec h2 .note{font-size:12px;font-weight:400;color:var(--tx3);margin-left:4px}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:16px;align-items:start}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.card h3{font-size:13px;color:var(--tx2);font-weight:600;margin-bottom:12px;
  letter-spacing:.4px;text-transform:uppercase}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;
  table-layout:auto}
.tblwrap{overflow-x:auto}
th{text-align:right;color:var(--tx3);font-weight:500;font-size:12px;padding:8px 8px;
  border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,th:nth-child(2){text-align:left}
th:last-child{text-align:left}
td{text-align:right;padding:9px 8px;border-bottom:1px solid rgba(37,47,61,.55);white-space:nowrap}
td:first-child,td:nth-child(2){text-align:left}
tr:hover td{background:rgba(75,139,245,.05)}
.rk{color:var(--tx3);font-size:12px;width:34px}
.nm{font-weight:600} .cd{color:var(--tx3);font-size:11.5px;margin-left:6px;font-weight:400}
.score{font-weight:700;font-variant-numeric:tabular-nums}
.bar{display:inline-block;width:44px;height:4px;background:var(--panel2);border-radius:2px;
  margin-left:8px;vertical-align:middle;overflow:hidden}
.bar i{display:block;height:100%;border-radius:2px}
.up{color:var(--up)} .down{color:var(--down)} .dim{color:var(--tx3)}
.tag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:11px;font-weight:600}
.tag.S{background:rgba(229,72,77,.16);color:#ff7b7f}
.tag.A{background:rgba(247,104,8,.16);color:#ff9b52}
.tag.B{background:rgba(245,165,36,.14);color:#f5c451}
.tag.C{background:rgba(139,141,152,.16);color:#a9adb8}
.bb{display:inline-block;min-width:26px;text-align:center;padding:1px 6px;border-radius:4px;
  font-size:11px;background:var(--panel2);color:var(--tx2)}
.bb.hot{background:rgba(229,72,77,.18);color:#ff8b8e;font-weight:600}
.reason{color:var(--tx3);font-size:11.5px;max-width:230px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.legend{display:flex;gap:14px;font-size:11.5px;color:var(--tx3);margin-top:8px;flex-wrap:wrap}
.legend i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px}
.warn{background:rgba(229,72,77,.07);border:1px solid rgba(229,72,77,.25);border-radius:8px;
  padding:10px 14px;font-size:12px;color:#ffb3b5;margin-top:12px}
.rlist li{position:relative;padding-left:13px;color:var(--tx)}
.rlist li::before{content:"";position:absolute;left:2px;top:12px;width:4px;height:4px;
  border-radius:50%;background:var(--up)}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--tx3);font-size:11.5px;line-height:1.9;text-align:center}
"""


# ---------------------------------------------------------------- 格式化
def money(v: float) -> str:
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1e8:
        return f"{v/1e8:+.2f}亿"
    if a >= 1e4:
        return f"{v/1e4:+.0f}万"
    return f"{v:+.0f}"


def pct(v: float) -> str:
    cls = "up" if v > 0 else "down" if v < 0 else "dim"
    return f'<span class="{cls}">{v:+.2f}%</span>'


def esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""))


def seal_time(t: str) -> str:
    t = str(t or "").zfill(6)
    return f"{t[:2]}:{t[2:4]}" if len(t) == 6 else "—"


# ---------------------------------------------------------------- SVG 图
def radar(dims: dict, size: int = 300) -> str:
    keys = ["capital", "lhb", "volume", "theme", "pattern"]
    labels = ["资金", "龙虎榜", "量能", "题材", "形态"]
    cx = cy = size / 2
    r = size / 2 - 46
    n = len(keys)

    def pt(i: int, ratio: float) -> tuple[float, float]:
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return cx + r * ratio * math.cos(ang), cy + r * ratio * math.sin(ang)

    parts = [f'<svg viewBox="0 0 {size} {size}" width="100%" height="{size}">']
    for ring in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, ring) for i in range(n)))
        parts.append(f'<polygon points="{pts}" fill="none" stroke="#252f3d" stroke-width="1"/>')
    for i in range(n):
        x, y = pt(i, 1.0)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#252f3d"/>')

    poly = []
    for i, k in enumerate(keys):
        v = dims.get(k)
        ratio = 0.0 if v is None else max(0.0, min(1.0, v / WEIGHTS[k]))
        poly.append(pt(i, ratio))
    fill = " ".join(f"{x:.1f},{y:.1f}" for x, y in poly)
    parts.append(f'<polygon points="{fill}" fill="rgba(229,72,77,.22)" stroke="#e5484d" stroke-width="2"/>')
    for x, y in poly:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="#e5484d"/>')

    for i, lab in enumerate(labels):
        x, y = pt(i, 1.22)
        v = dims.get(keys[i])
        val = "—" if v is None else f"{v:.0f}"
        anchor = "middle"
        if x < cx - 8:
            anchor = "end"
        elif x > cx + 8:
            anchor = "start"
        parts.append(f'<text x="{x:.1f}" y="{y:.1f}" fill="#93a1b5" font-size="12" '
                     f'text-anchor="{anchor}" dominant-baseline="middle">{lab} {val}</text>')
    parts.append("</svg>")
    return "".join(parts)


def hbars(items: list[tuple[str, float, str]], width: int = 560, row: int = 26) -> str:
    """横向条形图：items = [(标签, 数值, 颜色)]"""
    if not items:
        return '<div class="dim">无数据</div>'
    top = max(v for _, v, _ in items) or 1
    h = row * len(items) + 8
    parts = [f'<svg viewBox="0 0 {width} {h}" width="100%" height="{h}">']
    for i, (lab, v, color) in enumerate(items):
        y = i * row + 4
        bw = max(2.0, (width - 150) * v / top)
        parts.append(f'<text x="0" y="{y+14}" fill="#93a1b5" font-size="12">{esc(lab)}</text>')
        parts.append(f'<rect x="96" y="{y+4}" width="{bw:.1f}" height="12" rx="3" fill="{color}" opacity=".85"/>')
        parts.append(f'<text x="{96+bw+8:.1f}" y="{y+14}" fill="#e8eef7" font-size="12" '
                     f'font-variant-numeric="tabular-nums">{v:g}</text>')
    parts.append("</svg>")
    return "".join(parts)


def histogram(counts: list[tuple[str, int]], width: int = 560, height: int = 170) -> str:
    if not counts:
        return '<div class="dim">无数据</div>'
    top = max(c for _, c in counts) or 1
    n = len(counts)
    bw = (width - 40) / n
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">']
    for i, (lab, c) in enumerate(counts):
        bh = (height - 46) * c / top
        x = 20 + i * bw
        y = height - 30 - bh
        color = "#e5484d" if i >= n - 2 else "#4b8bf5"
        parts.append(f'<rect x="{x+4:.1f}" y="{y:.1f}" width="{bw-8:.1f}" height="{bh:.1f}" '
                     f'rx="3" fill="{color}" opacity=".8"/>')
        parts.append(f'<text x="{x+bw/2:.1f}" y="{y-5:.1f}" fill="#93a1b5" font-size="11" '
                     f'text-anchor="middle">{c}</text>')
        parts.append(f'<text x="{x+bw/2:.1f}" y="{height-12}" fill="#63748c" font-size="11" '
                     f'text-anchor="middle">{lab}</text>')
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------- 主体
def render(ctx: dict) -> str:
    rows = ctx["rows"]
    stats = ctx["stats"]
    top = rows[0] if rows else None

    kpis = [
        ("当日涨停", f'{stats["zt_count"]}', f'炸板 {stats["zb_count"]} · 跌停 {stats["dt_count"]}', "red"),
        ("最高连板", f'{stats["max_boards"]}', "连板高度即情绪高度", "gold"),
        ("S 级候选", f'{stats["tier_s"]}', f'A 级 {stats["tier_a"]} · B 级 {stats["tier_b"]}', "violet"),
        ("候选池均分", f'{stats["avg_score"]:.1f}', f'中位 {stats["median_score"]:.1f}', "blue"),
        ("最强个股", f'{top["total"]:.1f}' if top else "—", esc(top["name"]) if top else "—", ""),
        ("题材集中度", f'{stats["top_industry_share"]:.0f}%',
         f'第一题材 {esc(stats["top_industry"])}', "green"),
    ]
    kpi_html = "".join(
        f'<div class="kpi {c}"><div class="lbl">{l}</div><div class="val">{v}</div>'
        f'<div class="foot">{ft}</div></div>' for l, v, ft, c in kpis)

    idx_html = "".join(
        f'<div><span>{esc(i["name"])}</span><b>{i["close"]:.2f}</b>{pct(i["pct"])}</div>'
        for i in ctx.get("indexes") or [])

    # 表格
    trs = []
    for i, r in enumerate(rows[: ctx.get("top_n", 20)], 1):
        d = r["dims"]
        width = min(100, r["total"])
        trs.append(f"""<tr>
<td class="rk">{i}</td>
<td><span class="nm">{esc(r['name'])}</span><span class="cd">{esc(r['code'])}</span></td>
<td><span class="score" style="color:{r['tier_color']}">{r['total']:.1f}</span><span class="bar"><i style="width:{width}%;background:{r['tier_color']}"></i></span></td>
<td><span class="tag {r['tier']}">{r['tier_label']}</span></td>
<td><span class="bb {('hot' if r['boards'] >= 2 else '')}">{r['boards']}板</span></td>
<td>{pct(r['pct'])}</td>
<td class="{'up' if r['net_main'] > 0 else 'down' if r['net_main'] < 0 else 'dim'}">{money(r['net_main'])}</td>
<td>{r['lhb_count'] or '—'}{'<span class="dim"> 次</span>' if r['lhb_count'] else ''}</td>
<td>{r['turnover']:.1f}%</td>
<td class="dim">{esc(r['industry'])}</td>
<td class="reason" title="{esc(' / '.join(r['reasons']))}">{esc(' · '.join(r['reasons'][:3]))}</td>
</tr>""")

    # 行业热度
    ind_items = [(f"{name} ({cnt}家)", cnt, "#e5484d" if idx < 3 else "#4b8bf5")
                 for idx, (name, cnt) in enumerate(stats["industry_top"][:12])]
    # 资金 Top12
    cap_items = [(f"{r['name']}", round(r["net_main"] / 1e8, 2),
                  "#e5484d" if r["net_main"] > 0 else "#2fa96b")
                 for r in sorted(rows, key=lambda x: -x["net_main"])[:12]]

    radar_html = radar(top["dims"]) if top else '<div class="dim">无候选</div>'
    top_reasons = "".join(f"<li>{esc(x)}</li>" for x in (top["reasons"] if top else [])) or "<li>—</li>"

    hist_items = stats["score_hist"]

    warn_html = ""
    if stats.get("warnings"):
        warn_html = ('<div class="warn"><b>数据告警：</b>'
                     + " · ".join(esc(w) for w in stats["warnings"][:6])
                     + f'（共 {len(stats["warnings"])} 条，详见快照 JSON）</div>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>妖股挖掘量化看板 · {esc(ctx['trade_date'])}</title>
<style>{CSS}</style></head><body><div class="wrap">

<div class="head">
  <h1>妖股挖掘 · 量化看板<span class="sub">五维加权概率模型</span></h1>
  <div class="stamp">
    交易日 {esc(ctx['trade_date'])}<br/>
    生成于 {esc(ctx['generated_at'])}<br/>
    候选 {len(rows)} 只 · 权重 30/25/25/10/10
  </div>
</div>

<div class="disc">
⚠ 本看板为量化研究工具，不构成任何投资建议。妖股炒作高波动、追涨极易亏损。
模型输出的是「同池内相对概率排序」，<b>不是次日上涨概率的绝对估计</b>，也未经独立收益回测验证。
</div>

<div class="srcs">
  <div class="chip">行情与涨停池 <b>东方财富 push2ex / push2his</b></div>
  <div class="chip">龙虎榜 <b>datacenter-web</b></div>
  <div class="chip">K线 <b>前复权日线</b></div>
  <div class="chip">资金流 <b>逐票 fflow</b></div>
  <div class="chip">样本 <b>{len(rows)} 只涨停股</b></div>
</div>

<div class="kpis">{kpi_html}</div>
<div class="idx">{idx_html}</div>
{warn_html}

<div class="sec">
  <h2>候选池 · 妖股概率 Top{ctx.get('top_n', 20)}<span class="note">仅当日涨停股纳入评级</span></h2>
  <div class="card" style="padding:6px 10px">
    <div class="tblwrap">
    <table>
      <thead><tr><th>#</th><th>股票</th><th>概率</th><th>分级</th><th>连板</th>
      <th>涨跌幅</th><th>主力净流入</th><th>龙虎榜</th><th>换手</th><th>行业</th><th>核心理由</th></tr></thead>
      <tbody>{''.join(trs)}</tbody>
    </table>
    </div>
  </div>
  <div class="legend">
    <span><i style="background:#e5484d"></i>S ≥80 妖股候选</span>
    <span><i style="background:#f76808"></i>A 70-79 强关注</span>
    <span><i style="background:#f5a524"></i>B 60-69 潜力</span>
    <span><i style="background:#8b8d98"></i>C &lt;60 观察</span>
  </div>
</div>

<div class="sec">
  <h2>五维拆解 · Top1<span class="note">{esc(top['name']) if top else ''} 的得分构成</span></h2>
  <div class="grid2">
    <div class="card">
      <h3>五维得分（满分 30 / 25 / 25 / 10 / 10）</h3>
      {radar_html}
      <div class="legend">
        <span>资金 {top['dims']['capital'] if top else '—'}/30</span>
        <span>龙虎 {top['dims']['lhb'] if top else '—'}/25</span>
        <span>量能 {top['dims']['volume'] if top else '—'}/25</span>
        <span>题材 {top['dims']['theme'] if top else '—'}/10</span>
        <span>形态 {top['dims']['pattern'] if top else '—'}/10</span>
      </div>
    </div>
    <div class="card">
      <h3>命中理由</h3>
      <ul class="rlist" style="list-style:none;font-size:13px;line-height:2">{top_reasons}</ul>
      <h3 style="margin-top:18px">数据完备度</h3>
      <div class="legend" style="gap:10px;line-height:2">
        <span>K线 {stats['data_ready']['kline']}/{stats['scored']}</span>
        <span>资金流 {stats['data_ready']['flow']}/{stats['scored']}</span>
        <span>龙虎榜 {stats['data_ready']['lhb']} 只</span>
        <span>告警 {len(stats['warnings'])} 条</span>
      </div>
      <div class="dim" style="font-size:11.5px;margin-top:10px;line-height:1.8">
        评分口径：同池内相对排序。≥80 记为妖股候选，60-79 为潜力区间，
        &lt;60 仅作观察。该分数不是次日上涨概率。
      </div>
    </div>
  </div>
</div>

<div class="grid2" style="grid-template-columns:1fr 1fr">
  <div class="card">
    <h3>行业题材热度 · 当日涨停家数 Top12</h3>
    {hbars(ind_items)}
  </div>
  <div class="card">
    <h3>主力资金净流入 Top12（当日）</h3>
    {hbars(cap_items)}
    <div class="dim" style="font-size:11.5px;margin-top:8px">单位：亿元。红为净流入，绿为净流出。</div>
  </div>
</div>

<div class="sec" style="margin-top:26px">
  <div class="card">
    <h3>评分分布 · 当日涨停股</h3>
    {histogram(hist_items)}
  </div>
</div>

<footer>
妖股挖掘量化看板 · 五维加权模型（资金30 / 龙虎25 / 量能25 / 题材10 / 形态10）<br/>
数据来源：东方财富公开行情接口 ｜ 本工具仅供研究，不构成投资建议 ｜ 股市有风险，入市需谨慎
</footer>
</div></body></html>"""
