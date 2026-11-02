# -*- coding: utf-8 -*-
"""
主流程：取数 → 评分 → 渲染 → 落盘。

用法：
    python scripts/run.py                       # 最近交易日，全量涨停股
    python scripts/run.py --date 20261102       # 指定交易日
    python scripts/run.py --top 30 --limit 60   # Top30 展示，只评前 60 只涨停股

产物（默认落在 ~/WorkBuddy/ashare-yaogu-miner/，不写进技能目录，
避免行情缓存被打包进技能包；可用环境变量 YAOGU_WORK 覆盖）：
    yaogu_YYYYMMDD.html   看板
    yaogu_YYYYMMDD.json   结构化快照（可程序化消费）
    cache/YYYYMMDD.json   当日行情缓存（重跑免二次拉取）
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import engine  # noqa: E402
import render  # noqa: E402
import sources  # noqa: E402

# 产物落盘位置：刻意放在技能目录之外。技能包会被 publish 打成 zip，
# 若 work/ 留在包内，5MB 行情缓存会一起上传，且每次运行都在改动发布物。
WORK = Path(os.environ.get("YAOGU_WORK")
            or (Path.home() / "WorkBuddy" / "ashare-yaogu-miner"))


def load_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def build(date: str, top_n: int = 20, limit: int | None = None,
          use_cache: bool = True, workers: int = 8) -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    cache_path = WORK / "cache" / f"{sources.compact(date)}.json"
    cache = load_cache(cache_path) if use_cache else {}

    zt_meta = sources.zt_pool(sources.compact(date))
    zt_all = sorted(zt_meta["list"], key=lambda x: (-x["boards"], -x["amount"]))
    if not zt_all:
        raise SystemExit(f"{date} 无涨停数据（可能非交易日或接口未更新）")
    # --limit 只截断「评分对象」，行业统计与 KPI 仍用全池，否则题材热度会被截断失真
    zt = zt_all[:limit] if limit else zt_all

    zb = sources.zb_pool(sources.compact(date))
    dtp = sources.dt_pool(sources.compact(date))
    lhb_map = sources.lhb(date)
    indexes = sources.index_quotes()

    codes = [x["code"] for x in zt]
    k_cache = cache.setdefault("kline", {})
    f_cache = cache.setdefault("flow", {})

    need_k = [c for c in codes if c not in k_cache]
    need_f = [c for c in codes if c not in f_cache]

    if need_k:
        k_cache.update({c: sources.kline(c) for c, v in
                        sources.batch(need_k, sources.kline, workers).items()
                        if v is not None})
    if need_f:
        f_cache.update({c: sources.fflow(c) for c, v in
                        sources.batch(need_f, sources.fflow, workers).items()
                        if v is not None})
    save_cache(cache_path, cache)

    # 行业聚合用全池（不受 --limit 影响）
    ind_count: dict[str, int] = {}
    for s in zt_all:
        ind_count[s["industry"]] = ind_count.get(s["industry"], 0) + 1
    ind_rank = sorted(ind_count.items(), key=lambda kv: -kv[1])
    top3 = {name for name, _ in ind_rank[:3]}

    rows = []
    warn_pool: list[str] = []
    for s in zt:
        k = k_cache.get(s["code"]) or None
        f = f_cache.get(s["code"]) or None
        r = engine.evaluate(s, k, f, lhb_map.get(s["code"]),
                            ind_count.get(s["industry"], 1),
                            s["industry"] in top3, date)
        warn_pool.extend(f"{s['name']}: {w}" for w in r["warnings"])
        rows.append(r)

    rows.sort(key=lambda x: -x["total"])

    scores = [r["total"] for r in rows]
    hist = []
    for lo in range(30, 100, 10):
        hist.append((f"{lo}", len([s for s in scores if lo <= s < lo + 10])))
    tier_cnt = {t[1]: len([r for r in rows if r["tier"] == t[1]]) for t in engine.TIERS}

    stats = {
        "zt_count": zt_meta["count"],
        "zb_count": zb["count"],
        "dt_count": dtp["count"],
        "scored": len(rows),
        "max_boards": max((s["boards"] for s in zt_all), default=0),
        "tier_s": tier_cnt.get("S", 0),
        "tier_a": tier_cnt.get("A", 0),
        "tier_b": tier_cnt.get("B", 0),
        "tier_c": tier_cnt.get("C", 0),
        "avg_score": round(statistics.fmean(scores), 1) if scores else 0.0,
        "median_score": round(statistics.median(scores), 1) if scores else 0.0,
        "industry_top": ind_rank[:15],
        "top_industry": ind_rank[0][0] if ind_rank else "—",
        "top_industry_share": round(ind_rank[0][1] / max(zt_meta["count"], 1) * 100, 1)
        if ind_rank else 0.0,
        "score_hist": hist,
        "warnings": sorted(set(warn_pool)),
        "data_ready": {
            "kline": len(k_cache),
            "flow": len(f_cache),
            "lhb": len(lhb_map),
        },
    }

    ctx = {
        "trade_date": date,
        "generated_at": sources.now_str(),
        "rows": rows,
        "stats": stats,
        "indexes": indexes,
        "top_n": top_n,
    }
    return ctx


def main() -> None:
    ap = argparse.ArgumentParser(description="妖股挖掘量化看板")
    ap.add_argument("--date", default="", help="交易日 YYYYMMDD，默认最近交易日")
    ap.add_argument("--top", type=int, default=20, help="表格展示条数")
    ap.add_argument("--limit", type=int, default=0, help="只评前 N 只涨停股（0=全部）")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    date = sources.normalize_date(args.date)
    ctx = build(date, top_n=args.top, limit=args.limit or None,
                use_cache=not args.no_cache, workers=args.workers)

    out_html = WORK / f"yaogu_{sources.compact(date)}.html"
    out_json = WORK / f"yaogu_{sources.compact(date)}.json"
    out_html.write_text(render.render(ctx), encoding="utf-8")
    out_json.write_text(json.dumps(ctx, ensure_ascii=False, indent=1), encoding="utf-8")

    st = ctx["stats"]
    print(f"[ok] {date} 涨停 {st['zt_count']} 炸板 {st['zb_count']} 跌停 {st['dt_count']} "
          f"最高 {st['max_boards']} 板 | S{st['tier_s']} A{st['tier_a']} B{st['tier_b']}")
    print(f"[data] kline={st['data_ready']['kline']} flow={st['data_ready']['flow']} "
          f"lhb={st['data_ready']['lhb']} warn={len(st['warnings'])}")
    for r in ctx["rows"][:5]:
        print(f"  {r['total']:5.1f} {r['tier']} {r['name']}({r['code']}) "
              f"{r['boards']}板 资金{r['net_main']/1e8:+.2f}亿 龙虎{r['lhb_count']}次")
    print(f"[out] {out_html}")
    print(f"[out] {out_json}")


if __name__ == "__main__":
    main()
